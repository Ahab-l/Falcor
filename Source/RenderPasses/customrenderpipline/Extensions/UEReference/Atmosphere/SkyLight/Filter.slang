// Compile the complete original filter and permutation blocks as PC compute.
#define USE_COMPUTE 1
#define THREADGROUP_SIZE 8
#include "CubeCommon.slangh"
#include "Helpers.slangh"
#include "../UESkyLightFilter.ush"
