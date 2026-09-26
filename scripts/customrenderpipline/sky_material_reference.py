"""Offline sky material geometry/math; never upload these results to rendering."""
import math
import numpy as np
from atmosphere_reference import _transmittance_coordinates,sample_encoded_transmittance,_sphere_intersections
from sky_view_reference import sample_linear


def positive_half_toward_zero(value):
    """D3D render-target conversion used by these positive RGBA16Float controls."""
    value=np.asarray(value,dtype=float)
    nearest=value.astype(np.float16)
    return np.where(nearest>value,np.nextafter(nearest,np.float16(0)),nearest).astype(float)


def constant_sky_quantization_bounds(size,frame_index,sampled_rgb,factor):
    """Conservative FP32/noise interval, followed by native half truncation.

    Bounds include source literal, coordinate, dot and product roundoff. Fraction
    wrap crossings explicitly widen to [0,1]. This is an arithmetic enclosure
    for constant test inputs, not a proof about arbitrary filtered source LUTs.
    """
    w,h=size;y,x=np.mgrid[:h,:w];eps=np.finfo(np.float32).eps
    coords=np.stack((x+.5,y+.5),axis=-1)+(frame_index&7)*np.array([47,17])*.695
    dot=coords@np.array([.06711056,.00583715]);fraction=np.mod(dot,1)
    dot_error=8*eps*np.maximum(1,np.abs(coords)@np.array([.06711056,.00583715]))
    product=fraction*52.9829189;noise=np.mod(product,1)
    noise_error=52.9829189*dot_error+4*eps*np.maximum(1,np.abs(product))
    wraps=(fraction<dot_error)|(fraction>1-dot_error)|(noise<noise_error)|(noise>1-noise_error)
    lo=np.where(wraps,0,np.maximum(0,noise-noise_error))
    hi=np.where(wraps,1,np.minimum(1,noise+noise_error))
    color=np.asarray(sampled_rgb)*np.asarray(factor,dtype=np.float32)
    if color.shape!=(3,) or not np.isfinite(color).all() or np.any((color<.125)|(color>32000)):
        raise ValueError('Constant quantization controls require three finite positive normal-range colors')
    step=np.exp2(np.floor(np.log2(color/1024)))
    arithmetic_error=4*eps*(color+step)
    if np.any(np.floor(np.log2((color-arithmetic_error)/1024))!=np.floor(np.log2((color+arithmetic_error)/1024))):
        raise ValueError('Constant quantization controls must stay away from exponent boundaries')
    return (positive_half_toward_zero(color+step*lo[...,None]-arithmetic_error),
            positive_half_toward_zero(color+step*hi[...,None]+arithmetic_error))


def perspective_directions(position,target,up,focal,frame_height,size):
    w,h=size
    forward=np.asarray(target,dtype=float)-position;forward/=np.linalg.norm(forward)
    right=np.cross(forward,up);right/=np.linalg.norm(right)
    vertical=np.cross(right,forward)
    y,x=np.mgrid[:h,:w];scale=2*focal/frame_height
    ray=(forward+right*((2*(x+.5)/w-1)*w/h/scale)[...,None]
         +vertical*((1-2*(y+.5)/h)/scale)[...,None])
    ray/=np.linalg.norm(ray,axis=-1,keepdims=True)
    return np.stack((-ray[...,2],ray[...,0],ray[...,1]),axis=-1)


def sky_uv(directions,setup,bottom,size):
    """Independent angular mapping, retaining the UE fast trig approximation."""
    local=np.asarray(directions)@np.asarray(setup[2:5,:3],dtype=float).T
    height=float(setup[1,3])*float(np.float32(.00001))
    origin=np.array([0,0,height]);a,b=_sphere_intersections(origin,local,bottom)
    ground=(a>0)|(b>0)
    def acos_approx(x):
        t=np.abs(x)
        angle=np.sqrt(1-t)*(1.5707288-.2121144*t+.0742610*t*t-.0187293*t*t*t)
        return np.where(x>=0,angle,math.pi-angle)
    beta=acos_approx(np.sqrt(height*height-bottom*bottom)/height)
    horizon=math.pi-beta;zenith=acos_approx(local[...,2])
    y=np.where(ground,.5+.5*np.sqrt(np.maximum(0,(zenith-horizon)/beta)),
        .5*(1-np.sqrt(np.maximum(0,1-zenith/horizon))))
    dy,dx=-local[...,1],-local[...,0]
    largest=np.maximum(abs(dx),abs(dy));ratio=np.minimum(abs(dx),abs(dy))/largest
    angle=ratio*(1-.301895*ratio**2+.0872929*ratio**4)
    angle=np.where(abs(dy)>abs(dx),math.pi/2-angle,angle)
    angle=np.where(dx<0,math.pi-angle,angle);angle=np.where(dy<0,-angle,angle)
    u=(angle+math.pi)/(2*math.pi)
    uv=np.stack((u,y),axis=-1)
    return (uv*np.array(size)+.5)/(np.array(size)+1)


def sky_color(directions,setup,physical,sky_lut,transmittance_lut,factor,pre_exposure,frame_index):
    """Ideal FP64 sampling plus source noise; hardware storage errors are separate."""
    height,width,_=directions.shape
    lut_h,lut_w,_=sky_lut.shape
    uv=sky_uv(directions,setup,physical['BottomRadiusKm'],(lut_w,lut_h))
    view=sample_linear(sky_lut,uv)*np.asarray(factor)/pre_exposure
    exponent=np.floor(np.log2(np.maximum(view/1024,np.finfo(float).tiny)))
    error=np.where(view>0,np.exp2(exponent),0)
    y,x=np.mgrid[:height,:width]
    coords=np.stack((x+.5,y+.5),axis=-1)+(frame_index&7)*np.array([47,17])*.695
    noise=np.mod(52.9829189*np.mod(coords@np.array([.06711056,.00583715]),1),1)
    view+=error*noise[...,None]
    planet=(setup[0,:3].astype(float)-setup[1,:3])*float(np.float32(.00001))
    radius=np.linalg.norm(planet)
    a,b=_sphere_intersections(planet,directions,physical['BottomRadiusKm'])
    ground=(a>0)|(b>0)
    cosine=np.einsum('...i,i->...',directions,planet/radius)
    trans_uv=_transmittance_coordinates(np.full_like(cosine,radius),cosine,physical)
    trans=sample_encoded_transmittance(transmittance_lut,trans_uv)
    light_cos=np.einsum('...i,i->...',directions,setup[6,:3])
    apex=math.cos(float(setup[8,3]))
    soft=np.clip(2*(light_cos-apex)/(1-apex),0,1)
    disk=np.where(ground[...,None],0,trans*setup[8,:3]*soft[...,None])
    return (view+disk)*pre_exposure,uv,disk
