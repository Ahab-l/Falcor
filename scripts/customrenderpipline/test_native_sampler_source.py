"""CPU-only routing checks. Native descriptor behavior lives in FalcorTest."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PASS_DIR = ROOT / "Source/RenderPasses/customrenderpipline"


class NativeSamplerSourceTests(unittest.TestCase):
    def test_descriptor_parser_preserves_json_type_and_validates_before_conversion(self):
        source = (PASS_DIR / "CustomRenderPiplineShaderBindings.h").read_text(encoding="utf-8")
        match = re.search(r"inline Sampler::Desc samplerDesc\(const Json& value\)\s*\{(.*?)\n\}", source, re.S)
        self.assertIsNotNone(match, "One shared no-Device sampler descriptor parser is required")
        body = match.group(1)
        self.assertIn('keys(value, {"filter", "address", "max_anisotropy"}', body)
        self.assertIn('value.value("max_anisotropy", Json(1))', body)
        self.assertIn("anisotropy.is_number_integer() && anisotropy >= 1 && anisotropy <= 16", body)
        self.assertLess(body.index("FALCOR_CHECK"), body.index("anisotropy.get<uint32_t>()"))
        self.assertIn('std::string("Linear")', body)
        self.assertIn('std::string("Clamp")', body)
        self.assertIn("setMaxAnisotropy(anisotropy.get<uint32_t>())", body)
        self.assertNotIn("createSampler", body)

    def test_both_existing_executors_use_shared_parser_and_keep_binding_checks(self):
        for name, unique_check in (
            ("MeshDraw", "claimBinding(name)"),
            ("Shader", 'bindings.insert(name).second'),
        ):
            with self.subTest(executor=name):
                source = (PASS_DIR / f"CustomRenderPipline{name}Pass.cpp").read_text(encoding="utf-8")
                sampler_begin = source.index("const auto samplers =")
                body = source[sampler_begin:source.index("\n    }", sampler_begin)]
                self.assertIn(unique_check, body)
                self.assertRegex(body, r"createSampler\((?:CustomRenderPipline::ShaderBindings::)?samplerDesc\(value\)\)")
                self.assertNotIn("stringToEnum<TextureFilteringMode>", body)
                self.assertIn("ShaderBindings::sampler(p.root(), name, p.samplers[name])" if name == "Shader" else "sampler(root,name,value)", source)

    def test_real_cpu_tests_are_registered_without_gpu_setup(self):
        path = ROOT / "Source/Tools/FalcorTest/Tests/Core/CustomRenderPiplineSampler.cpp"
        self.assertTrue(path.is_file())
        source = path.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("CPU_TEST("), 4)
        self.assertIn("samplerDesc", source)
        self.assertNotIn("GPU_TEST(", source)
        self.assertNotIn("createSampler(", source)
        cmake = (ROOT / "Source/Tools/FalcorTest/CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("Tests/Core/CustomRenderPiplineSampler.cpp", cmake)


if __name__ == "__main__":
    unittest.main()
