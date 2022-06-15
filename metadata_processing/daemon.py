import asyncio
import logging
import concurrent.futures
from signal import SIGINT, SIGTERM
from time import sleep

from tortoise import Tortoise, connections
from metadata_processing.config import Config
from metadata_processing.worker import thread_main, TokenType
from metadata_processing.models import ItemToken, PlaceToken, MetadataStatus

_logger = logging.getLogger('deamon')

async def spawn_thread(loop, executor, token: tuple[TokenType, int]):
    #result =
    await loop.run_in_executor(executor, thread_main, token)

async def get_tokens(config: Config) -> tuple[TokenType, int]:
    item_tokens = await ItemToken.filter(metadata_status=MetadataStatus.New.value).order_by("level").limit(config.processing_workers) #, )
    for token in item_tokens:
        yield (TokenType.Item, token.id)

    place_tokens = await PlaceToken.filter(metadata_status=MetadataStatus.New.value).order_by("level").limit(config.processing_workers) #, metadata_status=MetadataStatus.New.value)
    for token in place_tokens:
        yield (TokenType.Place, token.id)

async def wait_for_database_online(config: Config):
    while True:
        try:
            await Tortoise.init(
                db_url=config.db_connection_url,
                modules={'models': ['metadata_processing.models']})

            # force open the connection
            conn = connections.get('default')
            await conn.execute_query("SELECT 1")

            _logger.info(f'DB connected: {config.db_connection_url}')

            break
        except Exception as e:
            _logger.info(f'DB connection failed: {e}, sleeping for 10s')
            await asyncio.sleep(10)

async def token_processing_task(loop):
    config = Config()

    try:
        await wait_for_database_online(config)

        tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.processing_workers) as executor:
            while True:
                async for token in get_tokens(config):
                    # spawn the task and let it run in the background
                    tasks.append(asyncio.create_task(
                        spawn_thread(loop, executor, token)))
                # if there was an exception, retrieve it now
                await asyncio.gather(*tasks)

                await asyncio.sleep(1)
    except asyncio.CancelledError:
        _logger.info("Shutdown requested")
    finally:
        await Tortoise.close_connections()

def main():
    logging.basicConfig(level=logging.INFO, style="$")

    loop = asyncio.get_event_loop()
    main_task = asyncio.ensure_future(token_processing_task(loop))
    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, main_task.cancel)

    #try:
    loop.run_until_complete(main_task)
    #finally:
    #    loop.close()