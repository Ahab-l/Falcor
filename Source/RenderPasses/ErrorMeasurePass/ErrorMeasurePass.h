/***************************************************************************
 # Copyright (c) 2015-23, NVIDIA CORPORATION. All rights reserved.
 #
 # Redistribution and use in source and binary forms, with or without
 # modification, are permitted provided that the following conditions
 # are met:
 #  * Redistributions of source code must retain the above copyright
 #    notice, this list of conditions and the following disclaimer.
 #  * Redistributions in binary form must reproduce the above copyright
 #    notice, this list of conditions and the following disclaimer in the
 #    documentation and/or other materials provided with the distribution.
 #  * Neither the name of NVIDIA CORPORATION nor the names of its
 #    contributors may be used to endorse or promote products derived
 #    from this software without specific prior written permission.
 #
 # THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS" AND ANY
 # EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 # IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 # PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 # CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 # EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 # PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 # PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
 # OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 # (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 # OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 **************************************************************************/
#pragma once
#include "Falcor.h"
#include "RenderGraph/RenderPass.h"
#include "Utils/Algorithm/ParallelReduction.h"
#include <chrono>
#include <deque>
#include <fstream>

using namespace Falcor;

class ErrorMeasurePass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(ErrorMeasurePass, "ErrorMeasurePass", "Measures error with respect to a reference image.");

    enum class OutputId
    {
        Source,
        Reference,
        Difference,
        Count
    };

    FALCOR_ENUM_INFO(
        OutputId,
        {
            {OutputId::Source, "Source"},
            {OutputId::Reference, "Reference"},
            {OutputId::Difference, "Difference"},
        }
    );

    static ref<ErrorMeasurePass> create(ref<Device> pDevice, const Properties& props) { return make_ref<ErrorMeasurePass>(pDevice, props); }

    ErrorMeasurePass(ref<Device> pDevice, const Properties& props);

    virtual Properties getProperties() const override;
    virtual RenderPassReflection reflect(const CompileData& compileData) override;
    virtual void execute(RenderContext* pRenderContext, const RenderData& renderData) override;
    virtual void renderUI(Gui::Widgets& widget) override;
    virtual bool onKeyEvent(const KeyboardEvent& keyEvent) override;
    virtual void setScene(RenderContext* pRenderContext, const ref<Scene>& pScene) override;
    virtual void onHotReload(HotReloadFlags reloaded) override;

    /// Read-only diagnostics. Frame is this pass's execute ordinal (not the host clock).
    Properties getStatistics() const;

private:
    bool loadReference();
    ref<Texture> getReference(const RenderData& renderData) const;
    bool loadMeasurementsFile();
    void saveMeasurementsToFile();

    void runDifferencePass(RenderContext* pRenderContext, const RenderData& renderData);
    void runReductionPasses(RenderContext* pRenderContext, const RenderData& renderData);
    void collectMeasurements();
    void invalidateMeasurements();

    ref<ComputePass> mpErrorMeasurerPass;
    std::unique_ptr<ParallelReduction> mpParallelReduction;
    ref<Buffer> mpReductionResult;

    struct MeasurementSample
    {
        uint64_t submittedFrame = 0;
        double submittedTime = 0.; ///< Monotonic seconds since pass construction, not simulation time.
        uint64_t generation = 0;
        uint32_t width = 0;
        uint32_t height = 0;
        bool squaredDifference = false;
        bool computeAverage = false;
        bool ignoreBackground = false; ///< Effective setting, including whether WorldPosition was bound.
        bool useLoadedReference = false;
        bool reportRunningError = false;
        float runningErrorSigma = 0.f;
        OutputId selectedOutput = OutputId::Source;
    };

    struct PendingMeasurement
    {
        MeasurementSample sample;
        CopyContext::ReadBufferTask::SharedPtr task;
    };

    // Invalid generations stay charged until their native fence is ready. Repeated
    // resize/config changes therefore cannot bypass admission or grow staging.
    static constexpr size_t kMaxPendingMeasurements = 4;
    std::deque<PendingMeasurement> mPendingMeasurements;
    uint64_t mMeasurementGeneration = 0;
    uint64_t mExecutionFrame = 0;
    uint64_t mSubmittedMeasurements = 0;
    uint64_t mCompletedMeasurements = 0;
    uint64_t mDiscardedMeasurements = 0;
    uint64_t mSkippedMeasurements = 0;
    uint64_t mLastCollectionFrame = 0;
    bool mBackpressured = false;
    bool mHasReference = false;
    const std::chrono::steady_clock::time_point mStartTime = std::chrono::steady_clock::now();
    ref<Texture> mpObservedSource;
    ref<Texture> mpObservedReference;
    ref<Texture> mpObservedWorldPosition;

    struct
    {
        float3 error = float3(0.f); ///< Error (either L1 or MSE) in RGB.
        float avgError = 0.f;      ///< Error averaged over color components.
        bool valid = false;
        MeasurementSample sample;
    } mMeasurements;

    // Internal state

    float3 mRunningError = float3(0.f, 0.f, 0.f);
    /// A negative value indicates that both running error values are invalid.
    float mRunningAvgError = -1.f;

    ref<Texture> mpReferenceTexture;
    ref<Texture> mpDifferenceTexture;

    std::ofstream mMeasurementsFile;

    // UI variables

    /// Path to the reference used in the comparison.
    std::filesystem::path mReferenceImagePath;
    /// Path to the output file where measurements are stored (.csv).
    std::filesystem::path mMeasurementsFilePath;

    /// If true, do not measure error on pixels that belong to the background.
    bool mIgnoreBackground = true;
    /// Compute the square difference when creating the difference image.
    bool mComputeSquaredDifference = true;
    /// Compute the average of the RGB components when creating the difference image.
    bool mComputeAverage = false;
    /// If true, use loaded reference image instead of input.
    bool mUseLoadedReference = false;
    /// Use exponetial moving average (EMA) for the computed error.
    bool mReportRunningError = true;
    /// Coefficient used for the exponential moving average. Larger values mean slower response.
    float mRunningErrorSigma = 0.995f;

    OutputId mSelectedOutputId = OutputId::Source;

    static const Gui::RadioButtonGroup sOutputSelectionButtons;
    static const Gui::RadioButtonGroup sOutputSelectionButtonsSourceOnly;
};

FALCOR_ENUM_REGISTER(ErrorMeasurePass::OutputId);
