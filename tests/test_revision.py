import json
from pathlib import Path
import pytest
from brick_engine import Engine, AssemblyError
from brick_engine.cli import dispatch

@pytest.fixture(scope='module')
def e():return Engine()

def test_grid_all_interfaces_and_compact(e):
    for p in e.catalog.values():
        g=p['grid']
        for i in p['interfaces']:
            c,r=i['grid'];assert type(c) is int and type(r) is int
            assert 0<=c<=g['column_range'][1] and 0<=r<=g['row_range'][1]
            assert i['position'][0]==pytest.approx(g['origin_ldu'][0]+20*c)
            assert i['position'][2]==pytest.approx(g['origin_ldu'][1]+20*r)
    p=dispatch(e,{'op':'describe','part':'91405'})['part']
    assert 'interfaces' not in p and 'collision' not in p
    assert p['interface_counts']=={'stud':256,'anti_stud':256}
    assert p['grid']['column_range']==[0,15]
    assert len(e.describe('91405',compact=False)['interfaces'])==512
    assert 'interfaces' not in e.describe('3001',compact=True)

@pytest.mark.parametrize('angle',[0,90,180,270])
def test_grid_propose_and_add(e,angle):
    a=e.root('91405');q=dict(part='3001',target='base',target_stud=[7,7],anchor=[1,0],rotation=angle,id='top')
    proposal=e.propose(a,**q);assert len(a['instances'])==1
    result=e.add(a,**q);assert result['instance']==proposal['instance']
    assert e.validate(a)['status']=='pass'
    lower=e.select_interface('91405',None,[7,7],'stud');upper=e.select_interface('3001',None,[1,0],'anti_stud')
    assert e.world(a['instances'][0],lower)==pytest.approx(e.world(a['instances'][1],upper))

def test_matching_grid_stacks_without_legacy_offset(e):
    a=e.root('3001');new=e.propose(a,part='3001',target='base',target_stud=[0,0],anchor=[0,0])
    assert new['instance']['position']==[0,-24,0]
    old=e.propose(a,part='3001',target='base',target_interface='s0',interface='a0')
    assert old['instance']['position']==[60,-24,20]

@pytest.mark.parametrize('grid',[[16,0],[-1,0],[0,99],[.5,0],[True,0],[0]])
def test_grid_rejects_invalid(e,grid):
    with pytest.raises(AssemblyError):e.propose(e.root('91405'),part='3001',target='base',target_stud=grid,anchor=[0,0])

def test_grid_collision_and_conflicting_alias(e):
    a=e.root('91405');q=dict(part='3001',target='base',target_stud=[2,2],anchor=[0,0])
    e.add(a,id='one',**q)
    with pytest.raises(AssemblyError) as exc:e.add(a,id='two',**q)
    assert exc.value.code=='E_COLLISION' and len(a['instances'])==2
    with pytest.raises(AssemblyError) as exc:e.propose(a,target_interface='s9999',**q)
    assert exc.value.code=='E_INPUT'

def test_floating_dof(e):
    a=e.root('3001');a['instances'].append({**a['instances'][0],'id':'floating','position':[100,-24,0]})
    result=e.validate(a);assert result['status']=='fail'
    assert result['degrees_of_freedom']['floating']['status']=='fail'
    assert result['degrees_of_freedom']['floating']['remaining']==6
    assert result['degrees_of_freedom']['base']['remaining']==0

def test_group_order_export(e,tmp_path):
    a=e.root('91405')
    for n,c in enumerate((0,6,12)):e.add(a,part='3001',target='base',target_stud=[c,0],anchor=[0,0],id=f'b{n}')
    e.add(a,part='3001',target='b0',target_stud=[0,0],anchor=[0,0],id='cap')
    a['instances'].reverse();order=e.order(a)
    assert [g['count'] for g in order['grouped_steps']]==[1,3,1]
    assert set(order['grouped_steps'][1]['add'])=={'b0','b1','b2'}
    assert set(next(s for s in order['steps'] if s['add']=='cap')['depends_on'])=={'b0','base'}
    e.export(a,tmp_path)
    assert (tmp_path/'model.ldr').read_text().count('0 STEP')==3
    assert '3 件' in (tmp_path/'instructions.md').read_text()
    assert len(json.loads((tmp_path/'scene.json').read_text())['steps'])==3

def test_same_layer_different_height_separate(e):
    a=e.root('91405')
    for id,part,col in [('brick','3001',0),('plate','3020',6)]:
        e.add(a,part=part,target='base',target_stud=[col,0],anchor=[0,0],id=id)
    groups=e.order(a)['grouped_steps']
    assert len(groups)==3 and groups[1]['dependency_layer']==groups[2]['dependency_layer']
    assert groups[1]['height_ldu']!=groups[2]['height_ldu']

