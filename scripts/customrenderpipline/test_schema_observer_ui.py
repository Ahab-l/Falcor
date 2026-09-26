"""Panel wiring tests with only the unavailable native widget boundary replaced."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_schema_observer_ui_model import Service, Preview


class Widget:
    def __init__(self, parent=None, **kwargs):
        self.parent, self.children, self.visible = parent, [], True
        if parent is not None:
            parent.children.append(self)
        self.callback = self.change_callback = self.click_callback = None
        self.texture = None
        self.value = 0
        self.__dict__.update(kwargs)

    def detach(self):
        if self.parent is not None:
            self.parent.children.remove(self)
        self.parent = None

    def show(self): self.visible = True
    def close(self): self.visible = False


def vector(*values):
    return SimpleNamespace(**dict(zip('xyzw', values)))


class PanelTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('schema_observer_ui'), 'V5 panel is missing')
        self.service = Service()
        self.service.observer = SimpleNamespace(
            _thread=lambda: None,
            graph=SimpleNamespace(name='Graph'), layout_hash='abc',
            contract={'schema': {'fields': [{'name':'id','type':'uint'}, {'name':'normal','type':'float3'}],
                                 'attachments': [{'name':'bits','format':'R32Uint'}]}},
            bindings={'bits':'GBuffer.bits'})
        self.listeners = {}
        self.service.add_frame_listener = lambda fn, **kwargs: self.listeners.setdefault('token', fn) and 'token'
        self.service.remove_frame_listener = lambda token: self.listeners.pop(token, None)
        ui = SimpleNamespace(**{name: Widget for name in (
            'Window','Group','Text','Button','Combobox','DragInt','DragInt4','DragFloat','TextInput','Image')})
        ui.open_file_dialog = lambda: 'chosen.npz'
        self.api = SimpleNamespace(ui=ui, float2=vector, uint2=vector, int4=vector)
        self.preview = Preview()
        from schema_observer_ui import SchemaInspectorPanel
        with patch.dict(sys.modules, falcor=self.api):
            self.panel = SchemaInspectorPanel(SimpleNamespace(screen=Widget()), self.service, preview=self.preview)

    def tearDown(self):
        if hasattr(self, 'panel'): self.panel.close()

    def frame(self): self.listeners['token']()

    def test_controls_queue_work_until_frame_boundary(self):
        self.panel.buttons['inspect'].callback()
        self.assertFalse(self.service.calls)
        self.frame()
        self.assertEqual(self.service.calls[-1]['operation'], 'inspect')
        self.assertIn('4294967295', self.panel.results.text)

    def test_pick_uses_displayed_source_and_texels(self):
        self.panel.buttons['refresh'].callback(); self.frame()
        self.panel.image.click_callback(vector(3, 2))
        self.assertEqual(len(self.preview.calls), 1)
        self.frame()
        self.assertEqual(self.service.calls[-1]['arguments']['region'], [3,2,1,1])
        self.assertEqual(self.panel.region.value.x, 3)

    def test_hidden_cancels_and_show_restores(self):
        self.panel.buttons['inspect'].callback()
        self.panel.controls.close(); self.frame()
        self.assertFalse(self.service.calls)
        self.assertFalse(self.panel.model.actions)
        self.panel.show()
        self.assertTrue(self.panel.controls.visible and self.panel.viewer.visible)

    def test_close_button_defers_native_tree_mutation(self):
        self.panel.buttons['close'].callback()
        self.assertIsNotNone(self.panel.controls.parent)
        self.frame()
        self.assertTrue(self.panel.model.closed)
        self.assertFalse(self.listeners)
        self.assertIsNone(self.panel.controls.parent)
        self.assertTrue(all(button.callback is None for button in self.panel.buttons.values()))
        self.assertIsNone(self.panel.image.click_callback)
        self.assertFalse(self.service.closed)

    def test_source_rule_and_dialog_controls(self):
        self.assertEqual(self.panel.source.items, ['field:id','field:normal','attachment:bits'])
        self.panel.field.value = 1
        self.panel.field.change_callback()
        self.assertEqual(self.panel.rule.items, ['numeric','angle'])
        self.panel.buttons['reference'].callback()
        self.assertEqual(self.panel.reference.value, '')
        self.frame()
        self.assertEqual(self.panel.reference.value, 'chosen.npz')

    def test_dialog_cancel_preserves_existing_value(self):
        self.panel.reference.value = 'existing.npz'
        self.api.ui.open_file_dialog = lambda: ''
        self.panel.buttons['reference'].callback()
        self.frame()
        self.assertEqual(self.panel.reference.value, 'existing.npz')

    def test_dialog_error_is_visible_and_future_dialog_action_still_works(self):
        calls = iter((RuntimeError('picker unavailable'), 'recovered.npz'))
        def choose():
            result = next(calls)
            if isinstance(result, Exception):
                raise result
            return result
        self.api.ui.open_file_dialog = choose

        self.panel.buttons['reference'].callback()
        self.frame()
        self.assertEqual(self.panel.reference.value, '')
        self.assertEqual(self.panel.status.text, 'ERROR: picker unavailable')
        self.assertIn('token', self.listeners)

        self.panel.buttons['reference'].callback()
        self.frame()
        self.assertEqual(self.panel.reference.value, 'recovered.npz')

    def test_live_reopen_control_defers_rebuild_and_reuses_service(self):
        import native_schema_observer_ui_live as live
        screen = self.panel.controls.parent
        with patch.dict(sys.modules, falcor=self.api):
            controls = live.LiveInspectorControls(SimpleNamespace(screen=screen), self.service, self.panel)
            self.assertFalse(controls.window.visible)
            old_panel = self.panel
            self.panel.close()
            controls.tick()
            self.assertTrue(controls.window.visible)
            self.assertFalse(self.service.closed)
            controls.button.callback()
            self.assertIs(controls.panel, old_panel, 'Native draw callback must not rebuild the tree')
            controls.tick()
            self.panel = controls.panel
            self.assertIsNot(self.panel, old_panel)
            self.assertIs(self.panel.service, self.service)
            self.assertEqual(controls.generation, 1)
            self.assertFalse(controls.window.visible)
            self.assertFalse(self.panel.model.actions, 'Reopening should not secretly submit GPU work')
            self.assertEqual(len(screen.children), 3)
            controls.close()
            self.assertIsNone(controls.button.callback)
            self.assertFalse(screen.children)
            self.assertFalse(self.service.closed)

    def test_live_reopen_control_reports_failure_and_can_retry(self):
        import native_schema_observer_ui_live as live
        from schema_observer_ui import SchemaInspectorPanel
        with patch.dict(sys.modules, falcor=self.api):
            controls = live.LiveInspectorControls(SimpleNamespace(screen=self.panel.controls.parent), self.service, self.panel)
            self.panel.close()
            controls.tick()
            with patch('schema_observer_ui.SchemaInspectorPanel', side_effect=RuntimeError('reopen failed')):
                controls.button.callback()
                controls.tick()
            self.assertIn('ERROR: reopen failed', controls.status.text)
            self.assertTrue(controls.window.visible)
            self.assertEqual(controls.generation, 0)
            controls.button.callback()
            controls.tick()
            self.panel = controls.panel
            self.assertIsInstance(self.panel, SchemaInspectorPanel)
            self.assertEqual(controls.generation, 1)
            controls.close()


if __name__ == '__main__': unittest.main()
