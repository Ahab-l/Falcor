"""Offline bilinear and unsigned-float oracles; never a renderer input."""
import numpy as np

def downsample_reference(image,quality='low'):
    a=np.asarray(image,dtype=np.float64);h,w,c=a.shape;oh,ow=(h+1)//2,(w+1)//2
    y,x=np.mgrid[:oh,:ow];x=(x+.5)*w/ow-.5;y=(y+.5)*h/oh-.5
    def sample(dx,dy):
        sx=np.clip(x+dx,0,w-1);sy=np.clip(y+dy,0,h-1)
        ix=np.floor(sx).astype(int);iy=np.floor(sy).astype(int)
        jx=np.minimum(ix+1,w-1);jy=np.minimum(iy+1,h-1)
        fx=(sx-ix)[...,None];fy=(sy-iy)[...,None]
        return (a[iy,ix]*(1-fx)+a[iy,jx]*fx)*(1-fy)+(a[jy,ix]*(1-fx)+a[jy,jx]*fx)*fy
    if quality=='low':return sample(0,0)
    if quality!='high':raise ValueError(quality)
    result=sum(sample(dx,dy) for dx,dy in ((-1,-1),(1,-1),(-1,1),(1,1)))*.25
    result[...,:3]=np.maximum(result[...,:3],0)
    return result

def pack_r11g11b10(rgb, *, rounding='nearest_even'):
    if rounding not in ('nearest_even','toward_zero'):raise ValueError(rounding)
    a=np.asarray(rgb,dtype=np.float64)
    result=np.zeros(a.shape[:-1],dtype=np.uint32)
    for channel,mantissa,shift in ((0,6,0),(1,6,11),(2,5,22)):
        v=np.maximum(a[...,channel],0)
        exp=np.floor(np.log2(np.maximum(v,2.0**-14)))
        step=np.exp2(exp-mantissa)
        rounded=(np.rint(v/step) if rounding=='nearest_even' else np.floor(v/step))*step
        exp2=np.floor(np.log2(np.maximum(rounded,2.0**-14)))
        normal=(rounded>=2.0**-14)
        code=np.where(normal,(exp2+15)*2**mantissa+(rounded/np.exp2(exp2)-1)*2**mantissa,
                      rounded*2**(14+mantissa)).astype(np.uint32)
        code=np.where(rounded>=65536,31<<mantissa,code).astype(np.uint32)
        result|=code<<np.uint32(shift)
    return result

def unpack_r11g11b10(words):
    words=np.asarray(words,dtype=np.uint32);result=np.ones(words.shape+(4,),dtype=np.float32)
    for channel,mantissa,shift in ((0,6,0),(1,6,11),(2,5,22)):
        code=(words>>np.uint32(shift))&np.uint32((1<<(mantissa+5))-1)
        exponent=code>>np.uint32(mantissa);fraction=code&np.uint32((1<<mantissa)-1)
        result[...,channel]=np.where(exponent==0,fraction*2.0**(-14-mantissa),
            (1+fraction/2.0**mantissa)*np.exp2(exponent.astype(np.int32)-15))
    return result
