"""Guard the vendored UE source identity independently of retired generators."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PASS = ROOT / 'Source/RenderPasses/customrenderpipline'


class UESourceReuseTests(unittest.TestCase):
    def test_original_lighting_closure_bytes_are_installed(self):
        catalog = json.loads((ROOT / 'scripts/customrenderpipline/ue_lighting_sources.json').read_bytes())
        for name, item in catalog['outputs'].items():
            path = PASS / 'Codecs/Lighting' / name
            self.assertTrue(path.is_file(), 'Original UE Lighting source has not been installed: ' + name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'])

    def test_original_brdf_bytes_are_present(self):
        expected = {
            'Lighting/UEBRDF.prefix.ush': '7ddeb1bc1a0c143f754ef7019c11ba5af0250f6ad8b7161e34ee0f9e294510f7',
            'Lighting/UEPow2.scalar.ush': '1fecb8d3b05f05cb732464d87fadcd672ffc5f6adc483e86bb710f6366f1e996',
        }
        for name, checksum in expected.items():
            path = PASS / 'Codecs' / name
            self.assertTrue(path.is_file(), 'Original UE source has not been installed: ' + name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)


if __name__ == '__main__':
    unittest.main()
