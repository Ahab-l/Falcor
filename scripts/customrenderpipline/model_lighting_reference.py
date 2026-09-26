"""Dependency-light CPU lighting oracle extracted from model_lighting_smoke.py.

Source provenance: source-before.zip member scripts/customrenderpipline/model_lighting_smoke.py,
SHA-256 60b700366caa855ff5de555190843629cf7367af888fc9aa0314174b7894a1ab.
This module is numerical reference data only and creates no RenderGraph/device.
"""
import colorsys
import hashlib
from pathlib import Path
import numpy as np
import capsule_lighting_smoke as capsule

MODEL_IDS = {'Unlit':0, 'DefaultLit':1, 'Subsurface':2, 'TwoSidedFoliage':6, 'Cloth':8}


def source_record(path):
    path = Path(path)
    return {'path':str(path), 'bytes':path.stat().st_size, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def unit(value):
    v = np.asarray(value, dtype=np.float64)
    return v / np.linalg.norm(v)


def absorption_color(color, distance):
    # Independent maximum-channel hue sectors, not the shader's HCV swizzles.
    # UE's 1e-10 denominators remain algorithmic: dark absorption can desaturate.
    raw=np.clip(color,1e-12,1)**(1/max(distance,1e-12))
    maximum=float(max(raw))
    chroma=maximum-float(min(raw))
    denominator=6*chroma+1e-10
    r,g,b=raw
    largest=int(np.argmax(raw))
    if largest==0:
        hue=(g-b)/denominator+(1 if b>g else 0)
    elif largest==1:
        hue=1/3+(b-r)/denominator
    else:
        hue=2/3+(r-g)/denominator
    saturation=chroma/(maximum+1e-10)
    return np.asarray(colorsys.hsv_to_rgb(float(hue),saturation,float(max(color))))


def case(name, model, **overrides):
    c = dict(name=name, model=model, base=[.125,.5,.75], metallic=.35, specular=.5,
        N=[0,0,1], V=unit([.4,.2,1]).tolist(), diffuseL=unit([-.3,.1,1]).tolist(),
        specularL=unit([-.3,.1,1]).tolist(), roughness=.5, falloff=.4,
        falloffColor=[.7,1.2,.5], sphere=0., soft=0., line=1.,
        customColor=[.8,.25,.03], opacity=.4, cloth=.5, ao=1.,
        surfaceShadow=.6, transmissionShadow=.2, transmittance=.4, distance=.15)
    c.update(overrides)
    return c


def pack(c, ids=MODEL_IDS):
    NoL = float(np.clip(np.dot(c['N'], c['diffuseL']), 0, 1))
    return np.asarray([[*c['base'],c['metallic']], [*c['N'],c['roughness']],
        [*c['V'],c['specular']], [*c['diffuseL'],NoL], [*c['specularL'],c['falloff']],
        [*c['falloffColor'],c['sphere']], [*c['customColor'],c['opacity']],
        [c['soft'],c['line'],c['cloth'],c['ao']],
        [c['surfaceShadow'],c['transmissionShadow'],c['transmittance'],c['distance']],
        [ids[c['model']],0,0,0]], dtype=np.float32)


def default_or_cloth(p, cloth):
    N, V, L = p[1,:3], p[2,:3], p[4,:3]
    NoL, rough = p[3,3], p[1,3]
    # DefaultLit itself guards front NoL; transmission models run outside it.
    if NoL <= 0 and not cloth:
        return np.zeros((2,3)), {'branch':'backface', 'ggx_d':1.}
    context, branch = capsule.sphere_context(capsule.initial_context(N,V,L),p[5,3],True)
    NoV = np.clip(abs(context['NoV'])+1e-5,0,1)
    NoH, VoH = context['NoH'], context['VoH']
    area = {'soft':p[7,0], 'sphere':p[5,3], 'line':p[7,1]}
    a2, energy = capsule.energy_oracle(rough,VoH,area)
    denominator = 1-(1-a2)*NoH**2
    if denominator < .01 and NoH < 1:
        raise ValueError('Unconditioned fixture GGX denominator')
    f0 = (1-p[0,3])*(.08*p[2,3]) + p[0,3]*p[0,:3]
    fc = (1-VoH)**5
    fresnel = np.clip(50*f0[1],0,1)*fc + (1-fc)*f0
    root = np.sqrt(a2)
    visibility = .5/(NoL*(NoV*(1-root)+root)+NoV*(NoL*(1-root)+root))
    geometry = p[5,:3]*p[4,3]*NoL
    diffuse = geometry*p[0,:3]*(1-p[0,3])/np.pi
    specular = geometry*a2*energy/(np.pi*denominator**2)*visibility*fresnel
    if cloth:
        # Actual UE inverse GGX, deliberately expressed through sin^2(thetaH).
        fuzz_a2 = rough**4
        fuzz_denominator = NoH**2 + fuzz_a2*(1-NoH**2)
        inverse_ggx = (1+4*fuzz_a2**2/fuzz_denominator**2)/(np.pi*(1+4*fuzz_a2))
        cloth_vis = 1/(4*(NoL+NoV-NoL*NoV))
        fuzz = p[6,:3]
        fuzz_fresnel = np.clip(50*fuzz[1],0,1)*fc+(1-fc)*fuzz
        spec2 = geometry*inverse_ggx*cloth_vis*fuzz_fresnel
        weight = np.clip(p[7,2],0,1)
        specular = (1-weight)*specular+weight*spec2
    return np.asarray([diffuse,specular]), {'branch':branch,'ggx_d':float(denominator)}


def oracle(packed, model):
    p = packed.astype(np.float64)
    if not np.isfinite(p).all() or not 0.02 <= p[1,3] <= 1:
        raise ValueError('Invalid component inputs')
    result = np.zeros((3,4),dtype=np.float64)
    result[0,3]=1
    details = {}
    if model == 'Unlit':
        return result, details
    result[:2,:3], details = default_or_cloth(p, model=='Cloth')
    L,N,V = p[3,:3],p[1,:3],p[2,:3]
    incident = p[5,:3]*p[4,3]
    if model == 'TwoSidedFoliage':
        wrapped = np.clip((.5-np.dot(N,L))/2.25,0,1)
        cosine = np.clip(-np.dot(V,L),0,1)
        scatter = .36/(np.pi*(1-.64*cosine*cosine)**2)
        result[2,:3] = incident*wrapped*scatter*p[6,:3]
        details.update(wrapped=float(wrapped), scatter=float(scatter))
    elif model == 'Subsurface':
        opacity, color = p[6,3],p[6,:3]
        in_scatter = np.clip(-np.dot(L,V),0,1)**12*(3*(1-opacity)+.1*opacity)
        wrapped = np.clip((np.dot(N,L)+.5)/1.5,0,1)**1.5*(2.5/1.5)
        back = p[7,3]*((1-opacity)+opacity*wrapped)/(2*np.pi)
        transmitted = absorption_color(color,p[8,3])
        t = p[8,2]
        result[2,:3] = incident*(back*(1-in_scatter)+in_scatter)*((1-t)*transmitted+t*color)
        details.update(in_scatter=float(in_scatter),wrapped=float(wrapped),backscatter=float(back),
            absorbed_color=transmitted.tolist())
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite oracle result')
    return result, details


def fixtures():
    items=[]
    back=unit([.1,0,-1]).tolist()
    for model in MODEL_IDS:
        for rough in (.25,.5,1.):
            for side in ('front','back'):
                for area in (False,True):
                    kwargs=dict(roughness=rough)
                    if side=='back':
                        kwargs.update(diffuseL=back,specularL=back,V=unit([.2,.3,1]).tolist())
                    if area:
                        kwargs.update(sphere=.04,soft=.02,line=.8)
                    items.append(case(f'{model}-{rough}-{side}-{area}',model,**kwargs))
    for opacity in (0.,.4,1.):
        for distance in (.05,.15,1.):
            for transmittance in (0.,.4,1.):
                items.append(case(f'sss-{opacity}-{distance}-{transmittance}','Subsurface',
                    opacity=opacity,distance=distance,transmittance=transmittance,
                    diffuseL=back,specularL=back,V=[0,0,1]))
    for index,color in enumerate(([0,0,0],[1,1,1],[0,.2,1],[1e-14,1e-6,.8],[.25,.25,.25], [.03,.8,.25])):
        items.append(case(f'sss-color-{index}','Subsurface',customColor=color,transmittance=0))
    for index,color in enumerate(([.2,.1,.05],[.1,.2,.05],[.1,.05,.2])):
        items.append(case(f'sss-dark-absorption-{index}','Subsurface',customColor=color,distance=.05,transmittance=0))
    for ao in (0.,.2):
        items.append(case('sss-ao-'+str(ao),'Subsurface',ao=ao))
    for weight in (0.,.37,1.):
        for color in ([.4,0,.25],[0,0,0],[.7,.5,.2]):
            items.append(case(f'cloth-{weight}-{color}','Cloth',cloth=weight,customColor=color))
    items.append(case('cloth-desktop-grazing-visibility','Cloth',cloth=1,
        V=unit([1,0,.01]).tolist(),diffuseL=unit([1,.1,.01]).tolist(),specularL=unit([1,.1,.01]).tolist()))
    for weight in (-.2,1.2):
        items.append(case('cloth-clamped-weight-'+str(weight),'Cloth',cloth=weight))
    items.append(case('cloth-different-directions','Cloth',diffuseL=[0,.6,.8],specularL=[-.8,0,.6]))
    for index,(opacity,ao) in enumerate(((0.,.2),(1.,1.))):
        items.append(case('foliage-independent-'+str(index),'TwoSidedFoliage',opacity=opacity,ao=ao))
    # DiffuseL deliberately differs from SpecularL: detect using the wrong area direction.
    for model in ('TwoSidedFoliage','Subsurface'):
        items.append(case(model+'-different-directions',model,diffuseL=back))
    return items
