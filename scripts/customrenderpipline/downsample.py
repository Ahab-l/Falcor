"""UE full-viewport downsample expressed as a reusable generic Compute node."""
from pathlib import Path
SHADER = Path(__file__).resolve().parents[2] / 'Source/RenderPasses/customrenderpipline/Codecs/Exposure/Downsample.slang'

def downsample_fragment(source, *, prefix='Half', source_format='RGBA32Float',
                        output_format='R11G11B10Float', quality='low', execution='raster'):
    formats=('RGBA16Float','RGBA32Float','R11G11B10Float')
    if source_format not in formats or output_format not in formats:
        raise ValueError('Downsample requires linear floating-point color')
    if quality not in ('low','high'):
        raise ValueError('Downsample quality must be low or high')
    if execution not in ('raster','compute'):
        raise ValueError('Downsample execution must be raster or compute')
    props={'shader':{'file':str(SHADER),'defines':{'DOWNSAMPLE_QUALITY':str(int(quality=='high')),
                                                'COMPUTESHADER':str(int(execution=='compute'))}},
        'resources':[
            {'name':'input','direction':'input','binding':'InputTexture','format':source_format},
            {'name':'color','direction':'output','binding':'OutComputeTexture','format':output_format,
             'size':{'relative_to':'input','divisor':[2,2]}}],
        'samplers':{'InputSampler':{'filter':'Linear','address':'Clamp'}},'dispatch':{'extent':'color'}}
    if execution=='raster':
        props['shader']['pixel']='MainPS'
        props.pop('dispatch')
        props['resources'][1].pop('binding')
        props['resources'][1]['slot']=0
        props['uniforms']={'Params.extent':{'type':'uint2','source':'extent'}}
    kind='CustomRenderPiplineComputePass' if execution=='compute' else 'CustomRenderPiplineFullscreenPass'
    return {'version':1,'nodes':[{'name':prefix,'type':kind,'file_inputs':['shader.file'],'properties':props}],
        'edges':[[source,prefix+'.input']],'outputs':[prefix+'.color']}
