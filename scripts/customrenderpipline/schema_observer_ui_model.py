"""Frame-boundary UI actions sharing the V4 service, without native widgets."""
from collections import deque
import copy
import json
from pathlib import Path
from schema_observer_compare import _validate_rule


def make_rule(field_type, kind, atol, rtol, angle):
    integer=field_type.startswith(('uint','int')) or field_type=='bool'
    if (kind=='exact' and not integer) or (kind!='exact' and integer) or (kind=='angle' and field_type!='float3'):
        raise ValueError('Comparison rule does not match the selected field type')
    rule={'kind':kind}
    if kind=='numeric':rule.update(atol=atol,rtol=rtol)
    elif kind=='angle':rule['max_degrees']=angle
    return _validate_rule(rule)


def _value(value):
    while isinstance(value,list) and len(value)==1:value=value[0]
    if isinstance(value,list):return '['+', '.join(_value(v) for v in value)+']'
    if isinstance(value,float):return format(value,'.8g')
    return str(value)


def format_values(values):
    lines=[]
    for name,desc in values.items():
        display=_value(desc['values']) if 'values' in desc else desc.get('path','No inline data')
        lines.append(f'{name} ({desc["dtype"]}): {display}')
    return '\n'.join(lines) or '(none)'


class InspectorModel:
    def __init__(self,service,preview):
        self.service,self.preview=service,preview
        self.actions=deque()
        self.pending=None
        self.status='Ready. Refresh creates a GPU snapshot; inspection is on demand.'
        self.texture=None
        self.preview_frame=None
        self.preview_dims=None
        self.preview_source=None
        self.last_reply=None
        self.last_state=None
        self.stale=False
        self.closed=False
        self.revision=0

    def enqueue(self,action,state):
        if self.closed:raise RuntimeError('Inspector is closed')
        if action not in ('refresh','inspect','pick','compare','export','raw'):
            raise ValueError('Unknown inspector action')
        if len(self.actions)+(self.pending is not None)>=8:raise ValueError('Inspector queue is full; wait for the next rendered frame')
        self.actions.append((action,copy.deepcopy(state)))

    def _call(self,operation,arguments=None):
        ticket=self.service.submit({'graph':self.service.observer.graph.name,'operation':operation,'arguments':arguments or {}})
        if not ticket.ready:raise RuntimeError('Metadata listing unexpectedly required GPU readback')
        reply=ticket.result()
        if reply['status']=='error':raise ValueError(reply['error']['message'])
        return reply

    def _request(self, operation, arguments, action, state):
        ticket=self.service.submit({'graph':self.service.observer.graph.name,'operation':operation,'arguments':arguments})
        self.pending=(ticket,action,state)
        self.status=f'Pending {action}: submitted frame {self.service.frame}'
        self._collect()

    def _collect(self):
        if self.pending is None or not self.pending[0].ready:return
        ticket,action,state=self.pending
        self.pending=None
        try:
            reply=ticket.result()
            if reply['status']=='error':raise ValueError(reply['error']['message'])
            self.last_reply=reply
            frame=reply['frame']
            if action=='compare':
                self.status=('PASS' if reply['status']=='ok' else 'FAIL: outside tolerance')+f' — comparison frame {frame}'
            elif action=='export':self.status=f'Decoded region exported at frame {frame}'
            elif action=='raw':self.status=f'Raw output exported at frame {frame}'
            else:self.status=f'Snapshot frame {frame}: {state["source"]}'
            self.last_state=state
        except Exception as error:
            self.status='ERROR: '+str(error)
            self.stale=True
        self.revision+=1

    def pump(self):
        if self.closed:return
        if self.service.closed or self.service.active_graph!=self.service.observer.graph.name:
            self.stale=True
        if self.pending is not None:
            self._collect()
            return
        if not self.actions:return
        action,state=self.actions.popleft()
        try:
            if self.service.closed:raise ValueError('Observation service is closed')
            if self.service.active_graph!=self.service.observer.graph.name:
                raise ValueError('Registered graph is inactive; preview is a previous snapshot')
            if action in ('refresh','inspect','pick'):
                info=self._call('list')['result']
                if action=='pick' and (state.get('display_dims')!=info['dimensions'] or
                                       state.get('display_source',state['source'])!=state['source']):
                    raise ValueError('Preview resized or source changed; refresh before picking')
                texture=self.preview.render(state['source'],mode=state['mode'],low=state['low'],high=state['high'],component=state['component'])
                self.texture=texture
                self.preview_dims=[texture.width,texture.height]
                self.preview_source=state['source']
                self.preview_frame=self.service.frame
                self.stale=False
                self.status=f'Snapshot frame {self.preview_frame}: {state["source"]}'
                if action!='refresh':
                    x,y=state['region'][:2]
                    self._request('inspect',{'region':[x,y,1,1]},action,state)
            elif action=='compare':
                path=state['rules_path'].strip()
                if path:
                    from generate_native_gbuffer import unique_keys
                    with Path(path).open('rb') as stream:data=stream.read(65537)
                    if len(data)>65536:raise ValueError('Rules JSON exceeds 64 KiB')
                    rules=json.loads(data.decode('utf-8-sig'),object_pairs_hook=unique_keys)
                else:
                    rules={state['field']:make_rule(state['field_type'],state['rule_kind'],state['atol'],state['rtol'],state['angle'])}
                if not state['reference'].strip():raise ValueError('Choose a reference NPZ before comparing')
                args={'region':state['region'],'reference':str(Path(state['reference']).resolve()),'rules':rules}
                if state['mask'].strip():args['mask']=state['mask'].strip()
                self._request('compare',args,action,state)
            elif action=='export':
                self._request('inspect',{'region':state['region'],'export':True},action,state)
            else:
                self._request('read',{'output':state['raw_output']},action,state)
            self.last_state=state
        except Exception as error:
            self.status='ERROR: '+str(error)
            self.stale=True
        self.revision+=1

    def close(self):
        if self.closed:return
        if self.pending is not None:
            self.pending[0].cancel()
            self.pending=None
        self.actions.clear()
        self.preview.close()
        self.texture=None
        self.closed=True
