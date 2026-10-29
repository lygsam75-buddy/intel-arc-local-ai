# 基准口径

跨机型、跨后端、跨时间点要能横向比较，前提是口径固定。**口径一旦变，历史数字全部作废，必须全量重测。**

> **路径写法约定**：本仓库**不出现任何机器的绝对路径**。所有本地路径一律写成
> **尖括号语义占位符**——`<仓库根目录>` / `<模型目录>` / `<llama.cpp>/build/bin` /
> `<SYCL 运行时目录>` / `<oneMKL 目录>` / `<部署目录>` / `<工具目录>` / `<非系统盘>` 等。
> 看到 `<…>` 就是「你按自己机器填」，**不是没写完的 TODO**。
> 仓库内部的日志引用写成**仓库相对路径**（`bench/logs/…`）。
> 采集脚本里机器相关的路径走环境变量（`ARC_REPO` / `ARC_MODELS` / `ARC_LLAMA_BIN` /
> `ARC_SYCL_PATH` / `ARC_PYTHON` / `ARC_MODEL_OFF_FLAG`），别硬编码。

> **`bench/notes/` 是过程性工程笔记**（为什么这么判、当年的拆解与负结果），**不是客户文档**；
> 对外结论一律在 `docs/`。

---

## 每次记录必须登记的东西

> ★ **只登记「测这张卡」用得上的项。** 判断标准一句话：**这个值变了，本次测的数字会不会跟着变？**
> 不会变的（别的卡 / 别的设备的型号、外设、机器上的无关硬件）**一律不写**——
> 读者没有义务替你判断某个值跟结果有没有关系，写上去只会误导。
> 典型反例：把一块**与本系产品无关的卡**的规格或速度并排进来；把机器上另一块 GPU、
> 芯片组挂了哪些外设也列进拓扑。
> 反过来，**会影响结果的一律不能省**：显存可用量、ECC 状态、槽位、驱动版本、
> 内存与页面文件、CPU 的 AVX-512 能力（关系到 MoE 专家在 CPU 侧算得动算不动）。

### 1. 硬件

| 项 | 说明 |
|---|---|
| GPU 型号 | 精确到 SKU（Arc Pro B70 32G / Arc Pro B50 16G …） |
| **芯片 DEV + SUBSYS** | **AIB 口径，必填。** Intel 走板卡伙伴模式，同型号不同厂的板子性能未必一致。`DEV_E212` 定 GPU 芯片，`SUBSYS_25221EF7` 定是哪块板（高 4 位板型号编码 + 低 4 位板厂 vendor id）。取证：`bench/harness/gpu_identity.py` |
| 驱动版本 | 例 `32.0.101.8976` |
| **VBIOS（OptionROM）** | **AIB 口径。从 2026-10-16 起新记录必填**（历史记录未落此字段，卡已拆的补不回来）。板厂各自刷 VBIOS，是区分批次最直接的一项。取证：`bench/harness/gpu_sysman.py`（Level Zero Sysman 固件枚举，读 `OptionROM` 那条；**不用开 IGS**）。本机 B50 = `2304240000` |
| **显存可用量（GiB）** | **必填。受 ECC 开关影响：27.25 GiB（ECC on）vs 31.16 GiB（ECC off）／B50：约 13.3 GiB vs 15.51 GiB** |
| **ECC 状态** | **必填。Intel 驱动默认关闭、需人工到 IGS 开启**；`off` / `on` 二选一。取证同 `gpu_sysman.py`（注意枚举值两代编号相反，**定论看物理容量**） |
| 系统内存 | 容量 + 通道数 |
| 页面文件 | 当前大小 + 是否系统托管 + **在哪个卷** |
| CPU | 型号（决定 AVX-512 / AVX2 支持，影响专家卸载场景） |
| 槽位 | CPU 直连槽 / 芯片组槽（**回溯上级链判定，别看总线号**）。取证：`bench/harness/gpu_identity.py`（含 `--topo`） |

