#!/usr/bin/env python3
"""Orthographic, depth-tested LDraw faces/edges; all brick geometry from scene.json."""
import json
import re
import sys
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from brick_engine.engine import rotation
BG = 249

def colors():
    result = {}
    for line in (ROOT/'src/brick_engine/data/ldraw/LDConfig.ldr').read_text().splitlines():
        m = re.search(r'CODE\s+(\d+)\s+VALUE\s+#([\dA-Fa-f]{6})\s+EDGE\s+#([\dA-Fa-f]{6})', line)
        if m:
            result[int(m[1])] = tuple(np.array([int(h[k:k+2],16) for k in (0,2,4)]) for h in (m[2],m[3]))
    return result

def conditional_visible(points):
    """LDraw type 5: projected controls must lie on the same side of AB.

    Only AB is drawn; control points never become line endpoints.
    Official specification: LDraw File Format, Line Type 5.
    """
    a,b,c,d = points[:,:2]
    cross = lambda p: (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    return cross(c)*cross(d) >= 0

def clip_polygon(tri):
    out=[]
    for a,b in zip(tri,np.roll(tri,-1,axis=0)):
        ina,inb=a[1]>=0,b[1]>=0
        if ina: out.append(a)
        if ina != inb: out.append(a+(b-a)*(-a[1]/(b[1]-a[1])))
    return [np.array([out[0],out[k],out[k+1]]) for k in range(1,len(out)-1)]

def font(size):
    return ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',size)

def caption(im, text, size=28, extra=70):
    out=Image.new('RGB',(im.width,im.height+extra),(BG,)*3);out.paste(im)
    ImageDraw.Draw(out).text((24,im.height+18),text,font=font(size),fill='#28323a')
    return out

class Renderer:
    def __init__(self,scene):
        self.scene=scene;self.palette=colors();self.items={}
        for inst in scene['instances']:
            mesh=scene['meshes'][inst['part']]
            def transform(v):
                p=np.asarray(v)@rotation(inst['rotation']).T+inst['position']
                return p[...,[0,2,1]]*np.array([.4,.4,-.4])
            self.items[inst['id']] = (inst,transform(mesh['positions'])[np.asarray(mesh['indices'])],
                transform(np.asarray(mesh['edges']).reshape(-1,2,3)),
                transform(np.asarray(mesh['conditional_edges']).reshape(-1,4,3)))

    def render(self,ids,width,height,az=-52,el=28,new=None,cut=False,fit=None,water=None):
        az,el=np.deg2rad([az,el]);view=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
        right=np.array([-np.sin(az),np.cos(az),0]);camera=np.stack([right,np.cross(view,right),view])
        bounds=np.concatenate([self.items[i][1].reshape(-1,3) for i in (fit or list(self.items))])@camera.T
        low,high=bounds.min(axis=0),bounds.max(axis=0)
        scale=min((width-64)/(high[0]-low[0]),(height-64)/(high[1]-low[1]));center=(low+high)/2
        def project(p):
            q=p@camera.T;q[...,0]=(q[...,0]-center[0])*scale+width/2;q[...,1]=height/2-(q[...,1]-center[1])*scale
            return q
        depth=np.full((height,width),-np.inf);pixels=np.full((height,width,3),BG,dtype=np.uint8)
        def face(t,color,alpha=1):
            xmin=max(0,int(np.floor(t[:,0].min())));xmax=min(width-1,int(np.ceil(t[:,0].max())))
            ymin=max(0,int(np.floor(t[:,1].min())));ymax=min(height-1,int(np.ceil(t[:,1].max())))
            if xmin>xmax or ymin>ymax:return
            x0,y0,z0=t[0];x1,y1,z1=t[1];x2,y2,z2=t[2];den=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
            if abs(den)<1e-8:return
            yy,xx=np.mgrid[ymin:ymax+1,xmin:xmax+1];xx=xx+.5;yy=yy+.5
            a=((y1-y2)*(xx-x2)+(x2-x1)*(yy-y2))/den;b=((y2-y0)*(xx-x2)+(x0-x2)*(yy-y2))/den;c=1-a-b
            z=a*z0+b*z1+c*z2;region=depth[ymin:ymax+1,xmin:xmax+1];mask=(a>=0)&(b>=0)&(c>=0)&(z>region)
            target=pixels[ymin:ymax+1,xmin:xmax+1]
            target[mask]=np.clip(alpha*color+(1-alpha)*target[mask],0,255).astype(np.uint8)
            if alpha==1:region[mask]=z[mask]
        for id in ids:
            inst,tris,edges,conds=self.items[id];base=self.palette[inst['color']][0]
            if cut:tris=np.asarray([t for tri in tris for t in clip_polygon(tri)]).reshape(-1,3,3)
            normal=np.cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0]);normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-9)
            shade=.78+.16*np.abs(normal@np.array([-.35,-.45,.82]))+.06*np.abs(normal@view)
            for t,k in zip(project(tris),shade):
                color=base*k
                if new is not None and id not in new:color=color*.20+BG*.80
                face(t,color)
        # Overlay only after every opaque face has contributed to the depth buffer.
        def line(segment,color):
            a,b=segment.copy()
            if cut:
                if a[1]<0 and b[1]<0:return
                if (a[1]<0)!=(b[1]<0):
                    hit=a+(b-a)*(-a[1]/(b[1]-a[1]))
                    if a[1]<0:a=hit
                    else:b=hit
            p,q=project(np.array([a,b]));length=np.linalg.norm(q[:2]-p[:2])
            samples=p+(q-p)*np.linspace(0,1,max(2,int(length*2)+1))[:,None]
            radius=max(.6,width/1800)
            # Subpixel depth tolerance is in screen pixels, not an object-wide bias.
            tolerance=.85/scale
            for dx in range(-int(np.ceil(radius)),int(np.ceil(radius))+1):
                for dy in range(-int(np.ceil(radius)),int(np.ceil(radius))+1):
                    x=np.floor(samples[:,0]+dx).astype(int);y=np.floor(samples[:,1]+dy).astype(int)
                    valid=(x>=0)&(x<width)&(y>=0)&(y<height)
                    x,y,z=x[valid],y[valid],samples[valid,2]
                    distance=np.abs((x+.5-p[0])*(q[1]-p[1])-(y+.5-p[1])*(q[0]-p[0]))/max(length,1e-9)
                    visible=(distance<=radius)&(z>=depth[y,x]-tolerance)
                    pixels[y[visible],x[visible]]=color
        for id in ids:
            inst,tris,edges,conds=self.items[id];edge=self.palette[inst['color']][1]
            if new is not None and id not in new:edge=edge*.22+BG*.78
            for segment in edges:line(segment,edge)
            for points in conds:
                if conditional_visible(project(points)):line(points[:2],edge)
        if water:
            left,right,front,back,floor,rim=water['measured_inner_bounds_ldu']
            z=-floor*.4+water['fill_depth_for_500ml_mm'];y0=max(0,front*.4) if cut else front*.4
            quad=np.array([[left*.4,y0,z],[right*.4,y0,z],[right*.4,back*.4,z],[left*.4,back*.4,z]])
            for t in (quad[[0,1,2]],quad[[0,2,3]]):face(project(t),np.array([77,165,194]),.48)
            for a,b in zip(quad,np.roll(quad,-1,axis=0)):line(np.array([a,b]),[54,126,150])
        return Image.fromarray(pixels)

