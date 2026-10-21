# 出图线：内核变体的构建差异与 A/B/C 分组（工程笔记）

> **这是工程笔记，不是客户文档。** 选型与对外结论请看
> [`../../docs/comfyui-image.md`](../../docs/comfyui-image.md)。
>
> 这里记的是 2026-10-15 ~ 10-17 拆「int8 为什么忽快忽慢」时的**构建级证据**：
> 两个 kernel 变体的文件清单与体积、`provider.json` 被改坏的排查、以及为把
> 「torch / kernel / provider」三者拆开而设计的 A/B/C 分组。
> **结论已在 `docs/comfyui-image.md` §0 / §0.5 / §0.6，这里只留过程。**

### §0.1 两个「内核变体」到底是什么：不是新版 vs 旧版，是**同一版本的两个构建**

用户直觉「越高版本越好」在这里**方向对、对象错**。实测两个环境的构建：

| | `python_embeded` | `python_embeded_torch213` |
|---|---|---|
| torch | 2.12.0+xpu | **2.13.0+xpu** |
| `omni_xpu_kernel` 版本 | `0.2.0b2+torch212.bmg` | `0.2.0b2+torch213.bmg` |
| **kernel 的 `Requires-Dist`** | **`torch==2.12.0`** | **`torch==2.13.0`** |
| **配套 provider** | **0.2.33**（revision `950214ad`） | **0.2.31**（revision `9eccb7f`） |
| provider 声明的 torch | 2.12.0+xpu ✓ 匹配 | 2.13.0+xpu ✓ 匹配 |
| kernel 包体积 / 文件数 | 93.0 MB / 17 | 85.2 MB / 14 |

**两条必须记住的事实：**

1. **两个 kernel 的版本号完全相同（都是 `0.2.0b2`）**——
   上游 `VERSIONING.md` 明写：*「版本号由仓库所有者控制，**不得因为加了功能、修复、
   性能里程碑或依赖固定而改版本**」*。
   → **「版本号相同」不代表「功能相同」。**
2. **真正的版本序在 provider 上**：`0.2.33`（rev `950214ad`）**新于** `0.2.31`（rev `9eccb7f`）。
   **torch 2.13 并不是「更高版本的内核」，它只是更旧那套 provider 配套的构建。**

**torch 与 kernel 与 provider 是绑死的**（kernel 的 `Requires-Dist` 锁死 torch 版本、
provider.json 只声明单一 `torch_version`），**无法单独换其中之一**——
所以任何「换内核」的实验，测的其实是**整套**。

### §0.2 两套的差异到底在哪：不是「能力有没有」，是「实现成熟度」

| 对比项 | 结果 |
|---|---|
| kernel 独有文件 | torch212 那套**多 16 个真实文件**：`_compile_meta.py` / `_compile_ops.py`、`cute/sol_attn_v2.py` + 6 个 `sol_attn_*.hpp`、`policies/kernel-policy-v1.json`、`csrc/kernel_tuning_overrides.h` + `csrc/generated/*` |
| 核心扩展体积 | `cute/cute_fmha_torch.pyd`：**8.74 MB vs 1.50 MB（5.8 倍）**；`_C.pyd`：9.56 MB vs 8.41 MB |
| **注册的能力清单** | **实测两边完全相同**（都含 `int8_linear` / `mm_int8` / `quantize_int8_tensorwise` / `convrot_w4a4_linear` / `dequantize_int8_convrot_weight` / `prepare_int4_weight_for_int8_linear`） |

⚠️ **能力清单相同，不代表跑得一样快。** 上游 README 明确：
*「XPU 后端从**已安装的 companion wheel 里的 native 符号**独立注册每个能力」*、
*「一个 ✓ 仍可能有 dtype / shape / layout / **数值**限制」*。

→ **能力清单不能当性能依据**。10-15 那次测出 `torch213` 的 int8 GEMM 慢近一倍，
而两边能力清单一模一样 —— 这只可能是**同一能力背后的实现成熟度不同**。

> 📌 **两个「清单」要分清**：
> `Found comfy_kitchen backend xpu: {...'capabilities': [...]}` 是 **comfy_kitchen registry 层**
> 的能力表；kernel 包里 pyd 导出的 native 符号是**更下一层**。10-15 说的「符号更多」指后者。

### §0.4 实验设计：三个数据点才能拆开「torch / kernel / provider」

A 与 B 只对比「整套」，跑出来的差异**不能归给任何一项**。
10-15 那次「换内核 int8 快 1.78×」也是同样性质的问题——它换的也是整套。

| 组 | torch | kernel 构建 | provider（revision） | 用途 |
|---|---|---|---|---|
| **A** | 2.12 | `…+torch212.bmg` | 0.2.33（`950214ad`） | 已知：int8 稳态 **51.75 s** |
| **B** | 2.13 | `…+torch213.bmg` | 0.2.31（`9eccb7f`） | 只换整套的对照 |
| **C** | **2.12** | `…+torch212.bmg` | **0.2.31** | **分离点：只降 provider** |

- **C 也慢** → 慢的是 **provider 0.2.31 那套代码**（0.2.33 增补的实现才是关键）
- **C 仍快** → 慢的是 **kernel 构建 / torch 版本**，与 provider 无关

C 组技术上可行：`0.2.31` 的 `provider.json` 声明 `torch_version = "2.12.0+xpu"`，
**与 torch 2.12 环境天然匹配**；只需把 `compatible_versions` 补上 `0.2.37`
（本机装的是它），`vendored_files` 的 sha256 随整包搬来**自洽**。
准备脚本 `_stage_provider_031.py`（`prepare` / `verify` / `restore`），
`verify` 会先校验 52 个 vendored 文件的哈希——这是 provider 启动的硬门槛。

### §0.3 ⚠️ 顺带查出：`python_embeded_torch213` 的 provider 声明被改坏了

该环境 `provider.json` 的 `torch_version` 被改成 `2.12.0+xpu`，而它实际装的是 `torch 2.13.0+xpu`
→ OmniXPU 的**字符串相等**校验（`runtime_bootstrap.py`）会**拒绝激活该 provider**，
`import comfy_kitchen` 落到 canonical 0.2.37（签名完整、不崩，但**走不到 XPU 原生路径**）。
同目录 `provider.json.bak` 里是正确的 `2.13.0+xpu`。

→ 已恢复（保留 `compatible_versions` 含 `0.2.37`）。**这条本身就是今晚能跑对照的前提**：
不修的话测的是「provider 被拒 vs provider 激活」，而不是「两套 provider 的差别」。
