;
; Input signature:
;
; Name                 Index   Mask Register SysValue  Format   Used
; -------------------- ----- ------ -------- -------- ------- ------
; TEXCOORD10_centroid      0   xyzw        0     NONE   float   xyz 
; TEXCOORD11_centroid      0   xyzw        1     NONE   float   xyzw
; INSTANCE_ID              0   x           2     NONE    uint   x   
; SV_IsFrontFace           0    y          2    FFACE    uint       
; TEXCOORD                 9   xyz         3     NONE   float   xyz 
; SV_Position              0   xyzw        4      POS   float   xyz 
;
;
; Output signature:
;
; Name                 Index   Mask Register SysValue  Format   Used
; -------------------- ----- ------ -------- -------- ------- ------
; SV_Target                0   xyzw        0   TARGET   float   xyzw
; SV_Target                1   xyzw        1   TARGET   float   xyzw
; SV_Target                2   xyzw        2   TARGET   float   xyzw
; SV_Target                3   xyzw        3   TARGET   float   xyzw
;
; shader hash: 268e4504c117eec2d9cef3616702c4c1
;
; Pipeline Runtime Information: 
;
;PSVRuntimeInfo:
; Pixel Shader
; DepthOutput=0
; SampleFrequency=0
; MinimumExpectedWaveLaneCount: 0
; MaximumExpectedWaveLaneCount: 4294967295
; UsesViewID: false
; SigInputElements: 6
; SigOutputElements: 4
; SigPatchConstOrPrimElements: 0
; SigInputVectors: 5
; SigOutputVectors[0]: 4
; SigOutputVectors[1]: 0
; SigOutputVectors[2]: 0
; SigOutputVectors[3]: 0
; EntryFunctionName: MainPS
;
;
; Input signature:
;
; Name                 Index             InterpMode DynIdx
; -------------------- ----- ---------------------- ------
; TEXCOORD10_centroid      0                 linear       
; TEXCOORD11_centroid      0                 linear       
; INSTANCE_ID              0        nointerpolation       
; TEXCOORD                 9                 linear       
; SV_Position              0          noperspective       
; SV_IsFrontFace           0        nointerpolation       
;
; Output signature:
;
; Name                 Index             InterpMode DynIdx
; -------------------- ----- ---------------------- ------
; SV_Target                0                              
; SV_Target                1                              
; SV_Target                2                              
; SV_Target                3                              
;
; Buffer Definitions:
;
; cbuffer 
; {
;
;   [6748 x i8] (type annotation not present)
;
; }
;
; cbuffer 
; {
;
;   [332 x i8] (type annotation not present)
;
; }
;
; cbuffer 
; {
;
;   [44 x i8] (type annotation not present)
;
; }
;
; Resource bind info for 
; {
;
;   [16 x i8] (type annotation not present)
;
; }
;
; Resource bind info for 
; {
;
;   [16 x i8] (type annotation not present)
;
; }
;
;
; Resource Bindings:
;
; Name                                 Type  Format         Dim      ID      HLSL Bind  Count
; ------------------------------ ---------- ------- ----------- ------- -------------- ------
;                                   cbuffer      NA          NA     CB0            cb0     1
;                                   cbuffer      NA          NA     CB1            cb1     1
;                                   cbuffer      NA          NA     CB2            cb2     1
;                                   sampler      NA          NA      S0             s0     1
;                                   texture  struct         r/o      T0             t0     1
;                                   texture  struct         r/o      T1             t1     1
;                                   texture     f32          2d      T2             t2     1
;                                   texture     f32          2d      T3             t3     1
;                                   texture     f32          2d      T4             t4     1
;
;
; ViewId state:
;
; Number of inputs: 20, outputs: 16
; Outputs dependent on ViewId: {  }
; Inputs contributing to computation of Outputs:
;   output 0 depends on inputs: { 8, 12, 13, 14, 16, 17, 18 }
;   output 1 depends on inputs: { 8, 16, 17, 18 }
;   output 2 depends on inputs: { 8, 12, 13, 14, 16, 17, 18 }
;   output 4 depends on inputs: { 0, 1, 2, 4, 5, 6, 7, 8, 16, 17 }
;   output 5 depends on inputs: { 0, 1, 2, 4, 5, 6, 7, 8, 16, 17 }
;   output 6 depends on inputs: { 0, 1, 2, 4, 5, 6, 7, 8, 16, 17 }
;   output 7 depends on inputs: { 8 }
;   output 8 depends on inputs: { 8, 16, 17 }
;   output 9 depends on inputs: { 8, 16, 17 }
;   output 10 depends on inputs: { 8, 16, 17 }
;   output 11 depends on inputs: { 8 }
;   output 12 depends on inputs: { 8, 16, 17 }
;   output 13 depends on inputs: { 8, 16, 17 }
;   output 14 depends on inputs: { 8, 16, 17 }
;   output 15 depends on inputs: { 8, 16, 17 }
;
target datalayout = "e-m:e-p:32:32-i1:32-i8:32-i16:32-i32:32-i64:64-f16:32-f32:32-f64:64-n8:16:32:64"
target triple = "dxil-ms-dx"

