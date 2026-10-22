#!/usr/bin/env python3
r"""把 ComfyUI 的**出图 / 音乐**数据迁入 `comfyui-xpu-bench/1`。

源数据：`<_bench_f>\sweep.jsonl`（浮点 vs INT8 同栈对照）
        `<_bench_f>\sweep_int8fix.jsonl`（打上「XPU 声明原生 INT8」补丁后的复测）
采集脚本：`sweep.py`（图构造照抄 `igerry/comfyui-b70-xpu` 的 `benchmarks/*.py`）

这三条与 H3 视频共用一套 schema，只换 `domain`：

    comfyui-video  MiniMax H3（i2v）
    comfyui-image  Qwen-Image 2.1 / Krea-2 Turbo（t2i）
    comfyui-audio  MiniMax Music 3（text→audio）

**为什么要落在同一套 schema 里**：对客要回答的是「这张卡跑 ComfyUI 行不行」——
出视频、出图、出音乐是同一个问题的三个面，分散在三套格式里就没法统一报。
指标单位也一致（秒），不需要为出图另造一套。

⚠️ 两条纪律：
  1. **分辨率必落盘**（`workload.width`/`height`）——分辨率差一倍、耗时差数倍，
     不带分辨率的「出图 15 秒」是没有量纲的。
  2. **`stack_variant: int8fix` 的记录不可与基线并排引用**——它跑在打了
     `OMNIXPU_INT8_COMPUTE` 补丁的栈上（把 ComfyUI 上游硬编码的
     「Intel XPU 不支持原生 INT8」翻过来），是**不同配置**。

用法:
  python bench/harness/migrate_comfy_media.py --src <_bench_f> --outdir bench/data
  python bench/harness/migrate_comfy_media.py --src ... --outdir ... --dry-run
"""

import argparse
import datetime as dt
import glob
import re
import json
import os
import sys
from pathlib import Path

SCHEMA = "comfyui-xpu-bench/1"

# 采集机的固定事实（与 migrate_comfy.py 同源）与软件栈
RIG = {
    "cpu": "AMD Ryzen 5 9600X",
    "ram_gb": 32,
    "os": "Windows",
}
# ⚠️ 组合后缀里内嵌卡名时（`sweep_b70same`），尾部剥离会先剥掉 `same`、
# 再剥不到 `b70`（它在中间）→ 认不出卡型。这里用**显式查表**而不是改文件命名，
# 理由：已跑完的批次数据文件不该为了迁就工具而重命名。
# 纪律：新增内嵌卡名的后缀时，两边都要登记（这里 + `annotate` 的 CARD_LOG_KEYS）。
SUFFIX_CARD = {
    "b70same": "b70", "b70sig": "b70", "b70t213": "b70",
    "b70base": "b70", "b70bf16": "b70",
    "b70m3teint8": "b70", "b70m3tebf16": "b70",
    "b70m3teint8b": "b70", "b70m3tebf16b": "b70",
    "b70m3fp16tebf16": "b70", "b70m3fp16teint8": "b70",
    "b70k2base": "b70", "b70k2sig": "b70", "b70k2res": "b70", "b70k2res2": "b70", "b70m3fp16a": "b70", "b70k2int8fix": "b70", "b70m3fp16b": "b70",
    "kvauto": "b70", "kvgpu": "b70", "kvcpu": "b70", "kvoff": "b70",
    "kvi8": "b70", "kvi4": "b70",
    # 2026-10-19 功耗专项（文件名 `sweep_b70pw.jsonl`；标记自带卡名）
    "b70pw": "b70",
    # 2026-10-20 B60 上机（`--suffix b60` → 文件名 `sweep_b60.jsonl`）
    "b60": "b60",
    # 2026-10-20 双 B65：`--suffix b65-dual`。⚠️ **必须登记**，
    # 否则 parse_tag 判不出卡型，`int8_convrot_b65-dual` 会整个残留成 quant
    # （实测：不登记时返回 card=None）。双卡身份仍按**单张 B65** 登记——
    # torch.xpu 只见到一张，别把 2× 的值写进 vram_visible_gib。
    "b65-dual": "b65",
    # 2026-10-21 B65 单卡上机。`--suffix b65` → `sweepb65.jsonl`；
    # 每模型独立后缀（driver 的 stage_c 派生）：q21→`b65`、krea2→`b65k2`、music3→`b65m3`，
    # 与 B60 的 `b60` / `b60k2` / `b60m3` 同一套规则。⚠️ 单卡这三条**没有** `-dual` 段，
    # 所以 SUFFIX_MARKS 不用登记（通用卡型正则已能剥 `b65`）。
    "b65": "b65",
    "b65k2": "b65",
    "b65m3": "b65",
    # 2026-10-20 **每个模型一个独立 suffix**（driver 的 stage_c 派生）：
    # q21 → `b60`，krea2 → `b60k2`，music3 → `b60m3`。
    # 🔴 原因是 sweep.py 的 jsonl / server 日志都是**追加**语义，同一个 suffix
    # 下跑第二个模型会被撞车检查拦下（B60 首轮 krea2 / music3 双双 rc=1 就是这条）。
    # Music 3 的 TE 档位已在 tag 里（`_te{bf16|int8_convrot}`），suffix 不带 TE。
    "b60k2": "b60",
    "b60m3": "b60",
    "b65-dualk2": "b65",
    "b65-dualm3": "b65",
    # 2026-10-21 B65 Music 3 的 reserve-vram 补测（`--reserve-vram 2`，其余逐字相同）。
    # 目的：B65 在 reserve 4 下每轮都 `loads=3`（三个组件全重装），
    # 与 B70 的 `loads=0` 不可比 → 松一档看是否转为驻留。
    "b65m3res2": "b65",
    # 2026-10-21 B65 补测（能力/容量表里 B65 那几列写着「未测」的格子）。
    # 每项一个后缀 —— sweep.py 的 jsonl 与 server 日志都是追加语义，
    # 同 suffix 混模型会被撞车检查直接拦下（B60 首轮就是这么双双 rc=1 的）。
    "b65q21b16": "b65",      # Qwen-Image 2.1 · DiT bf16 · 1280×720
    "b65q21r2k": "b65",      # Qwen-Image 2.1 · int8 · 2048×2048
    "b65k2b16": "b65",       # Krea-2 Turbo · bf16 · 1024×1024
    "b65m3f16": "b65",       # Music 3 · DiT fp16 + TE bf16
    "b65m3i8te8": "b65",     # Music 3 · DiT int8 + TE int8
    # 2026-10-22 24 GB 显存档补测（`--reserve-vram 11.83`）。
    # ⚠️ 后缀里带 `r24` 而不是 `rsv`：`infer_reserve` 只认 `rsv(\d+)`，
    # 判不出来会退回 5 —— 这批的档位必须靠 `--reserve-vram 11.83` 显式覆盖。
    "b65r24": "b65",         # Qwen-Image 2.1 · bf16 · 1280×720
    # 2026-10-22 B50 出图分辨率上限探测（3072×3072，reserve 4）。
    "b50img3072": "b50",
    "b65img3072": "b65",
    "b65img4096": "b65",
    "b65r24k2": "b65",       # Krea-2 Turbo · bf16 · 1280×720
    "b65r24m3f16": "b65",    # Music 3 · DiT fp16 + TE bf16
    "b65r24m3i8te8": "b65",  # Music 3 · DiT int8 + TE int8
    # 2026-10-22 B50 出图分辨率上限探测（3072×3072，`--suffix b50img3072`）。
    "b50img3072": "**B50 · Qwen-Image 2.1 · 3072×3072 分辨率档**（2026-10-22 上限探测；"
                   "reserve 4；first / resident 各一轮）",
    "b65img3072": "**B65 · Qwen-Image 2.1 · 3072×3072 分辨率档**（2026-10-22；"
                   "reserve 4；与 B50 同口径对照）",
    "b65img4096": "**B65 · Qwen-Image 2.1 · 4096×4096 分辨率档**（2026-10-22 上限探测；reserve 4）",
}

