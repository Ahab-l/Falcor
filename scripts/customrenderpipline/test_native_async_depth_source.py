import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
HEADER = ROOT / "Source/RenderPasses/customrenderpipline/CustomRenderPiplineReadback.h"
PLUGIN = ROOT / "Source/RenderPasses/customrenderpipline/CustomRenderPiplinePlugin.cpp"


class NativeAsyncDepthSourceTests(unittest.TestCase):
    def test_depth_readback_uses_one_async_plane_copy_implementation(self):
        source = HEADER.read_text(encoding="utf-8")
        self.assertIn("class DepthStencilReadbackTask", source)
        self.assertIn("readDepthStencilAsync", source)
        self.assertEqual(source.count("CopyTextureRegion("), 1)
        self.assertNotIn("DepthStencilReadback getData() const", source)
        self.assertIn("std::numeric_limits<uint64_t>::max())->getDataBlocking();", source)

    def test_both_plane_footprints_are_bounded_before_allocation(self):
        source = HEADER.read_text(encoding="utf-8")
        footprint = source.index("GetCopyableFootprints")
        budget_check = source.index("maxStagingBytes", footprint)
        first_allocation = source.index("createBuffer", budget_check)
        self.assertIn("for (uint32_t plane = 0; plane < 2; ++plane)", source[footprint - 200 : budget_check])
        self.assertLess(footprint, budget_check)
        self.assertLess(budget_check, first_allocation)

    def test_python_task_contract_is_nonblocking_and_bounded(self):
        source = PLUGIN.read_text(encoding="utf-8")
        self.assertIn('"DepthStencilReadbackTask"', source)
        self.assertIn('.def_property_readonly("ready"', source)
        self.assertIn('.def_property_readonly("staging_bytes"', source)
        self.assertIn('.def_property_readonly("byte_size"', source)
        self.assertIn('"customRenderPiplineReadDepthStencilAsync"', source)
        self.assertIn('pybind11::arg("max_bytes") = uint64_t(64 * 1024 * 1024)', source)


if __name__ == "__main__":
    unittest.main()
