#!/usr/bin/env python3
r"""把 ComfyUI 服务器日志里的证据回填进 comfyui-xpu-bench/1 记录。

解决两个问题：
  1. **卡型号只是「推断」** —— 迁移时 env 里没有 device_id/subsys（早期采集没落盘），
     身份靠注册表 PCI 枚举补写、标 inferred。若某轮服务器日志还在，
     日志里的 `Device: xpu:0 Intel(R) Arc(TM) Pro B70 Graphics` 就是**直接证据**，
     可以把置信度升为 recorded。
  2. **只有总时长，没有分解** —— 日志里的进度条能读出单步耗时、采样段总时长，
     以及 DiT 的装载方式（完全驻留 / 部分卸载）。这是区分「算力慢」与
     「装不下」的唯一依据，必须随数据一起落盘。

**配对判据（关键）**：日志里的 `Prompt executed in X seconds` 必须与该样本的
`server_sec` 对上（默认容差 1.0 s）。对不上就不认——不靠文件名猜。

用法:
  python annotate_comfy_evidence.py --data bench/data --logdir <目录> [--logdir ...] [--dry-run]

`--logdir` 可写成 `标签=路径`，标签会出现在写回记录的路径占位符里——
**本仓库不出现机器的绝对路径**（见 bench/README.md 顶部约定），
所以写回前会把日志根目录换成 `<标签>`（默认标签 `<日志目录>`）：

  --logdir "ComfyUI 日志目录=D:\\<ComfyUI 目录>\\_ab_logs" ->  <ComfyUI 日志目录>\\server_ab_on_s6_r0.log
  --logdir "bench_f=D:\\<工具目录>\\_bench_f"       ->  <bench_f>\\server_sweep.log
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

TOL_SEC = 1.0

# 日志根目录 -> 占位符标签。由 main() 从 --logdir 填。
LOG_ROOTS = []

# tag 形如 `<域前缀><键>`，键用来推候选日志名。
# 域前缀按 domain 分：视频 / 出图 / 音乐（见 migrate_comfy_media.py）。
TAG_PREFIXES = ("comfyui-h3-", "comfyui-qwen-image-2.1-", "comfyui-krea-2-turbo-",
                "comfyui-minimax-music-3-")
TAG_PREFIX = TAG_PREFIXES[0]      # 兼容旧引用

# 日志里的装载行用的是**模型类名**，与文件名不同。按 workload.model 选针。
# 注意：`Requested to load Krea2` 与 `Requested to load Krea2TEModel_` 是两行，
# 匹配式要求行尾紧跟换行，所以短名不会误吃长名（H3 处同理）。
DIT_NEEDLE = {
    "MiniMax H3": "MiniMaxH3",
    "Qwen-Image 2.1": "QwenImage21",
    "Krea-2 Turbo": "Krea2",
    "MiniMax Music 3": "MiniMaxMusic3",
}

# 文件名 -> 日志文件绝对路径（历史遗留：日志不在 _ab_logs 里）
LOG_OVERRIDES = {
    "2026-10-05_comfyui-h3-bench.json":
        r"<ComfyUI 日志目录>\_server_v034c.log",
}

# tag 派生键 -> 候选日志键。**只列历史遗留的命名不一致，不做模糊匹配**——
# 配对最终仍靠 `Prompt executed` 对时（见 match_round），别名只是把候选捞进来。
LOG_KEY_ALIASES = {
    "smoke": ["conv"],        # tag smoke  → server_conv.log
    "stab_on": ["stab"],      # tag stab_on → server_stab.log
    # 出图 / 音乐的本机复现是「一套 sweep 跑三组模型」，日志按批次命名，
    # 不按模型命名 → 三组都指向同一批日志，靠时间配对区分（见 match_round）。
    "qwen-image-2.1-bf16": ["sweep"],
    "qwen-image-2.1-int8_convrot": ["sweep"],
    "qwen-image-2.1-int8_convrot-int8fix": ["sweep_int8fix"],
    # 2026-10-16 新增：16 GB 档（B50）上 Qwen-Image 2.1 的三组 2×2 对照。
    # 三份日志按**变体**命名（base / sigfix / int8fix），与文件名后缀一致。
    "b50-16g_qwen-image-2.1-int8_convrot": ["sweep_b50base"],
    "b50-16g_qwen-image-2.1-int8_convrot-sigfix": ["sweep_b50sigfix"],
    "b50-16g_qwen-image-2.1-int8_convrot-int8fix": ["sweep_b50int8fix"],
    "krea-2-turbo-bf16": ["sweep"],
    "krea-2-turbo-int8_convrot": ["sweep"],
    "krea-2-turbo-int8_convrot-int8fix": ["sweep_int8fix"],
    "minimax-music-3-fp16": ["sweep"],
    "minimax-music-3-int8_convrot": ["sweep"],
    "minimax-music-3-int8_convrot-int8fix": ["sweep_int8fix"],
}

# 卡型 × 量化档 × 变体 → 该看哪份日志。**必须这么索引**：`rec["tag"]` 里不含卡型，
# 所以 `comfyui-qwen-image-2.1-int8_convrot` 这一个 tag 同时对应 B70 的
# `server_sweep.log`（10-14）和 B50 的 `server_sweep_b50base.jsonl`（10-16）——
# 只按 tag 找日志会把 B50 的记录配到 B70 的日志上。
# 好在型号一致性校验会当场报 MISMATCH（实测拦住了 4 条），但更该一开始就分清。
#
# 量化档也要参与索引：同为 `base` 变体，bf16 与 int8 在 B50 上是两轮不同的跑测
# （`server_sweep_b50.log` vs `server_sweep_b50base.log`）。
CARD_LOG_KEYS = {
    # 2026-10-21 B65 单卡上机（身份已按 gpu_identity.py 实测登记进 migrate_comfy.py 的 CARDS）。
    # 日志前缀**无下划线**：sweep.py 的规则是 `sweep{suffix}.jsonl` / `server_sweep{suffix}.log`，
    # stage_c 给的 suffix 是 `b65` / `b65k2` / `b65m3`（每模型一个，见 b60-24g 的说明）。
    # ⚠️ **"b65-dual-32g" 还没登记**：本次只有一张 B65 在机；双卡上机后补
    #    `sweepb65-dual` / `server_sweepb65-dual`，否则双卡记录会配到单卡日志上。
    "b65-32g": {
        ("bf16", "base"): ["sweepb65"],
        ("fp16", "base"): ["sweepb65"],
        ("int8_convrot", "base"): ["sweepb65"],
        ("int8_convrot", "sigfix"): ["sweepb65"],
        ("int8_convrot", "int8fix"): ["sweepb65"],
        ("int8_convrot", "b65k2"): ["sweepb65k2"],
        ("int8_convrot", "b65m3"): ["sweepb65m3"],
        # 2026-10-21 补测：Music 3 换 `--reserve-vram 2`。**必须单独登记**——
        # `sweepb65m3` 的 glob 会把 `server_sweepb65m3res2.log` 一起捞进来，
        # 而 tail 检查（剩 `res2`）又把它剔掉，于是 res2 记录配到 0 个日志（实测踩到）。
        ("int8_convrot", "b65m3res2"): ["sweepb65m3res2"],
    },
    # 2026-10-20 B60 上机。日志文件名形如 `sweepb60.jsonl` / `server_sweepb60.log`
    # （`--suffix b60`），与 b50/b70 的命名规律一致。
    # 🔴 **键名无下划线**：sweep.py 的命名规则是 `sweep{suffix}.jsonl`，
    # B50/B70 那批的 suffix 自带下划线（`--suffix _b50base`）才成了 `sweep_b50base`。
    # 曾按 `sweep_b60` 登记 → glob `server_sweep_b60*.log` 找不到实际文件
    # `server_sweepb60.log`，整批 B60 记录配不到服务日志（实测踩过）。
    "b60-24g": {
        ("bf16", "base"): ["sweepb60"],
        ("fp16", "base"): ["sweepb60"],
        ("int8_convrot", "base"): ["sweepb60"],
        ("int8_convrot", "sigfix"): ["sweepb60"],
        ("int8_convrot", "int8fix"): ["sweepb60"],
        # 2026-10-20 **每模型独立 suffix**（driver 的 stage_c 派生：q21→`b60`、
        # krea2→`b60k2`、music3→`b60m3`）。variant 由 jsonl 文件名剥出，
        # 所以这里按 variant 分条目，才不会和 q21 的 base 撞同一个键。
        ("int8_convrot", "b60k2"): ["sweepb60k2"],
        ("int8_convrot", "b60m3"): ["sweepb60m3"],
    },
    "b50-16g": {
        ("bf16", "base"): ["sweep_b50"],
        ("bf16", "k2bf16"): ["sweep_b50k2bf16"],
        ("int8_convrot", "base"): ["sweep_b50base"],
        ("int8_convrot", "sigfix"): ["sweep_b50sigfix"],
        ("int8_convrot", "int8fix"): ["sweep_b50int8fix"],
        # 2026-10-16 补测：Music 3 / 分辨率扫描 / Krea-2 bf16。
        # 这些标记编码的是「跑的是哪一组」，栈仍是 int8fix。
        ("int8_convrot", "m3i8"): ["sweep_b50m3i8"],
        ("fp16", "m3f16"): ["sweep_b50m3f16"],
        ("int8_convrot", "r1536"): ["sweep_b50r1536"],
        ("int8_convrot", "r2048"): ["sweep_b50r2048"],
        # 内核构建对照实验：B 组 = torch 2.13 环境；C 组 = torch 2.12 + provider 0.2.31
        ("int8_convrot", "t213"): ["sweep_b50t213"],
        ("int8_convrot", "prov031"): ["sweep_b50prov031"],
        ("int8_convrot", "r2048full"): ["sweep_b50r2048full"],
        ("int8_convrot", "tebf16"): ["sweep_b50tebf16"],
        ("bf16", "k2bf16retry"): ["sweep_b50k2bf16retry"],
        ("int8_convrot", "k2sig"): ["sweep_b50k2sig"],
        ("int8_convrot", "m3sig"): ["sweep_b50m3sig"],
        ("int8_convrot", "k2base"): ["sweep_b50k2base"],
    },
    "b70-32g": {
        ("bf16", "base"): ["sweep"],
        ("fp16", "base"): ["sweep"],
        ("int8_convrot", "base"): ["sweep"],
        ("int8_convrot", "sigfix"): ["sweep_int8fix"],
        ("int8_convrot", "int8fix"): ["sweep_int8fix"],
        # 2026-10-17 B70 装回机后的同代码对照。B50 那批采于 B70 拆机状态，
        # 这几组消除「同时双卡/只有单卡」这个差异，才能干净对比 B50 与 B70。
        ("int8_convrot", "b70same"): ["sweep_b70same"],
        ("int8_convrot", "b70sig"): ["sweep_b70sig"],
        ("int8_convrot", "b70base"): ["sweep_b70base"],
        ("bf16", "b70same"): ["sweep_b70bf16"],
        ("int8_convrot", "b70t213"): ["sweep_b70t213"],
        # B70 的 Music 3：此前全是 bf16 TE，这两组补上 int8 TE 这一维
        ("int8_convrot", "b70m3teint8"): ["sweep_b70m3teint8"],
        ("fp16", "b70m3tebf16"): ["sweep_b70m3tebf16"],
        # Music 3 的 **int8 DiT + bf16 TE** 这一格原来漏了（只登记了 fp16 DiT 的）。
        # 实测这份日志里 148.94 / 61.96 正好对上记录的 148.93 / 61.95。
        ("int8_convrot", "b70m3tebf16"): ["sweep_b70m3tebf16"],
        ("int8_convrot", "b70m3teint8b"): ["sweep_b70m3teint8b"],
        ("int8_convrot", "b70m3tebf16b"): ["sweep_b70m3tebf16b"],
        ("fp16", "b70m3fp16tebf16"): ["sweep_b70m3fp16tebf16"],
        ("fp16", "b70m3fp16teint8"): ["sweep_b70m3fp16teint8"],
        # B70 · Krea-2 的完整 2×2（验证「能力声明收益 ≤5%」是否跨卡一致）
        ("int8_convrot", "b70k2base"): ["sweep_b70k2base"],
        ("int8_convrot", "b70k2sig"): ["sweep_b70k2sig"],
        ("int8_convrot", "b70k2int8fix"): ["sweep_b70k2int8fix"],
        ("int8_convrot", "b70k2res"): ["sweep_b70k2res"],
        ("int8_convrot", "b70k2res2"): ["sweep_b70k2res2"],
        # Music 3 的 fp16 DiT + bf16 TE 复现组
        ("fp16", "b70m3fp16a"): ["sweep_b70m3fp16a"],
        ("fp16", "b70m3fp16b"): ["sweep_b70m3fp16b"],
        # KV 缓存对照（B70）
        ("int8_convrot", "kvauto"): ["sweep_kvauto"],
        ("int8_convrot", "kvgpu"): ["sweep_kvgpu"],
        ("int8_convrot", "kvcpu"): ["sweep_kvcpu"],
        ("int8_convrot", "kvoff"): ["sweep_kvoff"],
        ("int8_convrot", "kvi8"): ["sweep_kvi8"],
        ("int8_convrot", "kvi4"): ["sweep_kvi4"],
        # 2026-10-19 四组「TDR 修好后」的复跑 + 功耗专项批。
        # 每批一个日志文件（内含该批全部模型），所以三档量化都指向同一个键。
        # ⚠️ 功耗批的日志是 `server_sweepb70pw.log` —— **没有下划线**，
        # 与其它批次命名不一致，按 `sweepb70pw` 登记才能 glob 到。
        **{(q, "b70v2"): ["sweep_b70v2"] for q in ("bf16", "fp16", "int8_convrot")},
        **{(q, "b70k2v2"): ["sweep_b70k2v2"] for q in ("bf16", "fp16", "int8_convrot")},
        **{(q, "b70m3v2"): ["sweep_b70m3v2"] for q in ("bf16", "fp16", "int8_convrot")},
        **{(q, "b70m3i8v2"): ["sweep_b70m3i8v2"] for q in ("bf16", "fp16", "int8_convrot")},
        **{(q, "b70pw"): ["sweepb70pw"] for q in ("bf16", "fp16", "int8_convrot")},
    },
}


def _quant_of(rec):
    """从 dit_file 反推量化档（bf16 / int8_convrot / fp16）。"""
    f = str((rec.get("workload") or {}).get("dit_file") or "")
    for q in ("int8_convrot", "bf16", "fp16", "fp8_scaled"):
        if q in f:
            return q
    return ""

RE_DEVICE = re.compile(r"Device:\s*xpu:\d+\s+(.+?)\s*$", re.M)
RE_VRAM = re.compile(r"Total VRAM (\d+) MB")
RE_LOAD = re.compile(r"loaded (completely|partially);\s*(.*)")
# ⚠️ 两种格式：ComfyUI 对**超过 10 分钟**的任务改印 `HH:MM:SS`，不是秒数。
# 实测：301.75 s 还是 `Prompt executed in 301.75 seconds`，719 s 就变成
# `Prompt executed in 00:11:59`。只认秒数会让所有 ≥10 分钟的跑测（1920×1088、
# 10 s / 15 s 视频）取证**全部落空**，而且日志明明在、报出来却是「无匹配日志」。
RE_EXEC = re.compile(
    r"Prompt executed in (?:(\d+):(\d+):(\d+)|([\d.]+) seconds)")


def exec_sec(m):
    """把 `Prompt executed in …` 的两种格式统一成秒。"""
    h, mi, s, plain = m.groups()
    if plain is not None:
        return float(plain)
    return int(h) * 3600 + int(mi) * 60 + int(s)
# tqdm 进度条：[00:44<00:00,  7.43s/it] 与当前计数 N/M。
# ⚠️ 速率单位会变：慢的是 `s/it`（H3 / Music3），快到 1 step/s 以上时
# ComfyUI 的 tqdm 改用 `it/s`（Qwen-Image 0.4~0.9 s/步）。只认 `s/it`
# 会让整条出图线的采样段全部解析成 None。
# 反正只用 `elapsed`（进度条左侧的累计时间），速率字段只是用来匹配行尾。
RE_BAR = re.compile(r"(\d+)/(\d+) \[([\d:]+)<[\d:]+, +\s*([\d.]+)(?:s/it|it/s)\]")

# 卡身份 token -> 记录里 env.gpu 用的写法（做一致性核对）
# 注意：日志里的型号串是 `Intel(R) Arc(TM) Pro B70 Graphics`，
# 直接拿 "Intel Arc Pro B70" 去 in 会**永远匹配不上**（岔在 (R)/(TM) 上）。
# 所以两边都规范化成「只留字母数字」，再按下面的 token 匹配。
GPU_TOKENS = [
    ("prob70", "Intel Arc Pro B70"),
    ("prob65", "Intel Arc Pro B65"),
    ("prob60", "Intel Arc Pro B60"),
    ("prob50", "Intel Arc Pro B50"),
]


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def placeholder(path):
    """把日志路径归一成 `<标签>\\文件名`。

    依据：本仓库**不出现机器的绝对路径**。写回记录前必须过这一道，
    否则 `timing_breakdown.source` 会把机器路径重新带进仓库
    （2026-10-16 实测踩过：路径清洗之后跑一次取证回填，绝对路径全回来了）。
    """
    p = Path(path)
    best = None
    for root, label in LOG_ROOTS:
        try:
            rel = p.resolve().relative_to(Path(root).resolve())
        except (ValueError, OSError):
            continue
        if best is None or len(str(root)) > len(str(best[0])):
            best = (root, label, rel)
    if best is None:
        return "<日志目录>\\%s" % p.name
    _, label, rel = best
    return "<%s>\\%s" % (label, str(rel).replace("/", "\\"))


def card_token(device_str):
    """从日志的 Device 行认出是哪张卡。认不出返回 None。"""
    n = _norm(device_str)
    for tok, display in GPU_TOKENS:
        if tok in n:
            return tok, display
    return None, None


def hms_to_sec(s):
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def parse_segment(seg, dit_needle="MiniMaxH3"):
    """解析日志里的一段（= 一次执行）。"""
    out = {}

    # 进度条：按 (总数) 分组。
    # ⚠️ 一段里可能**不止一条**进度条——Music 3 每轮都同时有采样条（30 步，走完）
    # 和另一条 3001 的条（音频 token，只走到 300/795，走不完），而后者出现次数
    # 还更多（103 vs 31）。所以不能直接「取最频繁」，要**先筛出真正走完的**
    # （最后一格 == 总数），再在其中取最频繁。否则 music3 三组全部解析成 None。
    bars = {}
    for cur, tot, elapsed, rate in RE_BAR.findall(seg):
        bars.setdefault(int(tot), []).append((int(cur), hms_to_sec(elapsed), float(rate)))
    done = {k: v for k, v in bars.items() if max(c for c, _, _ in v) == k}
    if done:
        tot = max(done, key=lambda k: len(done[k]))
        # tqdm 会把末行 `100%|...| tot/tot` 打两遍，按 cur 去重后再算增量，
        # 否则轨迹尾部会多出一个 0。
        dedup = {}
        for cur, elapsed, rate in done[tot]:
            dedup[cur] = elapsed
        seq = sorted(dedup.items())
        out["steps"] = tot
        out["sampling_sec"] = seq[-1][1]
        out["sampling_sec_per_step"] = round(seq[-1][1] / tot, 2)
        out["step_sec_trace"] = [round(seq[0][1], 2)] + [
            round(seq[i][1] - seq[i - 1][1], 2) for i in range(1, len(seq))
        ]

    # 各模型组件的装载：`Requested to load <模型类名>` 之后的装载行。
    # 一段里可能请求多次，取最后一次（= 真正跑采样时的那次）。
    #
    # ⚠️ 为什么按类名分别记录而不只抽 DiT：**音乐域的容量账在 TE 上**——
    # Music 3 的文本编码器 int8 版 8.57 GiB、bf16 版 15.56 GiB，
    # 「装不装得下 / 要不要卸载」全看它。只记 DiT 会把这块证据丢掉。
    # 类名来自服务端日志（不是猜）：MiniMaxMusic3=DiT · MiniMaxMusic3TEModel=TE
    # · MiniMaxMusic3DAV=VAE。
    COMPONENT_PREFIX = {
        "MiniMaxMusic3TEModel": "te",# TE 要排在 DiT 之前匹配：
        "MiniMaxMusic3DAV": "dav",        # `MiniMaxMusic3` 是它两者的前缀，
        dit_needle: "dit",                # 正则会先命中短的那个。
    }
    for mm in re.finditer(
            r"Requested to load (%s)\s*\n\s*(.*)" % "|".join(
                re.escape(k) for k in sorted(COMPONENT_PREFIX, key=len,
                                             reverse=True)),
            seg):
        lm = RE_LOAD.search(mm.group(2))
        if not lm:
            continue
        key = COMPONENT_PREFIX.get(mm.group(1))
        if not key:
            continue
        mode, tail = lm.group(1), lm.group(2)
        off = re.search(r"([\d.]+) MB offloaded", tail)
        loaded = re.search(r"([\d.]+) MB loaded", tail)
        if key == "dit":
            out["dit_load_mode"] = mode
        out["%s_load_mode" % key] = mode
        out["%s_loaded_mb" % key] = int(float(loaded.group(1))) if loaded else None
        out["%s_offloaded_mb" % key] = int(float(off.group(1))) if off else 0

    return out


def parse_runs(path, dit_needle="MiniMaxH3"):
    """把一份服务器日志切成「每次执行」若干段。

    必须切：同一个日志里会跑多轮（如 clean / noprovider 各含 2 次执行，
    出图那边一套 sweep 里连着跑 22 轮），只取最后一次会与记录里的样本对不上——
    这正是它们最早被判成「无日志」的原因。
    """
    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    dev = RE_DEVICE.search(txt)
    vram = RE_VRAM.search(txt)
    common = {
        "path": str(path),
        "device": dev.group(1).strip() if dev else None,
        "total_vram_mb": int(vram.group(1)) if vram else None,
    }

    marks = list(RE_EXEC.finditer(txt))
    runs, prev = [], 0
    for m in marks:
        seg = txt[prev:m.start()]
        prev = m.end()
        r = dict(common)
        r["prompt_executed_sec"] = exec_sec(m)
        r.update(parse_segment(seg, dit_needle))
        runs.append(r)
    return runs


# 039 那批（2026-10-14/15）的 `batch_mark` 是 `None`（H-24 迁移器没写这一维），
# 所以 CARD_LOG_KEYS 那条路查不到。但**文件名里写着跑的是哪一组**，按后缀查。
# ⚠️ 长的放前面：`039cute4` 必须先于 `039cute` 命中，否则永远落到短键上。
# ⚠️ 同一组标记可能落在多个日志里（`039t212` 的 krea2/q21 在 v3、music3-int8 在 v4），
# 所以给的是**候选列表**，最终由 `Prompt executed` 对时决定用哪份。
FILENAME_LOG_KEYS = {
    "039cute4": ["039_cute4", "039_cute"],
    "039cute": ["039_cute", "039_cute4"],
    "039t212": ["039_v3", "039_v4"],
    "c3C": ["clean3_cute"],
    "c3S": ["clean3_sdpa"],
    # 10-14 那批跨了四个日志（v3/v4 是主批，clean2/clean3_sdpa 是后补的重测）
    "039": ["039_v3", "039_v4", "clean2_sdpa", "clean3_sdpa"],
    # 2026-10-21 B65 补测的五组（出图 bf16 / 出图 2048² / Krea-2 bf16 / Music 3 两档）
    "b65q21b16": ["sweepb65q21b16"],
    "b65q21r2k": ["sweepb65q21r2k"],
    "b65k2b16": ["sweepb65k2b16"],
    "b65m3f16": ["sweepb65m3f16"],
    "b65m3i8te8": ["sweepb65m3i8te8"],
}


def _suffix_keys(fn):
    """从记录文件名末尾取那一组标记 → 候选日志键。取不到返回 []。"""
    stem = fn.rsplit("-comfyui", 1)[0]
    for suf in sorted(FILENAME_LOG_KEYS, key=len, reverse=True):
        if stem.endswith("-" + suf):
            return FILENAME_LOG_KEYS[suf]
    return []


_OTHER_CARD_MARK = {"b50-32g": "b50", "b70-32g": "b70"}


def _filter_by_card(files, fn):
    """同目录里 `sweep` 这类键会 glob 到别的卡的日志（`server_sweep*.log` 同时命中
    `server_sweep_b50.log`）。按本记录文件名里的卡型把**别的卡**的日志剔掉。

    2026-10-17 实测踩过：一条 B70 的 bf16 记录被配到了 B50 的日志上，
    靠型号一致性校验报 MISMATCH 拦下 —— 但更该在这里就剔掉。
    """
    mine = next((m for m in _OTHER_CARD_MARK if m in fn), None)
    if not mine:
        return files
    others = {v for k, v in _OTHER_CARD_MARK.items() if k != mine}
    return [f for f in files
            if not any(("_" + o) in f.name for o in others)]


def find_log(rec, logdirs):
    """候选日志列表。文件名只是线索，配对靠 Prompt executed 对时（见 match_round）。"""
    fn = Path(rec.get("_path", "")).name
    if fn in LOG_OVERRIDES:
        p = Path(LOG_OVERRIDES[fn])
        return [p] if p.exists() else []
    key = rec["tag"]
    # 卡型优先：文件名里的 `b50-16g` / `b70-32g` × 量化档 × stack_variant
    for card_pat, table in CARD_LOG_KEYS.items():
        if card_pat in fn:
            env = rec.get("env", {})
            # 自由标记（batch_mark，如 m3i8 / r1536 / k2bf16）优先 —— 它才编码
            # 「这一组是哪一批」；没有才退回 stack_variant。
            variant = env.get("batch_mark") or env.get("stack_variant", "base")
            # ⚠️ **文件名后缀优先级最高**：039 那批的 `stack_variant` 都是 `int8fix`，
            # 而表里 `("int8_convrot","int8fix")` 恰好有条目（→ `sweep_int8fix`），
            # 放在后面就永远轮不到 —— 实测 int8 记录全挂、bf16 全过，就是这条链的锅。
            keys = _suffix_keys(fn) \
                or table.get((_quant_of(rec), variant), []) \
                or table.get((_quant_of(rec), env.get("stack_variant", "base")), [])
            found, seen = [], set()
            for d in logdirs:
                for k in keys:
                    # 这批的历史日志叫 `boot_039_*.log`，不是 `server_*` —— 两种前缀都试
                    for pre in ("server_", "boot_"):
                        for f in sorted(Path(d).glob("%s%s*.log" % (pre, k))):
                            # 🔴 glob 的前缀匹配会**过宽**：键 `sweepb60` 会把
                            # `server_sweepb60k2.log`（krea2 的日志）一起匹配进来，
                            # 于是 q21 的记录配到 krea2 的日志上（B60 实测踩过）。
                            # 判据：去掉 `前缀+键` 后，剩下的必须以 `_` 开头或为空 ——
                            # `server_sweepb60.log` → 剩 ""（算）；
                            # `server_sweepb60k2.log` → 剩 "k2"（不算）。
                            tail = f.stem[len(pre) + len(k):]
                            if tail and not tail.startswith("_"):
                                continue
                            if f not in seen:
                                seen.add(f)
                                found.append(f)
            return _filter_by_card(found, fn)
    # 候选键按「剥得越来越少」列全，别名表命中哪个都算。
    # 不能只剥域前缀——`comfyui-qwen-image-2.1-bf16` 剥掉域前缀只剩 `bf16`，
    # 把模型名也剥没了，别名就永远命中不了。
    cands = [key]
    if key.startswith("comfyui-"):
        cands.append(key[len("comfyui-"):])
    for pre in TAG_PREFIXES:
        if key.startswith(pre):
            cands.append(key[len(pre):])
            break
    keys = []
    for c in cands:
        keys.append(c)
        keys.extend(LOG_KEY_ALIASES.get(c, []))
    # 🔴 H3 视频组要单独重建键：记录 tag 是 `comfyui-h3-h3_864x480_b60`
    # （**下划线**分隔、卡型在**后**），而采集器写的日志是
    # `server_b60-h3-864x480.log`（**连字符**分隔、卡型在**前**）。
    # 两边格式对不上，直接 glob 永远配不到 —— 从 tag 里抽出卡型与分辨率重建。
    # 实测：不加这条时 B60 三条 H3 记录全部配到 0 个日志（而日志明明就在
    # `_bench_f/` 里躺着）。
    m = re.match(r"comfyui-h3-h3_(\d+x\d+)_(\S+)$", key)
    if m:
        keys.append("%s-h3-%s" % (m.group(2), m.group(1)))
    seen, out = set(), []
    for d in logdirs:
        for k in keys:
            for pat in ("server_%s*_r*.log" % k, "server_%s*.log" % k):
                for f in sorted(Path(d).glob(pat)):
                    # 与上面同一道边界：`b60-h3-864x480` 不该把
                    # `b60-h3-864x4800.log` 之类的也捞进来。
                    tail = f.stem[len("server_") + len(k):]
                    if tail and not tail.startswith("_") and not tail.startswith("-r"):
                        continue
                    if f not in seen:
                        seen.add(f)
                        out.append(f)
    return _filter_by_card(out, fn)


def match_round(log_parsed, rec):
    """日志的执行时长要能对上某个样本。

    优先用样本里的 `log_prompt_executed_s`（采集时就从同一份日志上量到的
    `Prompt executed` 值）——那是**精确配对**，不受容差影响：出图那套
    22 轮里有若干轮时长只差 0.07 s，用 ±1 s 容差会把两轮折成一轮。
    没有该字段时退回 `server_sec` ± TOL_SEC。

    ⚠️ **H3 视频组两条路都对不上**（2026-10-17 实测）：
    日志的 `Prompt executed in 65.17 seconds` vs 采集器量的 `server_sec=1268.67`
    —— 差 **1203 s**。原因是 ComfyUI 报的 `Prompt executed` 只算**节点执行**，
    不含客户端提交→服务端起跑→回传之间的等待；而 H3 的采样本身就很慢
    （179.82 s/步 × 6 步 = 1079 s），两者的口径根本不是一回事。
    → **第三道匹配：按采样段耗时 `sampling_sec` 配**（它也写在日志里，
    与该轮同源，且比`server_sec` 更接近真实计算量）。
    """
    if log_parsed.get("prompt_executed_sec") is None:
        return None
    t = log_parsed["prompt_executed_sec"]

    # H3 视频组：`Prompt executed` 与 server_sec 不同口径 →
    # 改用采样段耗时配对（同一份日志里 parse 出��，唯一性够）。
    samp = log_parsed.get("sampling_sec")
    if samp:
        for s in rec.get("samples", []):
            got = s.get("sampling_sec") or s.get("observed_sampling_sec")
            if got and abs(float(got) - float(samp)) <= max(5.0, samp * 0.02):
                return s
        # 记录里没有采样段字段时，退回「该轮是唯一一轮且它 ok」这种宽松配对 ——
        # 只在**日志只有一轮**时用，多轮时宁可匹配不上也不猜。
        if len(log_parsed.get("_all_runs", [1])) == 1:
            cands = [s for s in rec.get("samples", [])
                     if s.get("ok") and s.get("mode") == "cold"]
            if len(cands) == 1:
                return cands[0]
    for s in rec.get("samples", []):
        if s.get("log_prompt_executed_s") is not None:
            if abs(s["log_prompt_executed_s"] - t) <= 0.05:
                return s
    for s in rec.get("samples", []):
        if not s.get("server_sec"):
            continue
        if abs(s["server_sec"] - t) <= TOL_SEC:
            return s
    return None


def one_breakdown(ev):
    """把一轮日志的证据整理成 timing_breakdown。"""
    tb = {
        "source": placeholder(ev["path"]),
        "prompt_executed_sec": ev.get("prompt_executed_sec"),
        "matched_sample": ev.get("matched_sample"),
    }
    # ⚠️ **逐组件搬运，不能只搬 DiT**（2026-10-17 实测踩过）：
    # 解析层已经按类名抽出 te_/dav_ 字段，但这里若只显式搬 dit_*，
    # 新字段就会被静默丢掉（表现是「解析对了、落盘是 None」）。
    # 规则：凡解析层产出 `*_load_mode` / `*_loaded_mb` / `*_offloaded_mb`，
    # 就在这里成组搬运，**新增组件只改解析层的表，不用再改这里**。
    for comp in ("dit", "te", "dav"):
        if ev.get("%s_load_mode" % comp):
            tb["%s_load_mode" % comp] = ev["%s_load_mode" % comp]
            tb["%s_loaded_mb" % comp] = ev.get("%s_loaded_mb" % comp)
            tb["%s_offloaded_mb" % comp] = ev.get("%s_offloaded_mb" % comp)
    if ev.get("sampling_sec") is not None:
        tb["steps"] = ev["steps"]
        tb["step_sec_trace"] = ev.get("step_sec_trace")
        tb["sampling_sec"] = ev["sampling_sec"]
        tb["sampling_sec_per_step"] = ev["sampling_sec_per_step"]
        # ⚠️ **基数必须用样本的 `server_sec`（端到端），不能用 `prompt_executed_sec`**
        # （2026-10-17 踩过，产出过 `fixed_overhead_sec = -1012.8`、`share = 1654%`）：
        # ComfyUI 的 `Prompt executed` 只算**节点执行**，H3 视频组实测
        # `Prompt executed 65.17 s` vs 端到端 `server_sec 1268.67 s` ——差 20 倍。
        # 「固定开销」的定义是「端到端里不采样的那部分」，所以基数只能是端到端。
        base = (ev.get("matched_sample") or {}).get("server_sec")
        if base and base > ev["sampling_sec"]:
            tb["fixed_overhead_sec"] = round(base - ev["sampling_sec"], 1)
            tb["sampling_share_pct"] = round(
                100.0 * ev["sampling_sec"] / base, 1)
            # 记下这个基数，免得下次又要重新推一遍口径
            tb["overhead_base"] = "samples.server_sec (端到端)"
        elif ev.get("prompt_executed_sec") and \
                ev["prompt_executed_sec"] > ev["sampling_sec"]:
            # 兜底：出图/音乐组两者口径一致时仍可用（旧数据如此）
            tb["fixed_overhead_sec"] = round(
                ev["prompt_executed_sec"] - ev["sampling_sec"], 1)
            tb["sampling_share_pct"] = round(
                100.0 * ev["sampling_sec"] / ev["prompt_executed_sec"], 1)
            tb["overhead_base"] = "log.prompt_executed_sec"
        else:
            # 口径不一致且无法给出有意义的固定开销 → **不写这两个字段**，
            # 不产出负数 / 超过 100% 的假指标。
            tb["fixed_overhead_sec"] = None
            tb["sampling_share_pct"] = None
            tb["overhead_note"] = (
                "不可算：样本 server_sec(%s) ≤ 采样段(%s) 或缺失，"
                "两个口径不同源" % (base, ev["sampling_sec"]))
    return tb


def write_json(path, obj):
    """写回记录，**保留原文件行尾**。

    🔴 `Path.write_text()` 在 Windows 上会把每个 `\\n` 翻成 `\\r\\n`
    （默认 `newline=None`）—— 2026-10-21 实测：只跑一次取证，
    20 个原本纯 LF 的 `bench/data/*.json` 整篇变成 553 行「全删全加」，
    `git diff` 一片红。`.gitattributes` 是 `* -text`，行尾原样进库，
    所以这里必须按原文件自己的行尾写回。
    """
    p = Path(path)
    raw = p.read_bytes()
    text = json.dumps(obj, ensure_ascii=False, indent=2)   # 无尾换行
    if b"\r\n" in raw:
        data = text.replace("\n", "\r\n").encode("utf-8")
    else:
        data = text.encode("utf-8")
    p.write_bytes(data)


def annotate(rec_path, logdirs, dry_run=False):
    rec = json.loads(Path(rec_path).read_text(encoding="utf-8"))
    if rec.get("schema") != "comfyui-xpu-bench/1":
        return None
    rec["_path"] = str(rec_path)

    needle = DIT_NEEDLE.get(rec.get("workload", {}).get("model"), "MiniMaxH3")
    hits, used = [], set()
    for f in find_log(rec, logdirs):
        try:
            runs = parse_runs(f, needle)
        except OSError:
            continue
        for p in runs:
            s = match_round(p, rec)
            if s is None:
                continue
            # 同一轮（= 日志里的一条 `Prompt executed`）只认一次。
            # 判据用日志那条自己的时长，**不要用样本的 server_sec**——
            # 出图那套里有相邻两轮的 server_sec 只差 0.07 s，用样本值当签名
            # 会把两条日志轮折成一条（实测 krea2 少记 1 轮、q21 少记 2 轮）。
            sig = round(p["prompt_executed_sec"], 2)
            if sig in used:
                continue
            used.add(sig)
            ms = {"steps": s.get("steps"), "round": s.get("round"),
                  "server_sec": s.get("server_sec")}
            if s.get("role"):                      # 出图/音乐组按角色分，H3 组没有
                ms["role"] = s["role"]
            p["matched_sample"] = ms
            hits.append(p)

    if not hits:
        # 找不到日志时**不能就地把状态丢掉**：迁移器写进来的 `pending` 会一直挂着，
        # 读者看到「待回填」会以为补测一下就有，实际是日志早被后续批次覆盖了。
        # 判据：这条记录**确有跑成功的轮次**（`ok` 且带 `server_sec`）→ 本该有日志
        # → 记 `missing` 并说明「在本轮给出的目录里找不到」。
        # 一轮都没成功的记录不动它：那种记录没有时间分解本来就是对的。
        rec.pop("_path", None)
        ok_rounds = [s for s in (rec.get("samples") or [])
                     if s.get("ok") and s.get("server_sec")]
        prev = rec.get("log_evidence")
        prev_status = prev.get("status") if isinstance(prev, dict) else None
        if ok_rounds and prev_status != "annotated":
            if not dry_run:
                rec["log_evidence"] = {
                    "status": "missing",
                    "note": ("在本次给出的 %d 个日志目录里找不到与本记录样本 "
                             "`server_sec` 对得上的日志（%d 轮成功跑完，本该有日志）。"
                             "常见原因是该批日志被后续批次同名覆盖；"
                             "**因此本记录的时间分解不可用，不假装取证做过。**"
                             % (len(logdirs), len(ok_rounds))),
                }
                write_json(rec_path, rec)
            return {"status": "no_log", "wrote": "missing"}
        return {"status": "no_log"}

    env = rec.setdefault("env", {})
    conf = env.setdefault("env_confidence", {})

    # 1) 卡型号一致性核对——不一致就是数据事故，必须喊出来
    expect = env.get("gpu", "")
    found = set()
    for ev in hits:
        tok, display = card_token(ev.get("device"))
        if tok:
            found.add((tok, display))
            if expect and _norm(display) not in _norm(expect):
                return {"status": "MISMATCH", "device": display, "recorded": expect}
    if found:
        for fld in ("chip", "subsys", "device_id", "board_vendor", "board_code"):
            if fld in env and conf.get(fld) == "inferred":
                conf[fld] = "recorded"
        # 记下是哪一行日志给的证据
        dev_lines = sorted({"%s 出现在 %s" % (e.get("device"), placeholder(e["path"]))
                            for e in hits if e.get("device")})
        env["env_evidence"] = (
            "AIB 身份由服务器日志的 `Device: xpu:0 ...` 行直接证明：" +
            "；".join(dev_lines) +
            "。这四字段原为按注册表 PCI 枚举推断（backfill_aib.py），"
            "今有运行日志佐证，故 env_confidence 升为 recorded。"
        )

    # 2) 时间分解（多轮则记成表，键 = steps/r 组合）
    tbs = [one_breakdown(ev) for ev in hits]
    if len(tbs) == 1:
        rec["timing_breakdown"] = tbs[0]
    else:
        # 🔴 **合并，不要整块覆盖。** 迁移器写进去的 `timing_breakdown` 可能带
        # `one_breakdown` 等更细的组件分解；直接赋一个新 dict 会把它们抹掉
        # （2026-10-21 实测：只补取证，10-14 那批记录短了 2.6 KB，全是丢的组件账）。
        # 本次算出来的只有 `note` + `runs` 两项，其余键原样留着。
        new_tb = {
            "note": "按样本分列（同一组内不同步数/轮次）",
            "runs": tbs,
        }
        old_tb = rec.get("timing_breakdown")
        if isinstance(old_tb, dict):
            new_tb = {**old_tb, **new_tb}
        rec["timing_breakdown"] = new_tb

    # ⚠️ **必须是 dict，不是裸字符串**：迁移器（`migrate_comfy.py` /
    # `migrate_upgrade_ab.py`）写的是 `{"status": …}`，这里若写字符串，
    # 同一字段在全库就有两种形态 —— 消费方按 `le.get("status")` 读会
    # `AttributeError: 'str' object has no attribute 'get'`（2026-10-19 踩过）。
    rec["log_evidence"] = {
        "status": "annotated",
        "note": (
            "本记录的时间分解与卡型号由 %d 条服务器日志取证（%s）：每条日志的 "
            "`Prompt executed in X seconds` 均与对应样本的 server_sec 在 %.1fs 容差内对上，"
            "确认是同一轮；日志中的 `Device: xpu:0 ...` 行是卡型号的直接证据。" % (
                len(hits),
                "; ".join(sorted({placeholder(e["path"]) for e in hits})), TOL_SEC)
        ),
    }

    rec.pop("_path", None)
    if not dry_run:
        write_json(rec_path, rec)
    return {"status": "annotated", "n": len(hits), "tbs": tbs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="bench/data 目录")
    ap.add_argument("--logdir", action="append", required=True,
                    help="服务器日志目录，可给多个。支持 `标签=路径`；"
                         "标签用于写回记录时的路径占位符（默认「日志目录」）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    dirs, LOG_ROOTS[:] = [], []
    for raw in a.logdir:
        # `标签=路径` —— 只在第一个 `=` 处切；Windows 路径里的 `:` 不受影响。
        if "=" in raw:
            label, path = raw.split("=", 1)
            label, path = label.strip(), path.strip()
        else:
            label, path = "日志目录", raw
        dirs.append(path)
        LOG_ROOTS.append((path, label))
    # 先匹配最长的根目录，避免嵌套目录被短的那个抢走
    LOG_ROOTS.sort(key=lambda kv: len(str(kv[0])), reverse=True)

    # ⚠️ **不要只按 `*comfyui*.json` 找文件**（2026-10-17 修）：
    # 视频域 `migrate_comfy.py` 产出的文件名是 `<日期>_h3_<WxH>_<mark>.json`，
    # **不含 "comfyui"** → 这批 H3 记录从来没被取证遍历到（长期漏网）。
    # 正确判据是**内容**：schema 是不是 comfyui-xpu-bench/1。
    files = sorted(p for p in Path(a.data).glob("*.json"))
    files = [p for p in files
             if json.loads(p.read_text(encoding="utf-8")).get("schema")
             == "comfyui-xpu-bench/1"]
    if not files:
        print("[ERR] %s 下没有 comfyui 记录" % a.data)
        return 1

    n_ok = n_no = n_bad = 0
    for f in files:
        r = annotate(f, dirs, dry_run=a.dry_run)
        if r is None:
            continue
        if r["status"] == "no_log":
            n_no += 1
            print("  [--] %-46s 无匹配日志（留原状）" % f.name)
        elif r["status"] == "MISMATCH":
            n_bad += 1
            print("  [!!] %-46s 型号冲突！日志=%s 记录=%s" % (f.name, r["device"], r["recorded"]))
        else:
            n_ok += 1
            print("  [OK] %-46s %d 轮取证" % (f.name, r["n"]))
            for tb in r["tbs"]:
                ms = tb["matched_sample"]
                print("        %-9s %-3s步 | %-9s | 采样 %5ss (%.2f s/步) | 固定 %6ss | 卸载 %s MB" % (
                    ms.get("role") or ("r%s" % ms.get("round")), tb.get("steps"),
                    tb.get("dit_load_mode", "?"), tb.get("sampling_sec"),
                    tb.get("sampling_sec_per_step") or 0,
                    tb.get("fixed_overhead_sec"), tb.get("dit_offloaded_mb")))

    print("\n取证回填：%d 条成功 · %d 条无日志 · %d 条型号冲突%s"
          % (n_ok, n_no, n_bad, "（dry-run，未写盘）" if a.dry_run else ""))
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
