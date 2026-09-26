"""The sun adapter must retain exact UE bodies, not rewritten copies."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2] / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'


class SunSetupSourceTests(unittest.TestCase):
    def test_source_excerpts_are_exact_original_bytes(self):
        manifest = json.loads((ROOT / 'UESunSetupSource.json').read_text())
        output = (ROOT / manifest['output']['path']).read_bytes()
        self.assertEqual(hashlib.sha256(output).hexdigest(), manifest['output']['sha256'])
        self.assertIs(manifest['capture_inputs'], False)
        for item in manifest['excerpts']:
            source = Path(item['source']).read_bytes()
            self.assertEqual(hashlib.sha256(source).hexdigest(), item['source_sha256'])
            begin = item['byte_offset']
            excerpt = source[begin:begin + item['bytes']]
            self.assertEqual(source[:begin].count(b'\n') + 1, item['line'])
            self.assertEqual(hashlib.sha256(excerpt).hexdigest(), item['excerpt_sha256'])
            self.assertIn(excerpt, output)


if __name__ == '__main__':
    unittest.main()
