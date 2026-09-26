"""Byte identity for the original UE planet and camera setup functions."""
import hashlib,json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'
class SkyViewSourceTests(unittest.TestCase):
    def test_exact_source_bodies_and_constants(self):
        manifest=json.loads((ROOT/'UESkyViewSetupSource.json').read_text())
        output=(ROOT/manifest['output']['path']).read_bytes()
        self.assertFalse(manifest['capture_inputs'])
        self.assertEqual(hashlib.sha256(output).hexdigest(),manifest['output']['sha256'])
        self.assertEqual(len(manifest['excerpts']),4)
        for entry in manifest['excerpts']:
            data=Path(entry['source']).read_bytes();start=entry['byte_offset']
            source=data[start:start+entry['bytes']]
            self.assertEqual(hashlib.sha256(data).hexdigest(),entry['source_sha256'])
            self.assertEqual(hashlib.sha256(source).hexdigest(),entry['excerpt_sha256'])
            self.assertEqual(data[:start].count(b'\n')+1,entry['line'])
            self.assertIn(source,output)
class SkyViewLutSourceTests(unittest.TestCase):
    def test_exact_shader_bodies_and_third_party_notice(self):
        manifest=json.loads((ROOT/'UESkyViewLutSource.json').read_text())
        self.assertIs(manifest['capture_inputs'],False)
        for output in manifest['outputs']:
            self.assertEqual(hashlib.sha256((ROOT/output['path']).read_bytes()).hexdigest(),output['sha256'])
        for entry in manifest['excerpts']:
            source=Path(entry['source']).read_bytes();start=entry['byte_offset']
            chunk=source[start:start+entry['bytes']]
            self.assertEqual(hashlib.sha256(source).hexdigest(),entry['source_sha256'])
            self.assertEqual(hashlib.sha256(chunk).hexdigest(),entry['excerpt_sha256'])
            self.assertEqual(source[:start].count(b'\n')+1,entry['line'])
            self.assertIn(chunk,(ROOT/entry['output']).read_bytes())
        text=(ROOT/'UESkyViewHelpers.ush').read_text()
        self.assertIn('return GetSkyViewLutReferential(View.SkyViewLutReferential);',text)
        self.assertNotIn('SkyAtmosphereRealTimeReflectionLUTParameters',text)
        self.assertIn('The MIT License',(ROOT/'UESkyViewThirdPartyNotice.txt').read_text())

if __name__=='__main__':unittest.main()