%dx.types.Handle = type { i8* }
%dx.types.ResBind = type { i32, i32, i32, i8 }
%dx.types.ResourceProperties = type { i32, i32 }
%dx.types.CBufRet.f32 = type { float, float, float, float }
%dx.types.CBufRet.i32 = type { i32, i32, i32, i32 }
%dx.types.ResRet.f32 = type { float, float, float, float, i32 }
%"class.StructuredBuffer<vector<float, 4> >" = type { <4 x float> }
%"class.Texture2D<vector<float, 4> >" = type { <4 x float>, %"class.Texture2D<vector<float, 4> >::mips_type" }
%"class.Texture2D<vector<float, 4> >::mips_type" = type { i32 }
%hostlayout.View = type { [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <4 x float>, <4 x float>, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], [4 x <4 x float>], <4 x float>, <4 x float>, <2 x float>, <2 x float>, <2 x float>, <2 x float>, <4 x float>, <4 x float>, <4 x i32>, <4 x float>, <4 x float>, <4 x float>, <4 x float>, <2 x float>, <2 x float>, i32, float, float, float, <4 x float>, <4 x float>, <4 x float>, <2 x float>, <2 x float>, float, float, float, float, <3 x float>, float, float, float, float, float, float, float, float, i32, i32, i32, i32, i32, i32, i32, i32, float, float, float, float, float, <4 x float>, <3 x float>, float, [2 x <4 x float>], [2 x <4 x float>], <4 x float>, <4 x float>, float, float, float, float, float, float, float, float, float, float, float, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, [2 x <4 x float>], [2 x <4 x float>], [2 x <4 x float>], [2 x <4 x float>], [2 x <4 x float>], <4 x float>, <3 x float>, float, <4 x float>, [4 x <4 x float>], <4 x float>, float, float, float, float, <4 x float>, float, float, float, float, float, float, float, float, <3 x float>, float, float, float, float, float, <4 x float>, float, float, float, float, <4 x float>, float, float, float, float, [8 x <4 x float>], float, float, float, float, i32, float, float, float, <3 x float>, i32, [6 x <4 x float>], [6 x <4 x float>], [6 x <4 x float>], [6 x <4 x float>], float, float, i32, i32, <3 x float>, float, <3 x float>, float, float, float, i32, float, float, float, float, float, float, float, <2 x i32>, float, float, float, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <2 x float>, <2 x float>, <2 x float>, <2 x float>, <2 x float>, float, float, <3 x float>, float, <2 x float>, <2 x float>, float, float, float, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, <3 x float>, float, float, float, float, float, [2 x <4 x float>], <4 x float>, i32, i32, i32, i32, i32, i32, i32, float, <4 x float>, i32, i32, i32, float, <4 x float>, <4 x float>, <4 x float>, <4 x float>, <2 x float>, float, float, <3 x float>, float, i32, i32, i32, i32, [32 x <4 x i32>], [32 x <4 x i32>], i32, float, float, float, <4 x float>, <4 x float>, <4 x float>, <4 x float>, <2 x float>, float, float, <4 x float>, <4 x float>, <4 x float>, float, float, float, i32, <4 x i32>, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, <4 x float>, float, float, i32, i32, i32, i32, i32, i32, <4 x float>, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, i32, <3 x i32>, i32, <3 x i32>, i32, <3 x float>, float, <3 x float> }
%Scene = type { i32, i32, i32, i32, i32, i32, i32, float, i32, i32, i32, i32, i32, i32, i32, i32, i32, float, float, float, i32, i32, i32, i32, <4 x i32>, i32, i32, i32, i32, i32, float, float, float, i32, i32, i32, float, i32, i32, i32, i32, i32, i32, i32, float, i32, i32, i32, i32, i32, i32, i32, i32, i32, float, float, float, <2 x float>, i32, i32, i32, i32, i32, float, i32, i32, i32, i32, i32, float, float, float, i32, i32, i32, float, i32, i32, i32 }
%Material = type { [2 x <4 x float>], i32, i32, i32 }
%struct.SamplerState = type { i32 }

