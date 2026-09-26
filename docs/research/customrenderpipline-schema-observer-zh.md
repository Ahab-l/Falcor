# V4：通过 Python 和命令行观察自定义 GBuffer

V4 已把 Schema 附件绑定、GPU 解码、字段比较和外部程序访问接通。运行实例使用 Falcor 原生 Scene、RenderGraph、ComputePass 和异步 staging 读回；`to_numpy()` 等显式同步兼容 API 仍保留。材质/codec 仍由 G4/G5 生成结果及手写 Slang 定义，不依赖旧 UE 材质 ABI 或深度约定。

## 启动一个可访问的渲染实例

在 CMD 中执行：

```bat
cd /d E:\Project\falcor\Falcor-m0
set CRP_OBSERVER_SESSION=E:\Project\falcor\Falcor-m0\build\v4-session
build\windows-vs2022\bin\Release\Mogwai.exe --script scripts\customrenderpipline\native_schema_observer.py
```

`v4-session` 必须是尚不存在的目录，避免连接到另一实例或覆盖已有结果；再次启动时换一个目录名。也可以不设置环境变量，由程序创建唯一目录并输出 `V4_SESSION <完整路径>`。无窗口运行可加 `--headless`。启动脚本见 [native_schema_observer.py](../../scripts/customrenderpipline/native_schema_observer.py)。

另开 CMD 或 PowerShell，用任意能运行本客户端的 Python 3.10+ 执行以下命令；客户端只使用标准库，无需安装 Falcor 或 NumPy。`--session` 指向运行实例的会话目录。

```bat
python scripts\customrenderpipline\inspect_cli.py --session build\v4-session list --graph SchemaGBuffer
python scripts\customrenderpipline\inspect_cli.py --session build\v4-session inspect --graph SchemaGBuffer --region 64 36 1 1 --fields roughness materialID normalW
```

`--region X Y W H` 使用附件的整数 texel 坐标，第一维是 X，第二维是 Y。结果数组按 `[Y][X]` 排列；向量多一维通道。坐标相对附件，不是窗口缩放后的 UI 坐标。列举命令返回实际尺寸、可观察输出、字段类型、附件映射和布局标识。

## 查询结果

小区域直接返回 JSON，包含：

- `version`、`request_id`、`instance`：协议版本、请求和实例标识。
- `graph`、`frame`、`layout_hash`：图名、服务本地的已渲染帧序号、观察使用的布局标识。
- `fields`：调用生成 decoder 后的逻辑字段。
- `storage`：提取的存储槽，包括位字段的整数 code。
- `attachments`：GPU `Texture.Load()` 读到的附件值。

例如 `materialID` 返回 `{"dtype":"uint32","shape":[1,1],"values":[[12]]}`。UINT/INT 字段通过整数位传输，完整 32 位 ID 不经过 float 转换。bool 单独标记为 bool。

`attachments` 中的 UNORM 是归一化浮点数；sRGB RGB 通道经过硬件线性化，BGRA 按 Shader 的逻辑 RGBA 顺序读取。它们与纹理的原始字节不同。要获取原始字节，用下面的 `read` 命令。

## 导出字段和读取原始字节

```bat
python scripts\customrenderpipline\inspect_cli.py --session build\v4-session inspect --graph SchemaGBuffer --region 0 0 128 72 --export
python scripts\customrenderpipline\inspect_cli.py --session build\v4-session read --graph SchemaGBuffer --output GBuffer.materialBits
python scripts\customrenderpipline\inspect_cli.py --session build\v4-session read --graph SchemaGBuffer --output GBuffer.depth --mip 0 --slice 0
```

`inspect --export` 将所有返回分组写入会话目录的 `exports/<唯一标识>.npz`，JSON 返回每个数组的绝对路径、archive key、dtype 和 shape。未加 `--export` 时，超过 4096 个返回分量也自动导出。导出的内容保留原始数组类型：

```python
import numpy as np
with np.load(result['fields']['materialID']['path'], allow_pickle=False) as data:
    ids = data[result['fields']['materialID']['key']]
```

`read` 复用现有 `PipelineObserver.read()`，将 bytes 保存为 `.bin`，同时返回资源格式、尺寸等元数据。它可以读取该图已标记的普通纹理、缓冲及现有读回入口支持的子资源。D32FloatS8Uint 沿用现有 D3D12 单采样 Depth/Stencil 平面补充，各平面和行布局元数据一并返回；本次未扩展它的格式覆盖范围。原始文件需要按实际资源格式解释。

