"""Independent SkyLight reference mathematics; old graph/ABI wrapper retired."""
import re
import numpy as np
from sky_light_filter import SHADER_DIRECTORY

SHADER = SHADER_DIRECTORY/'Lighting.slang'




def evaluate_sky_reference(*,base_color,metallic,specular,roughness,normal,view,sh,reflected,ab,
                           sky_color,ao=1.,screen_ao=1.,pre_exposure=1.):
    """Independent numerical assertion oracle; it never authors GPU resources."""
    n = np.asarray(normal,dtype=float); n = n/np.linalg.norm(n)
    v = np.asarray(view,dtype=float); v = v/np.linalg.norm(v)
    x,y,z = n
    sh = np.asarray(sh)
    irradiance = np.maximum(sh[:3]@[x,y,z,1]+sh[3:6]@[x*y,y*z,z*z,z*x]+sh[6,:3]*(x*x-y*y),0)
    diffuse_color = np.asarray(base_color)*(1-metallic)
    f0 = .08*specular*(1-metallic)+np.asarray(base_color)*metallic
    diffuse = irradiance*np.asarray(sky_color)*min(ao,screen_ao)*diffuse_color*pre_exposure
    no_v = np.clip(n@v,0,1)
    visibility = np.clip((no_v+ao*screen_ao)**(roughness*roughness)-1+ao*screen_ao,0,1)
    environment_brdf = f0*ab[0]+np.clip(50*f0[1],0,1)*ab[1]
    reflection = np.asarray(reflected)*np.asarray(sky_color)*visibility*pre_exposure*environment_brdf
    return diffuse,np.maximum(reflection,0)
