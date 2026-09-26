"""Native PythonUI binding/lifetime smoke. Run with Mogwai --headless --script.

This checks actual rendering bounds, not mouse-driven interaction acceptance.
"""
import json
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/native-schema-observer-ui/native-python-ui-result.json'


def check_source_lifetime_contract():
    """Static regression only: Python does not expose native Texture ref counts."""
    source = (ROOT / 'Source/Falcor/Utils/UI/PythonUI.cpp').read_text(encoding='utf-8')
    body = source.split('void set_texture(ref<Texture> texture)', 1)[1].split('float2 get_size()', 1)[0]
    assert re.search(r'if\s*\(!is_tree_rendering\(\)\)\s*(?:\{\s*)?m_rendered_texture\.reset\(\)', body), (
        'Image.texture setter must release retained draw texture outside UI traversal, '
        'while preserving it inside draw callbacks')
    window = source.split('class Window :', 1)[1].split('class Group :', 1)[0]
    assert 'ImGui::SetNextWindowBgAlpha(m_background_alpha)' in window, 'Window background alpha must be applied per window'
    return {'native_texture_refcount_test': 'unavailable', 'retained_texture_release': 'static_source_regression'}


if '--source-lifetime-check' in sys.argv:
    print(json.dumps(check_source_lifetime_contract()))
    raise SystemExit(0)

import falcor


def expect_rejected(action):
    try:
        action()
    except (ValueError, RuntimeError):
        return
    raise AssertionError('Unsupported image input was accepted')


def run():
    missing = [name for name in ('Image', 'TextInput', 'open_file_dialog')
               if not hasattr(falcor.ui, name)]
    missing += ['m.' + name for name in ('screen', 'framebuffer') if not hasattr(m, name)]
    missing += ['Widget.detach'] if not hasattr(falcor.ui.Widget, 'detach') else []
    assert not missing, 'Missing native V5 APIs: ' + ', '.join(missing)
    assert callable(falcor.ui.open_file_dialog)  # Do not open a modal dialog in automation.
    assert hasattr(falcor.ui.Window, 'background_alpha'), 'Missing per-window background_alpha property'

    ui = falcor.ui
    count = len(m.screen.children)
    window = ui.Window(m.screen, 'Native PythonUI smoke', falcor.float2(10, 10), falcor.float2(460, 350))
    assert window.background_alpha == -1.0  # Existing native style remains the default.
    window.background_alpha = 0.98
    assert abs(window.background_alpha - 0.98) < 1e-6
    for alpha in (-0.5, 1.1, float('nan'), float('inf')):
        expect_rejected(lambda: setattr(window, 'background_alpha', alpha))
    changed = []
    text = ui.TextInput(window, 'Path', lambda: changed.append(True), 'initial')
    assert text.value == 'initial'
    text.value = '目录/' + 'long-path-' * 1024
    assert len(text.value) > 8192
    assert changed == []  # Programmatic setters do not masquerade as user edits.

    graph = falcor.RenderGraph('NativePythonUISmoke')
    device = graph.device
    texture = device.create_texture(width=64, height=32, format=falcor.ResourceFormat.RGBA32Float,
                                    mip_levels=1, bind_flags=falcor.ResourceBindFlags.ShaderResource)
    clicks = []
    image = ui.Image(window, texture, falcor.float2(320, 180), lambda pixel: clicks.append(pixel))
    assert image.texture is texture
    image.selection = falcor.uint2(12, 7)
    assert (image.selection.x, image.selection.y) == (12, 7)
    expect_rejected(lambda: setattr(image, 'size', falcor.float2(-1, 10)))
    expect_rejected(lambda: setattr(image, 'size', falcor.float2(float('nan'), 10)))
    for kwargs in [dict(format=falcor.ResourceFormat.R32Uint),
                   dict(format=falcor.ResourceFormat.RGBA32Float, array_size=2),
                   dict(format=falcor.ResourceFormat.RGBA32Float, depth=2)]:
        invalid = device.create_texture(width=8, height=8, mip_levels=1,
                                        bind_flags=falcor.ResourceBindFlags.ShaderResource, **kwargs)
        expect_rejected(lambda: setattr(image, 'texture', invalid))
        assert image.texture is texture  # Failed assignment preserves prior drawable state.
        before = len(window.children)
        expect_rejected(lambda: ui.Image(window, invalid))
        assert len(window.children) == before  # No dangling child on constructor failure.

    m.resizeFrameBuffer(640, 480)
    m.ui = True
    m.clock.pause()
    m.renderFrame()
    m.renderFrame()
    rect = image.rect
    assert rect.z > 0 and rect.w > 0
    assert abs(rect.z / rect.w - 2.0) < 1e-5
    assert rect.z <= 320 and rect.w <= 180
    assert m.framebuffer.width == 640 and m.framebuffer.height == 480
    window.close()
    assert not window.visible
    window.show()
    assert window.visible
    image.texture = None
    assert image.texture is None
    image.detach()
    assert image.parent is None and image not in window.children
    image.detach()  # Idempotent.
    window.detach()
    assert window.parent is None and len(m.screen.children) == count
    orphan = ui.Text(window, 'parent lifetime')
    text.detach()
    del window
    import gc
    gc.collect()
    assert orphan.parent is None
    m.renderFrame()
    assert clicks == []
    return {'status': 'passed', 'native_render_bounds': [rect.x, rect.y, rect.z, rect.w],
            'mouse_driven_acceptance': False, 'constructor_rejection_preserves_tree': True,
            'detach_and_orphan_lifetime': True,
            'per_window_background_alpha': True,
            **check_source_lifetime_contract()}


try:
    result = run()
    print('NATIVE_PYTHON_UI_PASS', flush=True)
except Exception:
    result = {'status': 'failed', 'error': traceback.format_exc()}
    print(result['error'], flush=True)
finally:
    OUT.parent.mkdir(exist_ok=True, parents=True)
    OUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    exit()