define void @MainPS() {
  %1 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 4, i32 4, i32 0, i8 0 }, i32 4, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %2 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 3, i32 3, i32 0, i8 0 }, i32 3, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %3 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 2, i32 2, i32 0, i8 0 }, i32 2, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %4 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 1, i32 1, i32 0, i8 0 }, i32 1, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %5 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind zeroinitializer, i32 0, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %6 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 0, i32 0, i32 0, i8 3 }, i32 0, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %7 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 2, i32 2, i32 0, i8 2 }, i32 2, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %8 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 1, i32 1, i32 0, i8 2 }, i32 1, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %9 = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 0, i32 0, i32 0, i8 2 }, i32 0, i1 false)  ; CreateHandleFromBinding(bind,index,nonUniformIndex)
  %10 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %7, %dx.types.ResourceProperties { i32 13, i32 44 })  ; AnnotateHandle(res,props)  resource: CBuffer
  %11 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %8, %dx.types.ResourceProperties { i32 13, i32 332 })  ; AnnotateHandle(res,props)  resource: CBuffer
  %12 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %9, %dx.types.ResourceProperties { i32 13, i32 6748 })  ; AnnotateHandle(res,props)  resource: CBuffer
  %13 = call float @dx.op.loadInput.f32(i32 4, i32 4, i32 0, i8 0, i32 undef), !dx.precise !37  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %14 = call float @dx.op.loadInput.f32(i32 4, i32 4, i32 0, i8 1, i32 undef), !dx.precise !37  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %15 = call float @dx.op.loadInput.f32(i32 4, i32 4, i32 0, i8 2, i32 undef), !dx.precise !37  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %16 = call float @dx.op.loadInput.f32(i32 4, i32 3, i32 0, i8 0, i32 undef), !dx.precise !37  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %17 = call float @dx.op.loadInput.f32(i32 4, i32 3, i32 0, i8 1, i32 undef), !dx.precise !37  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %18 = call float @dx.op.loadInput.f32(i32 4, i32 3, i32 0, i8 2, i32 undef), !dx.precise !37  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %19 = call i32 @dx.op.loadInput.i32(i32 4, i32 2, i32 0, i8 0, i32 undef)  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %20 = call float @dx.op.loadInput.f32(i32 4, i32 1, i32 0, i8 0, i32 undef)  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %21 = call float @dx.op.loadInput.f32(i32 4, i32 1, i32 0, i8 1, i32 undef)  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %22 = call float @dx.op.loadInput.f32(i32 4, i32 1, i32 0, i8 2, i32 undef)  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %23 = call float @dx.op.loadInput.f32(i32 4, i32 1, i32 0, i8 3, i32 undef)  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %24 = call float @dx.op.loadInput.f32(i32 4, i32 0, i32 0, i8 0, i32 undef)  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %25 = call float @dx.op.loadInput.f32(i32 4, i32 0, i32 0, i8 1, i32 undef)  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %26 = call float @dx.op.loadInput.f32(i32 4, i32 0, i32 0, i8 2, i32 undef)  ; LoadInput(inputSigId,rowIndex,colIndex,gsVertexAxis)
  %27 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 44)  ; CBufferLoadLegacy(handle,regIndex)
  %28 = extractvalue %dx.types.CBufRet.f32 %27, 0
  %29 = extractvalue %dx.types.CBufRet.f32 %27, 1
  %30 = extractvalue %dx.types.CBufRet.f32 %27, 2
  %31 = extractvalue %dx.types.CBufRet.f32 %27, 3
  %32 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 45)  ; CBufferLoadLegacy(handle,regIndex)
  %33 = extractvalue %dx.types.CBufRet.f32 %32, 0
  %34 = extractvalue %dx.types.CBufRet.f32 %32, 1
  %35 = extractvalue %dx.types.CBufRet.f32 %32, 2
  %36 = extractvalue %dx.types.CBufRet.f32 %32, 3
  %37 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 46)  ; CBufferLoadLegacy(handle,regIndex)
  %38 = extractvalue %dx.types.CBufRet.f32 %37, 0
  %39 = extractvalue %dx.types.CBufRet.f32 %37, 1
  %40 = extractvalue %dx.types.CBufRet.f32 %37, 2
  %41 = extractvalue %dx.types.CBufRet.f32 %37, 3
  %42 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 47)  ; CBufferLoadLegacy(handle,regIndex)
  %43 = extractvalue %dx.types.CBufRet.f32 %42, 0
  %44 = extractvalue %dx.types.CBufRet.f32 %42, 1
  %45 = extractvalue %dx.types.CBufRet.f32 %42, 2
  %46 = extractvalue %dx.types.CBufRet.f32 %42, 3
  %47 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 125)  ; CBufferLoadLegacy(handle,regIndex)
  %48 = extractvalue %dx.types.CBufRet.f32 %47, 0
  %49 = extractvalue %dx.types.CBufRet.f32 %47, 1
  %50 = extractvalue %dx.types.CBufRet.f32 %47, 2
  %51 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 128)  ; CBufferLoadLegacy(handle,regIndex)
  %52 = extractvalue %dx.types.CBufRet.f32 %51, 0
  %53 = extractvalue %dx.types.CBufRet.f32 %51, 1
  %54 = extractvalue %dx.types.CBufRet.f32 %51, 2
  %55 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 163)  ; CBufferLoadLegacy(handle,regIndex)
  %56 = extractvalue %dx.types.CBufRet.f32 %55, 0
  %57 = extractvalue %dx.types.CBufRet.f32 %55, 1
  %58 = extractvalue %dx.types.CBufRet.f32 %55, 2
  %59 = extractvalue %dx.types.CBufRet.f32 %55, 3
  %60 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 164)  ; CBufferLoadLegacy(handle,regIndex)
  %61 = extractvalue %dx.types.CBufRet.f32 %60, 0
  %62 = extractvalue %dx.types.CBufRet.f32 %60, 1
  %63 = extractvalue %dx.types.CBufRet.f32 %60, 2
  %64 = extractvalue %dx.types.CBufRet.f32 %60, 3
  %65 = fsub float -0.000000e+00, %48
  %66 = fsub float -0.000000e+00, %49
  %67 = fsub float -0.000000e+00, %50
  %68 = fmul fast float %26, %21
  %69 = fmul fast float %25, %22
  %70 = fsub fast float %68, %69
  %71 = fmul fast float %24, %22
  %72 = fmul fast float %26, %20
  %73 = fsub fast float %71, %72
  %74 = fmul fast float %25, %20
  %75 = fmul fast float %24, %21
  %76 = fsub fast float %74, %75
  %77 = fmul fast float %70, %23
  %78 = fmul fast float %73, %23
  %79 = fmul fast float %76, %23
  %80 = call %dx.types.CBufRet.i32 @dx.op.cbufferLoadLegacy.i32(i32 59, %dx.types.Handle %11, i32 0)  ; CBufferLoadLegacy(handle,regIndex)
  %81 = extractvalue %dx.types.CBufRet.i32 %80, 0
  %82 = extractvalue %dx.types.CBufRet.i32 %80, 1
  %83 = extractvalue %dx.types.CBufRet.i32 %80, 2
  %84 = and i32 %81, 31
  %85 = lshr i32 %19, %84
  %86 = and i32 %82, %19
  %87 = mul i32 %83, %85
  %88 = add i32 %87, %86
  %89 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %5, %dx.types.ResourceProperties { i32 12, i32 16 })  ; AnnotateHandle(res,props)  resource: StructuredBuffer<stride=16>
  %90 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %89, i32 %88, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %91 = extractvalue %dx.types.ResRet.f32 %90, 0
  %92 = bitcast float %91 to i32
  %93 = and i32 %92, 1048575
  %94 = fmul float %13, %28
  %95 = call float @dx.op.tertiary.f32(i32 46, float %14, float %33, float %94), !dx.precise !37  ; FMad(a,b,c)
  %96 = call float @dx.op.tertiary.f32(i32 46, float %15, float %38, float %95), !dx.precise !37  ; FMad(a,b,c)
  %97 = call float @dx.op.tertiary.f32(i32 46, float 1.000000e+00, float %43, float %96), !dx.precise !37  ; FMad(a,b,c)
  %98 = fmul float %13, %29
  %99 = call float @dx.op.tertiary.f32(i32 46, float %14, float %34, float %98), !dx.precise !37  ; FMad(a,b,c)
  %100 = call float @dx.op.tertiary.f32(i32 46, float %15, float %39, float %99), !dx.precise !37  ; FMad(a,b,c)
  %101 = call float @dx.op.tertiary.f32(i32 46, float 1.000000e+00, float %44, float %100), !dx.precise !37  ; FMad(a,b,c)
  %102 = fmul float %13, %30
  %103 = call float @dx.op.tertiary.f32(i32 46, float %14, float %35, float %102), !dx.precise !37  ; FMad(a,b,c)
  %104 = call float @dx.op.tertiary.f32(i32 46, float %15, float %40, float %103), !dx.precise !37  ; FMad(a,b,c)
  %105 = call float @dx.op.tertiary.f32(i32 46, float 1.000000e+00, float %45, float %104), !dx.precise !37  ; FMad(a,b,c)
  %106 = fmul float %13, %31
  %107 = call float @dx.op.tertiary.f32(i32 46, float %14, float %36, float %106), !dx.precise !37  ; FMad(a,b,c)
  %108 = call float @dx.op.tertiary.f32(i32 46, float %15, float %41, float %107), !dx.precise !37  ; FMad(a,b,c)
  %109 = call float @dx.op.tertiary.f32(i32 46, float 1.000000e+00, float %46, float %108), !dx.precise !37  ; FMad(a,b,c)
  %110 = fdiv float %97, %109
  %111 = fdiv float %101, %109
  %112 = fdiv float %105, %109
  %113 = fsub float %110, %52
  %114 = fsub float %111, %53
  %115 = fsub float %112, %54
  %116 = call float @dx.op.tertiary.f32(i32 46, float %48, float 2.097152e+06, float %113), !dx.precise !37  ; FMad(a,b,c)
  %117 = call float @dx.op.tertiary.f32(i32 46, float %49, float 2.097152e+06, float %114), !dx.precise !37  ; FMad(a,b,c)
  %118 = call float @dx.op.tertiary.f32(i32 46, float %50, float 2.097152e+06, float %115), !dx.precise !37  ; FMad(a,b,c)
  %119 = call float @dx.op.tertiary.f32(i32 46, float %65, float 2.097152e+06, float %116), !dx.precise !37  ; FMad(a,b,c)
  %120 = call float @dx.op.tertiary.f32(i32 46, float %66, float 2.097152e+06, float %117), !dx.precise !37  ; FMad(a,b,c)
  %121 = call float @dx.op.tertiary.f32(i32 46, float %67, float 2.097152e+06, float %118), !dx.precise !37  ; FMad(a,b,c)
  %122 = fsub float %113, %119
  %123 = fsub float %114, %120
  %124 = fsub float %115, %121
  %125 = fadd fast float %59, %58
  %126 = call float @dx.op.dot3.f32(i32 55, float %56, float %57, float %125, float %56, float %57, float %125)  ; Dot3(ax,ay,az,bx,by,bz)
  %127 = call float @dx.op.unary.f32(i32 25, float %126)  ; Rsqrt(value)
  %128 = fmul fast float %127, %56
  %129 = fmul fast float %127, %57
  %130 = fmul fast float %127, %125
  %131 = fmul fast float %128, %24
  %132 = call float @dx.op.tertiary.f32(i32 46, float %129, float %77, float %131)  ; FMad(a,b,c)
  %133 = call float @dx.op.tertiary.f32(i32 46, float %130, float %20, float %132)  ; FMad(a,b,c)
  %134 = fmul fast float %128, %25
  %135 = call float @dx.op.tertiary.f32(i32 46, float %129, float %78, float %134)  ; FMad(a,b,c)
  %136 = call float @dx.op.tertiary.f32(i32 46, float %130, float %21, float %135)  ; FMad(a,b,c)
  %137 = fmul fast float %128, %26
  %138 = call float @dx.op.tertiary.f32(i32 46, float %129, float %79, float %137)  ; FMad(a,b,c)
  %139 = call float @dx.op.tertiary.f32(i32 46, float %130, float %22, float %138)  ; FMad(a,b,c)
  %140 = call float @dx.op.dot3.f32(i32 55, float %133, float %136, float %139, float %133, float %136, float %139)  ; Dot3(ax,ay,az,bx,by,bz)
  %141 = call float @dx.op.unary.f32(i32 25, float %140)  ; Rsqrt(value)
  %142 = fmul fast float %141, %133
  %143 = fmul fast float %141, %136
  %144 = fmul fast float %141, %139
  %145 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %10, i32 0)  ; CBufferLoadLegacy(handle,regIndex)
  %146 = extractvalue %dx.types.CBufRet.f32 %145, 0
  %147 = extractvalue %dx.types.CBufRet.f32 %145, 1
  %148 = extractvalue %dx.types.CBufRet.f32 %145, 2
  %149 = extractvalue %dx.types.CBufRet.f32 %145, 3
  %150 = fmul fast float %147, %146
  %151 = fmul fast float %148, %146
  %152 = fmul fast float %149, %146
  %153 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %10, i32 1)  ; CBufferLoadLegacy(handle,regIndex)
  %154 = extractvalue %dx.types.CBufRet.f32 %153, 0
  %155 = extractvalue %dx.types.CBufRet.f32 %153, 1
  %156 = extractvalue %dx.types.CBufRet.f32 %153, 2
  %157 = extractvalue %dx.types.CBufRet.f32 %153, 3
  %158 = call %dx.types.CBufRet.i32 @dx.op.cbufferLoadLegacy.i32(i32 59, %dx.types.Handle %12, i32 169)  ; CBufferLoadLegacy(handle,regIndex)
  %159 = extractvalue %dx.types.CBufRet.i32 %158, 2
  %160 = uitofp i32 %159 to float
  %161 = fmul fast float %160, 0x4040551EC0000000
  %162 = fmul fast float %160, 0x4027A147A0000000
  %163 = fadd fast float %161, %13
  %164 = fadd fast float %162, %14
  %165 = call float @dx.op.dot2.f32(i32 54, float %163, float %164, float 0x3FB12E2860000000, float 0x3F77E8B200000000)  ; Dot2(ax,ay,bx,by)
  %166 = call float @dx.op.unary.f32(i32 22, float %165)  ; Frc(value)
  %167 = fmul fast float %166, 0x404A7DD040000000
  %168 = call float @dx.op.unary.f32(i32 22, float %167)  ; Frc(value)
  %169 = call float @dx.op.unary.f32(i32 7, float %154)  ; Saturate(value)
  %170 = call float @dx.op.unary.f32(i32 7, float %155)  ; Saturate(value)
  %171 = call float @dx.op.unary.f32(i32 7, float %156)  ; Saturate(value)
  %172 = call float @dx.op.unary.f32(i32 7, float %157)  ; Saturate(value)
  %173 = fmul fast float %172, %62
  %174 = fadd fast float %173, %61
  %175 = fadd fast float %64, %63
  %176 = call float @dx.op.unary.f32(i32 7, float %175)  ; Saturate(value)
  %177 = mul nuw nsw i32 %93, 44
  %178 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %4, %dx.types.ResourceProperties { i32 12, i32 16 })  ; AnnotateHandle(res,props)  resource: StructuredBuffer<stride=16>
  %179 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %178, i32 %177, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %180 = extractvalue %dx.types.ResRet.f32 %179, 0
  %181 = bitcast float %180 to i32
  %182 = and i32 %181, 8
  %183 = icmp ne i32 %182, 0
  %184 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 223)  ; CBufferLoadLegacy(handle,regIndex)
  %185 = extractvalue %dx.types.CBufRet.f32 %184, 3
  %186 = fcmp fast ogt float %185, 0.000000e+00
  %187 = and i1 %186, %183
  br i1 %187, label %188, label %240, !dx.controlflow.hints !43

