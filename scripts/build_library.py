#!/usr/bin/env python3
"""Download official library once, then rebuild all selected rectangular parts."""
import sys, re, json, gzip, zipfile, shutil, subprocess
from pathlib import Path
import numpy as np
from shapely.geometry import Point
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from brick_engine.geometry import LDraw, section, collision_layers

def main():
    archive=ROOT/'reference/official.zip'
    if not archive.exists():
        subprocess.run(['curl','-L','--fail','-o',str(archive),'https://library.ldraw.org/library/updates/complete.zip'],check=True)
    extracted=ROOT/'reference/unpacked'
    if not (extracted/'ldraw/parts').exists():
        with zipfile.ZipFile(archive) as z: z.extractall(extracted)
    source=extracted/'ldraw'; lib=LDraw(source)
    out=ROOT/'src/brick_engine/data'; (out/'meshes').mkdir(parents=True,exist_ok=True)
    catalog={}; errors=[]
    # Exact plain rectangular category+dimensions, plus standard groove/mould
    # variants. Decorated, sloped, modified, rounded and patterned are excluded.
    pattern=re.compile(r'^(Brick|Plate|Tile|Baseplate)\s+(\d+)\s+x\s+(\d+)(?:\s+x\s+(\d+))?(.*)$')
    candidates=[]
    for f in sorted((source/'parts').glob('*.dat')):
        text=f.read_text(errors='replace'); name=text.splitlines()[0][2:].strip(); m=pattern.match(name)
        if not m: continue
        category,w,l,h,suffix=m.groups(); w,l=int(w),int(l)
        if h and category!='Brick': continue
        if suffix and not re.fullmatch(r'\s*(?:without Understud|with Underside Ribs|without Underside Details|with Underside Details|Type 2|without Centre Studs?|without Center Studs?|without Centre Studs with (?:2 )?Internal Ribs|without Groove|with Groove|with Bottom Tubes|with Bottom Pin|with Centre Stud|with Center Stud|with Open Stud|with Hollow Stud|with Solid Studs|with Reinforced Underside|with Reinforced Underside and Studs|with Cross Supports|with Bottom Stud Holder|with Bottom Stud Holders|with Bottom Studs|with Studs on Edge|\(.*?\))',suffix): continue
        if category=='Brick' and (min(w,l)>2 or max(w,l)>16): continue
        if category in ('Plate','Tile') and max(w,l)>16: continue
        candidates.append((f,name,category,w,l,text))
    for n,(f,name,category,w,l,text) in enumerate(candidates):
        try:
            triangles,primitives=lib.expand(f.name)
            bounds=np.array([triangles.min(axis=(0,1)),triangles.max(axis=(0,1))]); height=float(bounds[1,1])
            layers,exact=collision_layers(triangles)
            interfaces=[]; seen=set()
            for p in primitives:
                base=Path(p['file']).name
                # stud3=bottom solid pin, stud4=bottom tube: never male studs.
                if base not in ('stud.dat','stud2.dat','stud2a.dat'): continue
                pos=np.array(p['position']); mat=np.array(p['matrix']); axis=mat@np.array([0,-1,0])
                if not np.allclose(axis,[0,-1,0]) or abs(pos[1])>1e-5: continue
                key=tuple(np.round(pos,5))
                if key in seen: continue
                seen.add(key)
                interfaces.append(dict(id=f's{len(interfaces)}',type='stud',position=pos.tolist(),axis=[0,-1,0],insertion=[0,1,0],status='pass',evidence=p['file']))
            cavity=section(triangles,height-2)
            # Candidate locations from measured outer walls at 20 LDU pitch;
            # accept only when actual cavity geometry supplies radial contacts.
            for x in np.arange(bounds[0,0]+10,bounds[1,0],20):
                for z in np.arange(bounds[0,2]+10,bounds[1,2],20):
                    disk=Point(x,z).buffer(5.98,quad_segs=16)
                    if cavity.intersection(disk).area>0.01: continue
                    contacts=[]
                    for theta in np.arange(0,360,45):
                        rad=np.deg2rad(theta); q=Point(x+6.1*np.cos(rad),z+6.1*np.sin(rad))
                        if cavity.distance(q)<.35: contacts.append(int(theta))
                    if len(contacts)<3: continue
                    interfaces.append(dict(id=f'a{len([i for i in interfaces if i["type"]=="anti_stud"])}',type='anti_stud',position=[float(x),height,float(z)],axis=[0,1,0],insertion=[0,1,0],status='pass',evidence={'method':'bottom cavity radial clearance/contact','contacts_degrees':contacts,'slice_y':height-2}))
            grid={'origin_ldu':[float(bounds[0,0]+10),float(bounds[0,2]+10)],'pitch_ldu':20,
                  'column_range':[0,int(round((bounds[1,0]-bounds[0,0])/20))-1],
                  'row_range':[0,int(round((bounds[1,2]-bounds[0,2])/20))-1],
                  'axes':'local column +X, row +Z; origin at minimum X/Z stud center; coordinates before rotation'}
            for interface in interfaces:
                interface['grid']=[int(round((interface['position'][0]-grid['origin_ldu'][0])/20)),int(round((interface['position'][2]-grid['origin_ldu'][1])/20))]
            reasons=[]
            male=sum(i['type']=='stud' for i in interfaces); female=sum(i['type']=='anti_stud' for i in interfaces)
            if category!='Tile' and male!=w*l: reasons.append(f'male count {male} differs from rectangular footprint {w*l}')
            if category!='Baseplate' and female!=w*l: reasons.append(f'validated receivers {female}/{w*l}')
            if not exact: reasons.append('non-prismatic surfaces: midpoint collision layers approximate')
            rawmesh={'positions':triangles.reshape(-1,3).round(6).tolist(),'indices':np.arange(len(triangles)*3).reshape(-1,3).tolist()}
            with gzip.open(out/'meshes'/f'{f.stem}.json.gz','wt') as g: json.dump(rawmesh,g,separators=(',',':'))
            catalog[f.stem]=dict(id=f.stem,name=name,category=category,stud_dimensions=[w,l],dimensions_ldu=(bounds[1]-bounds[0]).tolist(),dimensions_mm=((bounds[1]-bounds[0])*.4).tolist(),bbox=bounds.tolist(),body_height=height,grid=grid,interfaces=interfaces,collision={'kind':'mesh-derived horizontal solid prisms','exact':exact,'layers':layers},mesh=f'meshes/{f.stem}.json.gz',source={'file':f.name,'author':[s[10:] for s in text.splitlines() if s.startswith('0 Author: ')],'license':[s for s in text.splitlines() if s.startswith('0 !LICENSE')],'version':[s for s in text.splitlines() if s.startswith('0 !LDRAW_ORG')],'url':'https://library.ldraw.org/'},validation={'status':'unknown' if reasons else 'pass','reasons':reasons},unresolved_interfaces=[{'status':'unknown','type':'unknown','position':None,'reason':r} for r in reasons if 'prismatic' not in r],bottom_primitives=[p for p in primitives if Path(p['file']).name in ('stud3.dat','stud4.dat','stud4a.dat')])
            print(f'{n+1}/{len(candidates)} {f.stem} {male}/{female} '+('unknown' if reasons else 'pass'),flush=True)
        except Exception as exc: errors.append({'part':f.stem,'reason':str(exc)})
    for f in lib.used:
        dest=out/'ldraw'/f.relative_to(source); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(f,dest)
    for f in source.glob('*'):
        if f.is_file() and ('readme' in f.name.lower() or 'license' in f.name.lower() or f.name=='LDConfig.ldr'): shutil.copyfile(f,out/'ldraw'/f.name)
    (out/'catalog.json').write_text(json.dumps(catalog,separators=(',',':')))
    report={'processed':len(catalog),'selected':len(candidates),'interface_complete':sum(p['validation']['status']=='pass' for p in catalog.values()),'unknown':sum(p['validation']['status']=='unknown' for p in catalog.values()),'interfaces_extracted':sum(len(p['interfaces']) for p in catalog.values()),'parts_with_extracted_interfaces':sum(bool(p['interfaces']) for p in catalog.values()),'failed':errors,'categories':{c:sum(p['category']==c for p in catalog.values()) for c in ['Brick','Plate','Tile','Baseplate']},'unknown_reasons':{k:v['validation']['reasons'] for k,v in catalog.items() if v['validation']['reasons']},'selection':pattern.pattern,'archive':str(archive),'source':'official complete.zip downloaded 2026-11-14; per-part release in catalog'}
    (out/'coverage.json').write_text(json.dumps(report,indent=2)); (ROOT/'evidence/coverage.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__': main()
