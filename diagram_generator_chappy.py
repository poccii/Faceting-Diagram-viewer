import numpy as np
from scipy.spatial import HalfspaceIntersection
from scipy.optimize import linprog
from mesh_model import Mesh


class DiagramGenerator:
    def __init__(self):
        pass

    def generate_polygons(self, diagram):
        halfspaces = []
        planes_info = []

        gear = diagram.index_gear if diagram.index_gear else 64

        for facet in diagram.facets:
            distance = getattr(facet, 'distance', 0.5)
            abs_angle_rad = np.abs(np.radians(facet.angle))
            
            if hasattr(facet, 'raw_indices') and facet.raw_indices:
                indices = facet.raw_indices
            elif hasattr(facet, 'index') and facet.index and facet.index.original:
                indices = facet.index.original
            else:
                indices = [0]
            
            for idx in indices:
                azimuth_rad = np.radians(90.0 - (idx / gear) * 360.0)
                
                nx = np.sin(abs_angle_rad) * np.cos(azimuth_rad)
                ny = np.sin(abs_angle_rad) * np.sin(azimuth_rad)
                nz = np.cos(abs_angle_rad)

                if facet.angle < 0 or facet.section == "Pavilion":
                    nz = -nz

                halfspaces.append([nx, ny, nz, -distance])
                planes_info.append({
                    'facet': facet, 
                    'normal': np.array([nx, ny, nz]),
                    'specific_index': idx
                })

        bbox = 5.0
        bbox_planes = [
            [0, 0, 1, -bbox], [0, 0, -1, -bbox],
            [1, 0, 0, -bbox], [-1, 0, 0, -bbox],
            [0, 1, 0, -bbox], [0, -1, 0, -bbox]
        ]
        for bp in bbox_planes:
            halfspaces.append(bp)

        halfspaces_arr = np.array(halfspaces, dtype=float)

        # ★追加：距離0の面があっても確実に図形の内側となる「チェビシェフ中心」を計算してエラーを回避
        norm_vector = np.linalg.norm(halfspaces_arr[:, :3], axis=1)
        A_ub = np.hstack((halfspaces_arr[:, :3], norm_vector[:, np.newaxis]))
        b_ub = -halfspaces_arr[:, 3]
        c = np.array([0, 0, 0, -1])  # 半径(r)を最大化

        try:
            res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=[(None, None)]*3 + [(1e-5, None)])
            if res.success:
                feasible_point = res.x[:3]
            else:
                feasible_point = np.array([0.0, 0.0, -0.1])
        except Exception:
            feasible_point = np.array([0.0, 0.0, -0.1])
        
        try:
            hs = HalfspaceIntersection(halfspaces_arr, feasible_point)
        except Exception as e:
            print(f"Intersection failed: {e}")
            return []

        plane_to_vertices = {i: [] for i in range(len(planes_info))}

        for vertex_idx, poly_indices in enumerate(hs.dual_facets):
            vertex = hs.intersections[vertex_idx]
            if np.any(np.abs(vertex) > (bbox - 0.1)):
                continue
            for p_idx in poly_indices:
                if p_idx < len(planes_info):
                    plane_to_vertices[p_idx].append(vertex)

        ordered_polygons = []
        for p_idx, pts in plane_to_vertices.items():
            if len(pts) < 3:
                continue
            
            info = planes_info[p_idx]
            pts = np.array(pts)
            center = np.mean(pts, axis=0)
            normal = info['normal']
            
            v1 = pts[0] - center
            v1_norm = np.linalg.norm(v1)
            if v1_norm < 1e-6: continue
            v1 /= v1_norm
            
            v2 = np.cross(normal, v1)
            v2_norm = np.linalg.norm(v2)
            if v2_norm < 1e-6: continue
            v2 /= v2_norm

            angles = [np.arctan2(np.dot(pt - center, v2), np.dot(pt - center, v1)) for pt in pts]
            sort_idx = np.argsort(angles)
            
            ordered_polygons.append({
                'facet': info['facet'],
                'specific_index': info['specific_index'],
                'points': pts[sort_idx],
                'center': center
            })
# 連続する重複頂点を除去
        clean_pts = []

        for p in pts:
            if len(clean_pts) == 0:
                clean_pts.append(p)
            elif np.linalg.norm(p - clean_pts[-1]) > 1e-8:
                clean_pts.append(p)

# 最初と最後が同じなら最後を削除
        if len(clean_pts) > 2:
            if np.linalg.norm(clean_pts[0] - clean_pts[-1]) < 1e-8:
                clean_pts.pop()

        pts = np.array(clean_pts)


        return ordered_polygons
    
    def generate_mesh(self, diagram):

        polygons = self.generate_polygons(diagram)

        mesh = Mesh()

        vertex_map = {}

        def add_vertex(v):

            key = tuple(np.round(v, 8))

            if key in vertex_map:
                return vertex_map[key]

            idx = len(mesh.vertices)

            mesh.vertices.append(np.array(v))

            vertex_map[key] = idx

            return idx

        for poly in polygons:

            pts = poly["points"]
            print(len(pts))

            for p in pts:
                print(p)

                print("----------------")

            if len(pts) < 3:
                continue

            indices = []

            for p in pts:
                indices.append(add_vertex(p))
               

            # 扇形分割
            for i in range(1, len(indices)-1):

                mesh.triangles.append(
                    (
                        indices[0],
                        indices[i],
                        indices[i+1]
                    )
                )

                mesh.facets.append(poly["facet"])

                if "normal" in poly:
                    mesh.normals.append(poly["normal"])
                else:
                    mesh.normals.append(None)

        mesh.vertices = np.asarray(mesh.vertices)

        if len(mesh.vertices):

                mesh.bbox_min = mesh.vertices.min(axis=0)

                mesh.bbox_max = mesh.vertices.max(axis=0)
        print("First triangle =", mesh.triangles[0])
        return mesh