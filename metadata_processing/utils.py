import hashlib
import math

def toGrid(coordinate: float, gridSize: float) -> int:
    sign: int = 1
    if coordinate < 0:
        sign = -1
    return int(math.trunc(coordinate/gridSize)) + sign

def getGridCellHash(x: float, y: float, z: float, gridSize: float) -> str:
    hasher = hashlib.sha1()
    hasher.update(str.encode(f'{toGrid(x, gridSize)}-{toGrid(y, gridSize)}-{toGrid(z, gridSize)}'))
    return hasher.digest().hex()

def getOrRaise(metadata: dict, key: str):
    res = metadata.get(key)
    if res is None:
        raise Exception(f'Key {key} not in metadata')
    return res
