RWStructuredBuffer<uint> gResult;
uint gIterations;
uint gSeed;

// One invocation, bounded work, no host communication or device spinlock.
// Every iteration depends on the previous result; the CPU recomputes it.
[numthreads(1, 1, 1)]
void main()
{
    uint value = gSeed;
    [loop]
    for (uint i = 0; i < gIterations; ++i)
    {
        value = (value ^ (value >> 16)) * 1664525u + 1013904223u;
        value ^= i * 747796405u;
    }
    gResult[0] = value;
}
