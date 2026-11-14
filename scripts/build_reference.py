#!/usr/bin/env python3
"""Build reference exclusively through the same JSON dispatch used by agents."""
import json,sys,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from brick_engine import Engine
from brick_engine.cli import dispatch
from brick_engine.engine import rotation

def main():
    e=Engine();dest=ROOT/'reference/water-tool';dest.mkdir(parents=True,exist_ok=True)
    log=(dest/'tool-calls.jsonl').open('w')
    def call(q):
        r=dispatch(e,q);log.write(json.dumps({'request':q,'response':r},separators=(',',':'))+'\n');log.flush()
        if r['status']!='pass':raise RuntimeError(r)
        return r
    def choose(category,w,l):
        ps=[p for p in e.catalog.values() if p['category']==category and sorted(p['stud_dimensions'])==sorted([w,l]) and p['validation']['status']=='pass' and (category!='Brick' or p['body_height']==24)]
        ps.sort(key=lambda p:(len(p['name']),p['id']))
        if not ps:raise RuntimeError(f'No verified {category} {w}x{l}')
        call({'op':'describe','part':ps[0]['id']});return ps[0]['id']
    base=choose('Plate',16,16);brick8=choose('Brick',2,8);brick6=choose('Brick',2,6);ear=choose('Plate',4,8)
    plate4=choose('Plate',2,4);plate12=choose('Plate',2,12)
    a=call({'op':'root','part':base,'color':71})['assembly']
    def attach(part,position,angle,id,structure,color):
        # Layout selects desired footprint; only named connectors are sent to
        # the solver. No pose is injected into the assembly.
        receivers=[i for i in e.part(part)['interfaces'] if i['type']=='anti_stud']
        for old in reversed(a['instances']):
            for stud in e.part(old['part'])['interfaces']:
                if stud['type']!='stud':continue
                world=e.world(old,stud)
                for rec in receivers:
                    if np.allclose(world,rotation(angle)@rec['position']+position):
                        call({'op':'add','assembly':a,'part':part,'target':old['id'],'target_stud':stud['grid'],'anchor':rec['grid'],'rotation':angle,'id':id,'structure':structure,'color':color});return
        raise RuntimeError(f'No geometric connector for {id}')
    def wall_course(layer,y,full_axis):
        # A full side comprises two 2x8 bricks; the other sides have two 2x6.
        # Swapping the full axis on every course bonds all four corners.
        for axis in ('z','x'):
            full=axis==full_axis;part=brick8 if full else brick6;offset=80 if full else 60
            for side in (-1,1):
                for j,t in enumerate((-offset,offset)):
                    position=[t,y,side*140] if axis=='z' else [side*140,y,t]
                    attach(part,position,0 if axis=='z' else 90,f'wall_{layer}_{axis}{side}_{j}','wall',72 if layer%2==0 else 71)
    for layer in range(6):wall_course(layer,-24*(layer+1),'z' if layer%2==0 else 'x')
    # Entire plate course is level: two 4x8 ears span both wall rows, with
    # their inner edge flush to the cavity and two rows extending outside.
    for side in (-1,1):
        attach(ear,[0,-152,side*160],0,f'grip_{side}','grip',19)
        for j,x in enumerate((-120,120)):
            attach(plate4,[x,-152,side*140],0,f'bond_z{side}_{j}','bond',72)
        attach(plate12,[side*140,-152,0],90,f'bond_x{side}','bond',72)
    wall_course(6,-176,'x')
    report=call({'op':'validate','assembly':a});call({'op':'export','assembly':a,'directory':str(dest)})
    # Inner rectangle is bounded by actual wall exterior faces. Subtract base
    # studs conservatively using analytic circumscribed cylinders.
    walls=[i for i in a['instances'] if i['structure']=='wall']
    left=max(e.bounds(i)[1,0] for i in walls if '_x-1_' in i['id'])
    right=min(e.bounds(i)[0,0] for i in walls if '_x1_' in i['id'])
    front=max(e.bounds(i)[1,2] for i in walls if '_z-1_' in i['id'])
    back=min(e.bounds(i)[0,2] for i in walls if '_z1_' in i['id'])
    base_inst=a['instances'][0];floor_y=base_inst['position'][1]
    rim_y=min(i['position'][1] for i in walls)
    inner=[float((right-left)*.4),float((back-front)*.4)];height=float((floor_y-rim_y)*.4)
    count=sum(i['type']=='stud' and left<e.world(base_inst,i)[0]<right and front<e.world(base_inst,i)[2]<back for i in e.part(base)['interfaces'])
    stud_radius=2.4;stud_h=1.6  # circumscribed dimensions of the recognized standard stud primitive
    volume=inner[0]*inner[1]*height-count*math.pi*stud_radius**2*stud_h
    capacity={'status':'pass' if volume>=550000 else 'fail','interior_mm':[*inner,height],'measured_inner_bounds_ldu':[float(left),float(right),float(front),float(back),float(floor_y),float(rim_y)],'base_stud_count':int(count),'gross_ml':inner[0]*inner[1]*height/1000,'base_studs_displacement_ml':count*math.pi*stud_radius**2*stud_h/1000,'conservative_capacity_ml':volume/1000,'target_ml':500,'required_minimum_ml':550,'fill_depth_for_500ml_mm':(500000+count*math.pi*stud_radius**2*stud_h)/(inner[0]*inner[1]),'assumption':'User-specified seamless and leak-free joins; ignores extra usable volume inside wall underside cavities','grips':'Two symmetric centered 4x8 plates on opposite Z sides, two rows seated below and capped above, two rows (16 mm) outside; cavity unobstructed; clutch/load unknown'}
    (dest/'capacity.json').write_text(json.dumps(capacity,indent=2));print(json.dumps({'instances':len(a['instances']),'geometry':report['status'],'capacity_ml':volume/1000,'grouped_steps':len(report['order']['grouped_steps'])}))
if __name__=='__main__':main()
