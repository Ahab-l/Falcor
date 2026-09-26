"""Native Mogwai controls for an existing V4 service; all GPU work is deferred.

Construct/close between frames. Native callbacks only queue work. Hiding either
window pauses the panel; show() restores both. close() does not close the service.
"""
import json
import weakref

from schema_observer_ui_model import InspectorModel, format_values
from schema_observer_preview import SchemaFieldPreview


class SchemaInspectorPanel:
    def __init__(self, renderer, service, *, preview=None):
        import falcor
        self.api, self.service = falcor, service
        self.model = InspectorModel(service, preview if preview is not None else SchemaFieldPreview(service.observer))
        self._closed = self._close_requested = False
        self._dialog = None
        self._listener = None
        self._callbacks = []
        self.buttons = {}
        self.fields = service.observer.contract['schema']['fields']
        schema = service.observer.contract['schema']
        self.sources = (['field:'+field['name'] for field in self.fields] +
                        ['attachment:'+item['name'] for item in schema['attachments']])
        ui = falcor.ui
        self.controls = ui.Window(renderer.screen, title='customrenderpipline | Inspector',
                                  position=falcor.float2(10, 30), size=falcor.float2(475, 750))
        self.viewer = ui.Window(renderer.screen, title='Schema snapshot | Pixel / Results',
                                position=falcor.float2(495, 30), size=falcor.float2(770, 750))
        self.controls.background_alpha = self.viewer.background_alpha = 1.
        try:
            ui.Text(self.controls, text='Graph: '+service.observer.graph.name+' (bound observer)')
            ui.Text(self.controls, text='On demand. Click preview to refresh + inspect.')
            self.source = ui.Combobox(self.controls, label='Source', items=self.sources)
            self.mode = ui.Combobox(self.controls, label='Mapping', items=['gray','rgb','signed','id'])
            self.component = ui.DragInt(self.controls, label='Component', value=0, min=0, max=3)
            self.low = ui.DragFloat(self.controls, label='Low', value=0., speed=.01)
            self.high = ui.DragFloat(self.controls, label='High', value=1., speed=.01)
            self.region = ui.DragInt4(self.controls, label='x y w h', value=falcor.int4(0,0,1,1), min=0, max=16384)
            self._button(self.controls, 'refresh', 'Refresh preview', '_submit', 'refresh')
            self._button(self.controls, 'inspect', 'Inspect pixel (x, y)', '_submit', 'inspect')
            compare = ui.Group(self.controls, label='Compare region')
            self.field = ui.Combobox(compare, label='Field', items=[f['name'] for f in self.fields],
                                     change_callback=self._callback('_field_changed'))
            self._callbacks.append((self.field, 'change_callback'))
            self.rule = ui.Combobox(compare, label='Rule', items=['numeric'])
            self.atol = ui.DragFloat(compare, label='Atol (absolute)', value=.001, min=0., speed=.0001, format='%.6f')
            self.rtol = ui.DragFloat(compare, label='Rtol (relative)', value=0., min=0., speed=.0001, format='%.6f')
            self.angle = ui.DragFloat(compare, label='Angle (degrees)', value=.1, min=0., max=180., speed=.01)
            self.reference = ui.TextInput(compare, label='Reference NPZ', value='')
            self._button(compare, 'reference', 'Choose reference NPZ...', '_choose', 'reference')
            self.rules_path = ui.TextInput(compare, label='Rules JSON', value='')
            self._button(compare, 'rules_path', 'Choose rules JSON...', '_choose', 'rules_path')
            self.mask = ui.TextInput(compare, label='Mask key', value='')
            self._button(compare, 'compare', 'Compare region', '_submit', 'compare')
            exports = ui.Group(self.controls, label='Export to session / exports')
            self._button(exports, 'export', 'Export decoded region (.npz)', '_submit', 'export')
            self.raw_output = ui.TextInput(exports, label='Raw graph output', value=next(iter(service.observer.bindings.values())))
            self._button(exports, 'raw', 'Export raw output (.bin)', '_submit', 'raw')
            self._button(self.controls, 'close', 'Close inspector (keep CLI)', '_request_close')
            self.status = ui.Text(self.viewer, text=self.model.status)
            self.identity = ui.Text(self.viewer, text='No snapshot yet. Layout: '+service.observer.layout_hash)
            self.image = ui.Image(self.viewer, size=falcor.float2(730, 360), click_callback=self._callback('_pick'))
            self._callbacks.append((self.image, 'click_callback'))
            self.results = ui.Text(self.viewer, text='No numeric readback yet.')
            self._field_changed()
            self._listener = service.add_frame_listener(self._callback('_frame'), on_close=self._callback('close'))
        except Exception:
            self.close()
            raise

    def _callback(self, method, *bound):
        # Do not create a C++ Widget -> Python bound method -> panel cycle.
        owner = weakref.ref(self)
        def callback(*args):
            panel = owner()
            if panel is not None and not panel._closed:
                return getattr(panel, method)(*bound, *args)
        return callback

    def _button(self, parent, key, label, method, *args):
        button = self.api.ui.Button(parent, label=label, callback=self._callback(method, *args))
        self.buttons[key] = button
        self._callbacks.append((button, 'callback'))

    def _field_changed(self):
        dtype = self.fields[self.field.value]['type']
        integer = dtype.startswith(('uint','int')) or dtype == 'bool'
        self.rule.items = ['exact'] if integer else ['numeric','angle'] if dtype == 'float3' else ['numeric']
        self.rule.value = 0

    def state(self):
        region = self.region.value
        selected = self.fields[self.field.value]
        return dict(source=self.source.items[self.source.value], mode=self.mode.items[self.mode.value],
                    component=self.component.value, low=self.low.value, high=self.high.value,
                    region=[region.x,region.y,region.z,region.w], field=selected['name'], field_type=selected['type'],
                    rule_kind=self.rule.items[self.rule.value], atol=self.atol.value, rtol=self.rtol.value,
                    angle=self.angle.value, reference=self.reference.value, rules_path=self.rules_path.value,
                    mask=self.mask.value, raw_output=self.raw_output.value)

    def _submit(self, action, state=None):
        try:
            self.model.enqueue(action, self.state() if state is None else state)
        except Exception as error:
            self.status.text = 'ERROR: '+str(error)

    def _pick(self, pixel):
        state = self.state()
        state.update(region=[int(pixel.x),int(pixel.y),1,1],
                     display_dims=self.model.preview_dims, display_source=self.model.preview_source)
        self.region.value = self.api.int4(*state['region'])
        self._submit('pick', state)

    def _choose(self, field):
        self._dialog = field

    def _request_close(self):
        self._close_requested = True

    def _frame(self):
        if self._close_requested or self.service.closed:
            self.close()
            return
        if not (self.controls.visible and self.viewer.visible):
            self.controls.visible = self.viewer.visible = False
            self.model.actions.clear()
            self._dialog = None
            return
        if self._dialog:
            field, self._dialog = self._dialog, None
            try:
                path = self.api.ui.open_file_dialog()
            except Exception as error:
                self.status.text = 'ERROR: '+str(error)
                path = ''
            if path:
                getattr(self, field).value = path
        revision, stale = self.model.revision, self.model.stale
        self.model.pump()
        if (revision, stale) != (self.model.revision, self.model.stale):
            self._update()

    def _update(self):
        model = self.model
        self.status.text = ('STALE | ' if model.stale else '')+model.status
        self.identity.text = (f'Preview frame: {model.preview_frame} | {model.preview_source} | {model.preview_dims}\n'
                              'Layout: '+self.service.observer.layout_hash)
        self.image.texture = model.texture
        if model.last_state is not None:
            self.image.selection = self.api.uint2(*model.last_state['region'][:2])
        reply = model.last_reply
        if reply is None:
            return
        result = reply['result']
        lines = [f'Result frame: {reply["frame"]} | {reply["status"]}']
        if 'storage' in result or 'fields' in result and 'region' in result:
            for group in ('fields','storage','attachments'):
                lines += [group.upper(), format_values(result.get(group, {}))]
        else:
            lines += [json.dumps(result, indent=2, ensure_ascii=True)]
        self.results.text = '\n'.join(lines)

    def show(self):
        if self._closed:
            raise RuntimeError('Closed inspector: construct a new SchemaInspectorPanel with the existing service')
        self.controls.show()
        self.viewer.show()

    def close(self):
        """Release only this panel, from outside native draw callbacks."""
        if self._closed:
            return
        self._closed = True
        if self._listener is not None:
            self.service.remove_frame_listener(self._listener)
            self._listener = None
        for widget, attribute in self._callbacks:
            setattr(widget, attribute, None)
        self._callbacks.clear()
        if hasattr(self, 'image'):
            self.image.texture = None
        self.model.close()
        self.controls.detach()
        self.viewer.detach()