CARDS = {
    "b70": {
        "gpu": "Intel Arc Pro B70 32G",
        "chip": "E223",
        "subsys": "27421EF7",
        "device_id": "PCI\\VEN_8086&DEV_E223&SUBSYS_27421EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
        "board_code": "2742",
        "vram_visible_gib": 31.16,
        "ecc": "off",
        "driver": "32.0.101.8976",
        "stack": {
            "torch": "2.13",
            "omni_xpu_kernel": "0.2.0b2+torch213.bmg",
            "stack_note": "2026-10-14 采集，跑在 python_embeded_torch213",
        },
    },
    "b50": {
        "gpu": "Intel Arc Pro B50 LP 16G",
        "chip": "E212",
        "subsys": "25221EF7",
        "device_id": "PCI\\VEN_8086&DEV_E212&SUBSYS_25221EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
        "board_code": "2522",
        "vram_visible_gib": 15.51,
        "ecc": "off",
        "driver": "32.0.101.8976",
        # 2026-10-16 实测：这两批**软件栈差一档**，跨批比较必须声明。
        # B70 那批跑在 python_embeded_torch213，kernel 是 torch213 变体；
        # B50 这批跑在 python_embeded（torch 2.12），kernel 是 torch212 变体。
        # 取值来源＝各自服务端日志的 `omni_xpu_kernel` 与 `Device:` 行（已 recorded）。
        "stack": {
            "torch": "2.12",
            "omni_xpu_kernel": "0.2.0b2+torch212.bmg",
            "stack_note": "跑在 python_embeded（torch 2.12），与 B70 2026-10-14 那批"
                          "（torch 2.13 / kernel torch213）**不是同一栈**",
        },
    },
    # 2026-10-20 B60 上机。身份字段来自 gpu_identity.py 实测（DEV_E211 · SUBSYS_25421EF7
    # · 板厂 1EF7 = GUNNIR · VBIOS 2304140000 · 可见 23.33 GiB）。
    # 栈＝python_embeded（torch 2.12.0+xpu · provider 0.2.33），与 B50 那批同栈；
    # kernel 变体以服务端日志的 `omni_xpu_kernel` 行为准，跑完核对后再定稿。
    "b60": {
        "gpu": "Intel Arc Pro B60 24G",
        "chip": "E211",
        "subsys": "25421EF7",
        "device_id": "PCI\\VEN_8086&DEV_E211&SUBSYS_25421EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
        "board_code": "2542",
        "vram_visible_gib": 23.33,
        "ecc": "off",
        "driver": "32.0.101.9150",
        "stack": {
            "torch": "2.12",
            "omni_xpu_kernel": "0.2.0b2+torch212.bmg",
            "stack_note": "跑在 python_embeded（torch 2.12.0+xpu · provider 0.2.33）；"
                          "驱动 9150，与 B50/B70 已发布数据的 8976 不同",
        },
    },
    # 2026-10-21 B65 上机。身份字段来自 `gpu_identity` 实测（DEV_E222 · SUBSYS_27441EF7
    # · 板厂 1EF7 = GUNNIR · 可见 31.16 GiB），与 B70 的 E223 **只差 1**，认卡必须看 subsys。
    # 栈版本取自 site-packages 的 dist-info（不是报告头部那行写死的模板文字）：
    # `omni_xpu_kernel-0.2.0b2+torch212.bmg` / `comfy_kitchen-0.2.37` /
    # `comfy_kitchen_xpu_runtime-0.2.33`。
    "b65": {
        "gpu": "Intel Arc Pro B65 32G",
        "chip": "E222",
        "subsys": "27441EF7",
        "device_id": "PCI\\VEN_8086&DEV_E222&SUBSYS_27441EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
        "board_code": "2744",
        "vram_visible_gib": 31.16,
        "ecc": "off",
        "driver": "32.0.101.9150",
        "stack": {
            "torch": "2.12",
            "omni_xpu_kernel": "0.2.0b2+torch212.bmg",
            "stack_note": "跑在 python_embeded（torch 2.12.0+xpu · provider 0.2.33 · "
                          "comfy_kitchen 0.2.37）；驱动 9150，与 B70 已发布数据的 8976 不同",
        },
    },
}
STACK_COMMON = {
    "app": "ComfyUI",
    "app_version": "0.39.0",
    "comfy_kitchen": "0.2.37",
    "comfy_kitchen_xpu_runtime": "0.2.33",
    "backend": "XPU (SYCL)",
}
STACK_BASE = dict(STACK_COMMON)
# 打上 int8fix 补丁后的差异项。
# 注意 2026-10-16 起拆成两个独立开关（实测结论，见 STACK_VARIANTS）：
#   OMNIXPU_INT8_COMPUTE  → ① 能力声明（supports_int8_compute -> True）
#   OMNIXPU_INT8_SIGFIX   → ② 签名适配（int8_linear 8 参 -> 12 参）
# 两者对 Qwen-Image 2.1 的作用**完全不同**：② 决定能不能跑，① 不给它速度。
STACK_VARIANTS = {
    "base": {"OMNIXPU_INT8_COMPUTE": "0", "OMNIXPU_INT8_SIGFIX": "0"},
    "sigfix": {"OMNIXPU_INT8_COMPUTE": "0", "OMNIXPU_INT8_SIGFIX": "1"},
    "int8fix": {"OMNIXPU_INT8_COMPUTE": "1", "OMNIXPU_INT8_SIGFIX": "1"},
}
ENV_BASE = {
    "ZE_ENABLE_PCI_ID_DEVICE_ORDER": "1",
    "SYCL_CACHE_PERSISTENT": "1",
}
# 2026-10-14 那批（无卡型后缀）的卡型映射，依据＝其服务端日志的 Device / Total VRAM 行。
LEGACY_CARDS = {
    "sweep.jsonl": "b70",
    "sweep_int8fix.jsonl": "b70",
}

