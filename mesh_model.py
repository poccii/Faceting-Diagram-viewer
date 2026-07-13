from dataclasses import dataclass, field
import numpy as np

@dataclass
class Mesh:

    # 全頂点
    vertices: list = field(default_factory=list)

    # 三角形
    triangles: list = field(default_factory=list)

    # 各三角形が属するFacet
    facets: list = field(default_factory=list)

    # 法線
    normals: list = field(default_factory=list)

    # Bounding Box
    bbox_min: np.ndarray | None = None
    bbox_max: np.ndarray | None = None