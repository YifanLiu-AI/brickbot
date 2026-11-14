import argparse,json,sys
from pathlib import Path
from .engine import Engine,AssemblyError
CODES={'E_INPUT':2,'E_PART':3,'E_INTERFACE':4,'E_TARGET':4,'E_TYPE':5,'E_AXIS':5,'E_ROTATION':5,'E_COLLISION':6,'E_SUPPORT':7,'E_INSERTION':8,'E_ORDER':8,'E_ID':2,'E_GROUND':7}
def dispatch(e,q):
    op=q.get('op');args={k:v for k,v in q.items() if k!='op'}
    if op=='search':return {'status':'pass','parts':e.search(**args)}
    if op=='describe':return {'status':'pass','part':e.describe(**args)}
    if op=='root':return {'status':'pass','assembly':e.root(**args)}
    if op in ('propose','add','validate','order','export'):
        result=getattr(e,op)(**args)
        if op=='add':result['assembly']=args['assembly']
        return result
    raise AssemblyError('E_INPUT','Unknown op',suggestion='Use search, describe, root, propose, add, validate, order or export')
def if_not_object(q):
    if not isinstance(q,dict):raise ValueError('JSON request must be an object')
def main():
    p=argparse.ArgumentParser(epilog='describe: part, compact=true/false (auto compact above 64 interfaces). add/propose: target_stud=[column,row], anchor=[column,row], or legacy target_interface=sN, interface=aN. Grid origin: minimum local X/Z stud center; column +X, row +Z, before rotation. IDs are not grid order: s0 -> a0 can shift stacking by multiple grid cells. order returns piece steps plus grouped_steps; export uses grouped steps.',description='JSON-in / JSON-out LDraw assembly. Reads one request from stdin or --input; +Y is down, LDU=.4mm.')
    p.add_argument('--input',help='Request JSON file (default stdin)');p.add_argument('--catalog',help='Catalog data directory');a=p.parse_args()
    try:
        q=json.loads(Path(a.input).read_text() if a.input else sys.stdin.read(),parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON number: '+x)));if_not_object(q);e=Engine(a.catalog) if a.catalog else Engine();result=dispatch(e,q)
        code=0 if result['status']=='pass' else 10 if result['status']=='unknown' else 6
    except AssemblyError as ex:result=ex.result();code=CODES.get(ex.code,2)
    except (ValueError,KeyError,TypeError,OSError,AttributeError,IndexError) as ex:result={'status':'fail','error':{'code':'E_INPUT','reason':str(ex)}};code=2
    print(json.dumps(result,separators=(',',':')));return code
if __name__=='__main__':sys.exit(main())