# `--suffix` 里用到的自由标记（2026-10-16 起 B50 补测批次）。
# 这些标记本身就是「这一组跑的是什么」的编码，必须能被识别，否则：
#   ① 卡型判不出 → 迁移器直接报错（这是设计上的保护）
#   ② 变体段会混进量化档名 → 查表 KeyError
# 取值来自 bench/harness 与 sweep.py 的约定；新增 suffix 时**两边都要登记**。
MARK_STACK = {
    # 自由标记 → 实际生效的栈变体。B50 这几批都带 int8fix（能力声明 + 签名适配），
    # 标记本身编码的是「跑哪一组」而不是「栈变了」。
    "m3i8": "int8fix", "m3f16": "int8fix", "k2bf16": "int8fix",
    "r1536": "int8fix", "r2048": "int8fix",
    "t213": "int8fix", "prov031": "int8fix",
    "r2048full": "int8fix", "tebf16": "int8fix", "k2bf16retry": "int8fix",
    "k2sig": "sigfix", "m3sig": "sigfix", "k2base": "base",
    "b70same": "int8fix", "b70sig": "sigfix", "b70base": "base",
    "b70t213": "int8fix", "b70m3teint8": "int8fix", "b70m3tebf16": "int8fix",
    "b70m3teint8b": "int8fix", "b70m3tebf16b": "int8fix",
    "b70m3fp16tebf16": "int8fix", "b70m3fp16teint8": "int8fix",
    "b70k2base": "base", "b70k2sig": "sigfix", "b70k2res": "int8fix", "b70k2res2": "int8fix",
    "b70m3fp16a": "int8fix", "b70k2int8fix": "int8fix", "b70m3fp16b": "int8fix",
    "kvauto": "int8fix", "kvgpu": "int8fix", "kvcpu": "int8fix",
    "kvoff": "int8fix", "kvi8": "int8fix", "kvi4": "int8fix",
    "b70k2v2": "int8fix",
    "b70v2": "int8fix",
    "b70m3v2": "int8fix",
    "b70m3i8v2": "int8fix",
    "b70pw": "int8fix",
    # 2026-10-20 新卡队列（run_new_card.py 驱动）起的批次。这批的 suffix 里
    # **没有栈标记**（`--suffix b60` / `b60k2` / `b60m3`，只编码卡型+模型），
    # 但跑的确实是 int8fix 栈：driver 不设 OMNIXPU_INT8_COMPUTE / SIGFIX，
    # 而 custom_nodes/omni_int8fix.py 两个开关默认都是 '1'（该文件 63/77 行），
    # 服务日志 `[int8fix] (1) ... -> True` + `(2) int8_linear 已适配` +
    # `Native ops: convrot_w4a4, int8_tensorwise, asym_w4a8_int8, w6a8_int8`
    # 三处直接印证（b60 三个 server 日志均已核）。
    # ⚠️ 不映射的后果：`sweepb60k2` 的 variant 变成字符串 `b60k2`，
    #   STACK_VARIANTS['b60k2'] → KeyError，整批迁移硬崩（实测踩过）。
    "b60": "int8fix", "b60k2": "int8fix", "b60m3": "int8fix",
    # 2026-10-21 B65 单卡队列，同理（driver 的 stage_c 不设那两个开关）。
    # ⚠️ 只往 SUFFIX_MARKS 登记而漏了本表，后果同样是 KeyError ——
    # 登记 SUFFIX_MARKS 只解决「剥不剥得掉」，剥下来之后还得能查到栈。
    "b65": "int8fix", "b65k2": "int8fix", "b65m3": "int8fix",
    "b65m3res2": "int8fix",
    # ⚠️ 双卡批次 `b65-dual` 必须在 `b65` **前面**被匹配到（子串关系），
    # 否则 `b65` 先命中，`-dual` 残留成量化档名。见 SUFFIX_CARD 的排序说明。
    "b65-dual": "int8fix",
    # 2026-10-21 B65 补测五组（driver 不设开关，栈仍是 int8fix）。
    # ⚠️ 别只往 SUFFIX_MARKS 登记：剥下来了还得在这张表里查得到栈，否则 KeyError。
    "b65q21b16": "int8fix",
    "b65q21r2k": "int8fix",
    "b65k2b16": "int8fix",
    "b65m3f16": "int8fix",
    "b65m3i8te8": "int8fix",
    # 2026-10-22 24 GB 显存档补测：driver 不设开关，栈仍是 int8fix。
    "b65r24": "int8fix",
    "b65r24k2": "int8fix",
    "b65r24m3f16": "int8fix",
    "b65r24m3i8te8": "int8fix",
    # 2026-10-22 B50 出图分辨率上限探测（driver 不设开关，栈仍是 int8fix）。
    "b50img3072": "int8fix",
    "b65img3072": "int8fix",
    "b65img4096": "int8fix",
}
# 文件名里**完全不带栈标记**的新卡队列批次（`sweepb60.jsonl` → 卡型被 CARDS
# 分支先剥掉，SUFFIX_MARKS 无标记可剥 → variant 停在默认 "base"）。
# 这类批次的实际栈同样由 omni_int8fix.py 的默认值决定（两开关默认开），
# 依据同上。→ 判据是「卡型属于新卡队列且文件名无栈标记」，
# **不是猜**：b50/b70 历史批次的文件名都带显式标记（base/sigfix/int8fix），
# 不在这张表里，不会被误升级。
CARD_DEFAULT_STACK = {
    "b60": "int8fix",
    # 2026-10-21 B65 上机（单卡）。driver 的 stage_c **不设**那两个开关
    # （`OMNIXPU_INT8_COMPUTE` / `OMNIXPU_INT8_SIGFIX` 由 omni_int8fix.py 默认开），
    # 所以文件名 `sweepb65*` 里没有栈标记 → 判 base 变体时按 int8fix 记。
    "b65": "int8fix",
    # 双 B65 上机后再加 "b65-dual": "int8fix"。
}
MARK_NOTE = {
    "m3i8": "Music 3 · **DiT int8 + 文本编码器 int8**（bf16 TE 为 15.56 GiB，超 B50 整卡 15.51 GiB；int8 TE 为 8.56 GiB，装得下）",
    "m3f16": "Music 3 · DiT fp16 + 文本编码器 int8（与 m3i8 构成同栈的 DiT 浮点 vs 量化对照）",
    "k2bf16": "Krea-2 · bf16，用于与已测的 int8fix 构成**同卡同栈的 bf16 vs int8 对照**",
    "r1536": "Qwen-Image 2.1 · 1536×864 分辨率档",
    "r2048": "Qwen-Image 2.1 · 2048×2048 分辨率档",
    "b50img3072": "Qwen-Image 2.1 · 3072×3072 分辨率档（B50 上限探测）",
    "b65img3072": "Qwen-Image 2.1 · 3072×3072 分辨率档",
    "b65img4096": "Qwen-Image 2.1 · 4096×4096 分辨率档（上限探测）",
    "t213": "**内核构建对照 · torch 2.13 环境**（kernel 0.2.0b2+torch213.bmg + provider 0.2.31）",
    "r2048full": "2048×2048 **补齐稳态**（首轮那次被我误判中断，只留了 1 轮）",
    "tebf16": "Music 3 · **bf16 文本编码器**（15.56 GiB > B50 整卡 15.51 GiB → TE 必须全卸载到主机内存）",
    "k2bf16retry": "Krea-2 bf16 **重试**（首轮那次 UR_RESULT_ERROR_DEVICE_LOST，确认是必然还是偶发）",
    "k2sig": "Krea-2 · **只签名适配**（能力声明关闭）—— 2×2 的一格",
    # 2026-10-17 B70 装回机后的同代码对照（钉死 10-15 那个 1.78× 的归属）
    "b70same": "**B70 · 与 B50 完全同代码同栈的对照**（B50 数据采于 B70 拆机状态，这组消除该差异）",
    "b70sig": "**B70 · 只签名适配**（能力声明关闭）—— 与 b70same 构成 2×2，分离「能力声明」的贡献",
    "b70t213": "**B70 · 换内核构建**（torch 2.13 + kernel torch213.bmg + provider 0.2.31）—— 与 b70same 只差这一整套，直接检验 10-15 那个 1.78× 能不能复现",
    "b70m3teint8": "**B70 · Music 3 的 int8 DiT + int8 TE**（B70 此前 9 条 Music 3 记录**全部是 bf16 TE**，这一格是缺的；用来判定「DiT 量化 × TE 量化」是否有交互）",
    "b70m3tebf16": "**B70 · Music 3 的 fp16 DiT + int8 TE**（与 b70m3teint8 构成同栈 DiT 档位对照）",
    # 带 b 的是「补第2 个 resident」的重跑（第一轮只跑 1 个 resident，
    # 测几个百分点的差异时分不清信号与噪声 → 加轮次）
    "b70m3teint8b": "**B70 · Music 3 int8 DiT + int8 TE · 补第 2 个 resident**（单轮 66.74 与 bf16 TE 的 61.95 差 7.7%，在噪声边缘，必须加轮）",
    "b70m3tebf16b": "**B70 · Music 3 int8 DiT + bf16 TE · 补第 2 个 resident**（同上）",
    "b70m3fp16tebf16": "**B70 · Music 3 fp16 DiT + bf16 TE**（2×2 的一格；与 b70m3tebf16 构成同栈 DiT 档位对照）",
    "b70m3fp16teint8": "**B70 · Music 3 fp16 DiT + int8 TE**（2×2 的一格；与 b70m3fp16tebf16 / b70m3teint8 合起来闭掉 DiT×TE 二维）",
    # B70 · Krea-2 的完整 2×2（B50 上已跑齐，这里验证跨卡是否一致）
    "b70k2base": "**B70 · Krea-2 基线**（两开关全关）—— Krea-2 不走签名那条路径，base 格能跑，是唯一能量出「反量化 vs 原生」直接对照的模型",
    "b70k2sig": "**B70 · Krea-2 只签名适配**（能力声明关闭）",
    "b70k2int8fix": "**B70 · Krea-2 两个开关都开**（与 b70k2base / b70k2sig 构成完整 2×2）",
    "b70m3fp16b": "**B70 · Music 3 fp16 DiT + int8 TE · 复现组**（对照 b70m3fp16a 的 OOM 边界）",
    # B70 · Music 3 的 fp16 DiT 补跑（缺口表第 5 行的归因）
    "b70m3fp16a": "**B70 · Music 3 fp16 DiT + bf16 TE · OOM 复现组**（验证 20,608 MB 那条容量边界是否稳定复现）",
    "b70k2res": "**B70 · Krea-2 分辨率维度 · 1280×768**（此前只有 1024×1024 一点）",
    "b70k2res2": "**B70 · Krea-2 分辨率维度 · 1536×1024**",
    # KV 缓存对照（缺口表第 4 行）——上游 QwenImage21Cache 的 device × dtype 二维空间，
    # 此前完全没被测过。tag 里的 `_gpu` / `_int8` 等段编码了设置，
    # 这里给 suffix 一个可读的名字。
    "kvauto": "**KV 缓存 device=auto**（历史批次的默认设置，作为本组基线）",
    "kvgpu": "**KV 缓存 device=gpu**（强制放显存）",
    "kvcpu": "**KV 缓存 device=cpu**（放主机内存，上游说「在计算背后预取、代价很小」）",
    "kvoff": "**KV 缓存 device=off**（每步重算前缀，更慢 —— **上游明确说这是「排除缓存影响」的唯一办法**）",
    "kvi8": "**KV 缓存 dtype=int8**（约一半体积、bf16 精度）",
    "kvi4": "**KV 缓存 dtype=int4**（约四分之一体积、误差约翻倍）",
    "b70base": "**B70 · 基线**（两开关全关）—— Qwen-Image 2.1 在此格会撞签名错配而崩，是预期结果",
    "k2base": "Krea-2 · **基线**（两个开关都关，shim 完全不装）—— 2×2 的基线格。Krea-2 不走签名不适用的那条路径，能跑",
    "m3sig": "Music 3 · **只签名适配**（能力声明关闭）—— 与 int8fix 组构成 2×2",
    "prov031": "**分离点 · torch 2.12 环境 + provider 0.2.31**（只降 provider，torch 与 kernel 不动）",
    # 2026-10-20 新卡队列。这批 suffix 只编码「卡型 + 模型」，不编码栈 ——
    # 栈恒为 int8fix（driver 不设开关、omni_int8fix.py 默认两开关全开，
    # 服务日志三处印证，见 MARK_STACK 里 b60 条注释）。
    # 这里写「跑的是什么」，不写过程叙事（迁移姿势是工具链细节，不进数据）。
    "b60": "**B60 24G · Qwen-Image 2.1 int8**（qwen3vl_8b_int8_convrot 文本编码器）",
    "b60k2": "**B60 24G · Krea-2 Turbo int8 · 1280×720**（sweep.py 默认分辨率档）",
    "b60m3": "**B60 24G · Music 3 · 120 s · DiT int8 + 文本编码器 int8_convrot**",
    # 2026-10-21 B65 单卡（同 B70 的 BMG-G31 芯片，Xe2 核心 20 vs 32）。
    # 三条都只写「跑的是什么」——分辨率不写死，以 tag 实测为准。
    "b65": "**B65 32G · Qwen-Image 2.1 int8**（qwen3vl_8b_int8_convrot 文本编码器）",
    "b65k2": "**B65 32G · Krea-2 Turbo int8**（分辨率由 sweep.py 默认档决定，实测 tag 为 1280×720）",
    "b65m3": "**B65 32G · Music 3 · DiT int8 + 文本编码器 int8_convrot**",
    "b65m3res2": "**B65 32G · Music 3 · `--reserve-vram 2` 补测**"
                 "（与 b65m3 只差这一项：reserve 4 下三个组件每轮全部重装，"
                 "松一档看能不能驻留；TE 仍是 bf16）",
    "b65q21b16": "**B65 32G · Qwen-Image 2.1 · DiT bf16 · 1280×720**"
                 "（与已测的 int8 同栈构成 bf16 vs int8 对照）",
    "b65q21r2k": "**B65 32G · Qwen-Image 2.1 · int8 · 2048×2048**"
                 "（补齐稳态三轮与换提示词，此前这一档只有首轮）",
    "b65k2b16": "**B65 32G · Krea-2 Turbo · bf16 · 1024×1024**"
                "（DiT 24.48 + TE 8.27 + VAE 0.24 = 32.98 GiB > 31.16 GiB，"
                "整装不下；这一格量的是卸载代价）",
    "b65m3f16": "**B65 32G · Music 3 · DiT fp16 + 文本编码器 bf16**（20.34 GiB，装得下）",
    "b65m3i8te8": "**B65 32G · Music 3 · DiT int8 + 文本编码器 int8**（11.10 GiB）",
    "b65r24": "**24 GB 显存档 · Qwen-Image 2.1 · DiT bf16 · 1280×720**"
              "（`--reserve-vram 11.83`，可分配 19,798 MB；DiT 13.25 + TE 8.71 + VAE 0.63 = 22.59 GiB 装不下，量的是卸载代价）",
    "b65r24k2": "**24 GB 显存档 · Krea-2 Turbo · bf16 · 1280×720**"
                "（`--reserve-vram 11.83`；DiT 24.48 GiB 单件就超可分配量）",
    "b65r24m3f16": "**24 GB 显存档 · Music 3 · DiT fp16 + TE bf16**"
                   "（20.34 GiB 贴着可分配量 19,798 MB）",
    "b65r24m3i8te8": "**24 GB 显存档 · Music 3 · DiT int8 + TE int8**（11.10 GiB）",
}
# ⚠️ 这个脚本**没有 `--only`**：一次跑就是整个 `--src` 目录。
# 所以只要目录里混着一个从没登记过的后缀，**整次迁移硬失败**（判不出卡型就报错退出是对的，
# 但代价很大——实测 `sweep_b70k2retry.jsonl` 就是这样把一次全量迁移顶回来了）。
# 增量迁移的正确姿势：**把待迁文件 cp 到临时目录**，`--src` 指向临时目录，跑完删掉。
SUFFIX_MARKS = {
    "b60": "**B60 24G 首批采集**（2026-10-20 上机；`--suffix b60`；身份实测："
           "DEV_E211 · SUBSYS_25421EF7 · GUNNIR · 23.33 GiB · 驱动 9150）",
    # 2026-10-20 双 B65（`--suffix b65-dual`）。⚠️ 卡型段必须**两边都登记**：
    # SUFFIX_CARD（→ 规范卡型 b65）+ SUFFIX_MARKS（本表）。只登记前者时
    # parse_tag 剥不掉这段，`int8_convrot_b65-dual` 会整个残留成量化档名、
    # card 判成 None（实测踩过）。双卡跑法的边界见 run_new_card.py 顶部说明。
    "b65-dual": "**双 B65 同时在机**（`--suffix b65-dual`；llama.cpp 走 "
                "level_zero:0,1 吃到两张，ComfyUI/torch.xpu 只用第一张；"
                "容量翻倍但 MoE 解码是带宽瓶颈，速度预期与单卡持平）",
    # 2026-10-20 **每模型独立 suffix**（driver 的 stage_c 派生，`b60` + 模型段）。
    # 不这么做会被 sweep.py 的撞车检查拦下：jsonl 与 server 日志都是追加语义，
    # 同一个 suffix 下混模型就拒绝跑（B60 首轮 krea2 / music3 双双 rc=1 挂掉）。
    "b60k2": "**B60 · Krea-2 Turbo int8**（`--suffix b60k2`，与 q21 的 `b60` 分开；"
             "分辨率由 sweep.py 默认档决定，实测 tag 为 1280×720）",
    "b60m3": "**B60 · Music 3 · int8 TE**（`--suffix b60m3`；TE 档位另在 tag 里 "
             "`_teint8_convrot`，120 s 音频）",
    # 2026-10-21 B65 单卡的每模型后缀。⚠️ **必须在两边都登记**：
    # SUFFIX_CARD 只管「剥下来之后对应哪张卡」，能不能剥下来看的是本表。
    # 原先这里写着「不用登记，通用卡型正则已能剥 b65」——**那是错的**：
    # `sweepb65k2` 不以任何卡型结尾，剥不掉 k2 就判不出卡型（实测报
    # 「认不出卡型（sweepb65k2.jsonl）」）。b60k2 / b60m3 当初就是这么登记的。
    "b65k2": "**B65 · Krea-2 Turbo int8**（`--suffix b65k2`，与 q21 的 `b65` 分开；"
             "分辨率由 sweep.py 默认档决定，实测 tag 为 1280×720）",
    "b65m3": "**B65 · Music 3**（`--suffix b65m3`；TE 档位另在 tag 里 "
             "`_tebf16` / `_teint8_convrot`，120 s 音频）",
    # 2026-10-21 B65 Music 3 的 reserve 档位补测。⚠️ 长度必须让它在
    # `b65m3` 之前命中（SUFFIX_MARKS 按长度降序匹配），否则 `res2` 会残留。
    "b65m3res2": "**B65 · Music 3 · `--reserve-vram 2`**（`--suffix b65m3res2`；"
                 "与 b65m3 只差 reserve 这一项，用于分离「装不下 → 每轮重装」"
                 "与「算力差距」）",
    # 2026-10-21 B65 补测五组。⚠️ 本表按**长度降序**匹配，这些都比 `b65` 长，
    # 不会被通用段截胡；但仍须与 SUFFIX_CARD / MARK_STACK / MARK_NOTE 四处同步登记，
    # 缺一处就是 KeyError 或判不出卡型。
    "b65q21b16": "**B65 · Qwen-Image 2.1 · DiT bf16 · 1280×720**（`--suffix b65q21b16`）",
    "b65q21r2k": "**B65 · Qwen-Image 2.1 · int8 · 2048×2048**（`--suffix b65q21r2k`；"
                 "补稳态与换提示词，此前只有首轮）",
    "b65k2b16": "**B65 · Krea-2 Turbo · bf16 · 1024×1024**（`--suffix b65k2b16`）",
    "b65m3f16": "**B65 · Music 3 · DiT fp16 + TE bf16**（`--suffix b65m3f16`）",
    "b65m3i8te8": "**B65 · Music 3 · DiT int8 + TE int8**（`--suffix b65m3i8te8`）",
    # 2026-10-22 24 GB 显存档（`--reserve-vram 11.83` → 可分配 19,798 MB）。
    "b65r24": "**24 GB 显存档 · Qwen-Image 2.1 · bf16 · 1280×720**"
              "（`--suffix b65r24`；`--reserve-vram 11.83`）",
    "b65r24k2": "**24 GB 显存档 · Krea-2 Turbo · bf16 · 1280×720**"
                "（`--suffix b65r24k2`；`--reserve-vram 11.83`）",
    "b65r24m3f16": "**24 GB 显存档 · Music 3 · DiT fp16 + TE bf16**"
                   "（`--suffix b65r24m3f16`；`--reserve-vram 11.83`）",
    "b65r24m3i8te8": "**24 GB 显存档 · Music 3 · DiT int8 + TE int8**"
                     "（`--suffix b65r24m3i8te8`；`--reserve-vram 11.83`）",
    "b65-dualk2": "**双 B65 · Krea-2**（`--suffix b65-dualk2`；ComfyUI 只用第一张，"
                  "与单张 B65 同条件对照）",
    "b65-dualm3": "**双 B65 · Music 3**（`--suffix b65-dualm3`；TE 档位按**单卡**判，"
                  "容量翻倍对 ComfyUI 无效）",
    "b70pw": "**B70 · 功耗专项**（采集器默认带整卡功耗后重采，用于给台账补「功耗 / 能量」"
             "这一维；同一份图同一套栈，只是多了 `power` 字段）",
    "b70m3i8v2": "**B70 · Music 3 · int8 文本编码器档**（TE 8.57 GiB 才装得下 → 唯一能做「真驻留」量化对照的一档）",
    "b70m3v2": "**B70 · Music 3 采集器修复后复跑**（轮询循环补回 `time.sleep` 后重采，每组 2 个 resident 稳态）",
    "b70v2": "**B70 · 采集器修复后复跑**（轮询循环补回 `time.sleep` 后重采，每组 2 个 resident 稳态）",
    "b70k2v2": "**B70 · Krea-2 采集器修复后复跑**（连接泄漏修好后重采，每组 2 个 resident 稳态；"
               "10-17 那批只有首轮可信）",
    "int8fix": "能力声明 + 签名适配",
    "sigfix": "只签名适配",
    "base": "基线（无适配）",
    "m3i8": "Music 3 · int8 DiT + int8 文本编码器",
    "m3f16": "Music 3 · fp16 DiT + int8 文本编码器",
    "k2bf16": "Krea-2 · bf16（补齐同卡同栈对照）",
    "r1536": "Qwen-Image 2.1 · 1536×864 分辨率档",
    "r2048": "Qwen-Image 2.1 · 2048×2048 分辨率档",
    "b50img3072": "Qwen-Image 2.1 · 3072×3072 分辨率档（B50 上限探测）",
    "b65img3072": "Qwen-Image 2.1 · 3072×3072 分辨率档",
    "b65img4096": "Qwen-Image 2.1 · 4096×4096 分辨率档（上限探测）",
    "t213": "**内核构建对照 · torch 2.13 环境**（kernel 0.2.0b2+torch213.bmg + provider 0.2.31）",
    "r2048full": "2048×2048 **补齐稳态**（首轮那次被我误判中断，只留了 1 轮）",
    "tebf16": "Music 3 · **bf16 文本编码器**（15.56 GiB > B50 整卡 15.51 GiB → TE 必须全卸载到主机内存）",
    "k2bf16retry": "Krea-2 bf16 **重试**（首轮那次 UR_RESULT_ERROR_DEVICE_LOST，确认是必然还是偶发）",
    "k2sig": "Krea-2 · **只签名适配**（能力声明关闭）—— 2×2 的一格",
    # 2026-10-17 B70 装回机后的同代码对照（钉死 10-15 那个 1.78× 的归属）
    "b70same": "**B70 · 与 B50 完全同代码同栈的对照**（B50 数据采于 B70 拆机状态，这组消除该差异）",
    "b70sig": "**B70 · 只签名适配**（能力声明关闭）—— 与 b70same 构成 2×2，分离「能力声明」的贡献",
    "b70t213": "**B70 · 换内核构建**（torch 2.13 + kernel torch213.bmg + provider 0.2.31）—— 与 b70same 只差这一整套，直接检验 10-15 那个 1.78× 能不能复现",
    "b70m3teint8": "**B70 · Music 3 的 int8 DiT + int8 TE**（B70 此前 9 条 Music 3 记录**全部是 bf16 TE**，这一格是缺的；用来判定「DiT 量化 × TE 量化」是否有交互）",
    "b70m3tebf16": "**B70 · Music 3 的 fp16 DiT + int8 TE**（与 b70m3teint8 构成同栈 DiT 档位对照）",
    # 带 b 的是「补第2 个 resident」的重跑（第一轮只跑 1 个 resident，
    # 测几个百分点的差异时分不清信号与噪声 → 加轮次）
    "b70m3teint8b": "**B70 · Music 3 int8 DiT + int8 TE · 补第 2 个 resident**（单轮 66.74 与 bf16 TE 的 61.95 差 7.7%，在噪声边缘，必须加轮）",
    "b70m3tebf16b": "**B70 · Music 3 int8 DiT + bf16 TE · 补第 2 个 resident**（同上）",
    "b70m3fp16tebf16": "**B70 · Music 3 fp16 DiT + bf16 TE**（2×2 的一格；与 b70m3tebf16 构成同栈 DiT 档位对照）",
    "b70m3fp16teint8": "**B70 · Music 3 fp16 DiT + int8 TE**（2×2 的一格；与 b70m3fp16tebf16 / b70m3teint8 合起来闭掉 DiT×TE 二维）",
    # B70 · Krea-2 的完整 2×2（B50 上已跑齐，这里验证跨卡是否一致）
    "b70k2base": "**B70 · Krea-2 基线**（两开关全关）—— Krea-2 不走签名那条路径，base 格能跑，是唯一能量出「反量化 vs 原生」直接对照的模型",
    "b70k2sig": "**B70 · Krea-2 只签名适配**（能力声明关闭）",
    "b70k2int8fix": "**B70 · Krea-2 两个开关都开**（与 b70k2base / b70k2sig 构成完整 2×2）",
    "b70m3fp16b": "**B70 · Music 3 fp16 DiT + int8 TE · 复现组**（对照 b70m3fp16a 的 OOM 边界）",
    # B70 · Music 3 的 fp16 DiT 补跑（缺口表第 5 行的归因）
    "b70m3fp16a": "**B70 · Music 3 fp16 DiT + bf16 TE · OOM 复现组**（验证 20,608 MB 那条容量边界是否稳定复现）",
    "b70k2res": "**B70 · Krea-2 分辨率维度 · 1280×768**（此前只有 1024×1024 一点）",
    "b70k2res2": "**B70 · Krea-2 分辨率维度 · 1536×1024**",
    # KV 缓存对照（缺口表第 4 行）——上游 QwenImage21Cache 的 device × dtype 二维空间，
    # 此前完全没被测过。tag 里的 `_gpu` / `_int8` 等段编码了设置，
    # 这里给 suffix 一个可读的名字。
    "kvauto": "**KV 缓存 device=auto**（历史批次的默认设置，作为本组基线）",
    "kvgpu": "**KV 缓存 device=gpu**（强制放显存）",
    "kvcpu": "**KV 缓存 device=cpu**（放主机内存，上游说「在计算背后预取、代价很小」）",
    "kvoff": "**KV 缓存 device=off**（每步重算前缀，更慢 —— **上游明确说这是「排除缓存影响」的唯一办法**）",
    "kvi8": "**KV 缓存 dtype=int8**（约一半体积、bf16 精度）",
    "kvi4": "**KV 缓存 dtype=int4**（约四分之一体积、误差约翻倍）",
    "b70base": "**B70 · 基线**（两开关全关）—— Qwen-Image 2.1 在此格会撞签名错配而崩，是预期结果",
    "k2base": "Krea-2 · **基线**（两个开关都关，shim 完全不装）—— 2×2 的基线格。Krea-2 不走签名不适用的那条路径，能跑",
    "m3sig": "Music 3 · **只签名适配**（能力声明关闭）—— 与 int8fix 组构成 2×2",
    "prov031": "**分离点 · torch 2.12 环境 + provider 0.2.31**（只降 provider，torch 与 kernel 不动）",
}

