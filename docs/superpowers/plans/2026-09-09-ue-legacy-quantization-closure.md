# DefaultLit 六个残差的收口

继续已授权的 DefaultLit 原始 Buffer 验收。先有 Capture DebugPixel 与原生 MRT 的独立观测，再修改生产代码。

1. 已取得五个Specular及一个法线点的完整Capture trace。DBuffer specular输入是identity；其法线路径即使identity也执行归一化。
2. 已运行两个互不叠加的诊断：精确保留Codec最后bias加法的运算依赖，使B全allocation一致；补上identity DBuffer法线归一化，使A全allocation一致。诊断原始与变体分别保存。
3. 生产Codec保留最后bias加法的精度。DBuffer作为MaterialProgram之后、Codec之前的显式材质修饰步骤；仅支持disabled/identity，默认disabled。identity受primitive receives-decals标志和material decal response normal位控制，不能无条件对全部材质重复normalize，也不声称支持实际decal纹理。
4. Raster和显式Adapter共用此修饰步骤；相关配置进入现有完整Scene输入指纹，材质response进入程序契约。Schema继续只管布局/ID/分派。
5. 原生RDC验收改为A/B/C/D/depth/stencil全allocation精确相等。另验identity开关、primitive/response gating和未知mode拒绝；回归Schema迁移/回滚、Adapter和离线测试。保留SceneColor背景警告文字与后续Lighting等未完成项。

DebugPixel模拟值和理想UNORM公式不能代替真实GPU输出；实际MRT实验才用于确认修复。精度传播可改变编译结果，须依据整个allocation回归，不能只盯六点。

## 完成记录

以上限定工作已完成。实际生产A/B/C/D/depth/stencil全allocation逐位一致；最终严格RDC、双路径DBuffer门控、Schema迁移/回滚、Adapter及ViewRect/grid回归通过，79项离线通过。独立审查指出的完整A/D/depth断言缺口已修复并复核关闭。见 [阶段报告](../../research/ue-legacy-defaultlit-exact.md)。外部资源身份及整个渲染骨干仍未完成。