导出文件保留供调用程序消费，不自动删除。请求/响应的临时文件由命令通道清理；会话的结果文件由使用者在不再需要时管理。

## 按字段比较

参考文件使用数值 NPZ，字段键可以是 `roughness`，也可以直接使用观察导出的 `fields.roughness`。每个参考数组的 shape 和 dtype 必须与查询区域结果一致；不会自动裁剪整图参考、转换整数类型或变换颜色空间。允许在参考 NPZ 中附加 bool `[H,W]` 覆盖掩码。

规则文件示例，保存为 `rules.json`：

```json
{
  "materialID": {"kind": "exact"},
  "roughness": {"kind": "numeric", "atol": 0.001, "rtol": 0.0},
  "normalW": {"kind": "angle", "max_degrees": 0.1}
}
```

```bat
python scripts\customrenderpipline\inspect_cli.py --session build\v4-session compare --graph SchemaGBuffer --region 0 0 128 72 --reference reference.npz --rules rules.json --mask covered
```

`--mask covered` 表示使用参考 NPZ 中名为 `covered` 的 bool 数组；省略则比较全部像素。`--fields` 省略时采用规则文件中的字段，显式提供时必须与规则覆盖的字段集合一致。

| 规则 | 适用数据 | 判断 |
| --- | --- | --- |
| `exact` | 整数或 bool | 各分量完全相等 |
| `numeric` | 浮点标量/向量 | `abs(actual-reference) <= atol + rtol*abs(reference)` |
| `angle` | 浮点 float3 | 归一化后方向夹角不超过 `max_degrees` |

报告包含总体 `passed` 和逐字段结果。exact/numeric 的样本数是分量数，angle 是向量数；numeric 包含最大绝对误差、MAE、RMSE 等。使用掩码时 numeric 的 `worst_index` 指向筛选后的数组，而非原图坐标。阈值、颜色空间、法线语义均由调用者明确指定。

比较先应用覆盖掩码，再检查选中数据的有限性；选中的零长度法线、NaN/Inf 和空掩码会报错。未选中的背景 NaN 不会导致比较失败。普通 `inspect` 对请求字段的 NaN/Inf 保持报错；需要诊断其原始编码时使用 `read`。

## 供外部程序使用

CLI 的 stdout 始终为一份 JSON，诊断帮助信息写 stderr。退出码：

| 退出码 | 意义 |
| --- | --- |
| 0 | 查询成功或比较通过 |
| 1 | 比较完成，但超出容差 |
| 2 | 参数、文件、布局、Shader 或执行错误 |
| 3 | 请求超时 |

客户端模块也能直接使用：

```python
from observer_transport import request
reply = request(session_dir, 'inspect', 'SchemaGBuffer',
                {'region': [64, 36, 1, 1], 'fields': ['roughness']}, timeout=10)
```

模块位于 `scripts/customrenderpipline`，外部 Python 程序需把该目录加入 `sys.path`，或直接以 subprocess 参数列表调用 [inspect_cli.py](../../scripts/customrenderpipline/inspect_cli.py)。返回结构化错误而不是通过 stdout 日志推断状态。

本地命令通道使用原子 JSON 文件发布，无需网络端口。每个会话对应一个已注册图，请求明确指定图名。超时默认 10 秒、最大 300 秒；可用全局 `--timeout` 修改。排队请求超时后撤回；已开始的 GPU 工作不能被此接口强行取消，过期结果丢弃。渲染实例停止或没有推进帧时，请求会超时；正常关闭的会话会直接报告关闭状态。

客户端读取回复 JSON 时，如文件尚未出现或暂时被 Windows 共享锁占用，会沿用原请求期限继续轮询，不重新投递操作，不让渲染线程等待。持续占用或永久拒绝读取会最终返回 `timeout`；会话元数据、请求准入等错误仍立即报告，不由这个回复重试掩盖。

## 在自己的图中接入

在第一次渲染前注册，观察工具会标记 Schema 所需附件：

```python
from observer import PipelineObserver
from schema_observer_service import ObservationService
from observer_mogwai import MogwaiObservation

observer = PipelineObserver(graph).schema(artifacts, pass_name='GBuffer')
service = ObservationService(observer, session_dir)
attachment = MogwaiObservation(m, service)
```