> **为什么 DEV+SUBSYS 必填**：AI 加速卡很少是 Intel 自产整卡，多由蓝戟 / 华擎 / 宏碁
> 等厂做板。板厂不同 → VBIOS、功耗墙、显存颗粒、散热都不同。
> 本机 B50 与 B70 **同为蓝戟 GUNNIR 板**（`SUBSYS_25221EF7` / `SUBSYS_27421EF7`），
> 所以两者横向对比没有混入板厂差异；换别家的同型号卡则需重测。

### 2. 软件

| 项 | 说明 |
|---|---|
| 引擎与 commit | 例 `llama.cpp build 11431 commit c25030496` |
| **后端** | SYCL / Vulkan / HIP / IPEX —— **必须写明，不同后端不可混比** |
| 编译器 | 例 `IntelLLVM 2025.3.3 for Windows AMD64` |
| oneAPI 组件版本 | 例 `oneMKL 2025.3`（注意：2026.1 需 sycl9，与 sycl8 不匹配） |
| 操作系统 | Windows 10/11 版本号 或 Linux 发行版 |

### 3. 参数

- **测量工具**：`llama-bench` / `llama-server` / `llama-cli` —— **必填，不同工具不可混比**（见 `docs/pitfalls.md` 2.4）
- **完整命令行**，一个不漏（含 `-ngl`、`-fa`、`-ctk`、`-ctv` 等）
- **完整环境变量**（`SYCL_CACHE_PERSISTENT`、`OMP_NUM_THREADS`、`ONEAPI_DEVICE_SELECTOR` 等）
- 模型文件精确名称 + 体积 + 量化档

### 4. 采样方式

| 项 | 要求 |
|---|---|
| 样本数 | 每组不少于 4 次 |
| 冷启 / 稳态 | **分开报**。第 1 次含加载，第 2 次起才是稳态 |
| **SYCL 冷 JIT** | **`-r 1` 的数字一律作废**。实测冷/热差 7.9 倍（decode 9.58 → 75.92 tok/s）。采集必须 `-r 3` 以上；换工具、换参数、换驱动后，第一次视为预热 |
| 出片/出词核对 | **必须核对异常次数**——失败同样会返回一个「耗时」，不核对就是拿失败当成绩 |
| 计时来源 | 客户端 + 服务端两侧都要，对得上才算真跑通 |

---

## 报什么指标

| 指标 | 用途 |
|---|---|
| **解码 tok/s** | 生成速度，最直观 |
| **预填充 tok/s** | 长上下文读取速度 |
| **首 token 延迟** | 交互体感 |
| 稳态均值 | **批量连出的真实成本**（第 2 次起） |
| 显存峰值 | 判断能否再放宽上下文 |
| 提交内存峰值 | 判断页面文件够不够 |

---

## 数据格式

`bench/data/*.json`，schema 为 `arc-xpu-bench/1`：

```json
{
  "schema": "arc-xpu-bench/1",
  "tag": "b70-qwen3.6-35b-a3b-q4_0-sycl",
  "date": "2026-10-06",
  "source": "local",
  "env": {
    "gpu": "Intel Arc Pro B70 32G",
    "driver": "32.0.101.8976",
    "vram_visible_gib": 31.16,
    "ecc": "off",
    "ram_gb": 32,
    "engine": "llama.cpp",
    "engine_version": "0.6.0-dev build 11431 commit c25030496",
    "backend": "SYCL",
    "tool": "llama-bench",
    "device_selector": "opencl:0",
    "sycl_path": "<SYCL 运行时目录>;<oneMKL 目录>",
    "compiler": "IntelLLVM 2025.3.3",
    "oneapi": "oneMKL 2025.3",
    "os": "Windows 11"
  },
  "model": {
    "name": "Qwen3.6-35B-A3B",
    "quant": "Q4_0",
    "file": "Qwen_Qwen3.6-35B-A3B-Q4_0.gguf",
    "size_gib": 19.4
  },
  "args": ["-ngl", "999", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "--ctx-size", "4096"],
  "envvars": { "SYCL_CACHE_PERSISTENT": "1", "OMP_NUM_THREADS": "8" },
  "samples": [
    { "prompt_tok_s": 118.5, "decode_tok_s": 39.82, "note": "llama-server /completion 口径，prompt 48 tok，撞 n_predict 上限" },
    { "prompt_tok_s": 127.9, "decode_tok_s": 45.07, "note": "同上口径，自然 eos 结束" }
  ],
  "summary": { "prompt_tok_s": 123.2, "decode_tok_s": 42.45, "samples": 2 },
  "status": "active",
  "notes": ""
}
```

