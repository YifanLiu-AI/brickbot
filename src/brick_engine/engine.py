import re
import json, gzip, csv, math
from pathlib import Path
from collections import Counter
from functools import lru_cache
import numpy as np
from shapely import wkt, affinity
import networkx as nx
DATA=Path(__file__).parent/'data'
class AssemblyError(Exception):
    def __init__(self,code,message,**details):
        super().__init__(message); self.code=code; self.details=details
    def result(self): return dict(status='fail',error={'code':self.code,'reason':str(self),**self.details})
def rotation(angle):
    if angle not in (0,90,180,270): raise AssemblyError('E_ROTATION','Use 0, 90, 180 or 270 degrees',suggestion='Choose a rigid quarter turn; deformation is unsupported')
    c=round(math.cos(math.radians(angle))); s=round(math.sin(math.radians(angle)))
    return np.array([[c,0,s],[0,1,0],[-s,0,c]],dtype=float)
class Engine:
    def __init__(self,data=DATA):
        self.data=Path(data); self.catalog=json.loads((self.data/'catalog.json').read_text())
    def search(self,query='',limit=30):
        norm=lambda t:' '.join(re.sub(r'(\d)\s*x\s*(?=\d)',r'\1 x ',str(t).lower().replace('.dat',' ').replace('×','x')).split())
        q=norm(query)
        return [{'id':p['id'],'name':p['name'],'status':p['validation']['status'],'studs':sum(i['type']=='stud' for i in p['interfaces']),'receivers':sum(i['type']=='anti_stud' for i in p['interfaces'])} for p in self.catalog.values() if q in norm(p['name']+' '+p['id'])][:limit]
    def part(self,id):
        if isinstance(id,str) and id.lower().endswith('.dat') and id[:-4] in self.catalog: id=id[:-4]
        if id not in self.catalog: raise AssemblyError('E_PART',f'Unknown part {id}',part=id,suggestion='Search the catalog first')
        return self.catalog[id]
    def describe(self,part,compact=None):
        p=self.part(part)
        if compact is None: compact=len(p['interfaces'])>64
        if not compact:return p
        return {k:p[k] for k in ('id','name','dimensions_ldu','dimensions_mm','body_height','grid','validation')} | {
            'interface_counts':dict(Counter(i['type'] for i in p['interfaces'])),
            'rules':['target_stud=[column,row] on existing part; anchor=[column,row] on new part',
                     'Coordinates are local to each part, before rotation; only verified interfaces may be selected',
                     'stud -> anti_stud; rotation=0/90/180/270; insertion along +Y',
                     'IDs follow source traversal: s0 and a0 need not share a grid coordinate; use matching coordinates for aligned stacking',
                     'describe compact=false returns all interfaces and geometry']}
    def select_interface(self,part,id,grid,kind):
        if grid is None:return self.interface(part,id)
        if not isinstance(grid,(list,tuple)) or len(grid)!=2 or any(type(v) is not int for v in grid):
            raise AssemblyError('E_INPUT','Grid coordinate must be two integers [column,row]')
        for i in self.part(part)['interfaces']:
            if i['type']==kind and i['grid']==list(grid):
                if id is not None and id!=i['id']:
                    raise AssemblyError('E_INPUT','Interface ID and grid coordinate disagree')
                return i
        raise AssemblyError('E_INTERFACE',f'No verified {kind} at grid {grid}',part=part,suggestion='Use describe to check local grid bounds and interface types; compact=false lists verified sites')
    def interface(self,part,id):
        for i in self.part(part)['interfaces']:
            if i['id']==id:return i
        raise AssemblyError('E_INTERFACE',f'Unknown interface {id}',part=part,interface=id,suggestion='Describe the part and select a listed interface')
    def world(self,inst,interface):
        return rotation(inst.get('rotation',0))@np.array(interface['position'])+inst['position']
    @lru_cache(maxsize=512)
    def local_layers(self,part,angle):
        return [(l['lo'],l['hi'],affinity.rotate(wkt.loads(l['wkt']),-angle,origin=(0,0))) for l in self.part(part)['collision']['layers']]
    @lru_cache(maxsize=4096)
    def transformed_layers(self,part,angle,position):
        x,y,z=position;return [(lo+y,hi+y,affinity.translate(p,x,z)) for lo,hi,p in self.local_layers(part,angle)]
    def layers(self,inst):
        return self.transformed_layers(inst['part'],inst.get('rotation',0),tuple(inst['position']))
    def bounds(self,inst):
        b=np.array(self.part(inst['part'])['bbox']);r=rotation(inst.get('rotation',0));v=b@r.T+inst['position'];return np.array([v.min(axis=0),v.max(axis=0)])
    def collisions(self,a,b,sweep=False):
        aa,bb=self.bounds(a),self.bounds(b)
        if any(min(aa[1,k],bb[1,k])-max(aa[0,k],bb[0,k])<=1e-5 for k in (0,2)):return False
        if not sweep and min(aa[1,1],bb[1,1])-max(aa[0,1],bb[0,1])<=1e-5:return False
        if sweep and bb[0,1]>=aa[1,1]-1e-5:return False
        # Intersection of solid prism interiors, not footprint occupancy.
        for al,ah,ap in self.layers(a):
            for bl,bh,bp in self.layers(b):
                if (bl<ah-1e-5 if sweep else min(ah,bh)-max(al,bl)>1e-5):
                    if ap.intersection(bp).area>1e-3:return True
        return False
    def propose(self,assembly,part,target,target_interface=None,interface=None,rotation=0,id=None,structure='body',color=4,target_stud=None,anchor=None):
        old=next((i for i in assembly.get('instances',[]) if i['id']==target),None)
        if not old:raise AssemblyError('E_TARGET',f'No instance {target}',suggestion='Add a grounded root first')
        a=self.select_interface(old['part'],target_interface,target_stud,'stud');b=self.select_interface(part,interface,anchor,'anti_stud')
        target_interface,interface=a['id'],b['id']
        if (a['type'],b['type'])!=('stud','anti_stud'):raise AssemblyError('E_TYPE','Bottom-up attachment requires target stud and new anti_stud',part=part,interface=interface,suggestion='Choose target s* and new a*')
        r=globals()['rotation'](rotation)
        if not np.allclose(r@b['axis'],-np.array(a['axis'])):raise AssemblyError('E_AXIS','Connector axes do not oppose',suggestion='Use a supported quarter turn')
        position=(self.world(old,a)-r@b['position']).tolist()
        inst=dict(id=id or f'p{len(assembly.get("instances",[]))+1}',part=part,position=position,rotation=rotation,structure=structure,color=color)
        return {'status':'pass','instance':inst,'connection':dict(lower=target,upper=inst['id'],lower_interface=target_interface,upper_interface=interface),'rigid_transform':r.tolist()}
    def add(self,assembly,**args):
        proposal=self.propose(assembly,**args); inst=proposal['instance']
        if any(i['id']==inst['id'] for i in assembly['instances']):raise AssemblyError('E_ID','Duplicate instance id',suggestion='Use a unique instance id')
        if self.part(inst['part'])['validation']['status']!='pass':return {'status':'unknown','reason':'Part geometry/interfaces not fully verified','part':inst['part'],'details':self.part(inst['part'])['validation']}
        for old in assembly['instances']:
            if self.collisions(inst,old):raise AssemblyError('E_COLLISION','Solid material intersects',parts=[inst['id'],old['id']],interface=proposal['connection']['upper_interface'],suggestion='Select another target interface or quarter turn')
            if self.collisions(inst,old,sweep=True):raise AssemblyError('E_INSERTION','Vertical insertion path blocked',parts=[inst['id'],old['id']],suggestion='Install this part before the obstructing part')
        assembly['instances'].append(inst)
        assembly['connections']=self.connections(assembly)
        return {'status':'pass','instance':inst,'connections':[c for c in assembly['connections'] if c['upper']==inst['id']]}
    def root(self,part,id='base',color=7):
        p=self.part(part)
        return {'schema_version':1,'ground_y':p['bbox'][1][1],'instances':[dict(id=id,part=part,position=[0,0,0],rotation=0,structure='base',color=color)],'connections':[]}
    def connections(self,assembly):
        studs={}; out=[]
        for inst in assembly['instances']:
            for i in self.part(inst['part'])['interfaces']:
                if i['type']=='stud':studs.setdefault(tuple(np.round(self.world(inst,i),5)),[]).append((inst,i))
        for inst in assembly['instances']:
            for i in self.part(inst['part'])['interfaces']:
                if i['type']!='anti_stud':continue
                for old,j in studs.get(tuple(np.round(self.world(inst,i),5)),[]):
                    if old['id']!=inst['id']:out.append(dict(lower=old['id'],upper=inst['id'],lower_interface=j['id'],upper_interface=i['id']))
        return out
    def order(self,assembly):
        nodes={i['id']:i for i in assembly['instances']};g=nx.DiGraph();g.add_nodes_from(nodes)
        con=self.connections(assembly);g.add_edges_from((c['lower'],c['upper']) for c in con)
        # If an existing part obstructs another's insertion, it must be later.
        for a in nodes.values():
            for b in nodes.values():
                if a['id']!=b['id'] and self.collisions(a,b,sweep=True):g.add_edge(a['id'],b['id'])
        try:order=list(nx.lexicographical_topological_sort(g,key=lambda k:(-nodes[k]['position'][1],k)))
        except nx.NetworkXUnfeasible:raise AssemblyError('E_ORDER','Support/insertion constraint cycle',suggestion='Remove the enclosing part or rebuild from the base')
        layers={}
        for id in order:layers[id]=1+max((layers[parent] for parent in g.predecessors(id)),default=-1)
        groups={}
        for id in order:
            groups.setdefault((layers[id],nodes[id]['position'][1]),[]).append(id)
        grouped=[]
        for (layer,y),ids in sorted(groups.items(),key=lambda item:(item[0][0],-item[0][1])):
            structures=dict(Counter(nodes[id].get('structure','body') for id in ids))
            grouped.append(dict(step=len(grouped)+1,dependency_layer=layer,height_ldu=-y,count=len(ids),add=ids,
                new_parts=[dict(id=id,part=nodes[id]['part'],color=nodes[id].get('color',4),structure=nodes[id].get('structure','body')) for id in ids],
                subassembly='在已完成支撑上逐件安装：'+ '、'.join(f'{name} {count} 件' for name,count in structures.items())+'；同组零件互不依赖。'))
        return {'status':'pass','steps':[{'step':n+1,'add':id,'depends_on':list(g.predecessors(id)),'dependency_layer':layers[id]} for n,id in enumerate(order)],'grouped_steps':grouped}
    def validate(self,assembly):
        issues=[]; insts=assembly['instances']; con=self.connections(assembly); incoming=Counter(c['upper'] for c in con); dof={}
        if len({i['id'] for i in insts})!=len(insts):
            issues.append(dict(status='fail',code='E_ID',reason='Duplicate instance IDs',suggestion='Assign unique IDs'))
        actual={(c['lower'],c['upper'],c['lower_interface'],c['upper_interface']) for c in con}
        for c in assembly.get('connections',[]):
            key=(c.get('lower'),c.get('upper'),c.get('lower_interface'),c.get('upper_interface'))
            if key not in actual:
                issues.append(dict(status='fail',code='E_ALIGNMENT',connection=c,reason='Declared connection does not match coincident compatible connector positions and opposing axes',suggestion='Use propose/add to solve the exact transform'))
        for i in insts:
            if any(k in i for k in ('scale','matrix','deformation')):
                issues.append(dict(status='fail',code='E_DEFORMATION',part=i['id'],reason='Custom scale/matrix/deformation is not a supported rigid quarter-turn pose',suggestion='Use position and rotation only'))
            p=self.part(i['part']); rotation(i.get('rotation',0))
            if p['validation']['status']!='pass':issues.append(dict(status='unknown',part=i['id'],reason=p['validation']['reasons']))
            grounded=abs(i['position'][1]+p['bbox'][1][1]-assembly.get('ground_y',8))<1e-5
            count=incoming[i['id']]
            dof[i['id']]={'status':'pass' if grounded or count else 'fail','remaining':0 if grounded or count>=2 else 1 if count else 6,'model':'Grounded base fixed; unsupported rigid body has 6 DOF; held axial seating with one circular connector permits yaw, >=2 distinct connectors fixes yaw'}
            if not grounded and not incoming[i['id']]:issues.append(dict(status='fail',code='E_SUPPORT',part=i['id'],reason='No bottom connector support or ground contact',suggestion='Attach an anti_stud to a lower stud'))
            if i['position'][1]+p['bbox'][1][1]>assembly.get('ground_y',8)+1e-5:issues.append(dict(status='fail',code='E_GROUND',part=i['id'],reason='Below ground plane',suggestion='Raise root to ground'))
        for n,a in enumerate(insts):
            for b in insts[n+1:]:
                if self.collisions(a,b):issues.append(dict(status='fail',code='E_COLLISION',parts=[a['id'],b['id']],reason='Solid prism interiors overlap',suggestion='Change connector or orientation'))
        try:order=self.order(assembly)
        except AssemblyError as e:issues.append(e.result());order=None
        return {'status':'fail' if any(i['status']=='fail' for i in issues) else 'unknown' if issues else 'pass','geometry':{'status':'fail' if any(i['status']=='fail' for i in issues) else 'unknown' if issues else 'pass','issues':issues},'connections':con,'degrees_of_freedom':dof,'load_capacity':{'status':'unknown','reason':'No measured clutch force, material or load-test data'},'watertightness':{'status':'unknown','reason':'Seamless/no-leak assumption supplied by user'},'order':order}
    def export(self,assembly,directory):
        dest=Path(directory);dest.mkdir(parents=True,exist_ok=True);order=self.order(assembly); lookup={i['id']:i for i in assembly['instances']};lines=['0 LDraw brick-engine assembly','0 Units LDU; +Y down']
        for step in order['grouped_steps']:
            for id in step['add']:
                i=lookup[id];r=rotation(i.get('rotation',0));lines.append('1 '+str(i.get('color',4))+' '+' '.join(f'{v:g}' for v in i['position']+r.ravel().tolist())+' '+i['part']+'.dat')
            lines.append('0 STEP')
        instructions=['# 分组装配说明','同一依赖层、同一局部原点高度合为一步；组内逐件安装，不要求预先拼成独立组件。','']
        for step in order['grouped_steps']:
            instructions += [f"## 第 {step['step']} 步 · {step['count']} 件 · 高度 {step['height_ldu']*.4:g} mm",step['subassembly'],'']
            instructions += [f"- {i['id']}: {self.part(i['part'])['name']} ({i['part']}), color {i['color']}" for i in step['new_parts']]
            instructions += ['']
        (dest/'instructions.md').write_text('\n'.join(instructions))
        (dest/'model.ldr').write_text('\n'.join(lines)+'\n')
        # MPD includes all recursively used source files for self-contained load.
        sources=set()
        def include(name):
            name=name.replace('\\','/').lower()
            if name in sources:return
            for prefix in ('parts','p',''):
                f=self.data/'ldraw'/prefix/name
                if f.exists():break
            else:return
            sources.add(name)
            for line in f.read_text(errors='replace').splitlines():
                t=line.split()
                if t and t[0]=='1':include(' '.join(t[14:]))
            return f
        for i in assembly['instances']:include(i['part']+'.dat')
        mpd=['0 FILE model.ldr',*lines]
        for name in sorted(sources):
            for prefix in ('parts','p',''):
                f=self.data/'ldraw'/prefix/name
                if f.exists():break
            mpd+=['0 FILE '+name,f.read_text(errors='replace')]
        (dest/'model.mpd').write_text('\n'.join(mpd))
        bom=[dict(part=k[0],color=k[1],quantity=v,name=self.part(k[0])['name']) for k,v in sorted(Counter((i['part'],i.get('color',4)) for i in assembly['instances']).items())]
        with (dest/'bom.csv').open('w') as f:
            writer=csv.DictWriter(f,fieldnames=['part','color','quantity','name']);writer.writeheader();writer.writerows(bom)
        from .geometry import LDraw
        line_library=LDraw(self.data/"ldraw")
        meshes={}
        for id in {i['part'] for i in insts} if (insts:=assembly['instances']) else []:
            with gzip.open(self.data/self.part(id)['mesh'],'rt') as f:meshes[id]=json.load(f)
            edges,conditional=line_library.edge_lines(self.part(id)['source']['file'])
            meshes[id]['edges']=edges.round(6).tolist()
            meshes[id]['conditional_edges']=conditional.round(6).tolist()
        scene={'units':'LDU','mm_per_ldu':.4,'up':[0,-1,0],'meshes':meshes,'instances':assembly['instances'],'steps':order['grouped_steps'],'piece_steps':order['steps']}
        for name,data in [('bom.json',bom),('assembly.json',assembly),('steps.json',order),('scene.json',scene),('validation.json',self.validate(assembly))]: (dest/name).write_text(json.dumps(data,separators=(',',':')))
        return {'status':'pass','directory':str(dest),'files':['instructions.md','model.ldr','model.mpd','bom.csv','bom.json','assembly.json','steps.json','scene.json','validation.json']}