渲染线程提交异步查询，后续帧由现有 attachment 推进服务和池，再检查 ticket。不要在渲染线程写等待循环：

```python
ticket = service.submit({'operation': 'inspect', 'graph': graph.name,
                         'arguments': {'region': [64, 36, 1, 1], 'fields': ['roughness']}})
# 后续帧：
if ticket.ready:
    reply = ticket.result()
```

以下是仍保留的**显式同步兼容接口**，适合离线诊断，不是 UI/CLI 帧回调的默认路径：

```python
sample = observer.inspect([64, 36, 1, 1], fields=['roughness', 'materialID'])
report = observer.compare([0, 0, 128, 72], reference_arrays, rules, mask=coverage_mask)
reply = service.handle({'operation': 'list', 'graph': graph.name, 'arguments': {}})
```

Testbed/自有渲染循环可以在 `testbed.frame()` 后调用 `service.after_frame(graph.name)`。这些 GPU 操作必须由创建观察工具的同一渲染线程执行；通信客户端只投递请求。Mogwai 适配器会调用此前的图执行回调，未处理时执行一次原生图，然后处理本帧请求。`attachment.close()` 关闭会话并恢复仍由它持有的回调；保留应用后来安装的回调，已关闭的包装器不再执行观察。直接使用服务时由调用者负责在正确帧边界调用。

## 已实现范围和开销

Schema 字段解码目前接受声明格式的单采样、非数组二维附件，观察 mip 0。区域最多 1048576 像素，输出 word 缓冲最多 128 MiB，超出时显式拒绝。Cube、其他 mip/数组层继续使用原始 `read` 或已有图集入口；这里没有宣称任意子资源均可自动解码。

首次观察编译 ComputePass，随后复用 Shader；一次区域观察将字段、存储槽和附件值合并到一个 word 缓冲。默认 UI/CLI 在本次 dispatch 后立即异步复制到独立 staging，后续帧 ready 时才取数据；同步兼容接口仍使用 `to_numpy()`。选择少数字段限制返回字段，但 GPU 仍计算完整 decoder 和存储槽。无请求时不执行观察 Shader 或读回，正常帧仍有有界的本地命令轮询。

默认同线程共享池最多 8 个任务、合计 64 MiB staging；取消尚未完成的任务不立即释放计账。异步单请求也受 64 MiB 预算限制，可能早于上面的 decoder 理论上限被拒绝。这不是进程总内存或 FPS 保证；最终应用性能仍待验收。

默认绑定会核对原生 GBuffer Pass 使用的 definition 与生成结果一致，检查生成文件和直接 Shader 源哈希；变化后必须重新生成并重新绑定。独立第三方生产 Pass 可显式传入附件映射及 `producer_contract=layout_hash`，该值是调用者对匹配布局的声明，不是工具自动证明其 Shader 正确。传递 include 依赖仍未冻结。

V4 初始阶段的 C++ 补充是 `RenderGraph.device`、`RenderGraph.execute()` Python 绑定及 Mogwai 图执行回调版本标识；后续 R4 增加了原生 Texture/Buffer/精确 DepthStencil 异步任务。V5 真实 UI 交互、最终性能及最终 RDC 对齐仍独立跟踪；整图回滚按要求暂缓。

## Inspector 关闭与重开

正常 UI 入口是 `scripts/customrenderpipline/native_schema_observer_ui.py`。隐藏面板后可调用 `panel.show()`；`panel.close()` 会释放面板窗口、回调和预览，但保留图与 CLI 服务。彻底关闭后在帧间用 `SchemaInspectorPanel(m, service)` 构造新面板，不对旧面板调用 `show()`。

`native_schema_observer_ui_live.py` 是单独的真实鼠标验收工具：彻底关闭 Inspector 后出现 **Reopen Inspector** 原生按钮，帧间使用同一服务重建面板，不重建图。它有测试节流及动作截图，不能用其 FPS 衡量正常入口性能。当前原生 callback/重开后 idle 验证通过，真实鼠标/文件选择验收仍未完成。

验证证据见 [V4 验证索引](../../build/native-schema-observer/verification.json) 和 [真实 GPU/CLI 验收脚本](../../scripts/customrenderpipline/native_schema_observer_smoke.py)。