GIB = 1024 ** 3


def gib(n):
    return round(n / GIB, 3)


def card_from_mark(hit):
    """从内嵌卡名的组合标记里提卡型：`b70k2retry` → `b70`。

    ⚠️ 为什么需要它：`SUFFIX_CARD` 不可能穷举所有组合后缀
    （`b70same` / `b50k2sig` / `b70k2retry` / `b60k2` / `b65-dualk2` …），
    漏登一个就让迁移器防呆报错（实测：`sweep_b70k2retry.jsonl` 就这么崩的）。
    所以对「以 b+卡型数字开头」的标记直接按字头提取；**提取不到返回空串**，
    交给调用方的防呆去报错——不猜。
    """
    m = re.match(r"^(b50|b60|b65|b70)", hit)
    return m.group(1) if m else ""


def card_slug(card):
    """文件名里的卡型段，形如 `b60-24g` / `b70-32g` / `b65-dual-32g`。

    🔴 容量必须从 CARDS 的 gpu 名取，**不能写死**：这里原来是
    `16 if card == "b50" else 32`，B60 是 24G 于是被写成 `b60-32g`，
    与 `CARD_LOG_KEYS` 的键 `b60-24g` 对不上 → annotate 按文件名子串
    找不到日志段，整批 B60 记录配不到服务日志（实测踩过）。
    双卡键（`b65-dual`）也走同一函数，slug 自然带上 dual 标识，
    不会和单卡 `b65-32g` 撞。
    """
    gpu = CARDS.get(card, {}).get("gpu", "")
    m = re.search(r"(\d+)\s*G", gpu)
    cap = m.group(1) if m else "32"
    return "%s-%sg" % (card, cap)