def main():
    dest=ROOT/'reference/water-tool';scene=json.loads((dest/'scene.json').read_text());r=Renderer(scene);ids=list(r.items)
    capacity=json.loads((dest/'capacity.json').read_text())
    for name,az,el in [('finished',-52,28),('front',-90,0),('top-45',-45,45),('bottom',-90,-90)]:
        r.render(ids,2640,2160,az,el).save(dest/f'{name}.png');print(name,flush=True)
    caption(r.render(ids,2640,2070,cut=True,water=capacity),f"剖视 · 500 mL 水位 · 水深 {capacity['fill_depth_for_500ml_mm']:.1f} mm",42,90).save(dest/'cutaway.png')
    (dest/'steps').mkdir(exist_ok=True);(dest/'step-parts').mkdir(exist_ok=True)
    sheet=Image.new('RGB',(1920,3*590),(BG,)*3);assembled=[]
    for n,step in enumerate(scene['steps'],1):
        assembled.extend(step['add']);counts=Counter(r.items[i][0]['part'] for i in step['add'])
        label=f"第 {n} 步 · 新增 {step['count']} 件 · "+'、'.join(f'{p}×{k}' for p,k in counts.items())
        tile=caption(r.render(assembled,1280,1020,new=set(step['add'])),label,34,90)
        tile.save(dest/'steps'/f'{n:03}.png');sheet.paste(tile.resize((640,550),Image.Resampling.LANCZOS),(((n-1)%3)*640,((n-1)//3)*590))
        variants=Counter((r.items[i][0]['part'],r.items[i][0]['color']) for i in step['add'])
        parts=Image.new('RGB',(max(1,len(variants))*320,330),(BG,)*3)
        ImageDraw.Draw(parts).text((18,10),f'第 {n} 步 · 本步所需零件',font=font(24),fill='#28323a')
        for j,((part,color),count) in enumerate(variants.items()):
            inst={'id':'icon','part':part,'color':color,'rotation':0,'position':[0,0,0]}
            icon=Renderer({'meshes':scene['meshes'],'instances':[inst]}).render(['icon'],320,220)
            parts.paste(icon,(j*320,48));ImageDraw.Draw(parts).text((j*320+20,280),f'{part} × {count}  /  色号 {color}',font=font(20),fill='#28323a')
        parts.save(dest/'step-parts'/f'{n:03}.png');print(label,flush=True)
    sheet.save(dest/'steps-contact-sheet.png')
    (dest/'render-metadata.json').write_text(json.dumps({'geometry':'scene.json triangles, type 2 and conditional type 5 lines','palette_source':'bundled official LDConfig.ldr','water_depth_mm':capacity['fill_depth_for_500ml_mm'],'views':['finished','front','top-45','bottom','cutaway'],'step_images':9,'parts_lists':9},indent=2))
if __name__=='__main__':main()
