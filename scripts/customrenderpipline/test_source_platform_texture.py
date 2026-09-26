"""Offline BC1 platform-export contract, independent of captured textures."""
import copy
import hashlib
import struct
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from source_platform_texture import validate_export, make_dds
import source_platform_texture as platform


class PlatformTextureTests(unittest.TestCase):
    def test_native_options_default_strict_sampling_and_owned_path(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(platform.native_options(root, {}), (None, 1, []))
        for text in ('true', '8.0', '0', '17', '-1', ' 8'):
            with self.assertRaises(ValueError):
                platform.native_options(root, {'CRP_TARGETMAP_GRID_ANISOTROPY':text})
        with patch.object(platform, 'load_verified_export') as load:
            with self.assertRaises(ValueError):
                platform.native_options(root, {'CRP_TARGETMAP_SOURCE_PLATFORM_RUN':str(root/'build/targetmap-shading-a1/reference')})
            load.assert_not_called()
            run = root/'build/source-platform-texture/export-fixture'
            load.return_value=({'capture_inputs':False}, ['identities'])
            self.assertEqual(platform.native_options(root, {'CRP_TARGETMAP_SOURCE_PLATFORM_RUN':str(run),
                'CRP_TARGETMAP_GRID_ANISOTROPY':'8'}), ({'capture_inputs':False}, 8, ['identities']))
            load.assert_called_once_with(run)

    def fixture(self):
        sizes = [max(1, (max(1, 512 >> i)+3)//4)**2*8 for i in range(10)]
        payload = bytes((i*13+7) & 255 for i in range(sum(sizes)))
        mips = []
        offset = 0
        for level, size in enumerate(sizes):
            mips.append({'level': level, 'width': max(1,512 >> level), 'height': max(1,512 >> level),
                         'bytes': size, 'offset': offset})
            offset += size
        return {'status':'passed', 'source_object':'/Engine/OpenWorldTemplate/LandscapeMaterial/T_GridChecker_A.T_GridChecker_A',
                'capture_inputs':False, 'format':'BC1UnormSrgb', 'srgb':True, 'width':512, 'height':512,
                'payload':'platform-mips.bin', 'mips':mips}, payload

    def test_full_mip_chain_and_payload_preserved(self):
        metadata, raw = self.fixture()
        self.assertEqual(len(raw), 174776)
        validate_export(metadata, raw)
        dds = make_dds(metadata, raw)
        self.assertEqual(dds[:4], b'DDS ')
        self.assertEqual(dds[148:], raw)
        self.assertEqual(struct.unpack_from('<5I', dds, 128), (72,3,0,1,0))
        self.assertEqual(struct.unpack_from('<I', dds, 28)[0], 10)
        self.assertEqual(struct.unpack_from('<II', dds, 12), (512,512))

    def test_wrong_format_or_provenance_rejected(self):
        metadata, raw = self.fixture()
        for key,value in [('format','BGRA8UnormSrgb'),('srgb',False),('capture_inputs',True),('width',256),('status','failed')]:
            bad = dict(metadata, **{key:value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_export(bad, raw)

    def test_missing_or_bad_mip_geometry_rejected(self):
        metadata, raw = self.fixture()
        for field,value in [('bytes',7),('offset',3),('level',2),('width',16)]:
            bad=copy.deepcopy(metadata);bad['mips'][9][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_export(bad,raw)
        with self.assertRaises(ValueError):
            validate_export(dict(metadata,mips=metadata['mips'][:-1]),raw)
        with self.assertRaises(ValueError):
            validate_export(metadata,raw[:-1])

    def test_verified_export_requires_matching_bytes_protection_and_provenance(self):
        metadata, raw = self.fixture()
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); out = run/'Export'; out.mkdir()
            paths = [out/'result.json', out/'platform-mips.bin', out/'T_GridChecker_A.bc1.srgb.dds']
            for path, data in zip(paths, (json.dumps(metadata).encode(), raw, make_dds(metadata, raw))):
                path.write_bytes(data)
            def ident(path):
                data=path.read_bytes()
                return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            source = run/'original.fixture'; source.write_bytes(b'original-source')
            protected = [ident(source)]
            (run/'prepared.json').write_text(json.dumps({'protected':protected, 'capture_inputs':False, 'original_project_launched':False}))
            protection=run/'protected-after-fixture.json'
            protection.write_text(json.dumps({'unchanged':True, 'files':protected}))
            record = dict(status='passed', capture_inputs=False, original_project_launched=False,
                          protected_unchanged=True, protected=protected, protection_report=str(protection),
                          metadata=ident(paths[0]),payload=ident(paths[1]),texture=ident(paths[2]),
                          receipts=[{'exit_code':0}])
            receipt=run/'source-platform-result.json'; receipt.write_text(json.dumps(record))
            asset, identities = platform.load_verified_export(run)
            self.assertEqual(asset['mip_count'], 10)
            self.assertEqual(asset['format'], 'BC1UnormSrgb')
            self.assertEqual(asset['file'], str(paths[2]))
            self.assertTrue(any(e['path']==str(source) for e in identities))
            for key, value in [('capture_inputs',True),('protected_unchanged',False),('status','failed')]:
                receipt.write_text(json.dumps(dict(record, **{key:value})))
                with self.assertRaises(ValueError):
                    platform.load_verified_export(run)
            receipt.write_text(json.dumps(record))
            paths[2].write_bytes(make_dds(metadata, raw)[:-1]+b'!')
            with self.assertRaises(ValueError):
                platform.load_verified_export(run)


if __name__ == '__main__':
    unittest.main()
