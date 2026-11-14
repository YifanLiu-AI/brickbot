#!/usr/bin/env python3
"""Run the unmodified product request on DSH / saved SJ GPT-6-Astra."""
import json
import os
import sqlite3
import subprocess
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = '用乐高零件拼装一个能一次取出 0.5 L 水的工具，暂时假定拼装后没有缝隙、不漏水。请完成最终交付件。'


def main():
    evidence = Path(os.environ.get('BRICKBOT_ACCEPTANCE_DIR', ROOT / 'evidence' / 'v0.2.2')).resolve()
    if (evidence / 'tool-events.jsonl').exists():
        raise RuntimeError('Use a fresh BRICKBOT_ACCEPTANCE_DIR; existing evidence must not be mixed with another run')
    workspace = evidence / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(f'file:{Path.home()}/.cc-switch/cc-switch.db?mode=ro', uri=True)
    matches = []
    for raw, in db.execute("select settings_config from providers where app_type='codex' and name='SJ'"):
        saved = json.loads(raw)
        cfg = tomllib.loads(saved['config'])
        if cfg.get('model') == 'gpt-6-astra':
            matches.append((saved, cfg))
    db.close()
    if len(matches) != 1:
        raise RuntimeError('Expected one authorized saved SJ GPT-6-Astra provider')
    saved, cfg = matches[0]
    provider = cfg['model_providers'][cfg['model_provider']]
    env = os.environ.copy()
    env['LEGO_SJ_API_KEY'] = saved['auth']['OPENAI_API_KEY']
    env['BRICK_ENGINE_PYTHON'] = os.environ.get('BRICK_ENGINE_PYTHON', str(ROOT.parent.parent / 'core/.venv/bin/python'))
    env['PYTHONPATH'] = os.environ.get('PYTHONPATH', str(ROOT / 'src'))
    env['DSH_TELEMETRY_DISABLED'] = '1'
    env['BRICK_ENGINE_EVIDENCE'] = str(evidence / 'tool-events.jsonl')
    settings = evidence / 'settings.json'
    settings.write_text('{}\n')
    patch = [
        {'id': 'settings', 'config': {'path': str(settings)}},
        {'id': 'llm-pi-ai', 'config': {'providers': {'ccs-sj': {
            'api': 'openai-responses', 'apiKeyEnv': 'LEGO_SJ_API_KEY', 'baseURL': provider['base_url'],
            'models': [{'id': 'gpt-6-astra', 'name': 'GPT-6-Astra', 'contextWindow': 272000, 'maxTokens': 24000}],
            'retryPolicy': {'mode': 'normal', 'maxRetries': 2}}}}},
        {'id': 'agent-default-model', 'config': {'provider': 'ccs-sj', 'model': 'gpt-6-astra'}},
        {'id': 'session-title-llm', 'disabled': True},
        {'id': 'session-persistence-jsonl', 'config': {'root': str(evidence / 'sessions')}},
        {'insert': [{'id': 'brickbot', 'name': str(ROOT / 'plugin/index.mjs')}]},
    ]
    for tool in ['tool-bash', 'tool-pwsh', 'tool-fs', 'tool-fs-search', 'tool-str-replace-editor',
                 'tool-subagent', 'tool-subagent-fork', 'tool-workflow', 'tool-ralph', 'tool-web', 'tool-jobs']:
        patch.append({'id': tool, 'disabled': True})
    patch_path = evidence / 'patch.json'
    patch_path.write_text(json.dumps(patch, indent=2))
    (evidence / 'prompt.txt').write_text(PROMPT)
    (evidence / 'model.json').write_text(json.dumps({'provider': 'ccs-sj', 'model': 'gpt-6-astra',
        'endpoint': provider['base_url'], 'wire_api': provider['wire_api'], 'plugin': 'brickbot 0.2.2',
        'credential_source': 'authorized CC Switch storage; child environment only'}, indent=2))
    start = time.monotonic()
    with (evidence / 'dsh.log').open('w') as log:
        result = subprocess.run(['/Users/a123/.hermes/node/bin/dsh', '--profile', 'headless', '--patch', str(patch_path), PROMPT],
                                cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=2400)
    events = [json.loads(line) for line in Path(env['BRICK_ENGINE_EVIDENCE']).read_text().splitlines()]
    results = [event for event in events if event['event'] == 'tool_result']
    exports = [r['result'] for r in results if r['tool'] == 'lego_export' and r['result']['status'] == 'pass']
    report = {'exit_code': result.returncode, 'seconds': round(time.monotonic() - start, 2),
              'provider': 'ccs-sj', 'model': 'gpt-6-astra', 'prompt': PROMPT,
              'calls': [{'tool': r['tool'], 'status': r['result']['status']} for r in results],
              'engine_starts': sum(e['event'] == 'engine_started' for e in events), 'exports': exports}
    if exports:
        from brick_engine import Engine
        assembly = json.loads((Path(exports[-1]['directory']) / 'assembly.json').read_text())
        validation = Engine().validate(assembly)
        report.update(part_count=len(assembly['instances']), validation_status=validation['status'])
    report['status'] = 'pass' if result.returncode == 0 and exports and report.get('validation_status') == 'pass' else 'fail'
    (evidence / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False), flush=True)
    raise SystemExit(0 if report['status'] == 'pass' else 1)


if __name__ == '__main__':
    main()
