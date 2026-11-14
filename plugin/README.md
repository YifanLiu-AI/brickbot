# brickbot DSH plugin

`npx jsr add @shiyi/brickbot`

Registers `lego_search`, `lego_describe`, `lego_root`, `lego_propose`, `lego_add`, `lego_validate`, `lego_order`, `lego_export` with real Cordis `ctx.tools.register`.

Python engine: runs via `uvx` from github.com/YifanLiu-AI/brickbot automatically (install uv), or set BRICK_ENGINE_PYTHON to a python with brickbot installed. Load with a dsh `--patch` insert entry naming this package's index.mjs. Every tool takes a `request` JSON string with operation arguments, matching the Python CLI. BRICK_ENGINE_EVIDENCE optionally saves load/call/result events (no credentials).
