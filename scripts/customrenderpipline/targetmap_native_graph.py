"""Native source-only targetmap example graph; captures are offline oracles only."""
import copy

from targetmap_native import source_camera


FORMATS = [('sceneColor', 'RGBA16Float'), ('gbufferA', 'RGB10A2Unorm'),
           ('gbufferB', 'BGRA8Unorm'), ('gbufferC', 'BGRA8UnormSrgb'), ('gbufferD', 'BGRA8Unorm')]


def graph_definition(source, basic_ids, floor_ids, shader, codec, *, render_context=None, frame_index=0,
                     platform_texture=None, max_anisotropy=1):
    """Initial measurable source baseline, not a pixel-parity claim.

    Grid defaults to original uncompressed single-mip source DDS. A verified
    source-platform BC1 chain and sampler anisotropy are independent options.
    Frame phase is the explicit source-owned frame index. Contact shadow=true is constructor-default,
    not yet an audited map override; Floor indirect representation=false is
    likewise a source-default hypothesis. These are named fields, not raw ABI.
    """
    if source.get('capture_inputs') is not False:
        raise ValueError('Expected independently exported source scene')
    if type(max_anisotropy) is not int or not 1 <= max_anisotropy <= 16:
        raise ValueError('max_anisotropy must be integer 1..16')
    grid = {'kind': 'texture2D', 'file': source['source_texture']['original_export']['source_image']['path'],
            'format': 'BGRA8UnormSrgb', 'size': [512, 512], 'mip_count': 1, 'srgb': True}
    if platform_texture is not None:
        if (set(platform_texture) != {'capture_inputs', 'file', 'format', 'size', 'mip_count', 'srgb'} or
            platform_texture['capture_inputs'] is not False or platform_texture['format'] != 'BC1UnormSrgb' or
            platform_texture['size'] != [512, 512] or type(platform_texture['mip_count']) is not int or
            platform_texture['mip_count'] != 10 or platform_texture['srgb'] is not True or
            not isinstance(platform_texture['file'], str) or not platform_texture['file']):
            raise ValueError('Expected verified source-platform BC1 sRGB 10 mip texture')
        grid.update({k:v for k,v in platform_texture.items() if k != 'capture_inputs'})
    if type(frame_index) is not int or not 0 <= frame_index < 2**32:
        raise ValueError('frame_index must be uint32')
    ids = list(basic_ids) + list(floor_ids)
    if not basic_ids or not floor_ids or any(type(i) is not int or not 0 <= i < 2**32 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Need disjoint nonempty native BasicShape/ProcGrid instance sets')
    camera_source = dict(source['camera'])
    if render_context is not None:
        if set(render_context) != {'projection_resolution'}:
            raise ValueError('Render context currently requires only projection_resolution')
        camera_source['projection_resolution'] = render_context['projection_resolution']
    camera = source_camera(camera_source)
    size = [1424, 1040]
    base = {'shader': {'file': str(shader), 'vertex': 'vsMain',
                       'defines': {'CRP_CODEC_HEADER': '"'+str(codec).replace('\\', '/')+'"', 'PROCGRID': '0'}},
            'viewport': camera['view_rect'], 'view_projection': camera['view_projection'],
            'view_projection_binding': 'Transform.projection',
            'state': {'depth_func': 'GreaterEqual', 'depth_write': True, 'cull_mode': 'Back'},
            'depthTarget': {'name': 'depth', 'format': 'D32FloatS8Uint', 'size': size, 'clear': 0, 'stencilClear': 0}}
    pre = copy.deepcopy(base)
    pre['instanceIDs'] = ids
    # The native vertex entry is shared exactly by prepass and material passes.
    nodes = [{'name': 'Assets', 'type': 'CustomRenderPiplineAssetPass', 'properties': {'assets': {
        'grid': grid}}},
             {'name': 'Prepass', 'type': 'CustomRenderPiplineMeshDrawPass', 'properties': pre}]
    edges = [['Prepass.depth', 'Basic.depth'], ['Basic.depth', 'Floor.depth'], ['Assets.grid', 'Floor.grid']]
    for label, selection, material_name in [('Basic', basic_ids, 'BasicShape'), ('Floor', floor_ids, 'ProcGrid')]:
        props = copy.deepcopy(base)
        props['instanceIDs'] = list(selection)
        props['shader']['pixel'] = 'psMain'
        props['shader']['defines']['PROCGRID'] = '1' if label == 'Floor' else '0'
        props['state'].update(depth_write=False, stencil_enabled=True, stencil_func='Always',
                              stencil_reference=134, stencil_read_mask=255, stencil_write_mask=246,
                              stencil_fail='Keep', stencil_depth_fail='Keep', stencil_pass='Replace')
        props['depthTarget'] = {'name': 'depth', 'format': 'D32FloatS8Uint', 'size': size, 'load': 'load'}
        props['colorTargets'] = [dict(name=name, format=fmt, slot=i, size=size, clear=[0, 0, 0, 0])
                                 for i, (name, fmt) in enumerate(FORMATS)]
        if label == 'Floor':
            for target in props['colorTargets']:
                target.pop('clear')
                target['load'] = 'load'
                edges.append(['Basic.'+target['name'], 'Floor.'+target['name']])
        material = source['materials'][material_name]
        fields = {'baseColor': ('float3', material['base_color_linear']), 'roughness': ('float', material['roughness']),
                  'specular': ('float', material['specular']), 'metallic': ('float', material['metallic']),
                  'ao': ('float', 1), 'emissive': ('float3', material['emissive_linear']),
                  'capsuleRepresentation': ('uint', 0), 'castContactShadow': ('uint', 1),
                  'shadingModel': ('uint', 1), 'skipVelocity': ('uint', 1), 'firstPerson': ('uint', 0)}
        uniforms = {'Surface.'+name: {'type': typ, 'value': value} for name, (typ, value) in fields.items()}
        uniforms.update({'Frame.phase': {'type': 'uint', 'value': frame_index}, 'Frame.preExposure': {'type': 'float', 'value': 1}})
        # Exposure 1 here affects only zero emission; independent exposure is required at lighting.
        if label == 'Floor':
            uniforms.update({'ProcGridParams.'+name: {'type': 'float3' if isinstance(value, list) else 'float', 'value': value}
                             for name, value in source['procgrid_parameters'].items()})
            props['resources'] = [dict(name='grid', binding='gGrid', **{k:grid[k] for k in ('format', 'size', 'mip_count')})]
            props['samplers'] = {'gGridSampler': {'filter': 'Linear', 'address': 'Wrap'}}
            if platform_texture is not None or max_anisotropy != 1:
                props['samplers']['gGridSampler']['max_anisotropy'] = max_anisotropy
        props['uniforms'] = uniforms
        nodes.append({'name': label, 'type': 'CustomRenderPiplineMeshDrawPass', 'properties': props})
    return {'version': 1, 'nodes': nodes, 'edges': edges,
            'outputs': ['Floor.'+name for name, _ in FORMATS]+['Floor.depth']}