`source` 取值：`local`（本机实测） / `official`（厂商官方数据） / `community`（社区报告）。
**三者不得混同**，汇总表里必须标明。

`status` 取值：`active`（进入基准表） / `discarded`（作废留档——冷 JIT 预热、参数写错、异常未核对等）。
**作废记录不删**，留着当反面对照，但必须标明原因。

---

## 第二套口径：`comfyui-xpu-bench/1`（ComfyUI 生成：视频 / 图片 / 音乐）

`docs/comfyui-h3.md` 与 `docs/comfyui-image.md` 用的是另一套 schema——指标不是 tok/s 而是**秒**：

```json
{
  "schema": "comfyui-xpu-bench/1",
  "domain": "comfyui-video",
  "tool": "bench_h3.py + ComfyUI /prompt + /history",
  "mode": "fresh",
  "reserve_vram_gb": 5,
  "samples": [ { "ok": true, "server_sec": 240.66, "loads_delta": 5 } ],
  "summary": { "n_ok": 1, "n_fail": 1, "server_sec_mean": 240.66 },
  "env": {
    "gpu": "Intel Arc Pro B70 32G", "chip": "E223", "subsys": "27421EF7",
    "env_confidence": { "gpu": "recorded", "reserve_vram_gb": "inferred" },
    "env_evidence": "<哪份日志的哪一行给的证据>"
  },
  "timing_breakdown": {
    "source": "<服务器日志路径>",
    "dit_load_mode": "completely",
    "dit_loaded_mb": 19996, "dit_offloaded_mb": 0,
    "step_sec_trace": [7.81, 7.40, 7.26, 7.22, 7.21, 7.20],
    "sampling_sec": 43, "sampling_sec_per_step": 7.17,
    "fixed_overhead_sec": 274.5, "sampling_share_pct": 13.5
  }
}
```

**三个域，三条口径，不可跨域求均值**：

| `domain` | 内容 | 关键字段 | 产出工具 |
|---|---|---|---|
| `comfyui-video` | MiniMax H3 | `workload.width/height/resolution` + `frames`/`fps`/`duration_sec_exact`/`selector_megapixels` | `migrate_comfy.py`（H-10）+ `backfill_resolution.py`（H-21） |
| `comfyui-image` | Qwen-Image 2.1 · Krea-2 Turbo | `workload.dit_file/dit_size_gib` + `text_encoder_size_gib`/`vae_size_gib` + `width`/`height` | `migrate_comfy_media.py`（H-22） |
| `comfyui-audio` | MiniMax Music 3 | 同 image，另加 `seconds` | 同上 |

> **分辨率是这类数字的量纲，不是可选元数据。** 同一张卡同一个「0.5 MP」，
> 换套工作流就是 864×480 vs 960×544 —— 不记**实际像素**，这个数既没法核对也没法引用。
> 视频域的分辨率由 `ResolutionSelector` 算法决定（`total_pixels = MP × 1024²`，宽高各自
> round 到 multiple），回填见 H-21。
> **图片·音乐的体积字段（`dit_size_gib` 等）是容量账的唯一依据**——
> 「装不装得下」直接由它判，见 `docs/comfyui-capability.md` 第一节。

与 LLM 口径的关键差异：

