#!/usr/bin/env python3
"""Run with a clean venv's python -I; import must resolve inside that venv."""
import json,sys,importlib.metadata
from pathlib import Path
import brick_engine
from brick_engine import Engine,AssemblyError
ROOT=Path(__file__).resolve().parents[1]
assert Path(brick_engine.__file__).is_relative_to(Path(sys.prefix))
assert importlib.metadata.version('brickbot')==brick_engine.__version__=='0.2.2'
e=Engine();assert len(e.catalog)==109
assert e.search('Brick 2×4')==e.search('Brick 2 x 4')
assert e.search('3001.dat')==e.search('3001')
assert e.part('3001.dat')==e.part('3001')
assert 'interfaces' not in e.describe('91405')
a=e.root('91405')
for n,c in enumerate((0,6,12)):
    e.add(a,part='3001',target='base',target_stud=[c,0],anchor=[0,0],id=f'b{n}')
try:e.add(a,part='3001',target='base',target_stud=[0,0],anchor=[0,0],id='collision')
except AssemblyError as exc:assert exc.code=='E_COLLISION'
else:raise AssertionError('Collision accepted')
assert e.validate(a)['status']=='pass'
assert [g['count'] for g in e.order(a)['grouped_steps']]==[1,3]
export_dir=ROOT/'evidence'/f'{Path(sys.prefix).name}-export'
e.export(a,export_dir)
scene=json.loads((export_dir/'scene.json').read_text())
assert all(m['edges'] and m['conditional_edges'] for m in scene['meshes'].values())
reference=json.loads((ROOT/'reference/water-tool/assembly.json').read_text());assert e.validate(reference)['status']=='pass'
print(json.dumps({'status':'pass','version':importlib.metadata.version('brickbot'),'module':brick_engine.__file__,'parts':len(e.catalog),'smoke_instances':len(a['instances']),'reference_instances':len(reference['instances']),'collision':'E_COLLISION','grouped_steps':2}))
