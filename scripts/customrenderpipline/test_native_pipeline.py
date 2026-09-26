"""CPU contract tests: real loading/validation, with only Falcor's GPU boundary recorded."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from unittest.mock import patch

import pipeline


class RecordingGraph:
    def __init__(self, name):
        self.name = name
        self.passes, self.edges, self.outputs = {}, [], []

    def addPass(self, render_pass, name):
        self.passes[name] = render_pass

    def addEdge(self, source, target):
        self.edges.append([source, target])

    def markOutput(self, output):
        self.outputs.append(output)


class NativePipelineTests(unittest.TestCase):
    def setUp(self):
        self.created = []
        native = types.ModuleType('falcor')
        native.RenderGraph = self.new_graph
        native.createPass = lambda kind, properties: (kind, copy.deepcopy(properties))
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'falcor': native}).start()

    def new_graph(self, name):
        graph = RecordingGraph(name)
        self.created.append(graph)
        return graph

    def make_graph(self, definition, **kwargs):
        self.assertTrue(callable(getattr(pipeline, 'make_graph', None)),
                        'pipeline.make_graph must expose native RenderGraph assembly')
        return pipeline.make_graph('Native graph', definition, **kwargs)

    @staticmethod
    def declaration():
        return {'version': 1, 'nodes': [{'name': 'A', 'type': 'StockPass'},
                                        {'name': 'B', 'type': 'PluginPass'}],
                'edges': [['A.color', 'B.input']], 'outputs': ['B.color']}

    def test_stock_and_custom_passes_compose_as_an_ordinary_mutable_graph(self):
        definition = self.declaration()
        props = {'shader': {'file': 'Tint.cs.slang', 'entry': 'main'},
                 'resources': [{'name': 'color', 'direction': 'output', 'format': 'RGBA32Float'}],
                 'dispatch': [8, 8, 1], 'execution': 'every_frame',
                 'uniforms': {'gain': {'type': 'float', 'value': 2}}, 'samplers': {}}
        definition['nodes'][1].update(type='CustomRenderPiplineComputePass', properties=props)
        definition['metadata'] = {'description': 'No Schema, Scene or transaction'}
        original = copy.deepcopy(definition)
        graph = self.make_graph(definition, base_directory=Path.cwd())
        self.assertIs(graph, self.created[0])
        self.assertEqual(graph.name, 'Native graph')
        self.assertEqual(list(graph.passes), ['A', 'B'])
        self.assertEqual(graph.passes['A'], ('StockPass', {}))
        self.assertEqual(graph.passes['B'], ('CustomRenderPiplineComputePass', {
            **props, 'shader': {**props['shader'], 'file': str(Path.cwd() / 'Tint.cs.slang')}}))
        self.assertEqual(graph.edges, definition['edges'])
        self.assertEqual(graph.outputs, definition['outputs'])
        graph.addPass(('LaterPass', {}), 'Later')
        graph.addEdge('B.color', 'Later.input')
        graph.markOutput('Later.output')
        self.assertIn('Later', graph.passes)
        self.assertEqual(definition, original)

    def test_graph_json_paths_resolve_relative_to_the_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_path = root / 'graph.json'
            definition = {'version': 1, 'nodes': [{'name': 'Load', 'type': 'CustomAssetPass',
                'properties': {'shader': {'file': 'effect.slang'}, 'asset': {'source': 'data.bin'}},
                'file_inputs': ['asset.source', 'shader.file']}], 'outputs': ['Load.color']}
            graph_path.write_text(json.dumps(definition), encoding='utf-8')
            graph = self.make_graph(graph_path, base_directory=root / 'irrelevant')
            props = graph.passes['Load'][1]
            self.assertEqual(props['shader']['file'], str(root / 'effect.slang'))
            self.assertEqual(props['asset']['source'], str(root / 'data.bin'))

    def test_reusable_pass_paths_follow_the_origin_of_each_overridden_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'effects').mkdir()
            description = {'version': 1, 'metadata': {'label': 'Tint'},
                'type': 'CustomRenderPiplineFullscreenPass',
                'properties': {'shader': {'file': 'Tint.slang', 'ps': 'main'},
                    'asset': {'source': 'palette.bin'}, 'state': {'depthTest': False}},
                'file_inputs': ['asset.source']}
            (root / 'effects/Tint.json').write_text(json.dumps(description), encoding='utf-8')
            definition = {'version': 1, 'nodes': [
                {'name': 'A', 'description': 'effects/Tint.json'},
                {'name': 'B', 'description': 'effects/Tint.json',
                 'properties': {'shader': {'file': 'Other.slang'}, 'state': {'depthWrite': False},
                                'otherAsset': 'other.bin'}, 'file_inputs': ['otherAsset']}],
                'edges': [['A', 'B']], 'outputs': ['B.color']}
            graph = self.make_graph(definition, base_directory=root)
            a, b = graph.passes['A'][1], graph.passes['B'][1]
            self.assertEqual(a['shader']['file'], str(root / 'effects/Tint.slang'))
            self.assertEqual(b['shader'], {'file': str(root / 'Other.slang'), 'ps': 'main'})
            self.assertEqual(b['asset']['source'], str(root / 'effects/palette.bin'))
            self.assertEqual(b['otherAsset'], str(root / 'other.bin'))
            self.assertEqual(b['state'], {'depthTest': False, 'depthWrite': False})
            self.assertEqual(a['state'], {'depthTest': False})

    def test_mesh_description_passes_native_scene_selection_and_explicit_view_binding(self):
        props = {'instanceIDs': [0, 2], 'shader': {'file': 'Mesh.slang', 'vs': 'vs', 'ps': 'ps'},
                 'colorTargets': [{'name': 'color', 'format': 'RGBA32Float'}],
                 'depthTarget': {'name': 'depth', 'format': 'D32Float'}, 'resources': [],
                 'uniforms': {}, 'samplers': {}, 'state': {}, 'viewport': [0, 0, 32, 32],
                 'view_projection_binding': 'Params.viewProj', 'view_projection': list(range(16))}
        graph = self.make_graph({'version': 1, 'nodes': [{'name': 'Mesh',
            'type': 'CustomRenderPiplineMeshDrawPass', 'properties': props}]})
        self.assertEqual(graph.passes['Mesh'][1], {**props, 'shader': {
            **props['shader'], 'file': str(Path.cwd() / 'Mesh.slang')}})

    def reject(self, definition, message):
        with self.assertRaisesRegex(ValueError, message):
            self.make_graph(definition)
        self.assertEqual(self.created, [], 'validate the complete declaration before creating a graph')

    def test_unknown_and_missing_graph_and_node_keys_have_clear_errors(self):
        for field in ('version', 'nodes'):
            definition = self.declaration()
            del definition[field]
            with self.subTest(missing=field):
                self.reject(definition, 'missing.*' + field)
        for value in (0, 2, True, '1'):
            with self.subTest(version=value):
                self.reject({**self.declaration(), 'version': value}, 'version.*1')
        self.reject({**self.declaration(), 'unexpected': 1}, 'unknown.*unexpected')
        self.reject({**self.declaration(), 'metadata': 'implicit'}, 'metadata.*object')
        self.reject({**self.declaration(), 'nodes': []}, 'nonempty')
        for bad, message in (({'name': 'A', 'type': 'X', 'extra': 1}, 'unknown.*extra'),
                             ({'name': 'A'}, 'missing.*type'),
                             ({'type': 'X'}, 'missing.*name'),
                             ({'name': 'A', 'type': 'X', 'properties': []}, 'properties.*object')):
            with self.subTest(node=bad):
                self.reject({'version': 1, 'nodes': [bad]}, message)

    def test_duplicate_and_malformed_identifiers_are_rejected(self):
        definition = self.declaration()
        definition['nodes'][1]['name'] = 'A'
        self.reject(definition, 'duplicate node.*A')
        for key in ('name', 'type'):
            for value in ('', 'A.B', 'with space', '1First', '$packed', None):
                definition = self.declaration()
                definition['nodes'][0][key] = value
                with self.subTest(key=key, value=value):
                    self.reject(definition, 'identifier')

    def test_missing_and_malformed_endpoints_are_rejected(self):
        for edges, outputs, message in (
            ([['Missing.out', 'B.input']], [], 'unknown node Missing'),
            ([], ['Missing.out'], 'unknown node Missing'),
            ([['A.', 'B.input']], [], 'port.*identifier'),
            ([['A.out', 'B.']], [], 'port.*identifier'),
            ([], ['B.'], 'port.*identifier'),
            ([], ['B'], 'output.*port'),
            ([['A.out', 'B']], [], 'mix execution and resource'),
            ([['A.out.more', 'B.input']], [], 'port.*identifier'),
            ([['A.out']], [], 'two endpoints'),
            ([['A.out', 'A.input']], [], 'self edge'),
            ([], ['B.color', 'B.color'], 'duplicate output'),
        ):
            with self.subTest(edges=edges, outputs=outputs):
                self.reject({**self.declaration(), 'edges': edges, 'outputs': outputs}, message)

    def test_duplicate_targets_and_cycles_are_rejected(self):
        for edges, message in (([['A.x', 'B.input'], ['A.y', 'B.input']], 'duplicate destination'),
                               ([['A', 'B'], ['A', 'B']], 'duplicate edge'),
                               ([['A', 'B'], ['B', 'A']], 'cycle')):
            with self.subTest(edges=edges):
                self.reject({**self.declaration(), 'edges': edges}, message)

    def test_execution_fanin_and_resource_fanout_are_not_duplicate_targets(self):
        definition = self.declaration()
        definition['nodes'].append({'name': 'C', 'type': 'AnyPass'})
        definition['edges'] = [['A', 'C'], ['B', 'C'], ['A.color', 'B.input'], ['A.color', 'C.input']]
        self.assertEqual(self.make_graph(definition).edges, definition['edges'])

    def test_schema_macros_and_pipeline_inheritance_fail_instead_of_loading_legacy(self):
        for key, value in (('edges', [['A.$packed', 'B.$packed']]),
                           ('outputs', ['B.$field:normal'])):
            self.reject({**self.declaration(), key: value}, 'legacy Schema')
        for props in ({'resources': [{'schema': '$packed', 'direction': 'input'}]},
                      {'colorTargets': ['$packed']}, {'schemaPath': 'Schema.json'},
                      {'sceneDefinition': 'Scene.json'}, {'pipelinePath': 'Pipeline.json'}):
            definition = self.declaration()
            definition['nodes'][0]['properties'] = props
            with self.subTest(properties=props):
                self.reject(definition, 'legacy')
        definition = self.declaration()
        definition['nodes'][0]['inherit_pipeline'] = True
        self.reject(definition, 'inherit_pipeline.*false')
        definition['nodes'][0]['inherit_pipeline'] = False
        self.assertEqual(self.make_graph(definition).passes['A'], ('StockPass', {}))

    def test_file_inputs_and_non_json_values_fail_before_native_creation(self):
        for props, files, message in (({}, ['missing'], 'cannot resolve'),
            ({'asset': ''}, ['asset'], 'nonempty string'),
            ({'asset': 'a'}, ['asset', 'asset'], 'duplicate file_inputs'),
            ({'asset': 'a'}, 'asset', 'file_inputs.*array'),
            ({'shader': {'file': 3}}, [], 'nonempty string'),
            ({'gain': float('nan')}, [], 'finite'), ({'gain': object()}, [], 'JSON')):
            definition = {'version': 1, 'nodes': [{'name': 'A', 'type': 'X',
                          'properties': props, 'file_inputs': files}]}
            with self.subTest(props=props, files=files):
                self.reject(definition, message)

    def test_circular_or_nonstring_keyed_definitions_are_rejected_without_recursion_errors(self):
        cyclic = self.declaration()
        cyclic['metadata'] = cyclic
        self.reject(cyclic, 'circular')
        self.reject({**self.declaration(), 3: 'not JSON'}, 'string keys')

    def test_reusable_descriptions_validate_their_own_keys_version_and_inheritance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            definition = {'version': 1, 'nodes': [{'name': 'A', 'description': str(root / 'Pass.json')}]}
            for description, message in (({'type': 'X', 'extra': 1}, 'unknown.*extra'),
                ({'type': 'X', 'version': 2}, 'version.*1'),
                ({'type': 'X', 'metadata': []}, 'metadata.*object'),
                ({'type': 'X', 'inherit_pipeline': True}, 'inherit_pipeline.*false')):
                (root / 'Pass.json').write_text(json.dumps(description), encoding='utf-8')
                with self.subTest(description=description):
                    self.reject(definition, message)
            (root / 'Pass.json').write_text(json.dumps({'type': 'AnyStockPass'}), encoding='utf-8')
            self.assertEqual(self.make_graph(definition).passes['A'], ('AnyStockPass', {}))

    def test_native_import_and_assembly_work_when_all_legacy_modules_are_blocked(self):
        script = textwrap.dedent('''
            import importlib.abc, sys, types
            blocked = ('generate_schema', 'pipeline_snapshot', 'pass_definition', 'history_state',
                       'resource_snapshot', 'scene_package', 'extensions', 'Config')
            class BlockLegacy(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if any(part in blocked for part in fullname.split('.')):
                        raise AssertionError('legacy import: ' + fullname)
            sys.meta_path.insert(0, BlockLegacy())
            import pipeline
            assert 'SchemaPipeline' not in vars(pipeline)
            class Graph:
                def __init__(self, name): self.calls = []
                def addPass(self, value, name): self.calls.append(('pass', name, value))
                def addEdge(self, source, target): self.calls.append(('edge', source, target))
                def markOutput(self, output): self.calls.append(('output', output))
            falcor = types.ModuleType('falcor')
            falcor.RenderGraph = Graph
            falcor.createPass = lambda kind, properties: (kind, properties)
            sys.modules['falcor'] = falcor
            assert callable(getattr(pipeline, 'make_graph', None)), 'native API missing'
            graph = pipeline.make_graph('native', {'version': 1, 'nodes': [
                {'name': 'Stock', 'type': 'GBufferRaster'},
                {'name': 'Custom', 'type': 'CustomRenderPiplineComputePass', 'properties': {
                    'shader': {'file': 'Effect.slang'}, 'resources': []}}],
                'edges': [['Stock.normW', 'Custom.input']], 'outputs': ['Custom.color']})
            assert len(graph.calls) == 4
            assert not any(part in blocked for name in sys.modules for part in name.split('.'))
        ''')
        module_path = Path(__file__).resolve().parent
        for module, pythonpath in (('pipeline', module_path), ('customrenderpipline.pipeline', module_path.parent)):
            with self.subTest(module=module):
                source = script.replace('import pipeline\n', f'import {module} as pipeline\n')
                environment = dict(os.environ, PYTHONPATH=str(pythonpath))
                result = subprocess.run([sys.executable, '-c', source], env=environment,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_history_binding_happens_after_nodes_edges_and_outputs(self):
        calls = []
        def bind(graph):
            self.assertEqual(len(graph.passes), 2)
            self.assertEqual(graph.edges, [['Read', 'Write']])
            self.assertEqual(graph.outputs, ['Write.status'])
            calls.append(graph)
        sys.modules['falcor'].customRenderPiplineBindHistory = bind
        definition = {'version': 1, 'nodes': [
            {'name': 'Read', 'type': 'CustomRenderPiplineHistoryReadPass'},
            {'name': 'Write', 'type': 'CustomRenderPiplineHistoryWritePass'}],
            'edges': [['Read', 'Write']], 'outputs': ['Write.status']}
        graph = self.make_graph(definition)
        self.assertEqual(calls, [graph])


if __name__ == '__main__':
    unittest.main()
