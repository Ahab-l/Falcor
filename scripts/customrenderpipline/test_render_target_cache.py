from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MESH = (ROOT / "Source/RenderPasses/customrenderpipline/CustomRenderPiplineMeshDrawPass.cpp").read_text(
    encoding="utf-8"
)
SHADER = (ROOT / "Source/RenderPasses/customrenderpipline/CustomRenderPiplineShaderPass.cpp").read_text(
    encoding="utf-8"
)


def test_mesh_cache_tracks_resource_identity_and_invalidates():
    assert "ref<Fbo> cachedFbo" in MESH
    assert "Texture*" in MESH
    assert "invalidateAttachmentCache" in MESH
    assert "p.cachedFbo = candidate" in MESH


def test_shader_cache_tracks_resource_identity_and_invalidates():
    assert "ref<Fbo> cachedFbo" in SHADER
    assert "Texture*" in SHADER
    assert "invalidateFboCache" in SHADER
    assert "p.cachedFbo = candidate" in SHADER


def test_cache_is_published_after_validation():
    for source in (MESH, SHADER):
        marker = "// Publish only after validation and attachment succeed."
        assert source.index("p.cachedFbo = candidate") > source.index(marker)
