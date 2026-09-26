// Compile the complete original compute/pixel conditional block as PC compute.
#define USE_COMPUTE 1
#define THREADGROUP_SIZE 8
#include "CubeCommon.slangh"
#include "../UESkyLightDownsample.ush"
