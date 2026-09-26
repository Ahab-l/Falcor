"""Offline FP64 SkyView oracle; outputs/readbacks never enter rendering.

The independent mathematics retains the source angular parameterization,
quadratic variable-length segments, 0.3 sample offset, both phase functions,
planet shadow and multi-scattering. Hardware sampling/FP32/storage rounding
remain separate from this ideal integration. No shader text is evaluated.
"""
import math
import numpy as np
from atmosphere_reference import (_pixel_uv,_dot,_sphere_intersections,_path_end,_medium,
    _transmittance_coordinates,sample_encoded_transmittance)


def sky_view_directions(height,bottom,size):
    w,h=size
    uv=(_pixel_uv(size,np.float64)-.5/np.array(size))*np.array(size)/(np.array(size)-1)
    cosine=np.sqrt(height*height-bottom*bottom)/height
    x=abs(cosine)
    beta=np.sqrt(1-x)*(1.5707288-.2121144*x+.0742610*x*x-.0187293*x*x*x)
    horizon=math.pi-beta
    y=uv[...,1]
    zenith=np.where(y<.5,horizon*(1-(1-2*y)**2),horizon+beta*(2*y-1)**2)
    z=np.cos(zenith);s=np.sqrt(np.maximum(0,1-z*z))*np.where(zenith>0,1,-1)
    longitude=2*math.pi*uv[...,0];c=np.cos(longitude)
    t=np.sqrt(np.maximum(0,1-c*c))*np.where(longitude<=math.pi,1,-1)
    return np.stack((s*c,s*t,z),axis=-1)


def sample_linear(texture,uv):
    texture=np.asarray(texture,dtype=np.float64);h,w,_=texture.shape
    pos=np.clip(uv*np.array([w,h])-.5,[0,0],[w-1,h-1]);base=np.floor(pos).astype(int)
    fraction=pos-base;x,y=base[...,0],base[...,1];x1=np.minimum(w-1,x+1);y1=np.minimum(h-1,y+1)
    fx,fy=fraction[...,0,None],fraction[...,1,None]
    return (texture[y,x]*(1-fx)+texture[y,x1]*fx)*(1-fy)+(texture[y1,x]*(1-fx)+texture[y1,x1]*fx)*fy


def sky_view_reference(parameters,settings,view_height,light_direction,illuminance,transmittance,multi_scattering,*,pre_exposure=1.):
    p={k:np.asarray(v,dtype=np.float64) for k,v in parameters.items()}
    direction=sky_view_directions(view_height,float(p['BottomRadiusKm']),settings['size'])
    origin=np.zeros_like(direction);origin[...,2]=view_height
    intersects=np.ones(direction.shape[:-1],dtype=bool)
    if view_height>p['TopRadiusKm']:
        near,far=_sphere_intersections(origin,direction,p['TopRadiusKm'])
        t=np.where(near>=0,near,far);intersects=t>=0
        origin+=direction*np.where(intersects,t,0)[...,None]
        origin[...,2]-=.001
    distance,_=_path_end(origin,direction,p);distance=np.where(intersects,distance,0)
    count=settings['min_samples']+(settings['max_samples']-settings['min_samples'])*np.clip(distance*settings['distance_to_max_inv'],0,1)
    whole=np.floor(count);whole_distance=distance*whole/count
    light=np.asarray(light_direction,dtype=float)
    cos_theta=_dot(direction,light)
    phase_ray=3/(16*math.pi)*(1+cos_theta*cos_theta)
    phase_mie=(1-p['MiePhaseG']**2)/(4*math.pi*(1+p['MiePhaseG']**2-2*p['MiePhaseG']*cos_theta)**1.5)
    luminance=np.zeros_like(direction);throughput=np.ones_like(direction)
    irradiance=np.asarray(illuminance)*np.asarray(settings['luminance_factor'])*pre_exposure
    for i in range(math.ceil(float(np.max(count)))):
        active=(i<count)&intersects
        begin=whole_distance*(i/whole)**2
        end=np.where(((i+1)/whole)**2>1,distance,whole_distance*((i+1)/whole)**2)
        dt=np.where(active,end-begin,0)
        position=origin+direction*np.where(active,begin+.3*dt,0)[...,None]
        radius=np.linalg.norm(position,axis=-1);altitude=np.maximum(0,radius-p['BottomRadiusKm'])
        scattering,extinction=_medium(position,p)
        phase_scattering=(p['MieScattering']*np.exp(p['MieDensityExpScale']*altitude)[...,None]*phase_mie[...,None]+
            p['RayleighScattering']*np.exp(p['RayleighDensityExpScale']*altitude)[...,None]*phase_ray[...,None])
        up=position/radius[...,None];cos_sun=_dot(up,light)
        near,far=_sphere_intersections(position,light,p['BottomRadiusKm'],.001*up)
        visible=(near<0)&(far<0)
        sunlight=sample_encoded_transmittance(transmittance,_transmittance_coordinates(radius,cos_sun,p))
        uv=np.stack((cos_sun*.5+.5,(radius-p['BottomRadiusKm'])/(p['TopRadiusKm']-p['BottomRadiusKm'])),axis=-1)
        ms=sample_linear(multi_scattering,np.clip(uv,0,1))
        source=irradiance*(visible[...,None]*sunlight*phase_scattering+ms*scattering)
        optical=extinction*dt[...,None]
        luminance+=throughput*source*(-np.expm1(-optical))/np.maximum(extinction,1e-9)
        throughput*=np.exp(-optical)
    result=np.concatenate((luminance,np.mean(throughput,axis=-1)[...,None]),axis=-1)
    return np.where(intersects[...,None],result,0)
