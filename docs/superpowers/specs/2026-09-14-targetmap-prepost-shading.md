# targetmap 后处理前 shading：已确认范围

用户于 2026-09-14 确认：E:/rdc/ue/2.rdc，E2962 为最终验收，E2793 为中间检查点；不经过 Bloom、Tonemap、调色再比较。参考完整证据：E:/Project/falcor/Falcor-m0/build/rdc-shading-scope-audit-20260914/assessment-zh.md。

生产路径复用原生 RenderGraph、现有通用 Pass、Schema 和 Slang；不恢复旧 Config/SchemaPipeline/UE ABI/整图事务。捕获输出仅用于离线 oracle，不得作为生产 shading/GBuffer/depth/shadow/history 输入。

当前分项目 A0 仅建立可重现 raw HDR 基线与实际 pipeline/input 身份证据，不宣称 renderer 图像一致。E2793/E2962 均锁定 ResourceId::955、RGBA16F；读取实际 viewport/scissor/subresource 后验证，不能以 PNG 替代。分别报告有效区域和 padding、RGB 与 alpha。

后续顺序：A1 源场景/相机/GBuffer；A2 CSM/方向光；A3 GI/AO/反射及历史；A4 天空云雾；A5 clean-baseline 两截点全图验收。每个分项目依赖实际缺口后再细化，不以框架测试替代效果。

约束：实现树 E:/Project/falcor/Falcor-m0 已是独立 worktree；保留现有未提交修改，不 commit/merge/reset。GPU/replay/build 只由 root 串行启动，有界进程正常关闭。当前 V5 UI blocked 目标独立，不因此恢复桌面渲染。