def pw_resets(p):
    """整卡域的能耗计数器归零次数。

    顶层缺（早期采集器只写在 `domains` 子项里）就回落到同一下标的域。
    ⚠️ **取不到返回 None，不是 0** —— `or 0` 会把「没记录」伪装成「零次归零」。
    """
    v = p.get("counter_resets")
    if v is not None:
        return v
    dom = (p.get("domains") or {}).get(str(p.get("card_domain")))
    return (dom or {}).get("counter_resets")


# 模型清单：文件 + 精确字节数（体积是「能装多大」那一问的原始数据）
MODELS = {
    "q21": {
        "name": "Qwen-Image 2.1",
        "domain": "comfyui-image",
        "task": "text-to-image",
        "workflow": "官方 t2i 模板（QwenImage21Cache → KSampler）",
        "res": (1280, 720),
        "steps": 25,
        "cfg": 1.0,
        "dit": {
            "bf16": ("qwen_image_2.1_bf16.safetensors", 14230280616),
            "int8_convrot": ("qwen_image_2.1_int8_convrot.safetensors", 7256783064),
        },
        "text_encoder": ("qwen3vl_8b_int8_convrot.safetensors", 9350798360),
        "vae": ("qwen_image_2.1_vae_bf16.safetensors", 675509688),
    },
    "krea2": {
        "name": "Krea-2 Turbo",
        "domain": "comfyui-image",
        "task": "text-to-image",
        "workflow": "官方 t2i 模板（CLIPTextEncode → KSampler）",
        "res": (1024, 1024),
        "steps": 8,
        "cfg": 1.0,
        "dit": {
            "bf16": ("krea2_turbo_bf16.safetensors", 26283332608),
            "int8_convrot": ("krea2_turbo_int8_convrot.safetensors", 13492686496),
        },
        "text_encoder": ("qwen3vl_4b_bf16.safetensors", 8875719384),
        "vae": ("qwen_image_vae.safetensors", 253806246),
    },
    "music3": {
        "name": "MiniMax Music 3",
        "domain": "comfyui-audio",
        "task": "text-to-audio",
        "workflow": "MiniMaxMusic3TextEncode → KSampler → VAEDecodeAudio",
        "res": None,
        "seconds": 120.0,
        "steps": 30,
        "cfg": 1.7,
        "dit": {
            "fp16": ("minimax_music3_dit_fp16.safetensors", 4914197682),
            "int8_convrot": ("minimax_music3_dit_int8_convrot.safetensors", 2502161682),
        },
        "text_encoder": ("minimax_music3_text_encoder_pruned_bf16.safetensors",
                         16706629398),
        "vae": ("minimax_music3_dav.safetensors", 216696128),
    },
}

# 各组的抽样计划（sweep.py build_plan()）——role -> seed
PLAN = {
    "q21": {"first": 701, "resident": [702, 703], "newprompt": 704},
    "krea2": {"first": 401, "resident": [402, 403], "newprompt": 404},
    "music3": {"first": 601, "resident": [602], "new_song": 3001},
}

TAG_RE = None


# KV 缓存段的解析结果（parse_tag 是纯函数，用模块级单元素列表当出口，
# 避免改它的返回元组——那会牵动所有调用点）
CACHE_TAG = [None]