; <label>:188                                     ; preds = %0
  %189 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 156)  ; CBufferLoadLegacy(handle,regIndex)
  %190 = extractvalue %dx.types.CBufRet.f32 %189, 2
  %191 = extractvalue %dx.types.CBufRet.f32 %189, 3
  %192 = fmul fast float %190, %13
  %193 = fmul fast float %191, %14
  %194 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %3, %dx.types.ResourceProperties { i32 2, i32 1033 })  ; AnnotateHandle(res,props)  resource: Texture2D<4xF32>
  %195 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %6, %dx.types.ResourceProperties { i32 14, i32 0 })  ; AnnotateHandle(res,props)  resource: SamplerState
  %196 = call %dx.types.ResRet.f32 @dx.op.sampleLevel.f32(i32 62, %dx.types.Handle %194, %dx.types.Handle %195, float %192, float %193, float undef, float undef, i32 0, i32 0, i32 undef, float 0.000000e+00)  ; SampleLevel(srv,sampler,coord0,coord1,coord2,coord3,offset0,offset1,offset2,LOD)
  %197 = extractvalue %dx.types.ResRet.f32 %196, 0
  %198 = extractvalue %dx.types.ResRet.f32 %196, 1
  %199 = extractvalue %dx.types.ResRet.f32 %196, 2
  %200 = extractvalue %dx.types.ResRet.f32 %196, 3
  %201 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %2, %dx.types.ResourceProperties { i32 2, i32 1033 })  ; AnnotateHandle(res,props)  resource: Texture2D<4xF32>
  %202 = call %dx.types.ResRet.f32 @dx.op.sampleLevel.f32(i32 62, %dx.types.Handle %201, %dx.types.Handle %195, float %192, float %193, float undef, float undef, i32 0, i32 0, i32 undef, float 0.000000e+00)  ; SampleLevel(srv,sampler,coord0,coord1,coord2,coord3,offset0,offset1,offset2,LOD)
  %203 = extractvalue %dx.types.ResRet.f32 %202, 0
  %204 = extractvalue %dx.types.ResRet.f32 %202, 1
  %205 = extractvalue %dx.types.ResRet.f32 %202, 2
  %206 = extractvalue %dx.types.ResRet.f32 %202, 3
  %207 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %1, %dx.types.ResourceProperties { i32 2, i32 1033 })  ; AnnotateHandle(res,props)  resource: Texture2D<4xF32>
  %208 = call %dx.types.ResRet.f32 @dx.op.sampleLevel.f32(i32 62, %dx.types.Handle %207, %dx.types.Handle %195, float %192, float %193, float undef, float undef, i32 0, i32 0, i32 undef, float 0.000000e+00)  ; SampleLevel(srv,sampler,coord0,coord1,coord2,coord3,offset0,offset1,offset2,LOD)
  %209 = extractvalue %dx.types.ResRet.f32 %208, 0
  %210 = extractvalue %dx.types.ResRet.f32 %208, 1
  %211 = extractvalue %dx.types.ResRet.f32 %208, 2
  %212 = extractvalue %dx.types.ResRet.f32 %208, 3
  %213 = fmul fast float %203, 2.000000e+00
  %214 = fmul fast float %204, 2.000000e+00
  %215 = fmul fast float %205, 2.000000e+00
  %216 = fadd fast float %213, 0xBFF0101020000000
  %217 = fadd fast float %214, 0xBFF0101020000000
  %218 = fadd fast float %215, 0xBFF0101020000000
  %219 = fmul fast float %200, %169
  %220 = fmul fast float %200, %170
  %221 = fmul fast float %200, %171
  %222 = fadd fast float %219, %197
  %223 = fadd fast float %220, %198
  %224 = fadd fast float %221, %199
  %225 = fmul fast float %206, %142
  %226 = fmul fast float %206, %143
  %227 = fmul fast float %206, %144
  %228 = fadd fast float %216, %225
  %229 = fadd fast float %217, %226
  %230 = fadd fast float %218, %227
  %231 = call float @dx.op.dot3.f32(i32 55, float %228, float %229, float %230, float %228, float %229, float %230)  ; Dot3(ax,ay,az,bx,by,bz)
  %232 = call float @dx.op.unary.f32(i32 25, float %231)  ; Rsqrt(value)
  %233 = fmul fast float %232, %228
  %234 = fmul fast float %232, %229
  %235 = fmul fast float %232, %230
  %236 = fmul fast float %212, %174
  %237 = fadd fast float %236, %211
  %238 = fmul fast float %212, 5.000000e-01
  %239 = fadd fast float %238, %210
  br label %240

