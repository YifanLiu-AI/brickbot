"""Regression checks for source line transforms, visibility and occlusion."""
import importlib.util
from pathlib import Path
import numpy as np
from brick_engine.geometry import LDraw
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('render_reference',ROOT/'scripts/render_reference.py')
render=importlib.util.module_from_spec(spec);spec.loader.exec_module(render)

def test_recursive_ldraw_edges(tmp_path):
    (tmp_path/'child.dat').write_text('2 24 0 0 0 1 0 0\n5 24 0 0 0 0 1 0 1 1 0 1 0 0\n')
    (tmp_path/'parent.dat').write_text('1 16 10 20 30 0 -1 0 1 0 0 0 0 1 child.dat\n')
    edges,conds=LDraw(tmp_path).edge_lines('parent.dat')
    np.testing.assert_allclose(edges,[[[10,20,30],[10,21,30]]])
    np.testing.assert_allclose(conds,[[[10,20,30],[9,20,30],[9,21,30],[10,21,30]]])

def test_conditional_projected_controls():
    assert render.conditional_visible(np.array([[0,0,0],[1,0,0],[0,1,0],[1,2,0]]))
    assert not render.conditional_visible(np.array([[0,0,0],[1,0,0],[0,1,0],[1,-2,0]]))

def test_depth_test_hides_back_edges():
    # Camera faces -Z in LDraw coordinates; a far line lies behind a near quad.
    mesh={'positions':[[-10,-10,0],[10,-10,0],[10,10,0],[-10,10,0]],
          'indices':[[0,1,2],[0,2,3]],'edges':[[[-8,0,4],[8,0,4]]],'conditional_edges':[]}
    scene={'meshes':{'test':mesh},'instances':[{'id':'a','part':'test','position':[0,0,0],'rotation':0,'color':15}]}
    hidden=np.asarray(render.Renderer(scene).render(['a'],160,160,az=-90,el=0))
    mesh['edges']=[[[-8,0,-.01],[8,0,-.01]]]
    visible=np.asarray(render.Renderer(scene).render(['a'],160,160,az=-90,el=0))
    assert np.min(hidden[79:81,50:110])>150
    assert np.min(visible[79:81,50:110])<100
