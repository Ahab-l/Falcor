# 旧 UE 包装源码参考归档

这些 `.reference` 文件保留旧包装的原始字节、材质表达式和接线方式，**不参与 CMake Shader 发布，不是可运行入口**。

- `SourceProcGrid`：旧网格材质表达式及 UE/Falcor 坐标转换。
- `SourceSky`：旧天空材质表达式与原始算法的绑定参考。
- `UEReferenceLighting`：旧光照包装与旧 GBuffer ABI 的绑定参考。

它们引用的旧 Raster、FrameExposure、Lighting codec 已退役。需要使用其中算法时，应为当前材质/Schema 显式编写新的 Pass 绑定，而不是恢复旧 ABI。独立算法原文、来源和许可证继续保留在 `Source/RenderPasses/customrenderpipline/Extensions/UEReference`。

完整原路径、SHA256 与本次归档副本对应关系：`build/native-framework-completion/cleanup-wrapper-supplement.json`；压缩备份：同目录 `cleanup-wrapper-supplement.zip`。