; <label>:240                                     ; preds = %188, %0
  %241 = phi float [ %233, %188 ], [ %142, %0 ]
  %242 = phi float [ %234, %188 ], [ %143, %0 ]
  %243 = phi float [ %235, %188 ], [ %144, %0 ]
  %244 = phi float [ %222, %188 ], [ %169, %0 ]
  %245 = phi float [ %223, %188 ], [ %170, %0 ]
  %246 = phi float [ %224, %188 ], [ %171, %0 ]
  %247 = phi float [ %209, %188 ], [ 0.000000e+00, %0 ]
  %248 = phi float [ %239, %188 ], [ 5.000000e-01, %0 ]
  %249 = phi float [ %237, %188 ], [ %174, %0 ]
  %250 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %4, %dx.types.ResourceProperties { i32 12, i32 16 })  ; AnnotateHandle(res,props)  resource: StructuredBuffer<stride=16>
  %251 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %250, i32 %177, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %252 = extractvalue %dx.types.ResRet.f32 %251, 0
  %253 = bitcast float %252 to i32
  %254 = and i32 %253, 256
  %255 = icmp ne i32 %254, 0
  %256 = and i32 %253, 512
  %257 = icmp ne i32 %256, 0
  %258 = select i1 %257, float 1.000000e+00, float 0.000000e+00
  %259 = select i1 %255, float 2.000000e+00, float 0.000000e+00
  %260 = fadd fast float %259, %258
  %261 = fmul fast float %260, 0x3FD5555560000000
  %262 = fadd fast float %168, -5.000000e-01
  %263 = fmul fast float %262, 0x3F70101020000000
  %264 = call float @dx.op.unary.f32(i32 7, float %248)  ; Saturate(value)
  %265 = bitcast float %264 to i32
  %266 = and i32 %265, 2147483647
  %267 = call i32 @dx.op.binary.i32(i32 40, i32 %266, i32 1)  ; UMin(a,b)
  %268 = uitofp i32 %267 to float
  %269 = fmul fast float %263, %268
  %270 = fadd fast float %269, %264
  %271 = call float @dx.op.unary.f32(i32 7, float %270)  ; Saturate(value)
  %272 = fmul fast float %248, 0x3FB47AE140000000
  %273 = fsub fast float %244, %272
  %274 = fsub fast float %245, %272
  %275 = fsub fast float %246, %272
  %276 = fmul fast float %273, %247
  %277 = fmul fast float %274, %247
  %278 = fmul fast float %275, %247
  %279 = fadd fast float %276, %272
  %280 = fadd fast float %277, %272
  %281 = fadd fast float %278, %272
  %282 = fmul fast float %247, %244
  %283 = fmul fast float %247, %245
  %284 = fmul fast float %247, %246
  %285 = fsub fast float %244, %282
  %286 = fsub fast float %245, %283
  %287 = fsub fast float %246, %284
  %288 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 161)  ; CBufferLoadLegacy(handle,regIndex)
  %289 = extractvalue %dx.types.CBufRet.f32 %288, 3
  %290 = fmul fast float %289, %285
  %291 = fmul fast float %289, %286
  %292 = fmul fast float %289, %287
  %293 = extractvalue %dx.types.CBufRet.f32 %288, 0
  %294 = extractvalue %dx.types.CBufRet.f32 %288, 1
  %295 = extractvalue %dx.types.CBufRet.f32 %288, 2
  %296 = fadd fast float %290, %293
  %297 = fadd fast float %291, %294
  %298 = fadd fast float %292, %295
  %299 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 162)  ; CBufferLoadLegacy(handle,regIndex)
  %300 = extractvalue %dx.types.CBufRet.f32 %299, 3
  %301 = fmul fast float %300, %279
  %302 = fmul fast float %300, %280
  %303 = fmul fast float %300, %281
  %304 = extractvalue %dx.types.CBufRet.f32 %299, 0
  %305 = extractvalue %dx.types.CBufRet.f32 %299, 1
  %306 = extractvalue %dx.types.CBufRet.f32 %299, 2
  %307 = fadd fast float %301, %304
  %308 = fadd fast float %302, %305
  %309 = fadd fast float %303, %306
  %310 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 209)  ; CBufferLoadLegacy(handle,regIndex)
  %311 = extractvalue %dx.types.CBufRet.f32 %310, 3
  %312 = fcmp fast une float %311, 0.000000e+00
  %313 = fmul fast float %307, 0x3FDCCCCCC0000000
  %314 = fmul fast float %308, 0x3FDCCCCCC0000000
  %315 = fmul fast float %309, 0x3FDCCCCCC0000000
  %316 = fadd fast float %313, %296
  %317 = fadd fast float %314, %297
  %318 = fadd fast float %315, %298
  %319 = select i1 %312, float %316, float %296
  %320 = select i1 %312, float %317, float %297
  %321 = select i1 %312, float %318, float %298
  %322 = select i1 %312, float 0.000000e+00, float %307
  %323 = select i1 %312, float 0.000000e+00, float %308
  %324 = select i1 %312, float 0.000000e+00, float %309
  %325 = call float @dx.op.dot3.f32(i32 55, float %322, float %323, float %324, float 0x3FCB37C140000000, float 0x3FE6E2A960000000, float 0x3FB27B3220000000)  ; Dot3(ax,ay,az,bx,by,bz)
  %326 = fmul fast float %325, 0x400052BD40000000
  %327 = fadd fast float %326, 0xBFD5460AA0000000
  %328 = fmul fast float %325, 0x40132E2EC0000000
  %329 = fsub fast float 0x3FE488CE80000000, %328
  %330 = fmul fast float %325, 0x40060AA640000000
  %331 = fadd fast float %330, 0x3FE616F000000000
  %332 = fmul fast float %327, %176
  %333 = fadd fast float %329, %332
  %334 = fmul fast float %333, %176
  %335 = fadd fast float %331, %334
  %336 = fmul fast float %335, %176
  %337 = call float @dx.op.binary.f32(i32 35, float %176, float %336)  ; FMax(a,b)
  %338 = fmul fast float %322, 0x3FDCCCCCC0000000
  %339 = fmul fast float %323, 0x3FDCCCCCC0000000
  %340 = fmul fast float %324, 0x3FDCCCCCC0000000
  %341 = fadd fast float %319, %338
  %342 = fadd fast float %320, %339
  %343 = fadd fast float %321, %340
  %344 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 171)  ; CBufferLoadLegacy(handle,regIndex)
  %345 = extractvalue %dx.types.CBufRet.f32 %344, 0
  %346 = fmul fast float %341, %345
  %347 = fmul fast float %342, %345
  %348 = fmul fast float %343, %345
  %349 = call float @dx.op.binary.f32(i32 35, float %150, float 0.000000e+00)  ; FMax(a,b)
  %350 = call float @dx.op.binary.f32(i32 35, float %151, float 0.000000e+00)  ; FMax(a,b)
  %351 = call float @dx.op.binary.f32(i32 35, float %152, float 0.000000e+00)  ; FMax(a,b)
  %352 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 165)  ; CBufferLoadLegacy(handle,regIndex)
  %353 = extractvalue %dx.types.CBufRet.f32 %352, 2
  %354 = fcmp ogt float %353, 0.000000e+00
  br i1 %354, label %355, label %453, !dx.controlflow.hints !44