| 项 | 要求 |
|---|---|
| `fresh` vs `cached` | **不可混比**。`cached` 会跳过文本编码 + 首帧编码，只能比内核 |
| `first` vs `resident` vs `newprompt` | 图片·音乐域的三角色，**同样不可混比**：`first` 含模型加载、`resident` 是稳态、`newprompt` 会重跑文本编码 |
| `loads_delta` | **必须核对**——不核对就可能把缓存命中当成真在测 |
| 失败样本 | **保留**（`ok: false`）。fresh 口径第 2 至 3 条 `DEVICE_LOST` 是固有约束，不是采集失误 |
| `env.env_confidence` | 逐项标 `recorded` / `inferred`，**推断值绝不伪装成实测**。**位置在 `env` 内**——与本仓库其它 schema 及 `registry_audit.py` 的读法一致。 |
| `env.stack_variant` | `int8fix` = 能力声明 + 签名适配；`sigfix` = **只**签名适配；缺省 = 基线。**带此值的记录不可与基线并排引用**。2026-10-16 实测：Qwen-Image 2.1 的 `int8fix` 与 `sigfix` **采样段逐位相同** → 能力声明对它无收益（见 `docs/comfyui-image.md` §3.4 / §5.1） |
| `env.int8fix_env` | 该组两个开关的实际取值（`OMNIXPU_INT8_COMPUTE` / `OMNIXPU_INT8_SIGFIX`）——2×2 对照靠它还原 |
| 计时 | 服务端 `execution_start` → `execution_success`，不含排队 |
| **板卡身份** | `env` 必须含 `chip` / `subsys` / `device_id` / `board_vendor`（AIB 口径，见上文第 1 节） |
| **`timing_breakdown`** | 日志还在就必须填。**只看总时长会把「卡慢 / 装不下 / 栈变了」混成一个数**——采样段随卡变、固定开销随栈变，拆开才谈得上归因 |

**迁移脚本按卡查表，不再硬编码单卡**（2026-10-16 修正）：

```bash
# tag 里带 b50/b70 可自动判定；判不出会直接报错，不会静默套用默认卡
python bench/harness/migrate_comfy.py --src <_ab_logs> --outdir bench/data --only bench_b50
# 历史组 tag 不含卡名（如 ab_off / scanA），必须显式指定：
python bench/harness/migrate_comfy.py --src <_ab_logs> --outdir bench/data --card b70 --only bench_ab_off
```

> 修正前该脚本把 B70 的身份（`gpu` / `32.16 GiB`）写死在 `RIG` 里，
> 拿它迁 B50 的数据会给 B50 盖上 B70 的身份。现在改为 `CARDS` 表 + tag 判定，
> **判不出就报错退出**——宁可停下来，不能写错型号。

**第一步之前：先把平台身份固定下来**（T-20，两条命令、不需要管理员）：

```bash
python bench/harness/gpu_identity.py     # DEV/SUBSYS/板厂/驱动 + 上级链 → 判定 env.slot
python bench/harness/gpu_sysman.py       # ECC 状态 + VBIOS(OptionROM) + PCIe 能力 + 物理显存
```

- `上级链` 决定 `env.slot`：直达总线 0 的 CPU 根端口 = `pcie5-x8`（CPU 直连槽）；
  链里出现 `1022:43F4`/`43F5` = `pcie4-x4`（芯片组槽）。**别看总线号**——换槽后会变。
- **历史记录若缺 `env.slot`**：文件名带 `pcie5x8` / `pcie4x4` 的可用
  `python bench/harness/backfill_slot.py`（先 `--dry-run`）确定性补录（标 `inferred`）。
  文件名**不带** token 的**不要猜**——`python bench/harness/registry_audit.py` 会把
  「可判却缺失」（回归，要报警）与「不可判」（已知未知，只报数）分开列。
  ⚠️ `env.device_selector` 不能当槽位旁证：B50 单独在机时**副槽**也报 `opencl:0`。
- 固件段的 `OptionROM` 就是 **VBIOS**（填 `env` 用）。
- ECC 用物理容量定论，别只看 `currentState`（枚举值两代编号相反）。

**第二步：把服务器日志里的证据回填**（只要日志还在，就别让它躺在硬盘上）：

```bash
python bench/harness/annotate_comfy_evidence.py --data bench/data \
  --logdir "<ComfyUI 日志目录>" \
  --logdir "<ComfyUI 日志目录>"
```

回填两样东西：

| 回填项 | 来源 | 价值 |
|---|---|---|
| `env.env_confidence` 升为 `recorded` + `env.env_evidence` | 日志的 `Device: xpu:0 Intel(R) Arc(TM) Pro B70 Graphics` | 卡型号从「推断」变「有据」 |
| `timing_breakdown` | 进度条的累计时间 + `loaded completely/partially` 行 | **把「卡慢」与「装不下」「栈变了」拆开** |

