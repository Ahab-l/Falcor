"""CPU contracts for the bounded DefaultLit/Unlit sky contribution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

import numpy as np
from test_sky_light_capture import scene_fixture

ROOT = Path(__file__).resolve().parents[2]


def schema_fixture():
    schema = json.loads((ROOT/'Source/RenderPasses/customrenderpipline/Schemas/OpaqueModels.json').read_text())
    names = {'DefaultLit', 'Unlit'}
    schema['models'] = [m for m in schema['models'] if m['name'] in names]
    schema['codecs'] = {k: v for k,v in schema['codecs'].items() if k in names}
    for c in schema['consumers'].values():
        if 'required_fields_by_model' in c:
            c['required_fields_by_model'] = {k:v for k,v in c['required_fields_by_model'].items() if k in names}
    return schema


class SkyLightLightingTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('sky_light_lighting'), 'SkyLight consumer is missing')
        import sky_light_lighting
        return sky_light_lighting



    def test_wrappers_preserve_unlit_alpha_and_original_source_blocks(self):
        module = self.module()
        source = module.SHADER.read_text()
        self.assertIn('initial.a', source)
        self.assertIn('position.w <= 0', source)
        self.assertIn('surface.modelID != DefaultLitModel', source)
        self.assertNotIn('EnvBRDFApprox', source)
        self.assertNotIn('gMinRoughness', source)
        manifest = json.loads(module.SHADER.with_name('LightingSource.json').read_text())
        for excerpt in manifest['excerpts']:
            source_bytes = Path(excerpt['source']).read_bytes()
            expected = source_bytes[excerpt['byte_offset']:excerpt['byte_offset']+excerpt['bytes']]
            actual = module.SHADER.with_name(excerpt['output']).read_bytes()
            actual = actual[excerpt['output_byte_offset']:excerpt['output_byte_offset']+excerpt['bytes']]
            self.assertEqual(actual, expected)
            self.assertEqual(hashlib.sha256(expected).hexdigest(), excerpt['excerpt_sha256'])

    def test_cpu_reference_preserves_alpha_unlit_and_exposure_scales_both_contributions(self):
        module = self.module()
        self.assertTrue(hasattr(module, 'evaluate_sky_reference'), 'Independent consumer oracle is missing')
        sh = np.zeros((8,4)); sh[:3,3] = [1,2,3]
        kw = dict(base_color=[.4,.5,.6], metallic=0., specular=.5, roughness=.5,
                  normal=[0,0,1], view=[0,0,1], sh=sh, reflected=[2,3,4], ab=[.6,.02],
                  sky_color=[2,1,.5], ao=.5, screen_ao=.7, pre_exposure=1.)
        diffuse, specular = module.evaluate_sky_reference(**kw)
        np.testing.assert_allclose(diffuse, np.array([.4,.5,.6])*[1,2,3]*[2,1,.5]*.5)
        visibility = np.clip((1+.5*.7)**.25-1+.5*.7,0,1)
        np.testing.assert_allclose(specular, np.array([2,3,4])*[2,1,.5]*visibility*(.04*.6+.02))
        twice = module.evaluate_sky_reference(**dict(kw, pre_exposure=2.))
        np.testing.assert_allclose(twice, np.array([diffuse,specular])*2)
        self.assertTrue(np.all(np.array(module.evaluate_sky_reference(**dict(kw, metallic=1.)))[0] == 0))






if __name__ == '__main__':
    unittest.main()