; <label>:355                                     ; preds = %240
  %356 = add nuw nsw i32 %177, 18
  %357 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %250, i32 %356, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %358 = extractvalue %dx.types.ResRet.f32 %357, 0
  %359 = extractvalue %dx.types.ResRet.f32 %357, 1
  %360 = extractvalue %dx.types.ResRet.f32 %357, 2
  %361 = add nuw nsw i32 %177, 19
  %362 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %250, i32 %361, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %363 = extractvalue %dx.types.ResRet.f32 %362, 0
  %364 = extractvalue %dx.types.ResRet.f32 %362, 1
  %365 = extractvalue %dx.types.ResRet.f32 %362, 2
  %366 = add nuw nsw i32 %177, 17
  %367 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %250, i32 %366, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %368 = extractvalue %dx.types.ResRet.f32 %367, 3
  %369 = fmul float %358, 2.097152e+06
  %370 = fmul float %359, 2.097152e+06
  %371 = fmul float %360, 2.097152e+06
  %372 = fadd float %369, %363
  %373 = fadd float %370, %364
  %374 = fadd float %371, %365
  %375 = fsub float %372, %369
  %376 = fsub float %373, %370
  %377 = fsub float %374, %371
  %378 = fsub float %363, %375
  %379 = fsub float %364, %376
  %380 = fsub float %365, %377
  %381 = add nuw nsw i32 %177, 26
  %382 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %250, i32 %381, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %383 = extractvalue %dx.types.ResRet.f32 %382, 3
  %384 = add nuw nsw i32 %177, 27
  %385 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %250, i32 %384, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %386 = extractvalue %dx.types.ResRet.f32 %385, 3
  %387 = add nuw nsw i32 %177, 32
  %388 = call %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32 139, %dx.types.Handle %250, i32 %387, i32 0, i8 15, i32 4)  ; RawBufferLoad(srv,index,elementOffset,mask,alignment)
  %389 = extractvalue %dx.types.ResRet.f32 %388, 0
  %390 = fsub float %116, %372
  %391 = fsub float %117, %373
  %392 = fsub float %118, %374
  %393 = fsub float %122, %378
  %394 = fsub float %123, %379
  %395 = fsub float %124, %380
  %396 = fadd float %390, %393
  %397 = fadd float %391, %394
  %398 = fadd float %392, %395
  %399 = call float @dx.op.unary.f32(i32 6, float %396)  ; FAbs(value)
  %400 = call float @dx.op.unary.f32(i32 6, float %397)  ; FAbs(value)
  %401 = call float @dx.op.unary.f32(i32 6, float %398)  ; FAbs(value)
  %402 = fadd fast float %368, 1.000000e+00
  %403 = fadd fast float %383, 1.000000e+00
  %404 = fadd fast float %386, 1.000000e+00
  %405 = fcmp fast ogt float %399, %402
  %406 = fcmp fast ogt float %400, %403
  %407 = fcmp fast ogt float %401, %404
  %408 = or i1 %405, %406
  %409 = or i1 %408, %407
  br i1 %409, label %410, label %437

