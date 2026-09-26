import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeCompletionCleanupTests(unittest.TestCase):
    def test_cmake_slang_explicit_relative_includes_resolve(self):
        root = ROOT / "Source/RenderPasses/customrenderpipline"
        cmake = (root / "CMakeLists.txt").read_text(encoding="utf-8")
        sources = cmake.split("target_sources(customrenderpipline PRIVATE", 1)[1].split(")", 1)[0]
        pending = [root / item for item in re.findall(r"^\s*([^\s#]+\.(?:slang|slangh))\s*$", sources, re.M)]
        visited = set()
        while pending:
            source = pending.pop().resolve()
            if source in visited:
                continue
            visited.add(source)
            self.assertTrue(source.is_file(), str(source))
            for included in re.findall(r'^\s*#include\s+"([^"]+)"', source.read_text(encoding="utf-8"), re.M):
                dependency = (source.parent / included).resolve()
                if included.startswith(".") or dependency.is_file():
                    with self.subTest(source=str(source.relative_to(ROOT)), included=included):
                        self.assertTrue(dependency.is_file(), f"Published shader includes removed source: {included}")
                    if dependency.is_file():
                        pending.append(dependency)

    def test_retired_compatibility_and_graph_sealing_are_absent(self):
        source_roots = [ROOT / "Source" / "Falcor", ROOT / "Source" / "RenderPasses" / "customrenderpipline"]
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for root in source_roots
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".h", ".cpp"}
        )
        for retired in (
            "PassCompatibility",
            "MeshPassCompatibility",
            "setExecutionValidator",
            "validateExecution",
            "hasExternalInputs",
            "sealGraphContract",
            "requireDeclaredGraphInputs",
        ):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, text)

    def test_unreferenced_legacy_lighting_config_and_contract_are_archived(self):
        for retired in (
            "Source/RenderPasses/customrenderpipline/Extensions/UEReference/UEReferenceLightingConfig.h",
            "Source/RenderPasses/customrenderpipline/Extensions/UEReference/UEReferenceLightingConfig.cpp",
            "Source/Tools/FalcorTest/Tests/Core/UEReferenceLightingConfig.cpp",
        ):
            with self.subTest(path=retired):
                self.assertFalse((ROOT / retired).exists())

    def test_native_framework_surfaces_remain(self):
        graph = (ROOT / "Source/Falcor/RenderGraph/RenderGraph.h").read_text(encoding="utf-8")
        mesh = (ROOT / "Source/RenderPasses/customrenderpipline/CustomRenderPiplineMeshDrawPass.cpp").read_text(encoding="utf-8")
        for retained in ("getTopology", "getDevice", "execute", "setInput"):
            with self.subTest(retained=retained):
                self.assertIn(retained, graph)
        self.assertIn("createRasterDrawList", mesh)
        self.assertIn("CustomRenderPiplineReadback.h", (ROOT / "Source/RenderPasses/customrenderpipline/CMakeLists.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
