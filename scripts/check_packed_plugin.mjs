import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const {apply} = await import(process.env.BRICKBOT_PLUGIN ? pathToFileURL(process.env.BRICKBOT_PLUGIN).href : '../plugin/index.mjs');
const directory = mkdtempSync(join(tmpdir(), 'brickbot-plugin-'));
const registered = new Map();
const cleanup = apply({tools: {register(tool) {registered.set(tool.name, tool);}}}, {
  python: process.env.BRICK_ENGINE_PYTHON, stateDirectory: directory, evidence: join(directory, 'events.jsonl'),
});
const call = (op, args, signal) => registered.get(`lego_${op}`).execute(args, {signal});
try {
  assert.equal(registered.size, 11);
  assert([...registered.values()].every(tool => tool.parameters.type === 'object' && !('request' in tool.parameters.properties)));
  const [catalog, described] = await Promise.all([call('catalog', {}), call('describe', {part: '3001.dat'})]);
  assert.equal(catalog.total, 109);
  assert.equal(described.part.interface_counts.stud, 8);
  const root = await call('root', {part: '91405'});
  const args = {assembly_id: root.assembly_id};
  const placement = {part: '3001', target: 'base', target_stud: [0, 0], anchor: [0, 0], id: 'brick'};
  const added = await call('add', {...args, ...placement});
  assert.equal(added.status, 'pass');
  assert.equal(added.part_count, 2);
  assert(!('assembly' in added));
  const failed = await call('add_batch', {...args, placements: [{...placement, id: 'overlap'}]});
  assert.equal(failed.status, 'fail');
  assert.equal(failed.rolled_back, true);
  assert.equal((await call('get', args)).part_count, 2);
  assert.equal((await call('validate', args)).status, 'pass');
  const exported = await call('export', {...args, directory: join(directory, 'output')});
  assert.equal(exported.validation_status, 'pass');
  const aborted = new AbortController(); aborted.abort();
  await assert.rejects(call('catalog', {}, aborted.signal), {name: 'AbortError'});
  const events = readFileSync(join(directory, 'events.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(events.filter(e => e.event === 'engine_started').length, 1);
  console.log(JSON.stringify({status: 'pass', tools: registered.size, engine_starts: 1, tested: ['structured arguments', 'concurrent calls', 'catalog', 'incremental state', 'batch rollback', 'validation', 'export', 'cancellation']}));
} finally {cleanup(); rmSync(directory, {recursive: true, force: true});}