**配对判据不是文件名，是时间**：**优先**用日志自带的 `Prompt executed` 与源数据里的
`prompt_executed_s` 精确对齐（0.05 s 容差）；没有这个字段的老记录才回退到与 `server_sec`
±1 s 配对。**精确优先不是洁癖**——±1 s 的容差会把相邻两轮（实测只差 0.07 s）折成一轮，
Krea-2 与 Qwen-Image 各因此少算过一轮。对不上就报「无匹配日志」，宁可少填也不填错。
日志里的型号与记录里的型号冲突时会**直接报 MISMATCH 并以非零码退出**。

**证据覆盖三个域**（`comfyui-h3-*` / `comfyui-qwen-image-2.1-*` / `comfyui-krea-2-turbo-*`
/ `comfyui-minimax-music-*`）。两处读出上的坑已固化在脚本里，复现时不用再踩：

| 坑 | 现象 | 处理 |
|---|---|---|
| tqdm 速率单位会切 | >1 步/秒时打印 `0.68it/s` 而不是 `0.68s/it` | 正则同时接受 `s/it` \| `it/s`（出图线**每一条**采样记录都靠这个才取到） |
| 一段里有两条进度条 | Music 3 的采样条（30 步，走完）与音频 token 条（3001，走到 300 停），**后者出现次数更多** | 只在「**已完成的条**」里取众数 |
| 回填会把绝对路径写回数据 | 相邻几轮刚做的路径占位符化被撤销 | `placeholder()` + `--logdir "标签=路径"`，写回前先归一 |

**图片 / 音乐域的数据迁入**用 `migrate_comfy_media.py`（H-22），它带
`log_prompt_executed_s` 双路计时交叉核对，与上一步的配对判据同源：

```bash
python bench/harness/migrate_comfy_media.py --src <_bench_f> --outdir bench/data
```

**视频域的分辨率/帧数**由 `backfill_resolution.py`（H-21）复现工作流算法得出，
`migrate_comfy.py` 已把这一步设为**默认行为**（新批次不会再漏）：

```bash
python bench/harness/backfill_resolution.py --dry-run   # 先看计划，不落盘
python bench/harness/backfill_resolution.py             # 实际写入
```

> 该脚本只补**视频域**（按 `duration_sec` 推帧数）。图片 / 音乐域没有 `duration_sec`，
> 会被如实报成「不可判定」并跳过——**不猜**。

举例（`ab_on` / `ab_off` 两组，总时长只差 10.8%，但拆开看是两回事）：

| 组 | 采样 6 步 | 单步 | 固定开销 |
|---|---:|---:|---:|
| `ab_on` | 44 s | 7.33 s/步 | 227.1 / 233.2 s |
| `ab_off` | 81 s | 13.50 s/步 | 225.7 / 227.3 s |

→ 开关动的是**算子路径**，不是加载路径。

---

## 第三套口径：长上下文（`arc-xpu-context/1`）

上下文这件事要分成**两个完全不同的问题**量，混在一起就会得出错误结论：

| 问题 | 怎么量 | 16 GB 档实测结论 |
|---|---|---|
| **分配** 262144 的 KV 要付多少代价？ | `llama-server -c <N>`，短 prompt（≈50 tok）探一次 | **不用付**。`-c` 从 4096 到 262144 只掉 **1.6%**（45.21 → 44.93） |
| 上下文**真的塞满**之后有多快？ | 先 prefill N 个 token，再生成 | 解码随深度**近似线性下降**，见下 |

**必须显式 `cache_prompt: false`。** `llama-server` 默认缓存 prompt 前缀；
连续发「同前缀 + 更长尾巴」的请求时第二次只算增量，prefill 会被**严重高估**。
关掉才是干净的全量 prefill。

**解码时间的经验式**（B50 16G · IQ2_M 全驻留 · q8_0 KV · SYCL · **6 点拟合，最大残差 2.4%**）：

```
decode_ms ≈ 22.95 + 0.000298 × 上下文深度
```

