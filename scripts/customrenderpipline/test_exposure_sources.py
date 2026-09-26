"""Verify every vendored exposure span against the installed read-only UE source."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
UE = Path('E:/ue/engine/UnrealEngine/Engine/Shaders')
OUTPUT = ROOT / 'Source/RenderPasses/customrenderpipline/Codecs/Exposure'

class ExposureSourceTests(unittest.TestCase):
    def test_original_bytes_and_required_algorithm_entries(self):
        manifest = json.loads((ROOT / 'scripts/customrenderpipline/ue_exposure_sources.json').read_bytes())
        self.assertEqual(manifest['engine_head'], '53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0')
        all_bytes = b''
        for name, item in manifest['outputs'].items():
            data = (OUTPUT / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
            expected = b''
            for span in item['segments']:
                source = (UE / span['source']).read_bytes()
                self.assertEqual(hashlib.sha256(source).hexdigest(), span['source_sha256'])
                expected += source[span['input_start']:span['input_end']]
            self.assertEqual(data, expected)
            all_bytes += data
        for entry in (b'MainAtomicCS(', b'HistogramConvertCS(', b'ComputeAverageLuminanceWithoutOutlier(',
                      b'EyeAdaptationCommon(', b'EyeAdaptationCS(', b'0xffffffff - V < OldV', b'Val *= 0.5f',
                      b'DownsampleCommon(', b'SampleInput('):
            self.assertIn(entry, all_bytes)

if __name__ == '__main__':
    unittest.main()
