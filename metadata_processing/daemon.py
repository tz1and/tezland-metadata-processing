import asyncio
import logging
import argparse
from signal import SIGINT, SIGTERM

from tortoise import Tortoise, connections
from metadata_processing.config import Config
from metadata_processing.cursor import Cursor
from metadata_processing.task_pool import TaskPool
from metadata_processing.worker import MetadataProcessing, TokenType
from metadata_processing.models import ItemToken, PlaceToken

_logger = logging.getLogger('deamon')


async def wait_for_database_online(config: Config):
    while True:
        try:
            await Tortoise.init(
                db_url=config.db_connection_url,
                modules={'models': ['metadata_processing.models']})

            # force open the connection
            conn = connections.get('default')
            await conn.execute_query("SELECT 1")

            _logger.info(f'DB connected')

            break
        except Exception as e:
            _logger.info(f'DB connection failed: {e}, sleeping for 10s')
            await asyncio.sleep(10)


async def token_processing_task(config: Config):
    item_cursor = Cursor(ItemToken)
    place_cursor = Cursor(PlaceToken)

    try:
        await wait_for_database_online(config)

        processing = MetadataProcessing(config)
        await processing.init()

        task_pool = TaskPool(config.processing_workers)
        pending_tasks = 0

        def decrementPending(f):
            nonlocal pending_tasks
            pending_tasks -= 1
        
        while True:
            while task_pool.tasks.qsize() < config.processing_workers * 2:
                next_item = await item_cursor.next()
                if next_item is not None:
                    pending_tasks += 1
                    task_pool.submit(asyncio.create_task(processing.process_token((TokenType.Item, next_item.id)))).add_done_callback(decrementPending)

                next_place = await place_cursor.next()
                if next_place is not None:
                    pending_tasks += 1
                    task_pool.submit(asyncio.create_task(processing.process_token((TokenType.Place, next_place.id)))).add_done_callback(decrementPending)

                if next_item is None and next_place is None:
                    # reset cursors to starting position if all tasks done
                    if pending_tasks <= 0:
                        item_cursor.reset()
                        place_cursor.reset()
                    break
        
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        _logger.info("Shutdown requested")
    finally:
        task_pool.cancel_all()
        # TODO: maybe shield() these? seems kinda important.
        await task_pool.join()
        await processing.shutdown()
        await Tortoise.close_connections()


def main():
    logging.basicConfig(level=logging.INFO, style="$")

    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--env', help='The environment. production | staging | development.', type=str, default='staging')
    args = parser.parse_args()

    config = Config(args.env)

    loop = asyncio.get_event_loop()
    main_task = asyncio.ensure_future(token_processing_task(config))
    
    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, main_task.cancel)

    loop.run_until_complete(main_task)
