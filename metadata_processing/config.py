class Config:
    db_connection_url = 'postgres://dipdup:changeme@127.0.0.1:15435/dipdup'
    #db_connection_url = 'sqlite://../tezland-indexer/landex.sqlite3'
    #db_connection_url = 'sqlite://db.sqlite3'

    ipfs_gateways = [
        'https://ipfs.io',
        'https://cloudflare-ipfs.com',
        'https://nftstorage.link',
        'https://infura-ipfs.io',
        #'http://backend-ipfs:8080'
    ]

    ipfs_fallback_gateway = 'http://backend-ipfs:8080'

    processing_workers = 8

    download_retries = 8

    grid_size = 100.0 # default 100

    polygon_count_error = 500.0 # default 500

    # TODO
    #MaxMetadataFileSize int     `default:"10000" split_words:"true"`
	#MaxArtifactFileSize int     `default:"67108864" split_words:"true"`