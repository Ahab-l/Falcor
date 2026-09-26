import copy
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
import numpy as np
from atmosphere import component_parameters, atmosphere_lut_fragment, source_atmosphere

ROOT=Path(__file__).resolve().parents[2]


def inventory():
    return {'capture_inputs':False,'actors':[{'environment':[{'class':'SkyAtmosphereComponent',**component()}]}],
        'renderer_source_settings':{'working_color_space_choice':1,'working_color_space_choice_name':'SRGB',
            'working_color_space_chromaticities':{'red':[.64,.33],'green':[.30,.60],'blue':[.15,.06],'white':[.3127,.329]},
            'propagate_alpha':0,'mobile_propagate_alpha':0,'targeted_shader_formats':['PCD3D_SM6'],
            'lut_feature_level_branch':'desktop','lut_format_branch':'desktop_rgb','lut_pixel_format':'PF_FloatRGB',
            'provenance':{'source':'authored test settings, no runtime capture'}},
        'atmosphere_source_defaults':{'r.SkyAtmosphere.'+key:value for key,value in {
            'TransmittanceLUT':1,'TransmittanceLUT.UseSmallFormat':0,'MultiScatteringLUT.HighQuality':0,
            'TransmittanceLUT.Width':256,'TransmittanceLUT.Height':64,'MultiScatteringLUT.Width':32,
            'MultiScatteringLUT.Height':32,'TransmittanceLUT.SampleCount':10,'MultiScatteringLUT.SampleCount':15}.items()}}


def component():
    # Authored material medium: independent of capture and local source assets.
    return dict(bottom_radius=6360., atmosphere_height=60., ground_albedo=[170,170,170,255],
        multi_scattering_factor=1., rayleigh_scattering=[.2,.4,1.,1.], rayleigh_scattering_scale=.03,
        rayleigh_exponential_distribution=8., mie_scattering=[1.,1.,1.,1.], mie_scattering_scale=.004,
        mie_absorption=[1.,1.,1.,1.], mie_absorption_scale=.0004, mie_anisotropy=.8,
        mie_exponential_distribution=1.2, other_absorption=[.3,1.,.05,1.], other_absorption_scale=.002,
        other_tent_distribution=dict(tip_altitude=25.,tip_value=1.,width=15.))


