import {spawn} from 'node:child_process';
import {appendFileSync} from 'node:fs';
import {createInterface} from 'node:readline';
import {resolve} from 'node:path';

export const name = 'brickbot';
export const inject = ['tools'];
const string = (description, required = false) => ({type: 'string', description, required});
const grid = description => ({type: 'array', items: {type: 'integer'}, required: true, description});
// register() takes JSON Schema, not defineTool's parameter DSL.
const objectSchema = fields => ({
  type: 'object', additionalProperties: false,
  properties: Object.fromEntries(Object.entries(fields).map(([key, {required, ...schema}]) => [key, schema])),
  required: Object.keys(fields).filter(key => fields[key].required),
});
const assembly = {assembly_id: string('Assembly handle returned by lego_root. State is saved by the engine; never send the whole assembly.', true)};
const placement = {
  part: string('Catalog part ID.', true),
  target: string('Existing instance ID to attach onto (including an earlier placement in this batch).', true),
  target_stud: grid('Verified stud [column,row] on target, in its local grid before rotation.'),
  anchor: grid('Verified bottom receiver [column,row] on the new part, before rotation. Grid origin is minimum local X/Z stud center.'),
  rotation: {type: 'integer', description: 'Quarter turn about Y: 0 (default), 90, 180 or 270. Positive 90 maps local +X to world -Z.'},
  id: string('Unique instance name; omitted means auto-generated.'),
  structure: string('Human-readable role such as wall or handle.'),
  color: {type: 'integer', description: 'LDraw color code; default 4.'},
};
const definitions = {
  catalog: ['Start here: list ALL available parts grouped by category, with IDs, names, local X/Z stud size, body height and pass/unknown status. No keywords needed.', {category: string('Optional Brick, Plate, Tile or Baseplate; omit to list everything.')}],
  search: ['Optional substring search of the catalog by name or ID. Use lego_catalog to browse without guessing keywords.', {query: string('Name or part ID substring.'), limit: {type: 'integer', description: 'Maximum matches, default 30.'}}],
  describe: ['Inspect a chosen part: dimensions, verified local connector grid and rules. 8 mm stud pitch, +Y down, 1 LDU=0.4 mm. Use pass parts. Compact by default.', {part: string('Catalog part ID.', true), compact: {type: 'boolean', description: 'Default true; false includes all geometry and individual interface evidence.'}}],
  root: ['Start a new assembly with a grounded part. Returns assembly_id and root instance; all following operations use that handle.', {part: string('Verified base part ID.', true), id: string('Root instance ID, default base.'), color: {type: 'integer'}}],
  get: ['Inspect saved assembly instances and solved poses. Use after an interruption or to plan the next attachment.', assembly],
  propose: ['Preview a connector-derived rigid pose without adding it. Does not validate collision or support; lego_add performs checks.', {...assembly, ...placement}],
  add: ['Attach one part by local connectors. The engine solves its pose, checks solid collision and vertical insertion, discovers support connections, and saves only on success. Failure leaves state unchanged.', {...assembly, ...placement}],
  add_batch: ['Attach a list of parts in order, e.g. one wall course. Each placement uses existing or earlier batch instance IDs and local connectors, never world coordinates. Checks every part; ANY failure rolls back the entire batch. failed_index is zero-based.', {...assembly, placements: {type: 'array', required: true, items: objectSchema(placement), description: 'Nonempty ordered list of connector placements.'}}],
  validate: ['Validate saved geometry, connections, collision, support and build order. Pass is geometry only; load/clutch strength remains unknown. Returns compact counts and issues.', assembly],
  order: ['Get per-part dependencies and grouped assembly steps for the saved model.', assembly],
  export: ['Validate and deliver the model, BOM, instructions, steps, scene and validation files. Requires geometry pass. Returns absolute output directory. Default output is .brickbot/exports/<assembly_id>.', {...assembly, directory: string('Optional output directory.')}],
};

