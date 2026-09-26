"""Reusable declared UE atomic histogram exposure chain; inputs stay native.

source_color is pre-exposed linear SceneColor. Optional metering_source uses
the same pre-exposure with independent dimensions and format. The caller
selects the downsample branch; local exposure is separate.
"""
from pathlib import Path
from exposure import HistogramExposureSettings

SHADERS = Path(__file__).resolve().parents[2] / 'Source/RenderPasses/customrenderpipline/Codecs/Exposure'

def histogram_exposure_fragment(source_color, *, settings=None, prefix='Exposure', source_format='RGBA32Float',
                                metering_source=None, metering_format=None):
    if source_format not in ('RGBA16Float','RGBA32Float'):
        raise ValueError('Exposure requires linear floating-point SceneColor')
    if metering_source is None and metering_format is not None:
        raise ValueError('Metering format requires a separate metering source')
    meter = source_color if metering_source is None else metering_source
    meter_format = source_format if metering_format is None else metering_format
    if meter_format not in ('RGBA16Float','RGBA32Float','R11G11B10Float'):
        raise ValueError('Metering requires linear floating-point color')
    policy = HistogramExposureSettings.from_dict({} if settings is None else settings)
    values = policy.parameters(delta_time=0.0, history_valid=True)
    nodes, edges, outputs = [], [], []
    def name(suffix): return prefix + suffix
    def port(n, binding, direction='input', format='RGBA32Float', size=None, **extra):
        result = dict(name=n, binding=binding, direction=direction, format=format, **extra)
        if size is not None: result['size'] = size
        return result
    def edge(src, node, field): edges.append([src, name(node)+'.'+field])
    def compute(suffix, shader, entry, resources, *, uniforms=None, samplers=None, dispatch=None):
        props = {'shader':{'file':str(SHADERS/shader),'compute':entry},'resources':resources,
                 'dispatch':dispatch or {'threads':[1,1,1]}}
        if uniforms: props['uniforms'] = uniforms
        if samplers: props['samplers'] = samplers
        nodes.append({'name':name(suffix),'type':'CustomRenderPiplineComputePass','file_inputs':['shader.file'],'properties':props})
    history = [{'name':'exposure','format':'RGBA32Float','size':[2,1]}]
    for suffix,kind in (('Previous','Read'),('Publish','Write')):
        nodes.append({'name':name(suffix),'type':'CustomRenderPiplineHistory'+kind+'Pass',
                      'properties':{'key':name('History'),'resources':history}})
    compute('Neutral','Neutral.slang','main',[port('white','white','output',size=[1,1])])
    compute('Frame','FrameExposure.slang','main',[
        port('previous','previous',size=[2,1]),port('status','status',format='RGBA32Uint',size=[1,1]),
        port('preExposure','preExposure','output','R32Float',[1,1])])
    edge(name('Previous')+'.exposure','Frame','previous');edge(name('Previous')+'.status','Frame','status')

    def constants(names):
        result = {}
        for key in names.split():
            value = values['EyeAdaptation_'+key]
            result['ExposureSettings.EyeAdaptation_'+key] = {'type':'float'+(str(len(value)) if isinstance(value,(list,tuple)) else ''),'value':value}
        return result
    compute('Scatter','Histogram.slang','MainAtomicCS',[
        port('sceneColor','InputTexture',format=meter_format,max_size=[8191,65535]),
        port('preExposure','NativePreExposure',format='R32Float',size=[1,1]),
        port('mask','EyeAdaptation_MeterMaskTexture',size=[1,1]),
        port('scatter','HistogramScatter32Output','output','R32Uint',[128,1],clear=[0,0,0,0])],
        uniforms=constants('HistogramScale HistogramBias LuminanceMin BlackHistogramBucketInfluence LuminanceWeights'),
        samplers={'EyeAdaptation_MeterMaskSampler':{'filter':'Linear','address':'Clamp'}},
        dispatch={'groups':{'extent':'sceneColor','axes':['height',1,1]}})
    edge(meter,'Scatter','sceneColor');edge(name('Frame')+'.preExposure','Scatter','preExposure')
    edge(name('Neutral')+'.white','Scatter','mask')
    compute('Convert','Histogram.slang','HistogramConvertCS',[
        port('sceneColor','InputTexture',format=meter_format),port('previous','PreviousExposure',size=[2,1]),
        port('status','NativeHistoryStatus',format='RGBA32Uint',size=[1,1]),
        port('scatter','HistogramScatter32Texture',format='R32Uint',size=[128,1]),
        port('histogram','HistogramOutput','output',size=[16,2])],dispatch={'threads':[64,1,1]})
    edge(meter,'Convert','sceneColor');edge(name('Previous')+'.exposure','Convert','previous')
    edge(name('Previous')+'.status','Convert','status');edge(name('Scatter')+'.scatter','Convert','scatter')
    uniforms=constants('ExposureLowPercent ExposureHighPercent MinAverageLuminance MaxAverageLuminance '
        'ExposureCompensationSettings ExposureCompensationCurve ExposureSpeedUp ExposureSpeedDown '
        'HistogramScale HistogramBias ExponentialUpM ExponentialDownM StartDistance LuminanceMax '
        'EV100ToExposureCompensationCurveLUTScaleBias')
    uniforms['ExposureSettings.AuthoredForceTarget']={'type':'float','value':values['EyeAdaptation_ForceTarget']}
    compute('Adapt','EyeAdaptation.slang','EyeAdaptationCS',[
        port('histogram','HistogramTexture',size=[16,2]),port('curve','EyeAdaptation_ExposureCompensationCurveLUT',size=[1,1]),
        port('time','NativeFrameTime',format='R32Float',size=[1,1]),
        port('status','NativeHistoryStatus',format='RGBA32Uint',size=[1,1]),
        port('exposure','NativeExposureOutput','output',size=[2,1])],uniforms=uniforms,
        samplers={'EyeAdaptation_ExposureCompensationCurveSampler':{'filter':'Linear','address':'Clamp'}})
    edge(name('Convert')+'.histogram','Adapt','histogram');edge(name('Neutral')+'.white','Adapt','curve')
    edge(name('Previous')+'.frameTime','Adapt','time');edge(name('Previous')+'.status','Adapt','status')
    edge(name('Adapt')+'.exposure','Publish','exposure')
    compute('Apply','ApplyExposure.slang','main',[
        port('sceneColor','sceneColor',format=source_format),port('preExposure','preExposure',format='R32Float',size=[1,1]),
        port('exposure','exposure',size=[2,1]),port('exposedLinear','exposedLinear','output',
            size={'relative_to':'sceneColor','divisor':[1,1]})],
        uniforms={'Params.extent':{'type':'uint2','source':'extent'}},dispatch={'extent':'exposedLinear'})
    edge(source_color,'Apply','sceneColor');edge(name('Frame')+'.preExposure','Apply','preExposure')
    edge(name('Adapt')+'.exposure','Apply','exposure')
    outputs = [name(suffix)+'.'+field for suffix,field in (('Frame','preExposure'),('Scatter','scatter'),
        ('Convert','histogram'),('Adapt','exposure'),('Apply','exposedLinear'),('Publish','status'))]
    return {'version':1,'nodes':nodes,'edges':edges,'outputs':outputs}