class AtmosphereTests(unittest.TestCase):
    def test_inventory_loads_minimal_api_settings_by_reflected_class_path(self):
        path=ROOT/'scripts/customrenderpipline/inspect_targetmap.py'
        tree=ast.parse(path.read_text())
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
        reflected_paths={node.args[0].value for node in calls
            if isinstance(node.func,ast.Name) and node.func.id=='reflected_default' and node.args
            and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)}
        load_calls=[node for node in calls if isinstance(node.func,ast.Attribute) and node.func.attr=='load_class']
        self.assertTrue(load_calls)
        self.assertIn('/Script/Engine.RendererSettings',reflected_paths)
        self.assertIn('/Script/WindowsTargetPlatformSettings.WindowsTargetSettings',reflected_paths)
        direct_symbols={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)
            and isinstance(node.value,ast.Name) and node.value.id=='unreal'}
        self.assertNotIn('RendererSettings',direct_symbols)
        self.assertNotIn('WindowsTargetSettings',direct_symbols)
        editor_properties={node.args[0].value for node in calls
            if isinstance(node.func,ast.Attribute) and node.func.attr=='get_editor_property' and node.args
            and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)}
        for cpp_name in ('WorkingColorSpaceChoice','DefaultGraphicsRHI','D3D11TargetedShaderFormats',
                         'D3D12TargetedShaderFormats','VulkanTargetedShaderFormats',
                         'bEnableAlphaChannelInPostProcessing','bMobileEnableAlphaChannelInPostProcessing'):
            self.assertNotIn(cpp_name,editor_properties)
            self.assertIn(cpp_name,path.read_text())

    def test_ground_albedo_196_uses_original_float_literal(self):
        c=component();c['ground_albedo']=[196,0,255,255]
        actual=np.array(component_parameters(c)['GroundAlbedo'],dtype=np.float32).view(np.uint32)
        self.assertEqual(actual.tolist(),[0x3f0d509e,0,0x3f800000])
        analytic=np.float32(((196/255+.055)/1.055)**2.4).view(np.uint32)
        self.assertEqual(int(analytic),0x3f0d509f)

    def test_exact_srgb_table_has_original_literals_and_verified_provenance(self):
        path=ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/UESRGBToLinearTable.json'
        self.assertTrue(path.is_file(),'Missing source sRGB table artifact')
        table=json.loads(path.read_text())
        self.assertIs(table['capture_inputs'],False)
        self.assertEqual(len(table['literals']),256)
        self.assertEqual(table['literals'][196],'0.552011399099209f')
        for byte,literal in enumerate(table['literals']):
            c=component();c['ground_albedo']=[byte]*3
            self.assertEqual(component_parameters(c)['GroundAlbedo'][0],float(np.float32(literal[:-1])))
        source=Path(table['source'])
        if source.is_file():
            data=source.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),table['source_sha256'])
            match=re.search(rb'static constexpr float sRGBToLinearTable\[\]\s*=\s*\{.*?\};',data,re.S)
            self.assertIsNotNone(match)
            self.assertEqual(data[:match.start()].count(b'\n')+1,table['line'])
            self.assertEqual(hashlib.sha256(match.group()).hexdigest(),table['excerpt_sha256'])
            literals=re.findall(rb'\d+\.\d+(?:[eE][+-]?\d+)?f',match.group())
            self.assertEqual([v.decode() for v in literals],table['literals'])

    def test_source_rejects_unverified_or_unsupported_color_and_lut_branches(self):
        settings=inventory();source_atmosphere(settings)
        for key,value in [('working_color_space_choice',2),('working_color_space_choice',True),
                          ('propagate_alpha',1),('mobile_propagate_alpha',1),
                          ('lut_feature_level_branch','mobile'),('lut_format_branch','alpha_rgba'),
                          ('lut_pixel_format','PF_FloatRGBA'),('targeted_shader_formats',['GLSL_ES3_1_ANDROID']),
                          ('working_color_space_chromaticities',{'red':[.64,.33],'green':[.30,.60],'blue':[.15,.06],'white':[.33,.33]}),
                          ('provenance',{})]:
            i=copy.deepcopy(settings);i['renderer_source_settings'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):source_atmosphere(i)
        for key in settings['renderer_source_settings']:
            if key=='working_color_space_choice_name':continue
            i=copy.deepcopy(settings);del i['renderer_source_settings'][key]
            with self.subTest(missing=key),self.assertRaises(ValueError):source_atmosphere(i)
        del settings['renderer_source_settings']
        with self.assertRaises(ValueError):source_atmosphere(settings)

    def test_source_configuration_copy_filters_unrelated_secrets_and_retains_hashes(self):
        path=ROOT/'build/source-project-inventory/run_targetmap.py'
        tree=ast.parse(path.read_text())
        self.assertIn('copy_source_configuration',[n.name for n in tree.body if isinstance(n,ast.FunctionDef)])
        spec=importlib.util.spec_from_file_location('targetmap_launcher_for_test',path)
        launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);project=base/'Original';scratch=base/'Scratch'
            (project/'Config/Windows').mkdir(parents=True);scratch.mkdir()
            original=(b'[/Script/Engine.RendererSettings]\r\nWorkingColorSpaceChoice=2\r\n'
                b'r.PostProcessing.PropagateAlpha=True\r\n'
                b'[/Script/WindowsTargetPlatform.WindowsTargetSettings]\r\n'
                b'DefaultGraphicsRHI=DefaultGraphicsRHI_DX12\r\n+D3D12TargetedShaderFormats=PCD3D_SM6\r\n'
                b'[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]\r\nSecurityToken=private-test-token\r\n')
            engine=project/'Config/DefaultEngine.ini';engine.write_bytes(original)
            platform=project/'Config/Windows/WindowsEngine.ini'
            platform.write_text('[SystemSettings]\nr.SkyAtmosphere.TransmittanceLUT.SampleCount=12\n[Other]\nSecret=unrelated\n')
            (project/'Config/DefaultEditor.ini').write_text('[Other]\nSecret=editor-private\n')
            records=launcher.copy_source_configuration(project,scratch)
            self.assertEqual(len(records),2)
            self.assertEqual(engine.read_bytes(),original)
            copied=(scratch/'Config/DefaultEngine.ini').read_text()
            self.assertIn('WorkingColorSpaceChoice=2',copied)
            self.assertIn('r.PostProcessing.PropagateAlpha=True',copied)
            self.assertIn('+D3D12TargetedShaderFormats=PCD3D_SM6',copied)
            self.assertNotIn('SecurityToken',copied)
            self.assertNotIn('private-test-token',copied)
            self.assertFalse((scratch/'Config/DefaultEditor.ini').exists())
            self.assertIn('SampleCount=12',(scratch/'Config/Windows/WindowsEngine.ini').read_text())
            for record in records:
                for key in ('source','copied'):
                    entry=record[key]
                    self.assertEqual(hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest(),entry['sha256'])
                self.assertTrue(record['sections'])

    def test_reflected_renderer_text_probe_uses_engine_enum_declarations(self):
        path=ROOT/'build/source-project-inventory/run_targetmap.py'
        spec=importlib.util.spec_from_file_location('targetmap_probe_parser_for_test',path)
        launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as tmp:
            engine=Path(tmp)/'Engine'
            renderer=engine/'Engine/Source/Runtime/Engine/Classes/Engine/RendererSettings.h'
            windows=engine/'Engine/Source/Developer/Windows/WindowsTargetPlatformSettings/Classes/WindowsTargetSettings.h'
            renderer.parent.mkdir(parents=True);windows.parent.mkdir(parents=True)
            renderer.write_text('namespace EWorkingColorSpace { enum Type : int { sRGB = 1, Rec2020 = 2, }; }')
            windows.write_text('enum class EDefaultGraphicsRHI : uint8 { DefaultGraphicsRHI_Default = 0, DefaultGraphicsRHI_DX12 = 2, };')
            blocks={
                'WorkingColorSpaceChoice':['0) RendererSettings /Script/Engine.Default__RendererSettings.WorkingColorSpaceChoice = sRGB'],
                'DefaultGraphicsRHI':['0) WindowsTargetSettings /Script/WindowsTargetPlatformSettings.Default__WindowsTargetSettings.DefaultGraphicsRHI = DefaultGraphicsRHI_DX12'],
                'D3D11TargetedShaderFormats':['0) WindowsTargetSettings /Script/WindowsTargetPlatformSettings.Default__WindowsTargetSettings.D3D11TargetedShaderFormats ='],
                'D3D12TargetedShaderFormats':['0) WindowsTargetSettings /Script/WindowsTargetPlatformSettings.Default__WindowsTargetSettings.D3D12TargetedShaderFormats =','  0: PCD3D_SM6'],
                'VulkanTargetedShaderFormats':['0) WindowsTargetSettings /Script/WindowsTargetPlatformSettings.Default__WindowsTargetSettings.VulkanTargetedShaderFormats ='],
                'bEnableAlphaChannelInPostProcessing':['0) RendererSettings /Script/Engine.Default__RendererSettings.bEnableAlphaChannelInPostProcessing = False'],
                'bMobileEnableAlphaChannelInPostProcessing':['0) RendererSettings /Script/Engine.Default__RendererSettings.bMobileEnableAlphaChannelInPostProcessing = False']}
            lines=[]
            for name,xy in {'Red':(.64,.33),'Green':(.30,.60),'Blue':(.15,.06),'White':(.3127,.329)}.items():
                key=name+'ChromaticityCoordinate'
                blocks[key]=[f'0) RendererSettings /Script/Engine.Default__RendererSettings.{key} = (X={xy[0]},Y={xy[1]})']
            for key,body in blocks.items():
                lines.append('LogPython: TARGETMAP_RENDERER_PROPERTY_BEGIN '+key);lines.extend(body)
                lines.append('LogPython: TARGETMAP_RENDERER_PROPERTY_END '+key)
            parsed=launcher.parse_renderer_text_probe('\n'.join(lines),engine)
            self.assertEqual(parsed['working_color_space_choice'],1)
            self.assertEqual(parsed['working_color_space_choice_name'],'sRGB')
            self.assertEqual(parsed['default_graphics_rhi'],2)
            self.assertEqual(parsed['targeted_shader_formats'],['PCD3D_SM6'])
            self.assertEqual(parsed['lut_feature_level_branch'],'desktop')
            self.assertEqual(parsed['lut_format_branch'],'desktop_rgb')
            self.assertEqual(parsed['lut_pixel_format'],'PF_FloatRGB')
            self.assertFalse(parsed['enable_alpha_channel_in_post_processing'])
            self.assertEqual(parsed['working_color_space_chromaticities'],{'red':[.64,.33],'green':[.30,.60],
                'blue':[.15,.06],'white':[.3127,.329]})

    def test_component_units_and_color(self):
        p=component_parameters(component())
        self.assertEqual(p['BottomRadiusKm'],6360.)
        self.assertEqual(p['TopRadiusKm'],6420.)
        np.testing.assert_allclose(p['GroundAlbedo'],[.401977777826949]*3,rtol=0,atol=3e-8)
        np.testing.assert_allclose(p['RayleighScattering'],[.006,.012,.03],rtol=1e-7)
        np.testing.assert_allclose(p['MieExtinction'],[.0044]*3,rtol=1e-7)
        self.assertEqual(p['RayleighDensityExpScale'],-.125)
        self.assertAlmostEqual(p['AbsorptionDensity0ConstantTerm'],-2/3,places=6)
        self.assertAlmostEqual(p['AbsorptionDensity1ConstantTerm'],8/3,places=6)

    def test_source_clamps_and_disabled_tent(self):
        c=component();c.update(atmosphere_height=-2.,multi_scattering_factor=500.,rayleigh_scattering_scale=-1.)
        c['other_tent_distribution']['width']=0.
        p=component_parameters(c)
        self.assertEqual(p['MultiScatteringFactor'],100.)
        self.assertEqual(p['TopRadiusKm'],float(np.float32(6360.1)))
        self.assertEqual(p['RayleighScattering'],[0.,0.,0.])
        self.assertEqual(p['AbsorptionDensity0LayerWidth'],0.)
        self.assertEqual(p['AbsorptionDensity1ConstantTerm'],0.)

    def test_invalid_medium_rejects_before_graph(self):
        for key,value in [('bottom_radius',0.),('mie_exponential_distribution',0.),
                          ('rayleigh_scattering',[1.,float('nan'),1.]),('mie_anisotropy',1.)]:
            c=component();c[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):component_parameters(c)

    def test_native_dependency_and_fractional_samples(self):
        p=component_parameters(component());before=copy.deepcopy(p)
        g=atmosphere_lut_fragment(p,transmittance_size=(31,9),multi_size=(7,3),transmittance_samples=10.5)
        self.assertEqual(p,before)
        self.assertEqual(g['edges'],[['AtmosphereTransmittance.lut','AtmosphereMultiScattering.transmittance']])
        t,m=g['nodes']
        self.assertEqual(t['properties']['resources'][0]['format'],'R11G11B10Float')
        self.assertEqual(t['properties']['resources'][0]['size'],[31,9])
        self.assertEqual(t['properties']['uniforms']['SkyAtmosphere.TransmittanceSampleCount']['value'],10.5)
        self.assertEqual(m['properties']['samplers']['TransmittanceLutTextureSampler'],{'filter':'Linear','address':'Clamp'})
        for kwargs in [dict(transmittance_size=(0,64)),dict(multi_samples=float('nan')),dict(output_format='RGBA8Unorm')]:
            with self.assertRaises(ValueError):atmosphere_lut_fragment(p,**kwargs)

    def test_invalid_physical_block_rejects_before_shader(self):
        for key,value in [('TopRadiusKm',1.),('MieExtinction',[0.,0.,0.]),
                          ('RayleighDensityExpScale',1.),('GroundAlbedo',[1.,2.,1.])]:
            p=component_parameters(component());p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):atmosphere_lut_fragment(p)
        p=component_parameters(component());del p['MiePhaseG']
        with self.assertRaises(ValueError):atmosphere_lut_fragment(p)


if __name__=='__main__':unittest.main()