export function apply(ctx, config = {}) {
  const python = config.python || process.env.BRICK_ENGINE_PYTHON;
  const command = python ? [python, '-m', 'brick_engine'] : ['uvx', 'git+https://github.com/YifanLiu-AI/brickbot@v0.2.2'];
  command.push('--serve', '--state-directory', resolve(config.stateDirectory || process.env.BRICK_ENGINE_STATE || '.brickbot'));
  const evidence = config.evidence || process.env.BRICK_ENGINE_EVIDENCE;
  const record = value => {if (evidence) appendFileSync(evidence, JSON.stringify({time: new Date().toISOString(), ...value}) + '\n');};
  let worker, pending, queue = Promise.resolve(), disposed = false;
  const refs = (child, method) => {child[method](); for (const pipe of [child.stdin, child.stdout, child.stderr]) pipe[method]?.();};
  const stop = () => {if (worker) {const child = worker; worker = undefined; child.kill();}};
  const cleanup = () => {disposed = true; stop(); process.off('exit', stop);};
  process.once('exit', stop);
  ctx.on?.('dispose', cleanup);
  function start() {
    if (worker) return worker;
    const child = spawn(command[0], command.slice(1), {stdio: ['pipe', 'pipe', 'pipe'], env: process.env});
    worker = child;
    let stderr = '';
    child.stderr.on('data', data => {stderr = (stderr + data).slice(-800);});
    const lines = createInterface({input: child.stdout});
    lines.on('line', line => {
      if (pending?.child !== child) return;
      try {pending.finish(null, JSON.parse(line));}
      catch (error) {pending?.finish(error); stop();}
    });
    const failed = error => {
      if (worker === child) worker = undefined;
      if (pending?.child === child) pending.finish(error);
    };
    child.on('error', failed);
    child.stdin.on('error', failed);
    child.on('close', code => {lines.close(); failed(new Error(`brickbot engine exited (${code}): ${stderr}`));});
    record({event: 'engine_started', pid: child.pid});
    return child;
  }
  function request(body, signal) {
    return new Promise((resolveRequest, reject) => {
      if (disposed) return reject(new Error('brickbot plugin disposed'));
      if (signal?.aborted) return reject(signal.reason || new DOMException('Aborted', 'AbortError'));
      const child = start(); refs(child, 'ref');
      const abort = () => {finish(signal.reason || new DOMException('Aborted', 'AbortError')); stop();};
      function finish(error, value) {
        signal?.removeEventListener('abort', abort);
        pending = undefined;
        refs(child, 'unref');
        if (error) reject(error); else resolveRequest(value);
      }
      pending = {child, finish};
      signal?.addEventListener('abort', abort, {once: true});
      child.stdin.write(JSON.stringify(body) + '\n');
    });
  }
  for (const [op, [description, parameters]] of Object.entries(definitions)) {
    ctx.tools.register({
      name: `lego_${op}`, description, parameters: objectSchema(parameters),
      output: {schema: {type: 'object', additionalProperties: true, properties: {}}, render: (_args, value) => [{type: 'text', text: JSON.stringify(value)}]},
      async execute(args, exec = {}) {
        const body = {...(op === 'describe' ? {compact: true} : {}), ...args, op};
        const run = async () => {
          record({event: 'tool_called', tool: `lego_${op}`, request: body, callId: exec.callId});
          let result;
          try {result = await request(body, exec.signal);}
          catch (error) {
            if (exec.signal?.aborted) throw error;
            result = {status: 'fail', error: {code: 'E_ENGINE', reason: error.message, hint: 'Install uv or set BRICK_ENGINE_PYTHON to a Python with brickbot 0.2.2 installed. Saved assembly_id handles survive engine restarts.'}};
          }
          record({event: 'tool_result', tool: `lego_${op}`, callId: exec.callId, result});
          return result;
        };
        const result = queue.then(run);
        queue = result.catch(() => {});
        return result;
      },
    });
  }
  record({event: 'plugin_loaded', plugin: name, version: '0.2.2', registered_tools: Object.keys(definitions).length});
  return cleanup;
}
