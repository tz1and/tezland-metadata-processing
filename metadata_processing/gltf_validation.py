import orjson
import logging

from pygltflib import GLTF2, Node, TRIANGLES, TRIANGLE_FAN, TRIANGLE_STRIP
#from pygltflib.validator import validate, summary

_logger = logging.getLogger('gltf_validation')

def count_gltf_polygons(file) -> int:
    if isinstance(file, bytes):
        #_logger.info("GLTF file is binary")
        doc = GLTF2().load_from_bytes(file)
    else:
        #_logger.info("GLTF file is json")
        user_encode_data = orjson.dumps(file)
        doc = GLTF2().gltf_from_json(user_encode_data)

    # NOTE: Currently this experimental validator only validates a few rules about GLTF2 objects
    #validate(doc)  # will throw an error depending on the problem
    #summary(doc)  # will pretty print human readable summary of errors

    # Select the scene.
    # Either the default scene or the first scene.
    if doc.scene is not None:
        scene = doc.scenes[doc.scene]
    else:
        scene = doc.scenes[0]

    # Traverse the scene and count polygons.
    def traverseNodesCountPolygons(node: Node, doc: GLTF2) -> int:
        mesh = node.mesh
        polyCount = 0
        if mesh is not None:
            for prim in doc.meshes[mesh].primitives:
                if prim.indices is None:
                    continue

                match prim.mode:
                    case int(TRIANGLES):
                        polyCount += int(doc.accessors[prim.indices].count / 3)

                    case int(TRIANGLE_STRIP):
                        polyCount += int(doc.Accessors[prim.indices].count - 2)

                    case int(TRIANGLE_FAN):
                        polyCount += int(doc.Accessors[prim.indices].count - 1)

                    case _:
                        continue

        for c in node.children:
            child = doc.nodes[c]
            polyCount += traverseNodesCountPolygons(child, doc)

        return polyCount

    totalPolyCount = 0
    for n in scene.nodes:
        node = doc.nodes[n]
        totalPolyCount += traverseNodesCountPolygons(node, doc)

    #_logger.info(f'polycount: {totalPolyCount}')

    return totalPolyCount