# 出图线：ComfyUI 0.39 的 XPU INT8 门禁与签名适配（工程笔记）

> **这是工程笔记，不是客户文档。** 选型与对外结论看
> [`../../docs/comfyui-image.md`](../../docs/comfyui-image.md) 第五节。
>
> 这里留的是**源码级取证**：这行门禁的出处、签名不匹配的逐参数对账、验收数值、
> 以及诊断脚本怎么用。客户只需要知道「要打补丁、打了之后什么变化」。

## 一、门禁的出处分层

**别读成「Intel 官方说 XPU 不支持 INT8」。** 这行代码出自 **ComfyUI 上游 PR #16130**
（commit `313a76fb8`，2026-09-08，作者 Jialong(Bruce) Li），
**本机与上游 HEAD 逐字节一致，不是本机改的**。
该 commit 的注释**只解释了 MPS 的动机，没说为什么把 XPU 一起关掉**。

**同一套硬件在 ComfyUI 0.34（秋叶生产栈）上没有这道门禁**，int8 天然走原生
（启动日志 `Native ops: convrot_w4a4, asym_w4a8_int8, int8_tensorwise`）。
完整出处与 0.34 对照见 [`../../docs/comfyui-capability.md`](../../docs/comfyui-capability.md) §3.2。

## 二、Qwen-Image 2.1 跑不起来的真实原因：8 参 vs 12 参

首次 4 次全崩，报错很具体：

```
TypeError: int8_linear() got an unexpected keyword argument 'input_act_weight'
```

**根因（已定位到行，已修复并端到端实测）**：ComfyUI 0.39 的 `comfy/ops.py:1028`
按 **12 参契约**调用 `ck.int8_linear`（多传 `input_act_weight` / `input_act_eps` /
`residual` / `residual_scale`），而 `comfy_kitchen_xpu_runtime` 里 vendored 的那份
`comfy_kitchen` 是 **0.2.31 / 0.2.33 快照**，其 `int8_linear` 只有 **8 参**
→ 多出来的关键字直接 `TypeError`。

**这是签名不匹配，不是功能缺口。** XPU kernel 的融合激活白名单是
`(None, "none", "gelu_tanh", "swiglu")`——**含 `swiglu`**，而 Qwen-Image 2.1 的调用点
（`comfy/ldm/qwen_image21/model.py:65`）传的正是 `"swiglu"`。
被丢掉的 4 个参数在那条调用路径上**本来就是空值**
（`linear_input_act(linear, x, "swiglu")` 只给 3 个位置参数 ⇒ `act_weight=None`、
`act_eps=0.0`、`residual=None`），只有 pre-norm block 才会用到。
**⇒ 适配后语义完全等价、零性能代价。**

## 三、为什么不能直接改 vendored 文件

`provider.json` 的 `vendored_files` 对每个文件做 sha256 校验，
改一个字节就会 `vendored provider file hash mismatch` 启动失败。
**适配只能落在 provider 之外的运行时。**

## 四、验收与诊断

- 适配层：`ComfyUI/custom_nodes/omni_int8fix.py`
- 诊断脚本：`bench/harness/probe_int8_kernel.py`（复现崩溃 → 装适配层 → 对 cosine）
- 数值侧最小验证：cosine **0.9997**、相对 L2 误差 **2.43%**
- B50 上 4/4 端到端：74.93 / 47.93 / 47.42 / 46.95 s
- SOP 与逐步操作见 [`../build.md`](../build.md)、[`../install.md`](../install.md)
