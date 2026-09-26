"""On-demand Schema decoding of a native render graph's marked outputs."""
import json
import copy
from pathlib import Path
import threading
import numpy as np
from schema_observer_codegen import emit_observer, unpack_words, validate_region, MAX_BYTES
from schema_observer_contract_guard import ContractGuard


class SchemaObserver:
    def __init__(self, graph, artifacts, bindings=None, *, pass_name='GBuffer', producer_contract=None):
        self.graph = graph
        self._contract_guard = ContractGuard(artifacts)
        self.contract = self._contract_guard.contract
        self.artifacts = self.contract['artifacts']
        self.layout_hash = self.contract['layout_hash']
        self.pass_name = pass_name
        self.producer_contract = producer_contract
        self.owner = threading.get_ident()
        self.bindings = ({a['name']: pass_name+'.'+a['name'] for a in self.contract['schema']['attachments']}
                         if bindings is None else dict(bindings))
        names = {a['name'] for a in self.contract['schema']['attachments']}
        if set(self.bindings) != names or any(not isinstance(v, str) or not v for v in self.bindings.values()):
            raise ValueError('bindings must map every Schema attachment to an output')
        if len(set(self.bindings.values())) != len(names):
            raise ValueError('attachment bindings must be distinct')
        if producer_contract is not None and producer_contract != self.layout_hash:
            raise ValueError('External producer contract does not match Schema layout')
        self._validate_producer()
        # Registration is a setup operation, before the next graph compile/frame.
        for output in self.bindings.values():
            graph.mark_output(output)
        self.source, self.columns, self.stride = emit_observer(self.contract)
        self._program = self._buffer = None
        self._capacity = 0
        self.dispatch_count = self.readback_count = 0

    def _thread(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Schema observation must execute on its owning render thread')

    def _validate_producer(self):
        if self.producer_contract is not None:
            return  # Explicit assertion by an independently authored producer.
        if self.artifacts.definition is None:
            raise ValueError('External producer requires an explicit producer_contract layout hash')
        if any(value != self.pass_name+'.'+key for key, value in self.bindings.items()):
            raise ValueError('Remapped external outputs require an explicit producer_contract layout hash')
        props = self.graph.getPass(self.pass_name).getDictionary()
        definition = props.get('definition')
        if not definition or Path(definition).resolve() != self.artifacts.definition.resolve():
            raise ValueError('Native GBuffer producer definition no longer matches bound Schema')

    def _resources(self):
        import falcor
        self._thread()
        self._validate_producer()
        self._contract_guard.validate()
        catalog = {r['name']: r for r in json.loads(falcor.customRenderPiplineOutputCatalog(self.graph))}
        textures = {}
        dims = None
        for a in self.contract['schema']['attachments']:
            output = self.bindings[a['name']]
            record = catalog.get(output)
            if not record or record['kind'] != 'texture2D' or record.get('array_size', 1) != 1:
                raise ValueError('Schema observation requires marked non-array 2D outputs: '+output)
            if record['format'] != a['format']:
                raise ValueError('Output format does not match Schema: '+output)
            texture = self.graph.getOutput(output)
            if texture.sample_count != 1 or texture.depth != 1:
                raise ValueError('Schema observation requires single-sample 2D textures')
            dimensions = (texture.width, texture.height)
            if dims is not None and dimensions != dims:
                raise ValueError('Schema attachments have different dimensions')
            dims = dimensions
            textures[a['name']] = texture
        return textures, dims, list(catalog.values())

    def describe(self):
        _, dims, outputs = self._resources()
        return {'graph': self.graph.name, 'layout_hash': self.layout_hash, 'dimensions': list(dims),
                'fields': self.contract['schema']['fields'], 'storage': self.contract['schema']['storage'],
                'attachments': self.contract['schema']['attachments'], 'bindings': dict(self.bindings),
                'outputs': outputs, 'view': {'mip': 0, 'slice': 0, 'sample_count': 1},
                'attachment_values': 'Texture.Load values: typed integer or hardware-normalized/linear float; use read for bytes'}

    def _dispatch(self, region, fields=None, *, max_bytes=MAX_BYTES):
        import falcor
        textures, dims, _ = self._resources()
        region = validate_region(region, *dims)
        available = self.columns['fields']
        if fields is None:
            fields = list(available)
        if not isinstance(fields, (list, tuple)) or not fields or any(not isinstance(v, str) for v in fields):
            raise ValueError('fields must be a nonempty list of Schema field names')
        if len(set(fields)) != len(fields) or any(f not in available for f in fields):
            raise ValueError('Unknown or duplicate Schema field')
        count = region[2]*region[3]
        words = count*self.stride
        if type(max_bytes) is not int or max_bytes < 1 or words*4 > min(MAX_BYTES, max_bytes):
            raise ValueError('Observation exceeds GPU buffer byte limit')
        device = self.graph.device
        if self._program is None:
            self._program = falcor.ComputePass(device, string=self.source, cs_entry='main', shader_model=falcor.ShaderModel.SM6_6)
        if self._buffer is None or self._capacity != words:
            self._buffer = device.create_structured_buffer(4, words, falcor.ResourceBindFlags.UnorderedAccess)
            self._capacity = words
        self._program.globals['gWords'] = self._buffer
        self._program.globals['gRegion'] = falcor.uint4(*region)
        for i, a in enumerate(self.contract['schema']['attachments']):
            self._program.globals['gAttachment'+str(i)] = textures[a['name']]
        self._program.execute(threads_x=count)
        self.dispatch_count += 1
        return self._buffer, region, list(fields)

    def _decode(self, region, fields=None):
        buffer, region, fields = self._dispatch(region, fields)
        data = np.frombuffer(buffer.to_numpy().tobytes(), np.uint32).reshape(region[3], region[2], self.stride)
        self.readback_count += 1
        groups = unpack_words(data, self.columns)
        groups['fields'] = {f: groups['fields'][f] for f in fields}
        return {'region': list(region), 'layout_hash': self.layout_hash, **groups}

    def read_async(self, region, fields=None, *, max_bytes=64*1024*1024, strict=True):
        """Stage this decode before the scratch buffer is reused; never CPU-wait.

        Returns a native-compatible task for the shared bounded pool. Strict
        inspection rejects nonfinite fields; compare sets strict=False and
        applies its explicit mask before finiteness validation.
        """
        from observer_async import MappedReadback
        buffer, region, fields = self._dispatch(region, fields, max_bytes=max_bytes)
        task = buffer.read_async(max_bytes=max_bytes)
        self.readback_count += 1
        columns, stride, layout = copy.deepcopy(self.columns), self.stride, self.layout_hash
        def convert(raw):
            data = np.frombuffer(raw, np.uint32).reshape(region[3], region[2], stride)
            groups = unpack_words(data, columns)
            groups['fields'] = {f: groups['fields'][f] for f in fields}
            if strict:
                for name, array in groups['fields'].items():
                    if array.dtype.kind == 'f' and not np.isfinite(array).all():
                        raise ValueError('Decoder produced nonfinite field: '+name)
            return {'region': list(region), 'layout_hash': layout, **groups}
        return MappedReadback(task, convert)

    def inspect(self, region, fields=None):
        result = self._decode(region, fields)
        for name, array in result['fields'].items():
            if array.dtype.kind == 'f' and not np.isfinite(array).all():
                raise ValueError('Decoder produced nonfinite field: '+name)
        return result

    def compare(self, region, reference, rules, mask=None, fields=None):
        """Validate only mask-selected samples; inspection itself stays strict."""
        from schema_observer_compare import compare_fields
        if not isinstance(rules, dict) or not rules:
            raise ValueError('compare requires nonempty per-field rules')
        sample = self._decode(region, list(rules) if fields is None else fields)
        return compare_fields(sample['fields'], reference, rules, mask=mask)
