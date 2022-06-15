class Config:
    #db_connection_url = 'postgres://dipdup:changeme@127.0.0.1:15435/dipdup'
    db_connection_url = 'sqlite://../tezland-indexer/landex.sqlite3'
    #db_connection_url = 'sqlite://db.sqlite3'

    ipfs_gateways = [
        'https://ipfs.io',
        'https://cloudflare-ipfs.com',
        'https://nftstorage.link',
        'https://infura-ipfs.io'
    ]

    ipfs_fallback_gateway = 'http://backend-ipfs:8080'

    processing_workers = 1

    grid_size = 100.0