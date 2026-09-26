// One 8x8 group only. Preserve the source's shared-memory reduction and its
// assumption that the final sixteen lanes execute in wave lockstep. This is
// source integration, not a portable rewrite of that synchronization contract.
#define USE_COMPUTE 1
#define SHADER_DIFFUSE_TO_SH 1
#define THREADGROUP_SIZE_X 8
#define THREADGROUP_SIZE_Y 8
#include "CubeCommon.slangh"
#include "DiffuseSHOriginal.slangh"