| 项 | 含义 |
|---|---|
| 固定项 22.95 ms | 权重读取的硬下限 → 对应 **43.6 tok/s** 上限（与 `-c 4096` 的 45.2 吻合） |
| 斜率 0.298 ms / 千 token | **注意力成本**，与深度成正比 |

> 拟合式取自 6 个实测点（v2 补点后重拟）。同深度（181,454）拟合值 13.00 vs 实测 13.01，残差 +0.1%。
> **对外一律引用这一式**。

两个推论，都要写进对客材料：

1. **上下文越长越慢，而且是线性的，救不了。** 深度 19 万 token 时解码约 **12.6 tok/s**，
   26 万时约 **10.0 tok/s**。这和「卡不行」无关，是注意力的固有成本。
2. **这个模型只有 1/4 的层带 KV**（`full_attention_interval = 4`，40 层里只有 10 层）。
   换成 40 层全注意力的同尺寸模型，斜率会是 **4 倍左右** ——
   **混合注意力正是长上下文能在 16 GB 上跑得动的原因。**

`-c` 扫描与深度扫描分别由 `bench/harness/ctx_sweep.py` 和
`bench/harness/longctx_probe.py` 产出，schema 见文件内 `SCHEMA` 常量。

> ⚠️ 深上下文那几点必须核对 `predicted_n`。
> 纯重复文本会让模型立刻吐 EOS：曾经在深度 125356 上只生成 **3 个 token**，
> 首 token 开销摊不薄，算出来的 tok/s 偏低且不可信。
> **prompt 末尾必须带一条真实指令**，且 `predicted_n < 64` 的点要打 `decode_unreliable` 标记。

---

## 第四套口径：交付配置复测（`arc-xpu-ctx-sweep/1` + `llama-server-probe/1`）

前三套口径量的是**能力**（这张卡能跑多快）；这一套量的是**交付**——
客户拿到手的那条命令行、那个进程，实际给多少。

区别在这里：能力数据允许"实验室最优参数"，交付数据**必须是客户照抄就能复现的配置**。
所以这一套的两个纪律是：

1. **参数一个都别改**。`-lm dio`、`--fit off`、`--parallel 1`、`--api-key`、
   `--cache-type-*` 全都要跟交付脚本一致 —— 少一个就变成另一套配置了。
2. **`--api-key` 要同时给 server 和 client 两边**。只给 server，
   探针会拿到 401 而**速度字段全空、其它读数全部正常**——
   2026-10-16 就这么白跑了一轮 4 组配置。
   能被接受的凭据只有 `Authorization: Bearer <key>`（scheme 大写）
   和 `X-Api-Key: <key>`；body 里放 `api_key` 一律 401。

### 多模态怎么量（`arc-xpu-vision-probe/1`，`vision_probe.py`）

`llama-server` 起得来**不等于**多模态跑得通。判据要三条一起看：

| 判据 | 怎么取 |
|---|---|
| 装得下 | 对比挂/不挂 `--mmproj` 的 `vram_dedicated_mb` / `vram_shared_mb` |
| **真的看见了** | 送一张**答案唯一**的图，核对回答内容。服务正常时模型照样会编一段流畅的描述，tok/s 也照样有值 |
| 速度 | 图像 prompt token 数 + 首图墙钟；以及同图复用（prompt cache）的墙钟 |

测试图用程序生成的几何图形（`vision_probe.py` 自带，纯 stdlib 写 PNG），
不自然但**答案可机器核对**：白底 + 从左到右红方块 / 绿圆 / 蓝方块。

> ⚠️ **`max_tokens` 要给够**。首次实测用 96，返回 `completion_tokens: 96`
> 但 `content` 是**空字符串** —— 推理模型把预算全花在思考阶段，还没轮到正文。
> 现象与「多模态跑不起来」完全一样。给到 512，或传
> `chat_template_kwargs: {"enable_thinking": false}`。

---

## 显存怎么量（`xpu_vram.py`）——别只读日志第一处

**`llama-server` 在 SYCL 后端的 `-v` 日志里会打印 `buffer size`，但同一份日志会打两遍。**
默认 `--fit on` 时先有一次**试算加载**，此时 `SYCL0 model buffer size` / `KV buffer size`
报 `0.00 MiB`（还没真分配）；**再往下翻**才是真加载，报真值
（如 `SYCL0 model buffer size = 15195.34 MiB`）。**只 `grep buffer size` 会只命中第一处**，
进而误判成「字段没实现」——别犯这个错。
简记：**认后一遍 `llm_load_tensors` 的数字**；`--fit off` 时只有一遍、直接是真值。

