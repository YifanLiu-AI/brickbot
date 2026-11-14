# brickbot DSH plugin 0.2.2

Install with `npx jsr add @shiyi/brickbot`. Load `index.mjs` with a DSH `--patch` insert entry. Install [uv](https://docs.astral.sh/uv/), or set `BRICK_ENGINE_PYTHON` to a Python with brickbot 0.2.2 installed.

The plugin starts one persistent Python JSON-lines worker, loading the catalog once. Assemblies are saved under `.brickbot/` in the working directory (`BRICK_ENGINE_STATE` or plugin `stateDirectory` overrides it). Handles survive worker restarts. A plugin serializes calls; use separate state directories for independent workers.

Tools take **structured arguments**, not a JSON string:

- `lego_catalog({category?})`: list all 109 parts by category, with ID, name, local X/Z stud dimensions, body height and status.
- `lego_search({query?,limit?})`, `lego_describe({part,compact?})`: discover and inspect geometry and local connectors; describe defaults to compact.
- `lego_root({part,id?,color?})`: create an assembly and return `assembly_id`.
- `lego_get({assembly_id})`: inspect saved instances and solved poses.
- `lego_propose({assembly_id,part,target,target_stud,anchor,rotation?,id?,structure?,color?})`: preview a connector-derived pose without collision checks or mutation.
- `lego_add({...same parameters})`: solve, check collision/insertion and save one part; failure leaves the assembly unchanged.
- `lego_add_batch({assembly_id,placements:[...]})`: attach an ordered list with the same placement fields. Later entries may target earlier entries. Any failure rolls back the entire batch, returning `failed_index` (zero-based).
- `lego_validate({assembly_id})`, `lego_order({assembly_id})`: validate geometry/support and obtain build steps.
- `lego_export({assembly_id,directory?})`: require validation pass and write model MPD/LDR, scene, BOM, assembly, validation and instructions. Default: `.brickbot/exports/<assembly_id>`.

Example tool arguments:

```js
const {assembly_id} = await tools.lego_root({part: '91405', id: 'base'});
await tools.lego_add({assembly_id, part: '3001', target: 'base',
  target_stud: [0, 0], anchor: [0, 0], id: 'wall'});
await tools.lego_validate({assembly_id});
await tools.lego_export({assembly_id});
```

Grid coordinates are local `[column,row]`, before rotation, with origin at the minimum X/Z stud center and 8 mm pitch. Positive 90° about Y maps +X to -Z. Body height excludes studs. Choose verified (`pass`) parts and inspect their grid; the engine computes world poses. Geometry pass does not certify clutch force or load strength.

`BRICK_ENGINE_EVIDENCE` (or plugin `evidence`) saves load, worker-start, structured call and result events without credentials. Worker cancellation terminates the process; inspect the saved assembly with `lego_get` before retrying a mutation whose completion was interrupted. Disposal terminates the worker.

The standalone one-request CLI and Python API still accept explicit assemblies. `brickbot --serve --state-directory PATH` exposes the incremental JSON-lines API used by this plugin.
