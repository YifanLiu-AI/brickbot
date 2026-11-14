# DSH plugin

Registers `lego_search`, `lego_describe`, `lego_root`, `lego_propose`, `lego_add`, `lego_validate`, `lego_order`, `lego_export` with real Cordis `ctx.tools.register`.

Install the Python wheel into a venv, set BRICK_ENGINE_PYTHON to that venv's python. Load the package with an absolute path in a dsh `--patch` insert entry. Every tool takes a `request` JSON string with operation arguments, matching the Python CLI. BRICK_ENGINE_EVIDENCE optionally saves load/call/result events (no credentials).
