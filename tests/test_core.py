import json,subprocess,sys
import numpy as np
import pytest
from brick_engine import Engine,AssemblyError
from brick_engine.geometry import LDraw
@pytest.fixture(scope='module')
def e():return Engine()
def test_extraction(e):
    p=e.part('3001');assert sum(i['type']=='stud' for i in p['interfaces'])==8
    assert sum(i['type']=='anti_stud' for i in p['interfaces'])==8
    assert p['bottom_primitives'];assert all(i.get('evidence')!='stud4.dat' for i in p['interfaces'] if i['type']=='stud')
    assert p['collision']['exact']
def two(e,angle=0):
    a=e.root('3001');r=e.add(a,part='3001',target='base',target_interface='s0',interface='a0',rotation=angle,id='top');assert r['status']=='pass';return a
def test_pose(e):
    a=two(e);assert a['instances'][1]['position'][1]==-24
    assert e.validate(a)['status']=='pass'
def test_rotation(e):
    a=two(e,90);i=a['instances'][1]
    assert np.allclose(e.world(i,e.interface('3001','a0')),e.world(a['instances'][0],e.interface('3001','s0')))
def test_solid_collision(e):
    a=e.root('3001');b={**a['instances'][0],'id':'overlap','position':[1,0,0]}
    assert e.collisions(a['instances'][0],b)
    a['instances'].append(b);assert e.validate(a)['status']=='fail'
def test_float(e):
    a=e.root('3001');a['instances'].append({**a['instances'][0],'id':'floating','position':[100,-24,0]})
    assert any(i.get('code')=='E_SUPPORT' for i in e.validate(a)['geometry']['issues'])
def test_order(e):
    a=two(e);a['instances'].reverse();assert [s['add'] for s in e.order(a)['steps']]==['base','top']
def test_wrong_type(e):
    with pytest.raises(AssemblyError,match='Bottom-up'): e.propose(e.root('3001'),part='3001',target='base',target_interface='s0',interface='s0')
@pytest.mark.parametrize('q,code',[({'op':'x'},2),({'op':'describe','part':'bad'},3),({'op':'search','query':'Brick  2 x  4'},0)])
def test_cli(q,code):
    r=subprocess.run([sys.executable,'-m','brick_engine'],input=json.dumps(q),capture_output=True,text=True);assert r.returncode==code;assert json.loads(r.stdout)['status'] in ('pass','fail')
def test_deformation(e):
    with pytest.raises(AssemblyError):two(e,45)
def test_export(e,tmp_path):
    e.export(two(e),tmp_path);assert '0 FILE 3001.dat' in (tmp_path/'model.mpd').read_text();assert len(json.loads((tmp_path/'steps.json').read_text())['steps'])==2

def test_declared_connection_misalignment(e):
    a=two(e);a['instances'][1]['position'][0]+=.2
    r=e.validate(a);assert any(i.get('code')=='E_ALIGNMENT' for i in r['geometry']['issues'])
def test_insertion_blocked(e):
    base=e.root('3001')['instances'][0]
    above={**base,'id':'above','position':[0,-48,0]}
    assert not e.collisions(base,above)
    assert e.collisions(base,above,sweep=True)
def test_unknown_not_guessed(e):
    assert e.part('3067a')['validation']['status']=='unknown'
    r=e.add(e.root('3001'),part='3067a',target='base',target_interface='s0',interface='a0')
    assert r['status']=='unknown'
def test_deformed_assembly(e):
    a=e.root('3001');a['instances'][0]['scale']=[2,1,1]
    assert e.validate(a)['status']=='fail'
def test_large_plate(e):
    p=e.part('91405');assert p['validation']['status']=='pass'
    assert len(p['interfaces'])==512

def test_recursive_geometry_extraction(e):
    parser=LDraw(e.data/'ldraw');triangles,primitives=parser.expand('3001.dat')
    studs=[p for p in primitives if p['file']=='stud.dat']
    assert len(studs)==8
    assert any(p['file']=='stud4.dat' for p in primitives)
    assert np.allclose(triangles.min(axis=(0,1)),[-40,-4,-20])
    assert len(parser.used)>5

def test_cli_connection_errors(e):
    a=e.root('3001')
    def run(**kwargs):
        q=dict(op='add',assembly=a,part='3001',target='base',target_interface='s0',interface='a0',**kwargs)
        return subprocess.run([sys.executable,'-m','brick_engine'],input=json.dumps(q),capture_output=True,text=True)
    assert run(rotation=45).returncode==5
    assert run(id='base').returncode==2
    e.add(a,part='3001',target='base',target_interface='s0',interface='a0',id='occupied')
    r=run(id='collision');assert r.returncode==6;assert json.loads(r.stdout)['error']['code']=='E_COLLISION'

@pytest.mark.parametrize('raw',['[]','{"op":"search","limit":NaN}','{broken'])
def test_cli_malformed_input(raw):
    r=subprocess.run([sys.executable,'-m','brick_engine'],input=raw,capture_output=True,text=True)
    assert r.returncode==2;assert json.loads(r.stdout)['error']['code']=='E_INPUT';assert not r.stderr