; <label>:410                                     ; preds = %355
  %411 = fmul fast float %122, 0x3EF0000000000000
  %412 = fmul fast float %123, 0x3EF0000000000000
  %413 = fmul fast float %124, 0x3EF0000000000000
  %414 = fmul fast float %116, 0x3EF0000000000000
  %415 = fmul fast float %117, 0x3EF0000000000000
  %416 = fmul fast float %118, 0x3EF0000000000000
  %417 = call float @dx.op.unary.f32(i32 22, float %414)  ; Frc(value)
  %418 = call float @dx.op.unary.f32(i32 22, float %415)  ; Frc(value)
  %419 = call float @dx.op.unary.f32(i32 22, float %416)  ; Frc(value)
  %420 = call float @dx.op.unary.f32(i32 22, float %411)  ; Frc(value)
  %421 = call float @dx.op.unary.f32(i32 22, float %412)  ; Frc(value)
  %422 = call float @dx.op.unary.f32(i32 22, float %413)  ; Frc(value)
  %423 = fadd fast float %420, %417
  %424 = fadd fast float %421, %418
  %425 = fadd fast float %422, %419
  %426 = call float @dx.op.unary.f32(i32 22, float %423)  ; Frc(value)
  %427 = call float @dx.op.unary.f32(i32 22, float %424)  ; Frc(value)
  %428 = call float @dx.op.unary.f32(i32 22, float %425)  ; Frc(value)
  %429 = fmul fast float %426, 6.553600e+04
  %430 = fmul fast float %427, 6.553600e+04
  %431 = fmul fast float %428, 6.553600e+04
  %432 = call float @dx.op.dot3.f32(i32 55, float %429, float %430, float %431, float 0x3F52E83A20000000, float 0x3F52E83A20000000, float 0x3F52E83A20000000)  ; Dot3(ax,ay,az,bx,by,bz)
  %433 = call float @dx.op.unary.f32(i32 22, float %432)  ; Frc(value)
  %434 = fcmp fast ogt float %433, 5.000000e-01
  %435 = uitofp i1 %434 to float
  %436 = fsub fast float 1.000000e+00, %435
  br label %453

; <label>:437                                     ; preds = %355
  %438 = fcmp fast ogt float %389, 0.000000e+00
  br i1 %438, label %439, label %453

; <label>:439                                     ; preds = %437
  %440 = fsub fast float %110, %16
  %441 = fsub fast float %111, %17
  %442 = fsub fast float %112, %18
  %443 = call float @dx.op.unary.f32(i32 6, float %440)  ; FAbs(value)
  %444 = call float @dx.op.unary.f32(i32 6, float %441)  ; FAbs(value)
  %445 = call float @dx.op.unary.f32(i32 6, float %442)  ; FAbs(value)
  %446 = call float @dx.op.binary.f32(i32 35, float %444, float %445)  ; FMax(a,b)
  %447 = call float @dx.op.binary.f32(i32 35, float %443, float %446)  ; FMax(a,b)
  %448 = fsub fast float %447, %389
  %449 = call float @dx.op.unary.f32(i32 6, float %448)  ; FAbs(value)
  %450 = fmul fast float %449, 2.000000e+01
  %451 = call float @dx.op.unary.f32(i32 7, float %450)  ; Saturate(value)
  %452 = fsub fast float 1.000000e+00, %451
  br label %453

; <label>:453                                     ; preds = %439, %437, %410, %240
  %454 = phi float [ %436, %410 ], [ %452, %439 ], [ %349, %437 ], [ %349, %240 ]
  %455 = phi float [ 1.000000e+00, %410 ], [ 0.000000e+00, %439 ], [ %350, %437 ], [ %350, %240 ]
  %456 = phi float [ %435, %410 ], [ %452, %439 ], [ %351, %437 ], [ %351, %240 ]
  %457 = fadd fast float %454, %346
  %458 = fadd fast float %455, %347
  %459 = fadd fast float %456, %348
  %460 = fmul fast float %241, 5.000000e-01
  %461 = fmul fast float %242, 5.000000e-01
  %462 = fmul fast float %243, 5.000000e-01
  %463 = fadd fast float %460, 5.000000e-01
  %464 = fadd fast float %461, 5.000000e-01
  %465 = fadd fast float %462, 5.000000e-01
  %466 = lshr i32 %253, 24
  %467 = and i32 %466, 64
  %468 = or i32 %467, 129
  %469 = uitofp i32 %468 to float
  %470 = fmul fast float %469, 0x3F70101020000000
  %471 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 160)  ; CBufferLoadLegacy(handle,regIndex)
  %472 = extractvalue %dx.types.CBufRet.f32 %471, 2
  %473 = fmul fast float %472, %457
  %474 = fmul fast float %472, %458
  %475 = fmul fast float %472, %459
  %476 = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %12, i32 358)  ; CBufferLoadLegacy(handle,regIndex)
  %477 = extractvalue %dx.types.CBufRet.f32 %476, 2
  %478 = call float @dx.op.binary.f32(i32 36, float %473, float %477)  ; FMin(a,b)
  %479 = call float @dx.op.binary.f32(i32 36, float %474, float %477)  ; FMin(a,b)
  %480 = call float @dx.op.binary.f32(i32 36, float %475, float %477)  ; FMin(a,b)
  call void @dx.op.storeOutput.f32(i32 5, i32 0, i32 0, i8 0, float %478)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 0, i32 0, i8 1, float %479)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 0, i32 0, i8 2, float %480)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 0, i32 0, i8 3, float 0.000000e+00)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 1, i32 0, i8 0, float %463)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 1, i32 0, i8 1, float %464)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 1, i32 0, i8 2, float %465)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 1, i32 0, i8 3, float %261)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 2, i32 0, i8 0, float %247)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 2, i32 0, i8 1, float %271)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 2, i32 0, i8 2, float %249)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 2, i32 0, i8 3, float %470)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 3, i32 0, i8 0, float %244)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 3, i32 0, i8 1, float %245)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 3, i32 0, i8 2, float %246)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  call void @dx.op.storeOutput.f32(i32 5, i32 3, i32 0, i8 3, float %337)  ; StoreOutput(outputSigId,rowIndex,colIndex,value)
  ret void
}

; Function Attrs: nounwind readnone
declare float @dx.op.loadInput.f32(i32, i32, i32, i8, i32) #0

; Function Attrs: nounwind readnone
declare i32 @dx.op.loadInput.i32(i32, i32, i32, i8, i32) #0

