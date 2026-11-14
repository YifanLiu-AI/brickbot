import argparse,json,sys
from pathlib import Path
from .engine import Engine,AssemblyError
CODES={'E_INPUT':2,'E_PART':3,'E_INTERFACE':4,'E_TARGET':4,'E_TYPE':5,'E_AXIS':5,'E_ROTATION':5,'E_COLLISION':6,'E_SUPPORT':7,'E_INSERTION':8,'E_ORDER':8,'E_ID':2,'E_GROUND':7}
def dispatch(e,q,sessions=None):
    op=q.get('op');args={k:v for k,v in q.items() if k!='op'}
    if op=='catalog':return e.list_catalog(**args)
    if op=='search':return {'status':'pass','parts':e.search(**args)}
    if op=='describe':return {'status':'pass','part':e.describe(**args)}
    if sessions is not None:return sessions.dispatch(op,args)
    if op=='root':return {'status':'pass','assembly':e.root(**args)}
    if op in ('propose','add','validate','order','export'):
        result=getattr(e,op)(**args)
        if op=='add':result['assembly']=args['assembly']
        return result
    raise AssemblyError('E_INPUT','Unknown op',suggestion='Use catalog, search, describe, root, propose, add, validate, order or export')
def if_not_object(q):
    if not isinstance(q,dict):raise ValueError('JSON request must be an object')
def respond(e,raw,sessions=None):
    try:
        q=json.loads(raw,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON number: '+x)))
        if_not_object(q);result=dispatch(e,q,sessions)
        code=0 if result['status']=='pass' else 10 if result['status']=='unknown' else 6
    except AssemblyError as ex:result=ex.result();code=CODES.get(ex.code,2)
    except (ValueError,KeyError,TypeError,OSError,AttributeError,IndexError) as ex:result={'status':'fail','error':{'code':'E_INPUT','reason':str(ex)}};code=2
    return result,code
def main():
    p=argparse.ArgumentParser(epilog='describe: part, compact=true/false (auto compact above 64 interfaces). add/propose: target_stud=[column,row], anchor=[column,row], or legacy target_interface=sN, interface=aN. Grid origin: minimum local X/Z stud center; column +X, row +Z, before rotation. IDs are not grid order: s0 -> a0 can shift stacking by multiple grid cells. order returns piece steps plus grouped_steps; export uses grouped steps.',description='JSON-in / JSON-out LDraw assembly. Reads one request from stdin or --input; +Y is down, LDU=.4mm.')
    p.add_argument('--input',help='Request JSON file (default stdin)');p.add_argument('--catalog',help='Catalog data directory')
    p.add_argument('--serve',action='store_true',help='Persistent JSON-lines server using assembly_id; one response per request')
    p.add_argument('--state-directory',default='.brickbot',help='Durable assembly directory for --serve')
    a=p.parse_args()
    e=Engine(a.catalog) if a.catalog else Engine()
    if a.serve:
        from .session import Sessions
        sessions=Sessions(e,a.state_directory)
        for line in sys.stdin:
            result,_=respond(e,line,sessions)
            print(json.dumps(result,separators=(',',':')),flush=True)
        return 0
    try:
        result,code=respond(e,Path(a.input).read_text() if a.input else sys.stdin.read())
    except OSError as ex:result={'status':'fail','error':{'code':'E_INPUT','reason':str(ex)}};code=2
    print(json.dumps(result,separators=(',',':')));return code
if __name__=='__main__':sys.exit(main())
