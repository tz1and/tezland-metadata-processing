import logging
from os import environ

_logger = logging.getLogger('Config')


class Config:
    def __init__(self, env: str):
        assert env in ('production', 'staging', 'development', 'test'), 'env is invalid'
        _logger.info(f'Environment: {env}')
        self.env: str = env

        self.processing_workers: int = 8

        self.download_retries: int = 8

        self.grid_size: float = 100.0 # default 100.0

        self.polygon_count_error: float = 500.0 # default 500.0

        self.http_timeout_seconds: float = 60.0 # default 60.0

        self.max_metadata_file_size: int = 10000 # default 10000
        self.max_artifact_file_size: int = 67108864 # default 67108864

        self.startup_wait_time: float = 30.0 # in seconds

        db_password: str = environ.get('POSTGRES_PASSWORD', 'changeme')

        if self.env == 'production':
            self.db_connection_url: str = f'postgres://dipdup:{db_password}@db-dipdup:15435/dipdup'

            self.ipfs_gateways: list[str] = [
                'https://ipfs.io',
                'https://cloudflare-ipfs.com',
                'https://nftstorage.link',
                'https://infura-ipfs.io',
                'http://backend-ipfs:8080'
            ]

            self.ipfs_fallback_gateway: str = 'http://backend-ipfs:8080'
        elif self.env == 'staging':
            self.db_connection_url: str = f'postgres://dipdup:{db_password}@db-dipdup:15435/dipdup'

            self.ipfs_gateways: list[str] = [
                'https://ipfs.io',
                'https://cloudflare-ipfs.com',
                'https://nftstorage.link',
                'https://infura-ipfs.io',
                'http://ipfs:8080'
            ]

            self.ipfs_fallback_gateway: str = 'http://ipfs:8080'
        elif self.env == 'development':
            self.db_connection_url: str = f'postgres://dipdup:{db_password}@db-dipdup:15435/dipdup'
            #self.db_connection_url = 'sqlite://../tezland-indexer/landex.sqlite3'
            #self.db_connection_url = 'sqlite://db.sqlite3'
            #self.startup_wait_time = 0.0

            self.ipfs_gateways: list[str] = [
                'http://ipfs:8080'
                #'http://localhost:8080'
            ]

            self.ipfs_fallback_gateway: str = 'http://ipfs:8080'
            #self.ipfs_fallback_gateway: str = 'http://localhost:8080'
        elif self.env == 'test':
            self.db_connection_url: str = f'sqlite://:memory:'

            self.ipfs_gateways: list[str] = [
                'https://nftstorage.link'
            ]

            self.ipfs_fallback_gateway: str = 'http://backend-ipfs:8080'

            self.download_retries = 1
            self.processing_workers = 1