即便如此，**日志数字仍要用独立读数交叉验证** —— 本仓库口径是两者对得上才算数。
用 `bench/harness/xpu_vram.py`：

```bash
python bench/harness/xpu_vram.py --name llama     # 按进程名
python bench/harness/xpu_vram.py --pid 22192 --json
```

它读 Windows 性能计数器（`\GPU Process Memory(*)\...`）+ `GetProcessMemoryInfo`，
给出四个量，**每个都有明确用途**：

| 量 | 用途 |
|---|---|
| **显存（独显）** | 真正的显存占用，判断还能放宽多少上下文 |
| **共享显存** | **溢出到主机内存的部分** —— ⚠️ **只在 `-ncmoe 0` 时才能这么读**。`-ncmoe N>0` 会把 N 层的专家权重**刻意**放进 `SYCL_Host`，这部分**同样计入 `vram_shared_mb`，但它不是溢出**。本机实测：`-ncmoe 8` 时该 buffer = **3808.81 MiB**，而 `vram_shared_mb` = 3848 MB —— 直接当溢出读会把"完全不溢出"误判成"溢出 3.8 GB"。**报溢出必须先减掉 `SYCL_Host model buffer size`，并把这个减数一起写出来。** |
| 主机工作集 | mmap 的模型页在内存里占多少 |
| **主机提交** | 决定页面文件需求。这是 `32 GB + 页面文件` 那一节要的数字 |
| **硬缺页次数**（`ram_page_faults`） | `GetProcessMemoryInfo` 的 `PageFaultCount`，**累计值**。两次快照的**增量**才是"这段区间有没有真在换页"。`vram_shared_mb` 只能说明"显存溢出到主机内存"，溢出之后有没有继续被换到页面文件上，只有这个计数说得清。`ctx_sweep.py` 会把它记成 `page_faults_delta`。 |

**首个实测（IQ2_M · `-c 262144` · `-ncmoe 0` · q8_0 KV · 15.51 GiB 卡）：**
显存 **15,540 MB** · 共享 284 MB · 工作集 11,427 MB · 提交 17,002 MB。

> 读出来的一个反直觉事实：权重在显存里有 15.5 GB，**主机内存里还压着 11.4 GB 的
> mmap 页**，合计 26.9 GB。31.1 GB 的机器只剩约 4 GB 给其他一切 ——
> 这就是为什么权重加载模式（`-lm dio`）在 32 GB 机器上是**必需项**而不是优化项。

`ctx_sweep.py --sample-vram` 会把这两个快照（加载后 / 探完）自动写进记录。

---

## 关于 `-r 1` 的例外（需在文档里标明，不能默默用）

本 README 上面写了「**`-r 1` 的数字一律作废**」——这是针对
**SYCL 冷 JIT** 的规则（冷/热差 7.9 倍）。

**例外**：大范围**扫描**（拐点、参数扫）允许用 `-r 1`，但必须同时满足两条：

1. 该配置在**同一会话内已经热过**（同一进程内连续测，不是每次重启）；
2. 有**第二条独立路径**在关键点上交叉验证过。

本仓库已满足的例证：量化档 × `-ncmoe` 扫描用的 `-r 1`，
在 `-ncmoe 0` / IQ2_M 这一点上被 `llama-server + probe` 独立复核为
**45.99（llama-bench）vs 45.20（server）**，差 1.7% —— 在噪声内。

**未做交叉验证的 `-r 1` 读数不得进汇总表。** 记录里要显式写 `reps: 1` 与验证方式。

---

## 命名规范

```
bench/data/<日期>_<卡><显存>_<模型>-<量化>-<后端>.json

例：2026-10-06_b70-32g_qwen3.6-35b-a3b-q4_0-sycl.json
```

**同一套参数换后端（SYCL → Vulkan）算新记录，不是覆盖旧记录**——两者要能并排看。
