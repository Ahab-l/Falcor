"""Authored ordinary PC Histogram settings, independent of capture state.

Formulas: Renderer/Private/PostProcess/PostProcessEyeAdaptation.cpp:376,446,
533,593-774 at engine 53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0.
Defaults: Engine/Private/Scene.cpp:494-521 and SceneView.cpp:196. The test
project enables extended luminance. Speed >=0.02 is Scene.h authoring domain.
Curve/meter texture selection and GPU math belong to exposure_graph/shaders.
"""
from dataclasses import dataclass,fields
import math

def _finite(value,name,positive=False):
    if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>3.4028234663852886e38:
        raise ValueError(name+' requires finite float32')
    if positive and value < 1.1754943508222875e-38:
        raise ValueError(name+' requires positive normal float32')
    return float(value)

@dataclass(frozen=True)
class HistogramExposureSettings:
    extended: bool = True
    min_brightness: float = -10.0
    max_brightness: float = 20.0
    histogram_min: float = -10.0
    histogram_max: float = 20.0
    low_percent: float = 10.0
    high_percent: float = 90.0
    speed_up: float = 3.0
    speed_down: float = 1.0
    transition_distance: float = 1.5
    lens_attenuation: float = 0.78
    bias_ev: float = 1.0
    black_bucket_influence: float = 0.0
    luminance_method: int = 0
    working_luminance_weights: tuple | None = None

    @classmethod
    def from_dict(cls,values):
        if type(values) is not dict or set(values)-{f.name for f in fields(cls)}:
            raise ValueError('Unknown/invalid Histogram exposure settings')
        values=dict(values)
        if values.get('extended') is False:
            for k,v in dict(min_brightness=0.03,max_brightness=2.0,histogram_min=-8.0,histogram_max=4.0).items():
                values.setdefault(k,v)
        return cls(**values)

    def __post_init__(self):
        if type(self.extended) is not bool:raise ValueError('extended must be bool')
        if type(self.luminance_method) is not int or self.luminance_method not in (0,1,2):
            raise ValueError('luminance_method must be 0,1,2')
        if self.working_luminance_weights is not None:
            weights=self.working_luminance_weights
            if type(weights) not in (tuple,list) or len(weights)!=3:raise ValueError('Working luminance weights need three coefficients')
            weights=tuple(_finite(v,'working_luminance_weights') for v in weights)
            if min(weights)<0 or abs(sum(weights)-1)>1e-4:raise ValueError('Working luminance weights must be nonnegative and sum to one')
            object.__setattr__(self,'working_luminance_weights',weights)
        if self.luminance_method==2 and self.working_luminance_weights is None:
            raise ValueError('Working-space luminance method requires authored color-space coefficients')
        for f in fields(self):
            if f.name not in ('extended','luminance_method','working_luminance_weights'):_finite(getattr(self,f.name),f.name)
        if self.speed_up<0.02 or self.speed_down<0.02:raise ValueError('UE authored exposure speeds must be >=0.02')
        if self.transition_distance<=0:raise ValueError('transition_distance must be positive')
        if not 0<=self.black_bucket_influence<=1:raise ValueError('black_bucket_influence must be in 0..1')
        if not self.extended and min(self.min_brightness,self.max_brightness)<=0:
            raise ValueError('Nonextended white-point luminance must be positive')
        self.parameters(delta_time=0,history_valid=True)

    def parameters(self,*,delta_time,history_valid,camera_cut=False):
        dt=_finite(delta_time,'delta_time')
        if dt<0 or type(history_valid) is not bool or type(camera_cut) is not bool:
            raise ValueError('Time must be nonnegative and history/cut flags boolean')
        try:
            maximum=0.78/max(self.lens_attenuation,0.01) if self.extended else 1.0
            offset=math.log2(maximum) if self.extended else 0.0
            hi=self.histogram_max+offset
            lo=min(self.histogram_min+offset,hi-1)
            high_percent=min(99,max(1,self.high_percent))*0.01
            low_percent=min(min(99,max(1,self.low_percent))*0.01,high_percent)
            white_min=maximum*2**self.min_brightness if self.extended else self.min_brightness
            white_max=maximum*2**self.max_brightness if self.extended else self.max_brightness
            white_min=min(white_min,white_max)
            p=dict(ExposureLowPercent=low_percent,ExposureHighPercent=high_percent,
                MinAverageLuminance=white_min*0.18,MaxAverageLuminance=white_max*0.18,
                ExposureCompensationSettings=2**self.bias_ev,ExposureCompensationCurve=1.0,
                DeltaWorldTime=dt,ExposureSpeedUp=self.speed_up,ExposureSpeedDown=self.speed_down,
                HistogramScale=1/(hi-lo),HistogramBias=-lo/(hi-lo),LuminanceMin=2**lo,
                BlackHistogramBucketInfluence=self.black_bucket_influence,GreyMult=0.18,
                LuminanceWeights=([1/3]*3 if self.luminance_method==0 else
                                  [0.3,0.59,0.11] if self.luminance_method==1 else list(self.working_luminance_weights)),
                StartDistance=self.transition_distance,LuminanceMax=maximum,
                ForceTarget=float(camera_cut or not history_valid or self.min_brightness>=self.max_brightness),
                EV100ToExposureCompensationCurveLUTScaleBias=[63/(64*30),0.5/64+10*63/(64*30)])
            for suffix,speed in (('Up',self.speed_up),('Down',self.speed_down)):
                p['Exponential'+suffix+'M']=(1/60)/((1-2**(-speed/60))*(self.transition_distance/max(speed,0.001)))
            for name,value in p.items():
                for v in value if isinstance(value,list) else [value]:_finite(v,name)
            for name in ('MinAverageLuminance','MaxAverageLuminance','LuminanceMin','LuminanceMax',
                         'ExposureCompensationSettings','HistogramScale','ExponentialUpM','ExponentialDownM'):
                _finite(p[name],name,positive=True)
            return {'EyeAdaptation_'+key:value for key,value in p.items()}
        except (OverflowError,ZeroDivisionError) as error:
            raise ValueError('Exposure settings produce nonfinite parameters') from error