def parse_tag(tag):
    """`q21_int8_convrot_int8fix` -> ('q21', 'int8_convrot', True)

    尾部还可能带卡型段与变体段（由 `sweep.py --suffix` 拼进去）：
      `q21_int8_convrot_b50int8fix` -> quant='int8_convrot'（`_b50`/`_int8fix` 都要剥）
      `q21_int8_convrot_b50base`   -> 同上
    卡型/变体以**文件名**为准（`sweep_b50int8fix.jsonl`），tag 里这段只是回声；
    但两者都要能剥，否则 `_b50` 会被当成量化档的一部分而查表失败。
    """
    CACHE_TAG[0] = None          # 每次调用重置（同一个进程会连着解析多个 tag）
    variant = tag.endswith("_int8fix")
    base = tag[: -len("_int8fix")] if variant else tag
    card = None
    te = None
    res = None
    # 循环剥尾部的标记段：
    #   变体（int8fix / sigfix / base / m3i8 / …）、卡型（b50 / b70）、
    #   **文本编码器档位**（`teint8_convrot`，Music 3 有 bf16 / int8_convrot 两份 TE）、
    #   **分辨率段**（`1536x864`）—— 后两者是「这一组跑的是什么」的一部分，
    #   不剥掉会混进量化档名导致查表失败。
    while True:
        m = re.search(r"_(\d+x\d+)$", base)
        if m and not res:
            res = m.group(1)
            base = base[: m.start()]
            continue
        m = re.search(r"_te(bf16|int8_convrot|fp16)$", base)
        if m and not te:
            te = m.group(1)
            base = base[: m.start()]
            continue
        # ⚠️ **KV 缓存段必须剥**（2026-10-17 补，之前漏了 → KeyError）：
        # `sweep.py` 在 tag 里插了 `_{cache_dev}[_{cache_dtype}]`（见 sweep.py 的 ctag），
        # 于是 tag 形如 `q21_int8_convrot_cpu_kvcpu`。
        # 漏剥的后果：`_cpu` 混进量化档名 → `m["dit"]["int8_convrot_cpu"]` → KeyError，
        # **整批迁移直接崩**（不是静默错数据，是硬失败——比错数据好，但一样丢数据）。
        # 顺序上要放在「卡型/变体」之前：`auto_int8` 这种两段组合要先整体剥掉。
        m = re.search(r"_(auto|gpu|cpu|off)(?:_(int8|int4))?$", base)
        if m and "_te" not in m.group(0):
            cache = m.group(0).lstrip("_")
            base = base[: m.start()]
            # 记进 tag 的解析结果，供落盘时写进 workload
            CACHE_TAG[0] = cache
            continue
        hit = next((c for c in CARDS if base.endswith(c) or base.endswith("_" + c)), "")
        if hit:
            card = hit
            base = base[: -len(hit)].rstrip("_")
            continue
        hit = next((v for v in sorted(SUFFIX_MARKS, key=len, reverse=True)
                    if base.endswith(v) or base.endswith("_" + v)), "")
        if hit:
            variant = variant or hit == "int8fix"
            # ⚠️ 卡型段也可能只登记在 SUFFIX_MARKS 里（`b65-dual` 就是：
            # CARDS 是身份表、等 B65 实测后才填，但 tag 现在就会带上这段）。
            # 不在这里补一刀，parse_tag 就判不出卡型 —— 而本文件 753 行那个
            # 循环有这段赋值，两个循环曾因此不一致（一个判得出、一个判不出）。
            # ⚠️ 同样加字头提取兜底：SUFFIX_CARD 穷举不完 `b70k2retry` 这类组合。
            if not card:
                card = SUFFIX_CARD.get(hit) or card_from_mark(hit)
            base = base[: -len(hit)].rstrip("_")
            continue
        break
    for key in ("q21", "krea2", "music3"):
        if base.startswith(key + "_"):
            return (key, base[len(key) + 1:], variant,
                    {"card": card, "text_encoder_quant": te, "resolution": res,
                     "kv_cache": CACHE_TAG[0]})
    return None, None, variant, {"card": card, "text_encoder_quant": te, "resolution": res}


def resolve_seed(key, role, idx_in_role):
    p = PLAN.get(key, {})
    s = p.get(role)
    if isinstance(s, list):
        return s[idx_in_role] if idx_in_role < len(s) else None
    return s


def detect_reserve(jsonl_path, override=None):
    """确定这一批实际的 `--reserve-vram`。返回 (值 or None, 出处)。

    🔴 为什么必须这么做：本函数原来把 `reserve_vram_gb` 写死成 4（标 `inferred`）。
    一旦有人换档位重跑（2026-10-21 的 `--reserve-vram 2` 补测），
    记录里就会写着一个**没跑过的配置**——比缺字段危险得多。

    取值优先级（先准后宽）：
      1. `--reserve-vram` 命令行覆盖 —— 采集批次脚本是权威出处，人明确给了就用它；
      2. jsonl 行里的 `reserve_vram` 字段（2026-10-21 起 sweep.py 会写）；
      3. 同目录 `server_<stem>.log` 的启动命令行（ComfyUI 自己的日志通常**不含**参数，
         所以这一条只在别的采集器把命令行回显进去时才命中）；
      4. 都没有 → None，调用方退回写死的 4 并标 `inferred`。
    """
    if override is not None:
        return override, "--reserve-vram 参数"

    stem, _ = os.path.splitext(os.path.basename(jsonl_path))
    d = os.path.dirname(jsonl_path)

    # 2) jsonl 自带字段
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            first = next((l for l in f if l.strip()), "")
        if first:
            v = json.loads(first).get("reserve_vram")
            if isinstance(v, (int, float)):
                return v, "jsonl.reserve_vram"
    except (OSError, ValueError):
        pass

    # 3) 服务端日志的启动命令行
    cand = os.path.join(d, "server_%s.log" % stem)
    if os.path.isfile(cand):
        vals = set()
        with open(cand, encoding="utf-8", errors="replace") as f:
            for line in f:
                for m in re.finditer(r"--reserve-vram\s+([0-9]+(?:\.[0-9]+)?)", line):
                    vals.add(float(m.group(1)))
        # 多个不同的值 = 这次跑过不止一个档位 → 不猜
        if len(vals) == 1:
            v = vals.pop()
            return (int(v) if v == int(v) else v), os.path.basename(cand)

    return None, None



