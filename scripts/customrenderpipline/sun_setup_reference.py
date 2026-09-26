"""Offline mathematical sun oracle, never used to configure a render pass.

Float64 geometry/integration is intentional. The native UE ground routine uses
float32 radii and positions; source-planet cancellation is reported separately.
The integration schedule retains UE's float accumulator and 15-sample rule.
"""
import math
import numpy as np

def temperature_rgb(kelvin):
    t=min(15000.,max(1000.,kelvin))
    u=(.860117757+1.54118254e-4*t+1.28641212e-7*t*t)/(1+8.42420235e-4*t+7.08145163e-7*t*t)
    v=(.317398726+4.22806245e-5*t+4.20481691e-8*t*t)/(1-2.89741816e-5*t+1.61456053e-7*t*t)
    x=3*u/(2*u-8*v+4);y=2*v/(2*u-8*v+4)
    primaries=np.array([[.64,.30,.15],[.33,.60,.06],[.03,.10,.79]])
    white=np.array([.3127/.329,1,(1-.3127-.329)/.329])
    matrix=primaries@np.diag(np.linalg.solve(primaries,white))
    return np.maximum(0,np.linalg.solve(matrix,[x/y,1,(1-x-y)/y]))

def ground_transmittance(settings):
    p=settings['atmosphere'];direction=np.array(settings['direction_ue'],dtype=float)
    elevation=max(math.asin(direction[2]/np.linalg.norm(direction)),math.radians(settings['transmittance_min_elevation_degrees']))
    radius=p['BottomRadiusKm']+.5
    ray=np.array([math.cos(elevation),0,math.sin(elevation)])
    origin=np.array([0,0,radius]);b=2*np.dot(origin,ray)
    distance=(-b+math.sqrt(b*b-4*(radius*radius-p['TopRadiusKm']**2)))/2
    if distance<=0:return np.ones(3)
    optical=np.zeros(3);t=np.float32(0);step=np.float32(1)/np.float32(15)
    while t<1:
        h=np.linalg.norm(origin+ray*(distance*float(t)))-p['BottomRadiusKm']
        ozone=(p['AbsorptionDensity0LinearTerm']*h+p['AbsorptionDensity0ConstantTerm'] if h<p['AbsorptionDensity0LayerWidth']
               else p['AbsorptionDensity1LinearTerm']*h+p['AbsorptionDensity1ConstantTerm'])
        extinction=math.exp(p['MieDensityExpScale']*h)*np.array(p['MieExtinction'])
        extinction+=math.exp(p['RayleighDensityExpScale']*h)*np.array(p['RayleighScattering'])
        extinction+=np.clip(ozone,0,1)*np.array(p['AbsorptionExtinction'])
        optical+=distance*float(step)*extinction
        t=np.float32(t+step)
    return np.exp(-optical)

def evaluate_reference(settings):
    code=np.array(settings['color_srgb'],dtype=float)/255
    energy=np.where(code<=.04045,code/12.92,((code+.055)/1.055)**2.4)*settings['intensity']
    if settings['use_temperature']:energy*=temperature_rgb(settings['temperature_kelvin'])
    transmittance=ground_transmittance(settings)
    return {'outer_space_illuminance':energy,'ground_transmittance':transmittance,
        'direct_illuminance':energy*transmittance if settings['atmosphere_sun'] else energy}
