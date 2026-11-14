"""LDraw recursion and horizontal solid cross sections; units are LDU."""
from pathlib import Path
from functools import lru_cache
import numpy as np
import trimesh
from shapely.geometry import Polygon, LineString
from shapely.ops import polygonize, unary_union

class LDraw:
    def __init__(self, root):
        self.root = Path(root)
        self.used = set()
    def resolve(self, name):
        name = name.lower().replace('\\', '/')
        for prefix in ('parts', 'p', ''):
            p = self.root / prefix / name
            if p.exists(): return p
        raise FileNotFoundError(name)
    @lru_cache(maxsize=None)
    def edge_lines(self, name):
        """Recursively preserve type 2 endpoints and type 5 control points."""
        edges, conditional = [], []
        for line in self.resolve(name).read_text(errors='replace').splitlines():
            t = line.split()
            if not t:
                continue
            if t[0] == '1' and len(t) >= 15:
                values = np.array(list(map(float, t[2:14])))
                offset, matrix = values[:3], values[3:].reshape(3, 3)
                child_edges, child_conditional = self.edge_lines(' '.join(t[14:]))
                edges.extend(child_edges @ matrix.T + offset)
                conditional.extend(child_conditional @ matrix.T + offset)
            elif t[0] in ('2', '5'):
                points = np.array(list(map(float, t[2:]))).reshape(-1, 3)
                (edges if t[0] == '2' else conditional).append(points)
        return np.asarray(edges).reshape(-1, 2, 3), np.asarray(conditional).reshape(-1, 4, 3)

    @lru_cache(maxsize=None)
    def expand(self, name):
        path = self.resolve(name)
        self.used.add(path)
        triangles, primitives = [], []
        for line in path.read_text(errors='replace').splitlines():
            t = line.split()
            if not t: continue
            if t[0] == '1' and len(t) >= 15:
                a = np.array(list(map(float,t[2:14])))
                off, mat = a[:3], a[3:].reshape(3,3)
                ref = ' '.join(t[14:]).replace('\\','/').lower()
                child, prim = self.expand(ref)
                triangles.extend(np.asarray(child) @ mat.T + off)
                if Path(ref).name.startswith('stud'):
                    primitives.append(dict(file=ref, position=off.tolist(), matrix=mat.tolist()))
                primitives.extend(dict(file=p['file'],position=(mat@p['position']+off).tolist(),matrix=(mat@p['matrix']).tolist()) for p in prim)
            elif t[0] in ('3','4'):
                v = np.array(list(map(float,t[2:]))) .reshape(-1,3)
                triangles.append(v[:3])
                if t[0]=='4': triangles.append(v[[0,2,3]])
        return np.asarray(triangles).reshape(-1,3,3), primitives

def section(triangles, y):
    lines = trimesh.intersections.mesh_plane(trimesh.Trimesh(vertices=triangles.reshape(-1,3),faces=np.arange(len(triangles)*3).reshape(-1,3),process=False), [0,1,0],[0,y,0])
    # Polygonize noded segments and classify each face by even/odd crossing of
    # the original boundary. This preserves cavities, including hollow tubes.
    segments = [LineString(np.round(l[:,[0,2]],6)) for l in lines if np.linalg.norm(l[0]-l[1])>1e-7]
    if not segments: return Polygon()
    cells = list(polygonize(unary_union(segments)))
    accepted=[]
    coords=np.array([list(s.coords) for s in segments]); x1,z1=coords[:,0,0],coords[:,0,1]; x2,z2=coords[:,1,0],coords[:,1,1]
    for p in cells:
        q=p.representative_point(); x,z=q.x,q.y; crossings=0
        mask=(z1>z)!=(z2>z)
        crossings=np.count_nonzero(x < (x2[mask]-x1[mask])*(z-z1[mask])/(z2[mask]-z1[mask])+x1[mask])
        if crossings%2: accepted.append(p)
    return unary_union(accepted)

def collision_layers(triangles):
    ys=np.unique(np.round(triangles[:,:,1],5)); layers=[]; exact=True
    for lo,hi in zip(ys[:-1],ys[1:]):
        if hi-lo<1e-5: continue
        mid=section(triangles,(lo+hi)/2)
        # A prism is exact only if its cross-section stays constant throughout.
        a=section(triangles,lo+(hi-lo)*.2); b=section(triangles,lo+(hi-lo)*.8)
        if a.symmetric_difference(b).area>1e-3: exact=False
        layers.append({'lo':float(lo),'hi':float(hi),'wkt':mid.wkt})
    return layers, exact
