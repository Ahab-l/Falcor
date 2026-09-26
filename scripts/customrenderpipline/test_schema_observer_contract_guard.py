"""Avoid regenerating verified codecs per request without weakening byte checks."""
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from generate_native_gbuffer import generate, Artifacts
try:
    from schema_observer_contract_guard import ContractGuard
except ImportError:
    ContractGuard = None
from schema_observer_codegen import load_contract


class ContractGuardTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ContractGuard, 'Verified contract byte guard missing')
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for path in (Path(__file__).parent/'examples/schema_gbuffer').iterdir():
            if path.is_file(): (self.root/path.name).write_bytes(path.read_bytes())
        self.artifacts = generate(self.root/'Schema.json', self.root/'generated')

    def test_unchanged_requests_do_not_parse_validate_or_regenerate(self):
        guard = ContractGuard(self.artifacts)
        with patch('schema_observer_contract_guard.load_contract', side_effect=AssertionError('Repeated full codec regeneration')):
            for _ in range(20): guard.validate()
        self.assertEqual(guard.contract['layout_hash'], load_contract(self.artifacts)['layout_hash'])

    def test_every_dependency_checked_even_same_size_and_mtime(self):
        guard = ContractGuard(self.artifacts)
        paths = [self.artifacts.manifest, self.artifacts.metadata, self.artifacts.codec,
                 self.artifacts.definition, self.artifacts.codec.parent/'GBuffer.3d.slang',
                 self.root/'SurfaceCodec.slangh', self.root/'Material.slangh']
        for path in paths:
            with self.subTest(file=path.name):
                data=path.read_bytes(); stat=path.stat()
                changed=bytes([data[0]^1])+data[1:]
                path.write_bytes(changed);os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
                try:
                    with self.assertRaisesRegex(ValueError,'changed|modified'): guard.validate()
                finally: path.write_bytes(data)
                guard.validate()

    def test_removal_and_recovery(self):
        guard = ContractGuard(self.artifacts)
        path=self.artifacts.codec; data=path.read_bytes(); path.unlink()
        with self.assertRaisesRegex(ValueError,'unavailable|changed'): guard.validate()
        path.write_bytes(data); guard.validate()

    def test_initially_invalid_generated_files_reject(self):
        self.artifacts.codec.write_text('// invalid',encoding='utf-8')
        with self.assertRaises(ValueError): ContractGuard(self.artifacts)

    def link_directory(self, target, alias):
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(target),str(alias))
        else: alias.symlink_to(target,target_is_directory=True)

    def test_codec_alias_retarget_with_identical_bytes_rejects(self):
        alias=self.root/'alias';clone=self.root/'clone'
        shutil.copytree(self.artifacts.codec.parent,clone)
        self.link_directory(self.artifacts.codec.parent,alias)
        self.addCleanup(lambda: os.rmdir(alias) if alias.exists() else None)
        linked=Artifacts(alias/'Codec.slangh',self.artifacts.metadata,self.artifacts.definition,self.artifacts.manifest)
        guard=ContractGuard(linked)
        os.rmdir(alias); self.link_directory(clone,alias)
        with self.assertRaises(ValueError): load_contract(linked)
        with self.assertRaisesRegex(ValueError,'changed|modified'): guard.validate()

    def test_all_artifact_paths_through_alias_still_freeze_shader_target(self):
        import json
        alias=self.root/'alias';clone=self.root/'clone'
        self.link_directory(self.artifacts.codec.parent,alias)
        self.addCleanup(lambda: os.rmdir(alias) if alias.exists() else None)
        manifest=json.loads(self.artifacts.manifest.read_text(encoding='utf-8'))
        for field in ('codec','metadata','definition'):
            manifest[field]=str(alias/Path(manifest[field]).name)
        self.artifacts.manifest.write_text(json.dumps(manifest),encoding='utf-8')
        (self.artifacts.codec.parent/self.artifacts.manifest.name).write_bytes(self.artifacts.manifest.read_bytes())
        linked=Artifacts(alias/'Codec.slangh',alias/'Metadata.json',alias/'Layout.json',alias/self.artifacts.manifest.name)
        guard=ContractGuard(linked)
        shutil.copytree(self.artifacts.codec.parent,clone)
        os.rmdir(alias);self.link_directory(clone,alias)
        self.artifacts.codec.write_text('// original resolved shader changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'changed|modified'): guard.validate()

    def test_mutation_during_binding_cannot_be_blessed_by_snapshot(self):
        calls=[]
        def concurrent_edit(artifacts):
            result=load_contract(artifacts);calls.append(True)
            if len(calls)==2: self.artifacts.codec.write_text('// raced',encoding='utf-8')
            return result
        with patch('schema_observer_contract_guard.load_contract',side_effect=concurrent_edit):
            with self.assertRaisesRegex(ValueError,'changed|modified'): ContractGuard(self.artifacts)


if __name__=='__main__': unittest.main()
