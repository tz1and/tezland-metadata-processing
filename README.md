# metadata-processing

Supplemental to [tezland-indexer](https://github.com/tezland/tezland-indexer)

Prcoesses and validates metadata and artifacts.

You probably want to set the metadata and tags tables to be immune in dipdup, to prevent losing metadata on reindex:

- tag
- item_tag_map
- contract_tag_map
- item_token_metadata
- place_token_metadata
- contract_metadata
- ipfs_metadata_cache