; Function Attrs: nounwind
declare void @dx.op.storeOutput.f32(i32, i32, i32, i8, float) #1

; Function Attrs: nounwind readnone
declare float @dx.op.tertiary.f32(i32, float, float, float) #0

; Function Attrs: nounwind readnone
declare float @dx.op.unary.f32(i32, float) #0

; Function Attrs: nounwind readnone
declare float @dx.op.dot3.f32(i32, float, float, float, float, float, float) #0

; Function Attrs: nounwind readnone
declare float @dx.op.binary.f32(i32, float, float) #0

; Function Attrs: nounwind readonly
declare %dx.types.ResRet.f32 @dx.op.rawBufferLoad.f32(i32, %dx.types.Handle, i32, i32, i8, i32) #2

; Function Attrs: nounwind readnone
declare float @dx.op.dot2.f32(i32, float, float, float, float) #0

; Function Attrs: nounwind readonly
declare %dx.types.ResRet.f32 @dx.op.sampleLevel.f32(i32, %dx.types.Handle, %dx.types.Handle, float, float, float, float, i32, i32, i32, float) #2

; Function Attrs: nounwind readnone
declare i32 @dx.op.binary.i32(i32, i32, i32) #0

; Function Attrs: nounwind readonly
declare %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32, %dx.types.Handle, i32) #2

; Function Attrs: nounwind readonly
declare %dx.types.CBufRet.i32 @dx.op.cbufferLoadLegacy.i32(i32, %dx.types.Handle, i32) #2

; Function Attrs: nounwind readnone
declare %dx.types.Handle @dx.op.annotateHandle(i32, %dx.types.Handle, %dx.types.ResourceProperties) #0

; Function Attrs: nounwind readnone
declare %dx.types.Handle @dx.op.createHandleFromBinding(i32, %dx.types.ResBind, i32, i1) #0

attributes #0 = { nounwind readnone }
attributes #1 = { nounwind }
attributes #2 = { nounwind readonly }

!llvm.ident = !{!0}
!dx.version = !{!1}
!dx.valver = !{!2}
!dx.shaderModel = !{!3}
!dx.resources = !{!4}
!dx.viewIdState = !{!19}
!dx.entryPoints = !{!20}

!0 = !{!"dxc(private) 1.8.0.0 (private, 00000000)"}
!1 = !{i32 1, i32 6}
!2 = !{i32 1, i32 8}
!3 = !{!"ps", i32 6, i32 6}
!4 = !{!5, null, !13, !17}
!5 = !{!6, !8, !9, !11, !12}
!6 = !{i32 0, %"class.StructuredBuffer<vector<float, 4> >"* undef, !"", i32 0, i32 0, i32 1, i32 12, i32 0, !7}
!7 = !{i32 1, i32 16}
!8 = !{i32 1, %"class.StructuredBuffer<vector<float, 4> >"* undef, !"", i32 0, i32 1, i32 1, i32 12, i32 0, !7}
!9 = !{i32 2, %"class.Texture2D<vector<float, 4> >"* undef, !"", i32 0, i32 2, i32 1, i32 2, i32 0, !10}
!10 = !{i32 0, i32 9}
!11 = !{i32 3, %"class.Texture2D<vector<float, 4> >"* undef, !"", i32 0, i32 3, i32 1, i32 2, i32 0, !10}
!12 = !{i32 4, %"class.Texture2D<vector<float, 4> >"* undef, !"", i32 0, i32 4, i32 1, i32 2, i32 0, !10}
!13 = !{!14, !15, !16}
!14 = !{i32 0, %hostlayout.View* undef, !"", i32 0, i32 0, i32 1, i32 6748, null}
!15 = !{i32 1, %Scene* undef, !"", i32 0, i32 1, i32 1, i32 332, null}
!16 = !{i32 2, %Material* undef, !"", i32 0, i32 2, i32 1, i32 44, null}
!17 = !{!18}
!18 = !{i32 0, %struct.SamplerState* undef, !"", i32 0, i32 0, i32 1, i32 0, null}
!19 = !{[22 x i32] [i32 20, i32 16, i32 112, i32 112, i32 112, i32 0, i32 112, i32 112, i32 112, i32 112, i32 65527, i32 0, i32 0, i32 0, i32 5, i32 5, i32 5, i32 0, i32 63351, i32 63351, i32 7, i32 0]}
!20 = !{void ()* @MainPS, !"MainPS", !21, !4, !42}
!21 = !{!22, !34, null}
!22 = !{!23, !26, !28, !30, !32, !33}
!23 = !{i32 0, !"TEXCOORD10_centroid", i8 9, i8 0, !24, i8 2, i32 1, i8 4, i32 0, i8 0, !25}
!24 = !{i32 0}
!25 = !{i32 3, i32 7}
!26 = !{i32 1, !"TEXCOORD11_centroid", i8 9, i8 0, !24, i8 2, i32 1, i8 4, i32 1, i8 0, !27}
!27 = !{i32 3, i32 15}
!28 = !{i32 2, !"INSTANCE_ID", i8 5, i8 0, !24, i8 1, i32 1, i8 1, i32 2, i8 0, !29}
!29 = !{i32 3, i32 1}
!30 = !{i32 3, !"TEXCOORD", i8 9, i8 0, !31, i8 2, i32 1, i8 3, i32 3, i8 0, !25}
!31 = !{i32 9}
!32 = !{i32 4, !"SV_Position", i8 9, i8 3, !24, i8 4, i32 1, i8 4, i32 4, i8 0, !25}
!33 = !{i32 5, !"SV_IsFrontFace", i8 5, i8 13, !24, i8 1, i32 1, i8 1, i32 2, i8 1, null}
!34 = !{!35, !36, !38, !40}
!35 = !{i32 0, !"SV_Target", i8 9, i8 16, !24, i8 0, i32 1, i8 4, i32 0, i8 0, !27}
!36 = !{i32 1, !"SV_Target", i8 9, i8 16, !37, i8 0, i32 1, i8 4, i32 1, i8 0, !27}
!37 = !{i32 1}
!38 = !{i32 2, !"SV_Target", i8 9, i8 16, !39, i8 0, i32 1, i8 4, i32 2, i8 0, !27}
!39 = !{i32 2}
!40 = !{i32 3, !"SV_Target", i8 9, i8 16, !41, i8 0, i32 1, i8 4, i32 3, i8 0, !27}
!41 = !{i32 3}
!42 = !{i32 0, i64 16, i32 5, !24}
!43 = distinct !{!43, !"dx.controlflow.hints", i32 2}
!44 = distinct !{!44, !"dx.controlflow.hints", i32 1}
