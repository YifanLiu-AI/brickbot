"""Durable assemblies for incremental tool calls; one server serializes mutations."""
import json
import re
import uuid
from pathlib import Path
from .engine import AssemblyError


class Sessions:
    def __init__(self, engine, directory):
        self.engine = engine
        self.directory = Path(directory)

    def path(self, assembly_id):
        if not isinstance(assembly_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', assembly_id):
            raise AssemblyError('E_SESSION', 'Invalid assembly_id')
        return self.directory / (assembly_id + '.json')

    def load(self, assembly_id):
        path = self.path(assembly_id)
        if not path.exists():
            raise AssemblyError('E_SESSION', 'Assembly not found', suggestion='Use lego_root to create an assembly; reuse its assembly_id')
        return json.loads(path.read_text())

    def save(self, assembly_id, assembly):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path(assembly_id)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(assembly, separators=(',', ':')))
        temp.replace(path)

    @staticmethod
    def summary(assembly_id, assembly):
        return dict(assembly_id=assembly_id, part_count=len(assembly['instances']))

    @staticmethod
    def added(result):
        connections = result['connections']
        return dict(instance=result['instance'], connection_count=len(connections),
                    supported_by=sorted({c['lower'] for c in connections}))

    def dispatch(self, op, args):
        e = self.engine
        args = dict(args)
        if op == 'root':
            assembly = e.root(**args)
            status = e.part(assembly['instances'][0]['part'])['validation']['status']
            if status != 'pass':
                return dict(status=status, reason='Root geometry/interfaces not fully verified')
            assembly_id = uuid.uuid4().hex
            self.save(assembly_id, assembly)
            return dict(status='pass', **self.summary(assembly_id, assembly), instance=assembly['instances'][0])
        assembly_id = args.pop('assembly_id')
        assembly = self.load(assembly_id)
        summary = self.summary(assembly_id, assembly)
        if op == 'get':
            return dict(status='pass', **summary, instances=assembly['instances'])
        if op == 'add_batch':
            placements = args.pop('placements')
            if args or not isinstance(placements, list) or not placements:
                raise AssemblyError('E_INPUT', 'Provide a nonempty placements array')
            results = []
            for index, placement in enumerate(placements):
                try:
                    result = e.add(assembly, **placement)
                except AssemblyError as ex:
                    result = ex.result()
                if result['status'] != 'pass':
                    return dict(result, **summary, failed_index=index, rolled_back=True)
                results.append(self.added(result))
            self.save(assembly_id, assembly)
            return dict(status='pass', **self.summary(assembly_id, assembly), added=results)
        if op == 'add':
            result = e.add(assembly, **args)
            if result['status'] != 'pass':
                return dict(result, **summary)
            self.save(assembly_id, assembly)
            return dict(status='pass', **self.summary(assembly_id, assembly), **self.added(result))
        if op == 'validate':
            result = e.validate(assembly)
            return dict(status=result['status'], **summary, geometry=result['geometry'],
                        connection_count=len(result['connections']),
                        degrees_of_freedom={k:v for k,v in result['degrees_of_freedom'].items() if v['remaining']},
                        load_capacity=result['load_capacity'], watertightness=result['watertightness'],
                        grouped_step_count=len(result['order']['grouped_steps']) if result['order'] else None)
        if op == 'export':
            validation = e.validate(assembly)
            if validation['status'] != 'pass':
                return dict(status=validation['status'], **summary, geometry=validation['geometry'],
                            reason='Export requires a passing assembly')
            args['directory'] = str(Path(args.get('directory') or self.directory / 'exports' / assembly_id).resolve())
            result = e.export(assembly, **args)
            return dict(result, **summary, validation_status=validation['status'])
        if op in ('propose', 'order'):
            return dict(getattr(e, op)(assembly, **args), **summary)
        raise AssemblyError('E_INPUT', 'Unknown session operation')
