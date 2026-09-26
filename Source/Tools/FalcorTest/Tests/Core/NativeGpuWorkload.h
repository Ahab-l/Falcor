#pragma once
#include "Core/API/Fence.h"
#include "Core/API/GpuTimer.h"
#include "Core/API/RenderContext.h"
#include "Core/Error.h"
#include "Core/Pass/ComputePass.h"
#include "Utils/Logger.h"
#include <charconv>
#include <chrono>
#include <cstdlib>
#include <cstring>

namespace Falcor::testing
{
// Test-only, scheduling-sensitive pending-work fixture, NOT a deterministic
// gate. No future host semaphore signal, host event, sleep, or queue adapter.
// Declare retained readback tasks BEFORE this object so exceptional cleanup
// drains the finite work before releasing those tasks and their fences.
class NativeGpuWorkload
{
public:
    // 2M (~18ms locally) can finish during two warmed stacktrace exceptions.
    // 4M (~36ms) gives the observations margin, not an automatic retry. The
    // mandatory pending checks, exact oracle, and <=100ms GPU bound still apply.
    static constexpr uint32_t kDefaultIterations = 4u * 1024u * 1024u;
    static constexpr uint32_t kMaxIterations = 4u * 1024u * 1024u;
    static constexpr double kMaxGpuMilliseconds = 100.0;

    explicit NativeGpuWorkload(RenderContext* context) : mpContext(context)
    {
        FALCOR_CHECK(context, "NativeGpuWorkload needs a render context");
        mpDevice = context->getDevice();
        FALCOR_CHECK(context == mpDevice->getRenderContext(), "NativeGpuWorkload timer requires the device render context");
        mIterations = readIterations();
        mExpected = reference(mIterations);
        mpOutput = mpDevice->createStructuredBuffer(sizeof(uint32_t), 1);
        mpPass = ComputePass::create(mpDevice, "Tests/Core/NativeGpuWorkload.slang");
        mpMarker = mpDevice->createFence();
        mpTimer = GpuTimer::create(mpDevice);

        // Compile, specialize, create the pipeline, validate the uint oracle,
        // and drain all source initialization BEFORE the pending interval.
        dispatch(64);
        mpContext->submit(true);
        uint32_t warmResult = 0;
        mpOutput->getBlob(&warmResult, 0, sizeof(warmResult));
        FALCOR_CHECK(warmResult == reference(64), "NativeGpuWorkload warmup uint oracle failed");
        // Warm the real CPU-only rejection path before the bounded GPU window.
        // This fixture does not certify the first-ever exception's CPU latency.
        const auto errorWarmupStart = std::chrono::steady_clock::now();
        bool rejected = false;
        try { mpContext->asyncReadBuffer(nullptr); }
        catch (const RuntimeError&) { rejected = true; }
        FALCOR_CHECK(rejected, "NativeGpuWorkload invalid-request warmup did not reject");
        logInfo("NATIVE_WORKLOAD_ERROR_WARMUP flags={}, elapsed_us={}", uint32_t(getErrorDiagnosticFlags()),
            std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - errorWarmupStart).count());
    }

    NativeGpuWorkload(const NativeGpuWorkload&) = delete;
    NativeGpuWorkload& operator=(const NativeGpuWorkload&) = delete;

    ~NativeGpuWorkload() noexcept
    {
        // Cleanup only. Tests must capture pending observations before finish().
        if (!mEnqueued || mDrained) return;
        try { mpContext->submit(true); }
        catch (const std::exception& error) { logError("NativeGpuWorkload cleanup failed: {}", error.what()); }
        catch (...) { logError("NativeGpuWorkload cleanup failed with an unknown exception"); }
    }

