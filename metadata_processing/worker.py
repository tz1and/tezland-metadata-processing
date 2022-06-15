import asyncio
from enum import Enum, unique
import logging
import platform
import random
import aiohttp
import orjson

from json import JSONDecodeError
from tortoise import Tortoise

from metadata_processing import __version__
from metadata_processing.config import Config
from metadata_processing.gltf_validation import count_gltf_polygons
from metadata_processing.models import ItemTagMap, ItemToken, ItemTokenMetadata, PlaceToken, PlaceTokenMetadata, MetadataStatus, Tag
from metadata_processing.utils import getGridCellHash, getOrRaise

IPFS_PREFIX = 'ipfs://'

@unique
class TokenType(Enum):
    Item = 0
    Place = 1

class MetadataProcessing:
    def __init__(self) -> None:
        self._logger = logging.getLogger(f'MetadataProcessing')
        self._config = Config()
        self._user_agent = None
        self._session = None

    @property
    def user_agent(self) -> str:
        """Return User-Agent header compiled from aiohttp's one and dipdup environment"""
        if self._user_agent is None:
            user_agent_args = (platform.system(), platform.machine())
            user_agent = f'metdata-processing/{__version__} ({"; ".join(user_agent_args)})'
            user_agent += ' ' + aiohttp.http.SERVER_SOFTWARE
            self._user_agent = user_agent
        return self._user_agent

    def _random_gateway(self) -> str:
        return random.choice(self._config.ipfs_gateways)

    def _ipfs_gateway_link(self, url: str, gateway: str) -> str:
        assert url.startswith(IPFS_PREFIX) == True, "Not an IPFS URI"
        return f'{gateway}/ipfs/{url.removeprefix(IPFS_PREFIX)}'


    async def ipfs_download(self, ipfs_uri: str, gateway: str):
        """Wrapped aiohttp call with preconfigured headers and ratelimiting"""
        # TODO: implement retry logic ourselves, use fallback, etc
        gateway_link = self._ipfs_gateway_link(ipfs_uri, gateway)
        #self._logger.info(f'From {gateway_link}')

        headers = {} #kwargs.pop('headers', {})
        headers['User-Agent'] = self.user_agent

        #params = kwargs.get('params', {})
        #params_string = '&'.join(f'{k}={v}' for k, v in params.items())
        #request_string = f'{url}?{params_string}'.rstrip('?')
        #self._logger.debug('Calling `%s`', request_string)

        async with self._session.request(
            method='GET',
            url=gateway_link,
            headers=headers,
            raise_for_status=True,
            #**kwargs,
        ) as response:
            try:
                return await response.json()
            except (JSONDecodeError, aiohttp.ContentTypeError):
                return await response.read()


    async def ipfs_download_fallback(self, ipfs_uri: str):
        #self._logger.info(f'Downloading {ipfs_uri}')

        try:
            return await self.ipfs_download(ipfs_uri, self._random_gateway())
        except Exception as e:
            self._logger.error(f'Download failed: {e}')

            try:
                return await self.ipfs_download(ipfs_uri, self._config.ipfs_fallback_gateway)
            except Exception as e:
                self._logger.error(f'Download failed: {e}')
                raise Exception('IPFS download failed.')


    async def ipfs_download_retry(self, ipfs_uri: str):
        attempt = 1
        sleep_time = 1
        backoff_factor = 2

        while True:
            try:
                return await self.ipfs_download_fallback(ipfs_uri)
            except:
                # terminate loop if out of retries.
                if attempt >= 8:
                    break

                self._logger.info(f'Backoff: sleeping for {sleep_time}s')
                await asyncio.sleep(sleep_time)
                sleep_time = sleep_time * backoff_factor
                attempt += 1

        raise Exception(f'IPFS download failed after {attempt} retries.')


    async def process_place_token(self, token_id: int):
        self._logger.info(f'Processing Place token {token_id}...')
        place_token = await PlaceToken.get(id=token_id)

        # to catch unspecified errors and mark token as failed.
        # TODO: some failiure conditions need to be marked as invalid
        try:
            metadata: dict | bytes = await self.ipfs_download_retry(place_token.metadata_uri)

            if isinstance(metadata, bytes):
                self._logger.error("metadata invalid: not json")
                place_token.metadata_status = MetadataStatus.Invalid.value
                await place_token.save()
                return

            border_coordinates = getOrRaise(metadata, 'borderCoordinates')
            center_coordinates: list[float] = getOrRaise(metadata, 'centerCoordinates')
            grid_hash = getGridCellHash(center_coordinates[0], center_coordinates[1], center_coordinates[2], self._config.grid_size)

            # refersh token from db
            await place_token.refresh_from_db()

            # TODO: from here on, everything should be a transaction

            place_token_metadata = PlaceTokenMetadata(
                id=place_token.id,
                name=metadata.get('name', ''),
                desciption=metadata.get('desciption', ''),
                place_type=metadata.get('placeType', 'exterior'),
                center_coordinates=center_coordinates,
                border_coordinates=border_coordinates,
                grid_hash=grid_hash,
                level=place_token.level,
                timestamp=place_token.timestamp)

            if await PlaceTokenMetadata.exists(id=place_token.id):
                #self._logger.info("metadata exists, updating")
                await place_token_metadata.save(force_update=True)
            else:
                await place_token_metadata.save()

            place_token.metadata_status = MetadataStatus.Valid.value
            place_token.metadata = place_token_metadata
            await place_token.save()
        except Exception as e:
            self._logger.error(f'Failed to process Place token {token_id} metadata: {e}')
            place_token.metadata_status = MetadataStatus.Failed.value
            await place_token.save()


    async def process_item_token(self, token_id: int):
        self._logger.info(f'Processing Item token {token_id}...')
        item_token = await ItemToken.get(id=token_id)

        # to catch unspecified errors and mark token as failed.
        # TODO: some failiure conditions need to be marked as invalid
        try:
            metadata: dict | bytes = await self.ipfs_download_retry(item_token.metadata_uri)

            if isinstance(metadata, bytes):
                self._logger.error("metadata invalid: not json")
                item_token.metadata_status = MetadataStatus.Invalid.value
                await item_token.save()
                return

            polygon_count = getOrRaise(metadata, 'polygonCount')
            base_scale = getOrRaise(metadata, 'baseScale')
            artifact_uri = getOrRaise(metadata, 'artifactUri')

            mime_type = None
            file_size = None
            for format in getOrRaise(metadata, 'formats'):
                if getOrRaise(format, 'uri') == artifact_uri:
                    mime_type = getOrRaise(format, 'mimeType')
                    file_size = getOrRaise(format, 'fileSize')
                    break

            # make sure formats included artifact
            assert mime_type is not None, "Format didn't include artifact"

            tags: list[str] = getOrRaise(metadata, 'tags')

            # Download artifact
            artifact = await self.ipfs_download_retry(artifact_uri)

            try:
                counted_polygons = count_gltf_polygons(artifact)
                #self._logger.info("model is valid")

                # TODO: check polycount error margin and maybe set invalid status
                # TODO: check file size!!!!
                #if polygon_count == counted_polygons:
                #    self._logger.info("polygon count matches metadata")
            except Exception as e:
                self._logger.error(f'model invalid: {e}')
                item_token.metadata_status = MetadataStatus.Invalid.value
                await item_token.save()
                return

            # refersh token from db
            await item_token.refresh_from_db()

            # TODO: from here on, everything should be a transaction

            item_token_metadata = ItemTokenMetadata(
                id=item_token.id,
                name=metadata.get('name', ''),
                desciption=metadata.get('desciption', ''),
                artifact_uri=artifact_uri,
                thumbnail_uri=metadata.get('thumbnailUri'),
                display_uri=metadata.get('displayUri'),
                base_scale=base_scale,
                polygon_count=polygon_count,
                mime_type=mime_type,
                file_size=file_size,
                level=item_token.level,
                timestamp=item_token.timestamp)

            if await ItemTokenMetadata.exists(id=item_token.id):
                #self._logger.info("metadata exists, updating")
                await item_token_metadata.save(force_update=True)
            else:
                await item_token_metadata.save()

            item_token.metadata_status = MetadataStatus.Valid.value
            item_token.metadata = item_token_metadata
            await item_token.save()

            for tag_name in tags:
                tag, _ = await Tag.get_or_create(name=tag_name, defaults={
                    'level': item_token.level,
                    'timestamp': item_token.timestamp
                })

                tag_map_item = ItemTagMap(
                    item_token=item_token,
                    tag=tag,
                    level=item_token.level,
                    timestamp=item_token.timestamp)
                await tag_map_item.save()

        except Exception as e:
            self._logger.error(f'Failed to process Item token {token_id} metadata: {e}')
            item_token.metadata_status = MetadataStatus.Failed.value
            await item_token.save()


    async def process_token(self, token: tuple[TokenType, int]):
        # Here we create a SQLite DB using file "db.sqlite3"
        #  also specify the app name of "models"
        #  which contain models from "app.models"
        await Tortoise.init(
            db_url=self._config.db_connection_url,
            modules={'models': ['metadata_processing.models']}
        )

        self._session=aiohttp.ClientSession(
            json_serialize=lambda *a, **kw: orjson.dumps(*a, **kw).decode(),
            connector=aiohttp.TCPConnector(limit=100),
            timeout=aiohttp.ClientTimeout(connect=60),
        )

        try:
            token_type = token[0]
            token_id = token[1]

            # TODO: make sure to use transactions in process_*_token

            if token_type is TokenType.Item:
                await self.process_item_token(token_id)
            elif token_type is TokenType.Place:
                await self.process_place_token(token_id)
            else:
                raise Exception(f'Unknown token type "{token_type}", can\'t process metadata')
        except Exception as e:
            self._logger.error(f'Failed to process token: {e}')

        # Clean up
        await self._session.close()
        await Tortoise.close_connections()


def thread_main(token: tuple[TokenType, int]):
    _logger = logging.getLogger(f'ProcessingThread')

    try:
        #_logger.info("Thread: starting")

        #loop = asyncio.get_event_loop()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            processing = MetadataProcessing()
            loop.run_until_complete(processing.process_token(token))
        finally:
            loop.close()
 
        #_logger.info("Thread: finishing")
    except Exception as e:
        _logger.error("Error in thread: error %s", e)
