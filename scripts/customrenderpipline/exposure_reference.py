"""Offline NumPy oracle for analytic-image GPU validation; never a render input."""
import math
import numpy as np

def histogram_reference(scene_color,pre_exposure,parameters):
    p={k.removeprefix('EyeAdaptation_'):v for k,v in parameters.items()}
    rgb=np.asarray(scene_color,dtype=np.float32)[...,:3]*np.float32(1/pre_exposure)
    luminance=np.maximum(np.sum(rgb*np.asarray(p['LuminanceWeights'],dtype=np.float32),axis=-1,dtype=np.float32),
                         np.float32(p['LuminanceMin']))
    position=np.clip(np.log2(luminance)*np.float32(p['HistogramScale'])+np.float32(p['HistogramBias']),0,1)*np.float32(63)
    lower=position.astype(np.int32);upper=np.minimum(lower+1,63)
    fraction=position-lower.astype(np.float32)
    lower_weight=(1-fraction)*np.where(lower==0,np.float32(p['BlackHistogramBucketInfluence']),np.float32(1))
    weights0=(lower_weight*np.float32(1<<19)).astype(np.uint64)
    weights1=(fraction*np.float32(1<<19)).astype(np.uint64)
    totals=np.zeros(64,dtype=np.uint64)
    np.add.at(totals,lower.ravel(),weights0.ravel());np.add.at(totals,upper.ravel(),weights1.ravel())
    scatter=np.stack([totals&np.uint64(0xffffffff),totals>>np.uint64(32)],axis=1).astype(np.uint32).ravel()
    histogram=totals.astype(np.float64)/float(1<<19)*0.5/luminance.size
    return scatter,histogram

def adaptation_reference(histogram,old_scale,delta_time,parameters,valid=True):
    p={k.removeprefix('EyeAdaptation_'):v for k,v in parameters.items()}
    bins=np.asarray(histogram,dtype=np.float64).reshape(64)
    # Intersect every bin's CDF interval with the accepted percentile interval.
    cdf=np.concatenate(([0.0],np.cumsum(bins)))
    accepted=np.maximum(0,np.minimum(cdf[1:],cdf[-1]*p['ExposureHighPercent'])-
                          np.maximum(cdf[:-1],cdf[-1]*p['ExposureLowPercent']))
    if abs(p['ExposureHighPercent']-p['ExposureLowPercent'])<0.0001:average=1.0
    elif accepted.sum()==0:average=p['MinAverageLuminance']/0.18
    else:
        logs=(np.arange(64)/63-p['HistogramBias'])/p['HistogramScale']
        average=2**float(np.dot(logs,accepted)/accepted.sum())
    target=np.clip(average,p['MinAverageLuminance'],p['MaxAverageLuminance'])/0.18
    compensation=p['ExposureCompensationSettings']*p['ExposureCompensationCurve']
    old=compensation/(old_scale if old_scale else 1)
    distance=math.log2(target/old)
    which='Up' if distance>0 else 'Down'
    speed=p['ExposureSpeed'+which]
    if abs(distance)>p['StartDistance']:
        log_step=math.copysign(min(abs(distance),speed*delta_time),distance)
    else:log_step=distance*(-math.expm1(-math.log(2)*speed*delta_time))*p['Exponential'+which+'M']
    adapted=old*2**log_step
    if not valid or p['ForceTarget']:adapted=target
    adapted=np.clip(adapted,p['MinAverageLuminance']/0.18,p['MaxAverageLuminance']/0.18)
    return np.array([[compensation/max(0.0001,adapted),compensation/max(0.0001,target),average,compensation],
                     [1,0,0,0]],dtype=np.float64)
