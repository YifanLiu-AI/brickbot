import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from brick_engine import Engine, AssemblyError
from brick_engine.session import Sessions
from brick_engine.cli import respond


@pytest.fixture
def sessions(tmp_path):
    return Sessions(Engine(), tmp_path)


def placement(**overrides):
    return dict(part='3001', target='base', target_stud=[0, 0], anchor=[0, 0], id='brick', **overrides)


def test_catalog_all_and_categories(sessions):
    result = sessions.engine.list_catalog()
    assert result['total'] == 109
    assert sessions.engine.list_catalog(' ')['total'] == 109
    assert {k: len(v) for k, v in result['categories'].items()} == dict(Brick=38, Plate=34, Tile=21, Baseplate=16)
    assert sessions.engine.list_catalog('plate')['total'] == 34
    brick = next(p for p in result['categories']['Brick'] if p['id'] == '3001')
    assert brick['size_studs'] == [4, 2] and brick['body_height_mm'] == 9.6
    with pytest.raises(AssemblyError):
        sessions.engine.list_catalog('not-a-category')


def test_saved_state_survives_restart_and_failure(sessions):
    root = sessions.dispatch('root', dict(part='91405'))
    handle = root['assembly_id']
    added = sessions.dispatch('add', dict(assembly_id=handle, **placement()))
    assert added['part_count'] == 2 and added['connection_count'] == 8
    assert 'assembly' not in added and 'connections' not in added
    restarted = Sessions(sessions.engine, sessions.directory)
    with pytest.raises(AssemblyError, match='intersects'):
        restarted.dispatch('add', dict(assembly_id=handle, **(placement() | {'id': 'collision'})))
    assert restarted.dispatch('get', dict(assembly_id=handle))['part_count'] == 2
    assert restarted.dispatch('validate', dict(assembly_id=handle))['status'] == 'pass'


def test_batch_rollback_and_in_batch_targets(sessions):
    handle = sessions.dispatch('root', dict(part='91405'))['assembly_id']
    result = sessions.dispatch('add_batch', dict(assembly_id=handle, placements=[placement(), placement() | {'id': 'overlap'}]))
    assert result['status'] == 'fail' and result['rolled_back'] and result['failed_index'] == 1
    assert sessions.load(handle)['instances'][0]['id'] == 'base'
    assert len(sessions.load(handle)['instances']) == 1
    result = sessions.dispatch('add_batch', dict(assembly_id=handle, placements=[placement(), placement() | {'target': 'brick', 'id': 'top'}]))
    assert result['status'] == 'pass' and result['part_count'] == 3
    assert result['added'][1]['supported_by'] == ['brick']


def test_unknown_root_and_invalid_handle(sessions):
    assert sessions.dispatch('root', dict(part='3067a'))['status'] == 'unknown'
    assert not list(sessions.directory.glob('*.json'))
    with pytest.raises(AssemblyError):
        sessions.load('../outside')


def test_export_has_validated_artifacts(sessions, tmp_path):
    handle = sessions.dispatch('root', dict(part='3001'))['assembly_id']
    result = sessions.dispatch('export', dict(assembly_id=handle, directory=str(tmp_path / 'output')))
    assert result['validation_status'] == 'pass'
    assert json.loads((tmp_path / 'output/validation.json').read_text())['status'] == 'pass'


def test_server_recovers_from_bad_request(tmp_path):
    process = subprocess.Popen([sys.executable, '-m', 'brick_engine', '--serve', '--state-directory', str(tmp_path)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               env=os.environ | {'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')})
    def call(raw):
        process.stdin.write(raw + '\n'); process.stdin.flush()
        return json.loads(process.stdout.readline())
    try:
        assert call('{invalid')['status'] == 'fail'
        root = call(json.dumps(dict(op='root', part='3001')))
        handle = root['assembly_id']
        assert call(json.dumps(dict(op='get', assembly_id=handle)))['part_count'] == 1
        assert call(json.dumps(dict(op='validate', assembly_id=handle)))['status'] == 'pass'
    finally:
        process.stdin.close(); process.wait(timeout=10)
    assert process.returncode == 0 and process.stderr.read() == ''


def test_invalid_batch_never_commits(sessions):
    handle = sessions.dispatch('root', dict(part='3001'))['assembly_id']
    result, _ = respond(sessions.engine, json.dumps(dict(op='add_batch', assembly_id=handle, placements=[placement(), {}])), sessions)
    assert result['status'] == 'fail'
    assert len(sessions.load(handle)['instances']) == 1
