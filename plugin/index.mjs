import {spawn} from 'node:child_process';
import {appendFileSync} from 'node:fs';
export const name='ldraw-brick-engine';
export const inject=['tools'];
export function apply(ctx, config={}) {
  const python=config.python||process.env.BRICK_ENGINE_PYTHON;
  const cmd=python?[python,'-m','brick_engine']:['uvx','--from','git+https://github.com/YifanLiu-AI/ldraw-brick-engine@v0.2.0','brick-engine'];
  const evidence=config.evidence||process.env.BRICK_ENGINE_EVIDENCE;
  const record=o=>{if(evidence)appendFileSync(evidence,JSON.stringify({time:new Date().toISOString(),...o})+'\n')};
  for(const op of ['search','describe','root','propose','add','validate','order','export']) {
    ctx.tools.register({name:`lego_${op}`,description:`LDraw geometry assembly ${op}. JSON request fields: search(query,limit), describe(part,compact), root(part,id), propose/add(assembly,part,target,target_stud:[column,row],anchor:[column,row],rotation,id,structure,color), validate/order(assembly), export(assembly,directory). +Y down. Local grid origin minimum X/Z stud center; column +X, row +Z before rotation. Legacy target_interface=sN/interface=aN also supported but matching IDs can be offset. describe defaults compact for large parts. Use search/describe before choosing interfaces. Returns pass/fail/unknown.`,parameters:{request:{type:'string',required:true,description:'JSON object of operation arguments; omit op. Assembly is returned by root/add; pass it back unchanged.'}},output:{schema:{type:'object',additionalProperties:true,properties:{}},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},async execute(args,exec){
      let request; try {request={...JSON.parse(args.request),op}} catch {return {status:'fail',error:'Invalid request JSON'}}
      record({event:'tool_called',tool:`lego_${op}`,request,callId:exec?.id});
      const result=await new Promise((resolve,reject)=>{const child=spawn(cmd[0],cmd.slice(1),{stdio:['pipe','pipe','pipe'],env:process.env,signal:exec.signal});let out='',err='';child.stdout.on('data',x=>out+=x);child.stderr.on('data',x=>err+=x);child.on('error',e=>resolve({code:127,out:'',err:String(e)}));child.on('close',code=>resolve({code,out,err}));child.stdin.end(JSON.stringify(request));});
      let parsed;try{parsed=JSON.parse(result.out)}catch{parsed={status:'fail',error:{code:'E_ENGINE',reason:(result.err||'no output').slice(-800),hint:'Install uv (https://docs.astral.sh/uv/) or set BRICK_ENGINE_PYTHON to a python with ldraw-brick-engine installed'}}}
      record({event:'tool_result',tool:`lego_${op}`,code:result.code,result:parsed});
      return parsed;
    }});
  }
  record({event:'plugin_loaded',plugin:name,registered_tools:8});
}