    void enqueue()
    {
        FALCOR_CHECK(!mEnqueued, "NativeGpuWorkload can only be enqueued once");
        mEnqueued = true;
        mpTimer->begin();
        dispatch(mIterations);
        mpTimer->end();
        mpTimer->resolve();
        mpContext->submit(false);
        // Marker is independently owned and submitted BEFORE tested tasks.
        // If it remains pending AFTER a task reset, that reset cannot have
        // waited for the later task fence. It does not retain any task fence.
        mMarkerValue = mpContext->signal(mpMarker.get(), 1);
        // The resolving GPU signal and all of its dependencies are ALREADY
        // submitted. This legal wait makes marker completion an explicit task
        // prerequisite; it is not a gate waiting for a future host signal.
        mpContext->wait(mpMarker.get(), mMarkerValue);
    }

    bool markerPending() const
    {
        FALCOR_CHECK(mEnqueued && mMarkerValue != 0, "NativeGpuWorkload marker was not submitted");
        return mpMarker->getCurrentValue() < mMarkerValue;
    }

    void finish()
    {
        FALCOR_CHECK(mEnqueued && !mDrained, "NativeGpuWorkload needs exactly one finish");
        mpContext->submit(true);
        mDrained = true;
        mGpuMilliseconds = mpTimer->getElapsedTime();
        uint32_t actual = 0;
        mpOutput->getBlob(&actual, 0, sizeof(actual));
        logInfo("NATIVE_GPU_WORKLOAD iterations={}, gpu_ms={}, actual={}, expected={}",
            mIterations, mGpuMilliseconds, actual, mExpected);
        FALCOR_CHECK(actual == mExpected, "NativeGpuWorkload uint oracle failed");
        FALCOR_CHECK(!markerPending(), "NativeGpuWorkload marker did not complete after drain");
        FALCOR_CHECK(mGpuMilliseconds > 0.0 && mGpuMilliseconds <= kMaxGpuMilliseconds,
            "NativeGpuWorkload GPU duration {} ms is outside (0, {}] ms; fail without automatic retry",
            mGpuMilliseconds, kMaxGpuMilliseconds);
    }

    uint32_t iterations() const { return mIterations; }
    double gpuMilliseconds() const { return mGpuMilliseconds; }

private:
    static uint32_t readIterations()
    {
        const char* value = std::getenv("FALCOR_NATIVE_WORKLOAD_ITERATIONS");
        if (!value) return kDefaultIterations;
        uint32_t result = 0;
        const char* end = value + std::strlen(value);
        const auto parsed = std::from_chars(value, end, result);
        FALCOR_CHECK(parsed.ec == std::errc{} && parsed.ptr == end && result > 0 && result <= kMaxIterations,
            "FALCOR_NATIVE_WORKLOAD_ITERATIONS must be a decimal integer in [1, {}]", kMaxIterations);
        return result;
    }

    static uint32_t reference(uint32_t iterations)
    {
        uint32_t value = kSeed;
        for (uint32_t i = 0; i < iterations; ++i)
        {
            value = (value ^ (value >> 16)) * 1664525u + 1013904223u;
            value ^= i * 747796405u;
        }
        return value;
    }

    void dispatch(uint32_t iterations)
    {
        auto var = mpPass->getRootVar();
        var["gResult"] = mpOutput;
        var["gIterations"] = iterations;
        var["gSeed"] = kSeed;
        mpPass->execute(mpContext, 1, 1);
        mpContext->uavBarrier(mpOutput.get());
    }

    static constexpr uint32_t kSeed = 0x6d2b79f5u;
    ref<Device> mpDevice;
    RenderContext* mpContext;
    ref<Buffer> mpOutput;
    ref<ComputePass> mpPass;
    ref<Fence> mpMarker;
    ref<GpuTimer> mpTimer;
    uint32_t mIterations = 0;
    uint32_t mExpected = 0;
    uint64_t mMarkerValue = 0;
    double mGpuMilliseconds = 0.0;
    bool mEnqueued = false;
    bool mDrained = false;
};
} // namespace Falcor::testing
