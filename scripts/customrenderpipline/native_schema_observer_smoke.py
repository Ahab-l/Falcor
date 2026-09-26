"""D3D12 real-MRT/decoder acceptance with an independent CLI client process."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT/'scripts/customrenderpipline'
sys.path[:0] = [str(HERE), str(ROOT/'build/m0-evidence/python')]
import falcor
import numpy as np
from native_schema_observer import start
from observer_mogwai import MogwaiObservation
from schema_observer_compare import compare_fields

OUT = ROOT/'build/native-schema-observer'
OUT.mkdir(exist_ok=True)
out = Path(tempfile.mkdtemp(prefix='gpu-', dir=OUT))
print('V4_EVIDENCE '+str(out), flush=True)
assert hasattr(falcor.RenderGraph, 'device') and hasattr(falcor.RenderGraph, 'execute')
source = HERE/'examples/schema_gbuffer'
schema = json.loads((source/'Schema.json').read_text())
unorm_variant = os.environ.get('CRP_OBSERVER_TEST_UNORM') == '1'
if unorm_variant:
    schema['attachments'][0]['format'] = 'RGBA8Unorm'
    schema['attachments'][1]['format'] = 'BGRA8UnormSrgb'
    schema['storage'][1].update(channels='g', bits={'offset':0,'width':8})
    schema['storage'][2].update(channels='b', bits={'offset':0,'width':1})
    schema['codecs'][1]['range'] = [0,255]
schema['attachments'].append({'name':'exact', 'format':'RG32Uint'})
for name, channel, kind, bounds in [('fullID','r','uint',[0,4294967295]), ('signedID','g','sint',[-2147483648,2147483647])]:
    schema['fields'].append({'name':name,'type':'uint' if kind=='uint' else 'int'})
    schema['storage'].append({'name':name+'Code','attachment':'exact','channels':channel,'bits':{'offset':0,'width':32}})
    schema['codecs'].append({'kind':kind,'field':name,'storage':name+'Code','range':bounds,'overflow':'reject'})
for file in ('Material.slangh','SurfaceCodec.slangh'):
    (out/file).write_bytes((source/file).read_bytes())
material = (out/'Material.slangh').read_text().replace('return fields;', 'fields.fullID = 4294967295u; fields.signedID = (-2147483647 - 1); return fields;')
assert 'fields.fullID' in material
(out/'Material.slangh').write_text(material)
(out/'Schema.json').write_text(json.dumps(schema))
graph, artifacts, observer, service, attachment = start(m, schema_path=out/'Schema.json', session_dir=out/'session', output_dir=out/'generated')
graph.addPass(falcor.createPass('GBufferRaster', {'samplePattern':'Center'}), 'Stock')
for port in ('specRough','guideNormalW','diffuseOpacity'):
    graph.markOutput('Stock.'+port)
m.resizeFrameBuffer(128,72)
m.clock.pause()
m.ui = False
cli_calls = []


def cli(operation, *args, expected=0, timeout=20, pump=True):
    index = len(cli_calls)
    command = [os.environ.get('CRP_CLIENT_PYTHON', 'E:/IDE/Anaconda/python.exe'), str(HERE/'inspect_cli.py'),
               '--session', str(service.mailbox.session_dir), '--timeout', str(timeout), operation, '--graph', graph.name, *map(str,args)]
    stdout, stderr = out/f'cli-{index}.json', out/f'cli-{index}.stderr'
    with stdout.open('wb') as sout, stderr.open('wb') as serr:
        process = subprocess.Popen(command, stdout=sout, stderr=serr, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic()+timeout+15
        while process.poll() is None:
            if time.monotonic() > deadline:
                process.kill(); process.wait()
                raise AssertionError('Independent CLI exceeded test timeout')
            if pump:
                m.renderFrame()
            time.sleep(.005)
    response = json.loads(stdout.read_text())
    assert process.returncode == expected, (command,response,stderr.read_text())
    cli_calls.append({'operation':operation,'exit_code':process.returncode,'response':str(stdout)})
    return response


try:
    m.renderFrame()
    before = (observer.dispatch_count, observer.readback_count)
    for _ in range(4): m.renderFrame()
    assert before == (observer.dispatch_count, observer.readback_count) == (0,0), 'Idle frame issued observer GPU work'
    snapshot = observer.inspect([0,0,128,72])
    fields = snapshot['fields']
    mask = fields['coverage'] > 0
    assert int(mask.sum()) > 100
    assert fields['fullID'].dtype == np.dtype('uint32') and fields['signedID'].dtype == np.dtype('int32')
    np.testing.assert_array_equal(fields['fullID'][mask], 4294967295)
    np.testing.assert_array_equal(fields['signedID'][mask], -2147483648)
    raw = np.asarray(graph.getOutput('GBuffer.exact').to_numpy()).reshape(72,128,2)
    np.testing.assert_array_equal(raw[...,0], snapshot['attachments']['exact'][...,0])
    np.testing.assert_array_equal(snapshot['storage']['fullIDCode'][mask],4294967295)
    expected_rough = np.asarray(graph.getOutput('Stock.specRough').to_numpy())[...,3]
    quantized = np.rint(np.sqrt(expected_rough.astype(np.float64))*255)/255
    np.testing.assert_allclose(fields['roughness'][mask], (quantized**2)[mask], atol=3e-7, rtol=0)
    stock_color = np.asarray(graph.getOutput('Stock.diffuseOpacity').to_numpy())[...,:3]
    np.testing.assert_allclose(fields['baseColor'][mask],stock_color[mask],atol=0.005,rtol=0)
    if unorm_variant:
        raw_bits = np.frombuffer(graph.getOutput('GBuffer.materialBits').to_numpy().tobytes(),np.uint8).reshape(72,128,4)
        np.testing.assert_array_equal(snapshot['storage']['roughnessCode'],raw_bits[...,0])
        np.testing.assert_array_equal(snapshot['storage']['idCode'],raw_bits[...,1])
    stock_normal = np.asarray(graph.getOutput('Stock.guideNormalW').to_numpy())[...,:3].astype(np.float32)
    angle = compare_fields({'normalW':fields['normalW']}, {'normalW':stock_normal}, {'normalW':{'kind':'angle','max_degrees':0.01}}, mask=mask)
    assert angle['passed'], angle
    y,x = map(int,np.argwhere(mask)[0])
    pixel = observer.inspect([x,y,1,1], fields=['fullID','signedID','roughness','normalW'])
    response = cli('list')
    assert response['frame'] > 0 and response['layout_hash'] == observer.layout_hash
    response = cli('inspect','--region',x,y,1,1,'--fields','fullID','signedID','roughness','normalW')
    for name, value in pixel['fields'].items():
        descriptor = response['result']['fields'][name]
        np.testing.assert_array_equal(np.asarray(descriptor['values'],dtype=descriptor['dtype']), value)
    assert response['result']['fields']['fullID']['values'] == [[4294967295]]
    exported = cli('inspect','--region',0,0,128,72,'--export')
    descriptor = exported['result']['fields']['fullID']
    with np.load(descriptor['path'],allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive[descriptor['key']], fields['fullID'])
    np.savez(out/'reference.npz', **fields, mask=mask)
    rules = {'fullID':{'kind':'exact'}, 'signedID':{'kind':'exact'}, 'roughness':{'kind':'numeric','atol':1e-6,'rtol':0},
             'normalW':{'kind':'angle','max_degrees':0.01}}
    (out/'rules.json').write_text(json.dumps(rules))
    compared = cli('compare','--region',0,0,128,72,'--reference',out/'reference.npz','--rules',out/'rules.json','--mask','mask')
    assert compared['result']['passed']
    bad = fields['fullID'].copy(); bad[mask] -= 1
    np.savez(out/'bad.npz', **{**fields,'fullID':bad},mask=mask)
    failed = cli('compare','--region',0,0,128,72,'--reference',out/'bad.npz','--rules',out/'rules.json','--mask','mask',expected=1)
    assert not failed['result']['passed']
    invalid = cli('inspect','--region',128,0,1,1,expected=2)
    assert invalid['error']['code'] == 'invalid_request'
    cli('inspect','--region',0,0,1,1,'--fields','unknown',expected=2)
    read = cli('read','--output','GBuffer.exact')
    data = np.fromfile(read['result']['data']['path'],dtype=np.uint32).reshape(72,128,2)
    np.testing.assert_array_equal(data,raw)
    timed = cli('list', expected=3, timeout=.05, pump=False)
    assert timed['error']['code']=='timeout'
    # A request with stale producer configuration must be rejected before decode.
    previous_definition = graph.getPass('GBuffer').getDictionary()['definition']
    other_definition = out/'OtherLayout.json'
    other_layout = json.loads(artifacts.definition.read_text())
    other_layout['shader'] = str(artifacts.definition.parent/'GBuffer.3d.slang')
    other_definition.write_text(json.dumps(other_layout))
    graph.updatePass('GBuffer',{'definition':str(other_definition)})
    rejected = cli('inspect','--region',x,y,1,1,expected=2)
    assert 'definition' in rejected['error']['message']
    graph.updatePass('GBuffer',{'definition':previous_definition})
    m.renderFrame()
    # Preserve an existing callback and execute the ordinary graph once.
    attachment.close()
    assert m.graphExecutionCallback is None, 'Observer detach did not restore callback'
    calls=[]
    def previous(current, clock_time):
        calls.append(clock_time)
        current.execute()
        return True
    m.graphExecutionCallback = previous
    from schema_observer_service import ObservationService
    second_service = ObservationService(observer,out/'second-session')
    second = MogwaiObservation(m,second_service)
    m.renderFrame()
    assert len(calls)==1 and second_service.frame==1
    second.close()
    m.renderFrame()
    assert len(calls)==2, 'Previous graph executor was not restored'
    m.graphExecutionCallback=None
    third_service = ObservationService(observer,out/'third-session')
    third = MogwaiObservation(m,third_service)
    m.graphExecutionCallback = lambda current, clock_time: False
    newer_revision = m.graphExecutionCallbackRevision
    third.close()
    assert m.graphExecutionCallbackRevision == newer_revision, 'Detach replaced a newer callback'
    m.graphExecutionCallback=None
    # Native wrappers retained by applications must become transparent on close.
    wrapped_service = ObservationService(observer,out/'wrapped-session')
    wrapped = MogwaiObservation(m,wrapped_service)
    saved_callback = m.graphExecutionCallback
    m.graphExecutionCallback = lambda current,clock_time: saved_callback(current,clock_time)
    wrapped.close()
    m.renderFrame()
    m.graphExecutionCallback=None
    outer = MogwaiObservation(m,ObservationService(observer,out/'outer-session'))
    inner = MogwaiObservation(m,ObservationService(observer,out/'inner-session'))
    inner.close(); outer.close()
    assert m.graphExecutionCallback is None
    # Custom decoders may leave undefined background fields. Comparison uses
    # the explicit mask; unmasked inspection and comparison must still reject.
    background = out/'background'; background.mkdir()
    (background/'Schema.json').write_text(json.dumps(schema))
    (background/'Material.slangh').write_bytes((out/'Material.slangh').read_bytes())
    custom = (out/'SurfaceCodec.slangh').read_text().replace('return value;',
        'if (storage.roughnessCode == 0u && all(storage.oct == 0.f)) value.roughness = asfloat(0x7fc00000u); return value;')
    (background/'SurfaceCodec.slangh').write_text(custom)
    m.removeGraph(graph)
    bg_graph,bg_artifacts,bg_observer,bg_service,bg_attachment = start(m,schema_path=background/'Schema.json',
        session_dir=background/'session',output_dir=background/'generated')
    try:
        m.renderFrame()
        try:
            bg_observer.inspect([0,0,128,72],fields=['roughness'])
        except ValueError as error:
            assert 'nonfinite' in str(error)
        else:
            raise AssertionError('Unmasked NaN inspection accepted')
        masked = bg_observer.compare([0,0,128,72],fields,{'roughness':rules['roughness']},mask=mask)
        assert masked['passed']
        service = bg_service
        cli('compare','--region',0,0,128,72,'--reference',out/'reference.npz','--rules',out/'rules.json','--mask','mask')
        cli('compare','--region',0,0,128,72,'--reference',out/'reference.npz','--rules',out/'rules.json',expected=2)
    finally:
        bg_attachment.close()
    result={'status':'passed','covered_pixels':int(mask.sum()),'native_bindings':True,'full_integer_precision':True,
            'custom_codec_independent_reference':True,'raw_and_typed_export':True,'idle_no_readback':True,
            'callback_restore':True,'retained_closed_callback':True,'masked_nonfinite_background':True,
            'callback_chain_once':True,'bit_storage':'UNORM' if unorm_variant else 'UINT',
            'color_format':schema['attachments'][1]['format'],'cli_calls':cli_calls,'layout_hash':observer.layout_hash}
    (out/'result.json').write_text(json.dumps(result,indent=2))
    print('NATIVE_SCHEMA_OBSERVER_PASS '+str(out/'result.json'),flush=True)
finally:
    attachment.close()
exit()
