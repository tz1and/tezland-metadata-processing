from enum import Enum, unique
import logging, platform, random
import asyncio, aiohttp
from typing import Any
import orjson, urllib.parse

from json import JSONDecodeError
import tortoise.transactions, tortoise.exceptions

from metadata_processing import __version__
from metadata_processing.config import Config
from metadata_processing.gltf_validation import count_gltf_polygons
from metadata_processing.models import ContractTagMap, ItemTagMap, ItemToken, ItemTokenMetadata, PlaceToken, PlaceTokenMetadata, MetadataStatus, Tag, IpfsMetadataCache, BaseToken, Contract, ContractMetadata
from metadata_processing.utils import getGridCellHash, getOrRaise


# TODO: add retry logic in process_*. 5-10 if failed. if invalid just stop retrying.


IPFS_PREFIX = 'ipfs://'

GLTF_MIME_TYPES = ['model/gltf-binary', 'model/gltf+json']
IMAGE_MIME_TYPES = ['image/png', 'image/jpeg']
ALLOWED_MIME_TYPES = GLTF_MIME_TYPES + IMAGE_MIME_TYPES


@unique
class MetadataType(Enum):
    Item = 0
    Place = 1
    Contract = 2


class MetadataProcessing:
    def __init__(self, config: Config) -> None:
        self._logger = logging.getLogger(f'MetadataProcessing')
        self._config = config
        self._user_agent = None
        self._session = None

    @property
    def user_agent(self) -> str:
        """Return User-Agent header compiled from aiohttp's one and metdata-processing environment"""
        if self._user_agent is None:
            user_agent_args = (platform.system(), platform.machine())
            user_agent = f'metdata-processing/{__version__} ({"; ".join(user_agent_args)})'
            user_agent += ' ' + aiohttp.http.SERVER_SOFTWARE
            self._user_agent = user_agent
        return self._user_agent

    def _random_gateway(self) -> str:
        return random.choice(self._config.ipfs_gateways)

    def _ipfs_gateway_link(self, url: str, gateway: str) -> str:
        assert url.startswith(IPFS_PREFIX) == True, f'Not an IPFS URI: {url}'
        return f'{gateway}/ipfs/{url.removeprefix(IPFS_PREFIX)}'

    def _fix_ipfs_uri(self, uri: str) -> str:
        return 'ipfs://' + urllib.parse.quote(urllib.parse.unquote(uri.removeprefix('ipfs://')))


    async def ipfs_download(self, ipfs_uri: str, gateway: str, max_size: int = -1):
        """Wrapped aiohttp call with preconfigured headers and ratelimiting"""
        gateway_link = self._ipfs_gateway_link(self._fix_ipfs_uri(ipfs_uri), gateway)
        self._logger.debug(f'From {gateway_link}')

        headers = {}
        headers['User-Agent'] = self.user_agent

        async with self._session.request(
            method='GET',
            url=gateway_link,
            headers=headers,
            raise_for_status=True
        ) as response:
            # Pretty sure we don't need to check this.
            #if not (response.status >= 200 and response.status <= 299):
            #    raise Exception('download failed, response not 200')

            # TODO: max_size does nothing currently.
            body = await response.read()
            try:
                return (orjson.loads(body), len(body))
            except JSONDecodeError:
                return (body, len(body))


    async def ipfs_download_fallback(self, ipfs_uri: str, max_size: int = -1):
        self._logger.debug(f'Downloading {ipfs_uri}')

        try:
            # TODO: don't fallback on 400 range error: ClientResponseError
            return await self.ipfs_download(ipfs_uri, self._random_gateway(), max_size)
        except Exception as e:
            self._logger.error(f'IPFS download failed: {e}')

            try:
                return await self.ipfs_download(ipfs_uri, self._config.ipfs_fallback_gateway, max_size)
            except Exception as e:
                message = f'IPFS fallback download failed: {e}'
                self._logger.error(message)
                raise Exception(message) from e


    async def ipfs_download_retry(self, ipfs_uri: str, max_size: int = -1):
        attempt = 1
        sleep_time = 10
        backoff_factor = 1.5

        while True:
            try:
                # TODO: don't retry on 400 range error: ClientResponseError
                return await self.ipfs_download_fallback(ipfs_uri, max_size)
            except Exception:
                # terminate loop if out of retries.
                if attempt >= self._config.download_retries:
                    break

                self._logger.info(f'Backoff: sleeping for {sleep_time}s')
                await asyncio.sleep(sleep_time)
                sleep_time = sleep_time * backoff_factor
                attempt += 1

        raise Exception(f'IPFS download failed after {attempt} retries.')


    async def download_and_cache_metadata(self, token: BaseToken | Contract) -> Any:
        # transaction for metadata cache
        async with tortoise.transactions.in_transaction():
            # If we already have the metadata cached, use that.
            metadata_cache = await IpfsMetadataCache.get_or_none(metadata_uri=token.metadata_uri)

            if metadata_cache is not None:
                metadata = metadata_cache.metadata_json
                self._logger.info(f'Loaded ipfs metadata from cache: {token.metadata_uri}')
            else:
                metadata, _ = await self.ipfs_download_retry(token.metadata_uri, self._config.max_metadata_file_size)

                if isinstance(metadata, bytes):
                    self._logger.error("metadata invalid: not json")
                    token.metadata_status = MetadataStatus.Invalid.value
                    await token.save()
                    return

                await IpfsMetadataCache.create(metadata_uri=token.metadata_uri, metadata_json=metadata)
                self._logger.info(f'Cached ipfs metadata: {token.metadata_uri}')

            return metadata

    
    async def process_contract(self, address: str):
        contract: Contract = await Contract.get(address=address).prefetch_related("metadata")
        self._logger.info(f'Processing Contract {contract.address}...')

        # Early out if contract already has metadata.
        if contract.metadata is not None:
            return

        # TODO: NOTE: have another MetadataStatus Refresh?
        # If we already have metadata for this token, use it.
        existing_metadata = await ContractMetadata.get_or_none(address=contract.address)
        if existing_metadata is not None:
            self._logger.info(f'Using existing metadata for Contract {contract.address}.')
            contract.metadata_status = MetadataStatus.Valid.value
            contract.metadata = existing_metadata
            await contract.save()
            return

        # to catch unspecified errors and mark token as failed.
        try:
            metadata = await self.download_and_cache_metadata(contract)

            # required fields
            try:
                name = getOrRaise(metadata, 'name')
                description = getOrRaise(metadata, 'description')
            except Exception as e:
                self._logger.error(f'required fields: {e}')
                contract.metadata_status = MetadataStatus.Invalid.value
                await contract.save()
                return

            # Optional fields.
            user_description = metadata.get('userDescription')
            # Split tags by comma as well. Because people are people...
            tags: list[str] = []
            metadata_tags: list[str] | None = metadata.get('tags')
            if metadata_tags is not None:
                for tag in metadata_tags:
                    for split in tag.split(','):
                        stripped = split.strip()
                        if len(stripped) > 0:
                            tags.append(stripped.lower())

            # transaction for creating metadata, saving place
            async with tortoise.transactions.in_transaction():
                # refresh from DB in case the thing has been deleted.
                await contract.refresh_from_db()

                # TODO: maybe don't use create and get_or_create. something with transactions.
                contract_metadata = await ContractMetadata.create(
                    address=contract.address,
                    name=name,
                    description=description,
                    user_description=user_description,
                    level=contract.level,
                    timestamp=contract.timestamp)

                contract.metadata_status = MetadataStatus.Valid.value
                contract.metadata = contract_metadata
                await contract.save()

                for tag_name in tags:
                    tag, _ = await Tag.get_or_create(name=tag_name, defaults={
                        'level': contract.level,
                        'timestamp': contract.timestamp})

                    await ContractTagMap.create(
                        contract_metadata=contract_metadata,
                        tag=tag,
                        level=contract.level,
                        timestamp=contract.timestamp)
        # If it fails due to a transaction error, don't mark it as failed.
        except tortoise.exceptions.TransactionManagementError as e:
            raise Exception(f'Transaction failed, Contract address={contract.address}: {e}') from e
        # If it fails due to anything else, mark as failed and don't throw.
        except Exception as e:
            self._logger.error(f'Failed to process Contract address={contract.address} metadata: {e}')
            contract.metadata_status = MetadataStatus.Failed.value
            await contract.save()


    async def process_place_token(self, transient_id: int):
        place_token: PlaceToken = await PlaceToken.get(transient_id=transient_id).prefetch_related("contract", "metadata")
        self._logger.info(f'Processing Place token {place_token.token_id} ({place_token.contract.address})...')

        # Early out if token already has metadata.
        if place_token.metadata is not None:
            return

        # If we already have metadata for this token, use it.
        existing_metadata = await PlaceTokenMetadata.get_or_none(contract=place_token.contract.address, token_id=place_token.token_id)
        if existing_metadata is not None:
            self._logger.info(f'Using existing metadata for Place token {place_token.token_id} ({place_token.contract.address}).')
            place_token.metadata_status = MetadataStatus.Valid.value
            place_token.metadata = existing_metadata
            await place_token.save()
            return

        # to catch unspecified errors and mark token as failed.
        try:
            metadata = await self.download_and_cache_metadata(place_token)

            # required fields
            try:
                place_type = getOrRaise(metadata, 'placeType')
                border_coordinates = getOrRaise(metadata, 'borderCoordinates')
                center_coordinates: list[float] = getOrRaise(metadata, 'centerCoordinates')
                build_height = getOrRaise(metadata, 'buildHeight')
                # TODO: grid hash for interior places?
                grid_hash = getGridCellHash(center_coordinates[0], center_coordinates[1], center_coordinates[2], self._config.grid_size)
            except Exception as e:
                self._logger.error(f'required fields: {e}')
                place_token.metadata_status = MetadataStatus.Invalid.value
                await place_token.save()
                return

            # transaction for creating metadata, saving place
            async with tortoise.transactions.in_transaction():
                # refresh from DB in case the thing has been deleted.
                await place_token.refresh_from_db()

                # TODO: maybe don't use create and get_or_create. something with transactions.
                place_token_metadata = await PlaceTokenMetadata.create(
                    contract=place_token.contract.address,
                    token_id=place_token.token_id,
                    name=metadata.get('name', ''),
                    description=metadata.get('description', ''),
                    place_type=place_type,
                    build_height=build_height,
                    center_coordinates=center_coordinates,
                    border_coordinates=border_coordinates,
                    grid_hash=grid_hash,
                    level=place_token.level,
                    timestamp=place_token.timestamp)

                place_token.metadata_status = MetadataStatus.Valid.value
                place_token.metadata = place_token_metadata
                await place_token.save()
        # If it fails due to a transaction error, don't mark it as failed.
        except tortoise.exceptions.TransactionManagementError as e:
            raise Exception(f'Transaction failed, Place token_id={place_token.token_id} contract={place_token.contract.address}: {e}') from e
        # If it fails due to anything else, mark as failed and don't throw.
        except Exception as e:
            self._logger.error(f'Failed to process Place token_id={place_token.token_id} contract={place_token.contract.address} metadata: {e}')
            place_token.metadata_status = MetadataStatus.Failed.value
            await place_token.save()


    async def process_item_token(self, transient_id: int):
        item_token: ItemToken = await ItemToken.get(transient_id=transient_id).prefetch_related("contract", "metadata")
        self._logger.info(f'Processing Item token {item_token.token_id} ({item_token.contract.address})...')

        # Early out if token already has metadata.
        if item_token.metadata is not None:
            return

        # If we already have metadata for this token, use it.
        existing_metadata = await ItemTokenMetadata.get_or_none(contract=item_token.contract.address, token_id=item_token.token_id)
        if existing_metadata is not None:
            self._logger.info(f'Using existing metadata for Item token {item_token.token_id} ({item_token.contract.address}).')
            item_token.metadata_status = MetadataStatus.Valid.value
            item_token.metadata = existing_metadata
            await item_token.save()
            return

        # to catch unspecified errors and mark token as failed.
        try:
            metadata = await self.download_and_cache_metadata(item_token)

            # required fields
            try:
                polygon_count = getOrRaise(metadata, 'polygonCount')
                base_scale = getOrRaise(metadata, 'baseScale')
                artifact_uri = getOrRaise(metadata, 'artifactUri')

                mime_type = None
                file_size = None
                found_format = False
                width: int | None = None
                height: int | None = None
                for format in getOrRaise(metadata, 'formats'):
                    if getOrRaise(format, 'uri') == artifact_uri:
                        mime_type = getOrRaise(format, 'mimeType')
                        file_size = getOrRaise(format, 'fileSize')
                        dimensions = format.get('dimensions')
                        if dimensions is not None:
                            assert dimensions.unit == 'px', f"Image dimensions not in pixels: {dimensions.unit}"
                            values = dimensions.value.split('x')
                            assert len(values) == 2, f"Incorrect number of values in dimensions: {len(values)}"
                            width = int(values[0])
                            height = int(values[1])
                        found_format = True
                        break

                # Make sure formats included artifact.
                assert found_format is True, "Formats didn't include artifact"

                # Validate mimeType.
                assert mime_type in ALLOWED_MIME_TYPES, f"Unsupported mime type: {mime_type}"

                image_frame_json: Any | None = None
                if mime_type in IMAGE_MIME_TYPES:
                    assert width is not None, "width is None for image"
                    assert height is not None, "height is None for image"
                    image_frame_json = getOrRaise(metadata, 'imageFrame')

                # Split tags by comma as well. Because people are people...
                metadata_tags: list[str] = getOrRaise(metadata, 'tags')
                tags: list[str] = []
                for tag in metadata_tags:
                    for split in tag.split(','):
                        stripped = split.strip()
                        if len(stripped) > 0:
                            tags.append(stripped.lower())
            except Exception as e:
                self._logger.error(f'required fields: {e}')
                item_token.metadata_status = MetadataStatus.Invalid.value
                await item_token.save()
                return

            # Download artifact
            artifact, artifact_size = await self.ipfs_download_retry(artifact_uri, self._config.max_artifact_file_size)

            try:
                # Check file size
                if artifact_size != file_size:
                    raise Exception(f'file size does not match metadata, token_id={item_token.token_id} contract={item_token.contract.address}')

                if mime_type in GLTF_MIME_TYPES:
                    counted_polygons = count_gltf_polygons(artifact)
                # TODO: validate width ein height in image files.
                else: counted_polygons = 0

                # Check the model doesn't have more polygons than the metadata says.
                diff = max(0, counted_polygons - polygon_count)
                # error precision is upto 2 decimal places
                maxDiff = polygon_count * self._config.polygon_count_error / 10000.00
                if diff > maxDiff:
                    raise Exception(f'polycount > max diff, token_id={item_token.token_id} contract={item_token.contract.address} expected_count={polygon_count}, got_count={counted_polygons}')

                if diff != 0:
                    self._logger.warn(f'polycount did not match, token_id={item_token.token_id} contract={item_token.contract.address}, expected_count={polygon_count}, got_count={counted_polygons}, diff={diff}')
            except Exception as e:
                self._logger.error(f'model invalid: {e}')
                item_token.metadata_status = MetadataStatus.Invalid.value
                await item_token.save()
                return

            # transaction for creating metadata, saving item and tags
            async with tortoise.transactions.in_transaction():
                # refresh from DB in case the thing has been deleted.
                await item_token.refresh_from_db()

                # TODO: maybe don't use create and get_or_create. something with transactions.
                item_token_metadata = await ItemTokenMetadata.create(
                    contract=item_token.contract.address,
                    token_id=item_token.token_id,
                    name=metadata.get('name', ''),
                    description=metadata.get('description', ''),
                    artifact_uri=artifact_uri,
                    thumbnail_uri=metadata.get('thumbnailUri'),
                    display_uri=metadata.get('displayUri'),
                    base_scale=base_scale,
                    polygon_count=polygon_count,
                    mime_type=mime_type,
                    file_size=file_size,
                    width=width,
                    height=height,
                    image_frame_json=image_frame_json,
                    level=item_token.level,
                    timestamp=item_token.timestamp)

                item_token.metadata_status = MetadataStatus.Valid.value
                item_token.metadata = item_token_metadata
                await item_token.save()

                for tag_name in tags:
                    tag, _ = await Tag.get_or_create(name=tag_name, defaults={
                        'level': item_token.level,
                        'timestamp': item_token.timestamp})

                    await ItemTagMap.create(
                        item_metadata=item_token_metadata,
                        tag=tag,
                        level=item_token.level,
                        timestamp=item_token.timestamp)
        # If it fails due to a transaction error, don't mark it as failed.
        except tortoise.exceptions.TransactionManagementError as e:
            raise Exception(f'Transaction failed, Item token_id={item_token.token_id} contract={item_token.contract.address}: {e}') from e
        # If it fails due to anything else, mark as failed and don't throw.
        except Exception as e:
            self._logger.error(f'Failed to process Item token_id={item_token.token_id} contract={item_token.contract.address} metadata: {e}')
            item_token.metadata_status = MetadataStatus.Failed.value
            await item_token.save()


    async def process_metadata(self, token: tuple[MetadataType, int | str]):
        try:
            metadata_type = token[0]
            metadata_id = token[1]

            if metadata_type is MetadataType.Item:
                await self.process_item_token(metadata_id)
            elif metadata_type is MetadataType.Place:
                await self.process_place_token(metadata_id)
            elif metadata_type is MetadataType.Contract:
                await self.process_contract(metadata_id)
            else:
                raise Exception(f'Unknown metadata type "{metadata_type}", can\'t process')
        except Exception as e:
            message = f'Failed to process token: {e}'
            self._logger.error(message)
            raise Exception(message) from e

    async def init(self):
        #await Tortoise.init(
        #    db_url=self._config.db_connection_url,
        #    modules={'models': ['metadata_processing.models']}
        #)

        self._session=aiohttp.ClientSession(
            json_serialize=lambda *a, **kw: orjson.dumps(*a, **kw).decode(),
            connector=aiohttp.TCPConnector(limit=100),
            timeout=aiohttp.ClientTimeout(
                total=None,
                sock_connect=self._config.http_timeout_seconds,
                sock_read=self._config.http_timeout_seconds)
        )

    async def shutdown(self):
        await self._session.close()
        #await Tortoise.close_connections()
