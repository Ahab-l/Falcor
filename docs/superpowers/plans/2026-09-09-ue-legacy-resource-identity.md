# 参考场景、文件资源与实际GPU身份

继续已授权的完整骨干目标，先补齐DefaultLit参考帧的外部输入边界，再进入真实模型扩展。前轮进展为Capture A/B/C/D/depth/stencil全allocation逐位一致；不能把JSON/Shader快照误称为所有资源已冻结。

1. Pipeline自动复制材质DDS及source_geometry三类sidecar至内容地址资源目录，重写Scene.json引用，记录大小/SHA1/SHA256。重放验证完整引用注册表，原生Config及纹理加载前后检查实际文件。旧prepared图持有已加载GPU资源；新图拒绝损坏的冻结文件。
2. 独立RDC场景包保存manifest、四个NPZ、stock/source loader、DDS、sidecar及UE材质定义，消除原build/rdc-scene路径依赖；模板/逻辑引用参与包ID，避免包含绝对目标目录的哈希循环。离线验证封包完整性和重放路径。
3. 项目原生接口读取实际Scene的GPU顶点/索引/纹理（所有mip/层）、实例变换、材质/采样器、相机、灯光/环境参数，输出canonical identity。严格参考模式将该identity纳入Scene输入指纹，Init在清除输出前每帧验证。支持当前static triangle范围；动态内容需重新绑定，不能悄悄沿用参考身份。
4. 验收必须包含原输入文件改变后的旧包独立重载、同图/新图原始输出逐位不变、同路径内容变化更新输入身份、冻结资源损坏拒绝，以及真实相机/几何/材质或GPU纹理变化的运行时失配。失败不应改写旧参考图输出。
5. 保留Schema/Codec职责与默认generation，运行79项既有离线及新增测试、RDC严格原始比较、Schema/Adapter和相关实际GPU回归。记录性能成本、覆盖范围和未完成项，不将参考帧锁定当作动画/时间历史系统。

允许牺牲性能：引用身份诊断使用同步GPU回读。Web编辑以后应生成新绑定/图；最终灯光、SSR、TSR等仍按权威顺序实现。

## 2026-09-09 验收状态

步骤 1–5 已完成当前静态参考范围的实现与验证，见 [资源身份报告](../../research/ue-legacy-resource-identity.md) 和 [机器证据](../../research/ue-legacy-resource-identity-result.json)。102项离线、18项原生测试和实际Scene/独立package/Adapter资源保留/Schema/严格RDC回归通过。实际GPU资源变化拒绝与恢复、源fixture消失后的独立重载均已执行；原始NPZ hash保持不变。

严格身份限定同步后的static undisplaced triangle + StandardMaterial，排除尚未覆盖的sideband材质、UDIM/profile与动画历史；原生view/typeless能力缺口仍保留。独立规格/质量审查已通过，无提交/合并。下一阶段为真实Shading Model扩展，整个渲染骨干与最终画面仍未完成。