def build_records(rows, date, variant, card, reserve=None):
    """把同一 (tag) 的样本聚成一条记录。`card` 决定 env 里的卡身份。"""
    groups = {}
    for r in rows:
        groups.setdefault(r["tag"], []).append(r)

    out = []
    for tag, rs in groups.items():
        key, quant, _suffix_variant, extra = parse_tag(tag)
        if key is None:
            print("[skip] 认不出 tag: %s" % tag)
            continue
        m = MODELS[key]
        dit_file, dit_bytes = m["dit"][quant]
        te_file, te_bytes = m["text_encoder"]
        vae_file, vae_bytes = m["vae"]

        samples = []
        seen = {}
        for r in rs:
            role = r["role"]
            k = seen.get(role, 0)
            seen[role] = k + 1
            samples.append({
                "role": role,
                "ok": bool(r.get("ok")),
                "server_sec": r.get("server_sec"),
                "wall_sec": r.get("wall_sec"),
                # 采集时从服务器日志 `Prompt executed` 行量到的值。
                # 与 server_sec（来自 /history 的两条时间戳之差）是**两条独立路径**，
                # 留着可做交叉核对；取证回填用它做精确配对（见 annotate_comfy_evidence.py）。
                "log_prompt_executed_s": r.get("prompt_executed_s"),
                "loads": r.get("n_load"),
                "loaded_complete": r.get("n_loaded_complete"),
                "offload": r.get("n_offload"),
                "seed": resolve_seed(key, role, k),
                "oom": r.get("oom"),
                "device_lost": r.get("device_lost"),
                "cuda_pin_crash": r.get("cuda_pin_crash"),
                # 整卡功耗（2026-10-19 起采集器默认采）。None = 未采集，不是 0；
                # 均值覆盖整轮（含装载），所以「装不下、每轮必重装」的配置
                # 功耗均值会被稀释，比 `it/s` 更需要结合 `loads` 一起看。
                "power": r.get("power"),
            })

        # ⚠️ `ok=false` + 有服务端时长 **不等于「跑完了才失败」**。
        # 实测踩过两种截然不同的情况，字段长得一样：
        #   · TypeError（节点抛异常）→ 时长 0.04 / 0.05 / 0.44 / 34.53 s，秒级失败
        #   · DEVICE_LOST（设备失联）→ 时长 88.31 s，采样跑完才炸
        # 所以这里**只如实列出服务端报告过的时长与采集器打的诊断标记，不替读者下结论**；
        # 判「到底是哪种」需要看服务端日志，那由 annotate 阶段负责。
        served = [s for s in samples
                  if not s["ok"] and s.get("log_prompt_executed_s")]
        flags = sorted({f"{k}={v}" for s in samples for k, v in s.items()
                        if k in ("device_lost", "oom", "cuda_pin_crash")})
        ok = [s["server_sec"] for s in samples if s["ok"] and s["server_sec"]]
        summary = {
            "n_total": len(samples),
            "n_ok": len(ok),
            "n_fail": len(samples) - len(ok),
        }
        if ok:
            summary.update({
                "server_sec_mean": round(sum(ok) / len(ok), 2),
                "server_sec_min": round(min(ok), 2),
                "server_sec_max": round(max(ok), 2),
            })
        # 分角色给均值：resident 才是「稳态」，first 含加载，不可混
        for role in ("first", "resident", "newprompt", "new_song"):
            v = [s["server_sec"] for s in samples
                 if s["role"] == role and s["ok"] and s["server_sec"]]
            if v:
                summary["%s_sec_mean" % role] = round(sum(v) / len(v), 2)

        if served:
            # **不进 n_ok**（那会虚高稳定性），但也不丢（那是唯一的信息量）。
            summary["n_failed_with_server_reported_sec"] = len(served)
            summary["server_reported_sec_on_failure"] = sorted(
                s["log_prompt_executed_s"] for s in served)

        # 功耗汇总：只统计真采到的轮次；一条都没有就留 None（不是 0）
        _pw = [s["power"] for s in samples
               if isinstance(s.get("power"), dict) and s["power"].get("avg_w") is not None]
        if _pw:
            summary["power"] = {
                "basis": "整卡电源域 · 能耗计数器求差 · 均值覆盖整轮（含装载）",
                "card_domain": _pw[0].get("card_domain"),
                "card_limit_mw": _pw[0].get("card_limit_mw"),
                "n_rounds": len(_pw),
                "avg_w_min": min(p["avg_w"] for p in _pw),
                "avg_w_max": max(p["avg_w"] for p in _pw),
                # P90 判断「有没有把卡压满」；avg_w 会被装载段稀释（见 power_lib）
                "p90_w_min": min(p.get("p90_w") or 0 for p in _pw),
                "p90_w_max": max(p.get("p90_w") or 0 for p in _pw),
                "peak_w_max": max(p.get("peak_w", 0) for p in _pw),
                "peak_basis": "1s",
                # 能量：Krea-2 那种「装不下、每轮必重装」的配置，能量里装载段占比很高，
                # 所以它必须与 avg_w / busy_share 一起看，不能单独当「这模型多耗电」的结论。
                "energy_j_max": max(p.get("energy_j", 0) for p in _pw),
                "counter_resets_max": (max(_r) if (_r := [x for x in (pw_resets(p) for p in _pw)
                                                          if x is not None]) else None),
                "busy_share_mean": round(
                    sum(p.get("busy_share") or 0 for p in _pw) / len(_pw), 3),
            }
        else:
            summary["power"] = None
            if flags:
                summary["collector_flags"] = flags

        wl = {
            "model": m["name"],
            "task": m["task"],
            "workflow": m["workflow"],
            "dit_file": dit_file,
            "dit_size_gib": gib(dit_bytes),
            "text_encoder_file": te_file,
            "text_encoder_size_gib": gib(te_bytes),
            "vae_file": vae_file,
            "vae_size_gib": gib(vae_bytes),
            "steps": m["steps"],
            "cfg": m["cfg"],
            "sampler": "euler",
            "scheduler": "simple",
        }
        if extra.get("resolution"):
            rw, rh = (int(x) for x in extra["resolution"].split("x"))
            wl.update({"width": rw, "height": rh, "resolution": extra["resolution"]})
        elif m["res"]:
            w, h = m["res"]
            wl.update({"width": w, "height": h, "resolution": "%dx%d" % (w, h)})
        if extra.get("text_encoder_quant"):
            wl["text_encoder_quant"] = extra["text_encoder_quant"]
            # TE 档位变了，字节数也要跟着变 —— 容量账的依据
            te_alt = {"bf16": ("minimax_music3_text_encoder_pruned_bf16.safetensors",
                               16706629398),
                      "int8_convrot": ("minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
                                       9196611886)}
            if key == "music3" and extra["text_encoder_quant"] in te_alt:
                te_file, te_bytes = te_alt[extra["text_encoder_quant"]]
                wl["text_encoder_file"] = te_file
                wl["text_encoder_size_gib"] = gib(te_bytes)
        if m.get("seconds"):
            wl["seconds"] = m["seconds"]

        # 置信度按「原始数据里到底有什么」标，不按「我们知道什么」标：
        #   SWEEP_REPORT.md 的表头写明机型 / 显存 / 内存 / 栈 → recorded
        #   AIB 四要素（chip/subsys/device_id/board_vendor）与驱动 → 原始数据里没有，
        #   按机器级事实填但标 inferred，待服务器日志取证（annotate_comfy_evidence.py）
        #   把卡片型号那一行作为直接证据后再升为 recorded。
        conf = {
            "gpu": "recorded", "vram_visible_gib": "recorded", "ecc": "recorded",
            "cpu": "recorded", "ram_gb": "recorded", "os": "recorded",
            "app": "recorded", "app_version": "recorded",
            "comfy_kitchen": "recorded", "omni_xpu_kernel": "recorded",
            "chip": "inferred", "subsys": "inferred", "device_id": "inferred",
            "board_vendor": "inferred", "driver": "inferred", "board_code": "inferred",
            "width": "recorded", "height": "recorded", "resolution": "recorded",
            "steps": "recorded", "cfg": "recorded",
            "reserve_vram_gb": "recorded" if reserve is not None else "inferred",
            "seed": "inferred",
        }

        env = dict(RIG, **CARDS[card])
        env.update(CARDS[card].get("stack", {}))
        env.update(STACK_BASE)
        env["env_confidence"] = conf
        eff = MARK_STACK.get(variant, variant)      # 自由标记 → 实际栈变体
        env["batch_mark"] = variant                # 含 base：否则 annotate 会回退默认键而串卡
        if eff != "base":
            env["stack_variant"] = eff
            env["int8fix_env"] = dict(STACK_VARIANTS[eff])
            env["batch_mark_note"] = MARK_NOTE.get(variant, "")
            if variant in ("m3i8", "m3f16", "k2bf16", "r1536", "r2048",
                           "t213", "prov031", "r2048full", "tebf16",
                           "k2bf16retry", "b70same", "b70sig", "b70t213",
                           "b50img3072", "b65img3072", "b65img4096",
                           "b70m3teint8", "b70m3tebf16", "b70m3teint8b", "b70m3tebf16b",
                                    "b70m3fp16tebf16", "b70m3fp16teint8",
                                    "b70k2base", "b70k2sig", "b70k2res", "b70k2res2", "b70m3fp16a",
                           "b70k2int8fix", "b70m3fp16b",
                                    "b70k2int8fix", "b70m3fp16b",
                                    "kvauto", "kvgpu", "kvcpu", "kvoff", "kvi8", "kvi4"):
                env["comfyui_patch"] = "OMNIXPU_INT8_COMPUTE=1 + OMNIXPU_INT8_SIGFIX=1"
                env["comfyui_patch_note"] = (
                    "能力声明 + 签名适配，与 2026-10-16 其余 B50 批次同一栈。"
                    "**不可与 2026-10-14 那批（torch213 内核 / 无 int8fix）并排引用。**")
            elif variant == "int8fix":
                env["comfyui_patch"] = "OMNIXPU_INT8_COMPUTE=1 + OMNIXPU_INT8_SIGFIX=1"
                env["comfyui_patch_note"] = (
                    "① 能力声明：把 ComfyUI 上游 comfy/model_management.py 里 "
                    "`if is_intel_xpu(): return False`（supports_int8_compute）翻成 True，"
                    "使 convrot_w4a4 / w6a8_int8 / asym_w4a8_int8 从 emulated 转 native。"
                    "② 签名适配：XPU provider 里 vendored 的 comfy_kitchen（0.2.31/0.2.33 快照）"
                    "的 int8_linear 只有 8 参，而 ComfyUI 0.39 按 12 参契约调用 → "
                    "适配层补齐缺失的 4 个可选关键字。"
                    "**2026-10-16 实测：对 Qwen-Image 2.1，② 是能不能跑的分界线，① 不给速度。**"
                    "**这是与基线不同的软件栈，不可并排引用。**"
                )
            elif variant == "sigfix":
                env["comfyui_patch"] = "OMNIXPU_INT8_SIGFIX=1（仅签名适配，能力声明保持关闭）"
                env["comfyui_patch_note"] = (
                    "只装 int8_linear 签名适配，不翻 supports_int8_compute。"
                    "用于把「能不能跑」与「快多少」两件事分开量——"
                    "2026-10-16 实测：Qwen-Image 2.1 的 int8 权重是 int8_tensorwise 格式，"
                    "该格式在能力声明开/关两种状态下都是 native，"
                    "所以能力声明对它没有可解锁的东西。"
                    "**不可与基线并排引用。**"
                )

        status = "active"
        discard_reason = None
        if summary["n_ok"] == 0:
            status = "discarded"
            if served:
                # **不下「哪一类失败」的结论**：TypeError 与 DEVICE_LOST 的字段形状相同，
                # 只靠时长猜会把一种错记成另一种（实测已踩）。诊断留给服务端日志。
                discard_reason = (
                    "客户端 %d/%d 轮判失败，其中 %d 轮服务端报过执行时长：%s 秒。"
                    "采集器打的诊断标记：%s。"
                    "**该组不构成有效性能证据**（时长不可引用）；"
                    "失败类型需查服务端日志区分——节点抛异常会是秒级，设备失联则先跑完再炸。"
                    % (summary["n_fail"], summary["n_total"], len(served),
                       ", ".join(str(x) for x in summary["server_reported_sec_on_failure"]),
                       "、".join(flags) if flags else "（采集器未标记任何已知故障类型）"))
            else:
                # 没有服务端完成记录 → 真的没跑成。按样本里的错误原因如实记，不编故事。
                _errs = {str((s.get("error") or s.get("tail") or "")[:160])
                         for s in samples if s.get("error") or s.get("tail")}
                discard_reason = (
                    "该组 %d 轮全部失败，无服务端完成记录。" % summary["n_total"]
                    + ("样本记录的错误：" + " ｜ ".join(sorted(_errs)[:2])
                       if _errs else "（原始数据里没有留下错误信息）"))

        rec = {
            "schema": SCHEMA,
            "tag": "comfyui-%s-%s" % (m["name"].lower().replace(" ", "-"), quant),
            "date": date,
            "source": "local",
            "domain": m["domain"],
            "tool": "sweep.py + ComfyUI /prompt + /history",
            "status": status,
            "env": env,
            "envvars": dict(ENV_BASE, **({"OMNIXPU_INT8_COMPUTE": "1"}
                                         if variant == "int8fix" else {})),
            "workload": wl,
            # 读得到服务端命令行就用实际值（`recorded`），读不到才退回写死的 4（`inferred`）。
            # 2026-10-21 起：`--reserve-vram 2` 的补测与 `4` 的历史批次同时存在，
            # 写死会让两条记录看起来配置相同 —— 那是错的口径。
            "reserve_vram_gb": 4 if reserve is None else reserve,
            "samples": samples,
            "summary": summary,
            "notes": (
                "口径：服务端 execution_start → execution_success，不含排队。"
                "**分辨率必读**：出图/出音频的时间与分辨率（音频为时长）强相关，"
                "workload 里的 width/height 是该数字的量纲。"
                "`first` 含模型加载、`resident` 是同提示词换种子（稳态）、"
                "`newprompt` 是换提示词（ComfyUI 节点缓存全失效）——三者不可混比。"
                "seed 由 sweep.py 的计划表推得（标 inferred）。"
                "文本编码器 2.1 本机只有 int8 版（无 bf16 8B），故 bf16 行的 TE"
                "与对照口径有偏差，见 SWEEP_REPORT.md。"
                + (" stack_variant=int8fix：跑在打了 OMNIXPU_INT8_COMPUTE 补丁的栈上。"
                   if variant == "int8fix" else "")
            ),
        }
        if discard_reason:
            rec["discard_reason"] = discard_reason
            rec["superseded_by"] = None
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="_bench_f 目录（含 sweep*.jsonl）")
    ap.add_argument("--outdir", required=True, help="输出目录（bench/data）")
    ap.add_argument("--card", default="",
                    # 动态取，不写死：曾写死 `["", "b50", "b70"]`，B60 上机后想手工
                    # 指定卡型时它不在可选项里（自动识别正常时用不到，一旦要手工
                    # 指定就被卡住）。CARDS 加了 b65 / b65-dual 后这里自动跟上。
                    choices=[""] + sorted(CARDS),
                    help="默认卡型；留空则从 sweep*.jsonl 的文件名后缀判定"
                         "（sweep_b50int8fix.jsonl -> b50 + int8fix）")
    ap.add_argument("--only", default=None,
                    # 增量迁移用：只处理文件名含该子串的 sweep*.jsonl。
                    # 没有它就只能整目录重跑，而这个目录里躺着 B50/B60/B70 的历史批次，
                    # 整目录重跑既慢、又会把已回填的取证字段再抹一遍。
                    help="只处理文件名含该子串的 sweep*.jsonl（增量迁移用）")
    ap.add_argument("--reserve-vram", type=float, default=None,
                    # 批次级覆盖：采集时用的 `--reserve-vram` 是多少就填多少。
                    # 🔴 不填的话记录会写死 4 并标 inferred —— 换了档位的补测
                    # （如 2026-10-21 的 reserve 2）就会在数据里变成「跑的是 4」。
                    help="这一批采集时用的 --reserve-vram（不填则尝试自动判定，最后退回 4）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    outdir = Path(a.outdir)
    if not a.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)

    n = 0
    # 自动发现：sweep.jsonl / sweep_int8fix.jsonl / sweep_b50sigfix.jsonl / sweep_b50base.jsonl …
    srcs = sorted(glob.glob(os.path.join(a.src, "sweep*.jsonl")))
    if a.only:
        srcs = [p for p in srcs if a.only in os.path.basename(p)]
        if not srcs:
            raise SystemExit("--only %r 没匹配到任何 sweep*.jsonl" % a.only)
    for p in srcs:
        fn = os.path.basename(p)
        stem = fn[: -len(".jsonl")]
        # 反复剥尾部的标记段：`sweep_b50int8fix` → 剥 int8fix、b50；
        # `sweep_b50base` → 剥 base、b50；`sweep` → 什么都不剥（走 legacy 映射）。
        card = a.card
        variant = "base"
        while True:
            if not card:
                hit = next((c for c in CARDS if stem.endswith(c)), "")
                if hit:
                    card, stem = hit, stem[: -len(hit)]
                    stem = stem.rstrip("_")
                    continue
            # ⚠️ 必须按**长度降序**匹配：组合标记（`k2base` / `k2bf16retry`）
            # 比单段标记（`base` / `sigfix`）长，若不排序会先剥掉 `base`
            # 留下 `b50k2` → 认不出卡型 → 迁移器直接报错（防呆是对的，但那是自找的）。
            hit = next((v for v in sorted(SUFFIX_MARKS, key=len, reverse=True)
                        if stem.endswith(v)), "")
            if hit:
                variant, stem = hit, stem[: -len(hit)]
                stem = stem.rstrip("_")
                # 组合标记里内嵌了卡名（`b70same` / `b50k2sig`）→ 剥完就查表取卡型。
                # ⚠️ 不能放到循环之后：`b70same` 本身就在 SUFFIX_MARKS 里，
                # 循环会先把它剥成 `variant=b70same` + `stem=sweep`，卡型无处可取。
                # ⚠️ 也不能只信 SUFFIX_CARD：穷举不完所有组合（`b70k2retry`
                # 就漏过，迁移直接崩），所以加一层按字头提取的兜底。
                if not card:
                    card = SUFFIX_CARD.get(hit) or card_from_mark(hit)
                continue
            break
        # 新卡队列的批次文件名只带卡型（`sweepb60.jsonl`），卡型被上面的 CARDS
        # 分支先剥掉后，SUFFIX_MARKS 无标记可剥 → variant 停在 "base"。
        # 但实测这批跑的是 int8fix 栈（omni_int8fix.py 两开关默认开，
        # 服务日志三处印证，见 MARK_STACK 里 b60 条注释）。
        # 不补这一刀的后果：记录写成「两开关全关」，而日志写明开着
        # → **对客材料里的假声明**，比 KeyError 更危险（那个至少会崩）。
        if variant == "base" and card in CARD_DEFAULT_STACK:
            variant = CARD_DEFAULT_STACK[card]
        if not card:
            # 历史命名没有卡型后缀（2026-10-14 那批）。不是猜：对应服务日志里
            # `Device: xpu:0 Intel(R) Arc(TM) Pro B70 Graphics` + `Total VRAM 31907 MB`
            # 已直接证明是 B70（台账 §3 审计行「卡型号由日志反证」）。
            card = LEGACY_CARDS.get(fn, "")
        if not card:
            # **判不出直接报错退出** —— 静默套默认卡会给 B50 数据盖上 B70 身份
            raise SystemExit(
                "认不出卡型（%s）。请用 --card b50|b70 显式指定，"
                "或把文件名改成 sweep_<卡型>[int8fix|sigfix|base].jsonl。" % fn)
        rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        date = dt.date.fromtimestamp(os.path.getmtime(p)).isoformat()
        # 确定这一批实际的 `--reserve-vram`（命令行覆盖 / jsonl 字段 / 服务端日志 / 退回 4）
        reserve, reserve_src = detect_reserve(p, a.reserve_vram)
        print("    reserve-vram=%s（出处：%s）"
              % (reserve if reserve is not None else "4（写死的 inferred）",
                 reserve_src or "无"))
        for rec in build_records(rows, date, variant, card, reserve=reserve):
            name = "%s_%s_%s%s-comfyui.json" % (
                rec["date"], card_slug(card),
                rec["tag"].replace("comfyui-", ""),
                "-%s" % variant if variant != "base" else "")
            print("%-30s -> %-58s %s | ok=%d/%d%s"
                  % (fn, name, rec["status"],
                     rec["summary"]["n_ok"], rec["summary"]["n_total"],
                     " mean=%s" % rec["summary"].get("server_sec_mean")
                     if rec["summary"]["n_ok"] else ""))
            if not a.dry_run:
                # ⚠️ 合并而不是覆盖：`timing_breakdown` / `log_evidence` / `env_evidence`
                # 是 annotate_comfy_evidence.py 从服务器日志回填的**取证字段**，
                # 重跑 migrate 会把它们抹掉（实测踩过：9 条历史记录被抹成 None）。
                # 迁移只负责骨架，取证归 annotate —— 这里保住已存在的取证结果。
                tgt = outdir / name
                if tgt.exists():
                    old = json.loads(tgt.read_text(encoding="utf-8"))
                    for k in ("timing_breakdown", "log_evidence"):
                        if old.get(k) is not None:
                            rec[k] = old[k]
                    for k in ("env_evidence",):
                        if isinstance(old.get("env", {}).get(k), str) and \
                                not isinstance(rec.get("env", {}).get(k), str):
                            rec["env"][k] = old["env"][k]
                    conf = rec["env"].get("env_confidence", {})
                    oldconf = old.get("env", {}).get("env_confidence", {})
                    for k, v in oldconf.items():
                        # 取证跑过的字段能从 inferred 升 recorded，不许降级
                        if v == "recorded" and conf.get(k) != "recorded":
                            conf[k] = "recorded"
                    merged = sum(1 for k in ("timing_breakdown", "log_evidence")
                                 if rec.get(k) is not None)
                    print("%-30s    ↺ 合并已有记录，保留取证字段 %d/2"
                          % (fn, merged))
                tgt.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                               encoding="utf-8")
            n += 1

    print("\n[%s] 生成 %d 条记录"
          % ("dry-run 未落盘" if a.dry_run else "OK", n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