@pytest.mark.parametrize('dimensions',[(1,1,3),(1,2,2),(1,2,3),(1,2,5),(2,2,3),(1,4,3),(1,6,5)])
def test_tall_bricks_selected(e,dimensions):
    import re
    w,l,h=dimensions
    parts=[p for p in e.catalog.values() if re.fullmatch(rf'Brick\s+{w}\s+x\s+{l}\s+x\s+{h}(?:\s.*)?',p['name'])]
    assert parts,dimensions
    assert all(p['body_height']==24*h for p in parts)
    assert all(p['interfaces'] and p['source']['license'] for p in parts)

@pytest.fixture(scope='module')
def reference():
    root=Path(__file__).resolve().parents[1]/'reference/water-tool'
    return root,json.loads((root/'assembly.json').read_text())

def test_reference_capacity_and_geometry(e,reference):
    root,a=reference
    assert len(a['instances'])==65
    assert e.validate(a)['status']=='pass'
    capacity=json.loads((root/'capacity.json').read_text())
    assert capacity['conservative_capacity_ml']>=550
    assert capacity['interior_mm']==[96,96,70.4]
    assert len(e.order(a)['grouped_steps'])==9
    assert {i['color'] for i in a['instances']}=={19,71,72}

def test_reference_grips_symmetric_sandwich_clear_opening(e,reference):
    from shapely.geometry import box
    _,a=reference;grips=[i for i in a['instances'] if i['structure']=='grip'];assert len(grips)==2
    assert grips[0]['position']==[0,-152,-160] and grips[1]['position']==[0,-152,160]
    connections=e.connections(a);cavity=box(-120,-120,120,120)
    for grip in grips:
        lower=[c for c in connections if c['upper']==grip['id']]
        upper=[c for c in connections if c['lower']==grip['id']]
        assert len(lower)==16 and len(upper)==16
        lower_rows={e.interface(grip['part'],c['upper_interface'])['grid'][1] for c in lower}
        upper_rows={e.interface(grip['part'],c['lower_interface'])['grid'][1] for c in upper}
        assert len(lower_rows)==2 and lower_rows==upper_rows
        assert all(poly.intersection(cavity).area<1e-5 for _,_,poly in e.layers(grip))

def test_reference_corner_bond_each_course(e,reference):
    _,a=reference
    # At each corner, the upper corner brick/plate must also connect to the
    # adjacent lower side. This fails the former all-courses-same-direction design.
    courses=sorted({i['position'][1] for i in a['instances'] if i['structure']!='base'},reverse=True)
    incoming={}
    for c in e.connections(a):incoming.setdefault(c['upper'],set()).add(c['lower'])
    nodes={i['id']:i for i in a['instances']}
    for y in courses[1:]:
        for x,z in [(-140,-140),(-140,140),(140,-140),(140,140)]:
            corner=next(i for i in a['instances'] if i['position'][1]==y and e.bounds(i)[0,0]<=x<=e.bounds(i)[1,0] and e.bounds(i)[0,2]<=z<=e.bounds(i)[1,2])
            parents=[nodes[id] for id in incoming[corner['id']]]
            assert len({p['rotation'] for p in parents})==2,(y,x,z,corner['id'])

def test_reference_uses_grid_tool_calls(reference):
    root,a=reference
    calls=[json.loads(line) for line in (root/'tool-calls.jsonl').read_text().splitlines()]
    adds=[c for c in calls if c['request']['op']=='add'];assert len(adds)==len(a['instances'])-1
    assert all('target_stud' in c['request'] and 'anchor' in c['request'] and 'position' not in c['request'] for c in adds)
    assert all(c['response']['status']=='pass' for c in calls)

def test_reference_group_renders(reference):
    from PIL import Image
    root,_=reference
    assert len(list((root/'steps').glob('*.png')))==9
    assert Image.open(root/'finished.png').size==(2640,2160)
    assert Image.open(root/'cutaway.png').size==(2640,2160)
    assert Image.open(root/'steps-contact-sheet.png').size==(1920,1770)

def test_real_dsh_fail_repair_export_evidence(e):
    root=Path(__file__).resolve().parents[1]/'evidence'
    if not (root/'dsh-assembly-verification.json').exists():pytest.skip('dsh evidence not shipped')
    report=json.loads((root/'dsh-assembly-verification.json').read_text())
    assert report['status']=='pass' and report['provider']=='ccs-sj' and report['model']=='gpt-6-astra'
    assert report['failure']['code']=='E_COLLISION'
    assert report['failure']['target_stud']==[0,0] and report['repair']['target_stud']==[3,0]
    assert report['tool_calls']==report['tool_results']==18
    a=json.loads((root/'dsh-assembly-workspace/export/assembly.json').read_text())
    assert len(a['instances'])==4 and e.validate(a)['status']=='pass'
    base=a['instances'][0]['id']
    assert all(any(c['upper']==i['id'] and c['lower']==base for c in e.connections(a)) for i in a['instances'][1:])

def test_search_normalization_and_dat_suffix(e):
    expected=e.search('Brick 2 x 4')
    assert expected
    for query in ('Brick 2x4','  BRICK   2 × 4  ','Brick 2 x4'):
        assert e.search(query)==expected
    assert e.search('3001.dat')==e.search('3001')
    assert e.part('3001.dat')==e.part('3001.DAT')==e.part('3001')
