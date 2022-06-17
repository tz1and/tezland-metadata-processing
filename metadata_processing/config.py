import logging
from os import environ

_logger = logging.getLogger('Config')


class Config:
    def __init__(self, env: str):
        assert env in ('production', 'staging', 'development'), 'env is invalid'
        _logger.info(f'Environment: {env}')
        self.env = env

        db_password = environ.get('POSTGRES_PASSWORD', 'changeme')

        if self.env == 'production':
            self.db_connection_url = f'postgres://dipdup:{db_password}@db-dipdup:15435/dipdup'

            self.ipfs_gateways = [
                'https://ipfs.io',
                'https://cloudflare-ipfs.com',
                'https://nftstorage.link',
                'https://infura-ipfs.io',
                'http://backend-ipfs:8080'
            ]

            self.ipfs_fallback_gateway = 'http://backend-ipfs:8080'
        elif self.env == 'staging':
            self.db_connection_url = f'postgres://dipdup:{db_password}@db-dipdup:15435/dipdup'

            self.ipfs_gateways = [
                'https://ipfs.io',
                'https://cloudflare-ipfs.com',
                'https://nftstorage.link',
                'https://infura-ipfs.io'
            ]

            self.ipfs_fallback_gateway = 'http://backend-ipfs:8080'
        elif self.env == 'development':
            self.db_connection_url = f'postgres://dipdup:{db_password}@localhost:15435/dipdup'
            #self.db_connection_url = 'sqlite://../tezland-indexer/landex.sqlite3'
            #self.db_connection_url = 'sqlite://db.sqlite3'

            self.ipfs_gateways = [
                'https://ipfs.io',
                'https://cloudflare-ipfs.com',
                'https://nftstorage.link',
                'https://infura-ipfs.io'
            ]

            self.ipfs_fallback_gateway = 'http://backend-ipfs:8080'

        self.processing_workers = 8

        self.download_retries = 8

        self.grid_size = 100.0 # default 100

        self.polygon_count_error = 500.0 # default 500

        # TODO
        #MaxMetadataFileSize int     `default:"10000" split_words:"true"`
        #MaxArtifactFileSize int     `default:"67108864" split_words:"true"`