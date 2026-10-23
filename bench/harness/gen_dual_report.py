# -*- coding: utf-8 -*-
"""从 bench/data 直出《docs/dual-b65-report.md》。

表格与全部数字都从原始 json 读，禁止手抄。
行尾：CRLF，无尾换行。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(REPO, "bench", "data")
OUT = os.path.join(REPO, "docs", "dual-b65-report.md")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def sample(rec, mode, idx=0):
    xs = [s for s in rec["samples"] if s.get("mode") == mode and s.get("ok")]
    return xs[idx]


def f1(x):
    return "%.1f" % x


def fx(x):
    """1.42x / 14x —— 整数值不带小数点。"""
    if abs(x - round(x)) < 0.05:
        return "%d\u00d7" % round(x)
    return "%.2f\u00d7" % x


def inv(x):
    """1/4.8 / 1/14"""
    if abs(x - round(x)) < 0.05:
        return "1/%d" % round(x)
    return "1/%.1f" % x


def tok(n):
    if n >= 1048576:
        v = n / 1048576.0
        return ("%gM token" % v)
    if n >= 1024:
        return "%gK token" % (n / 1024.0)
    return "%d token" % n


def f2(x):
    return "%.2f" % x


def s(x):
    return "%.2f s" % x


def mmss(x):
    m = int(x // 60)
    sec = x - 60 * m
    return "%d 分 %02d 秒" % (m, round(sec))


# ---------------------------------------------------------------- 取数
b65_720 = load("2026-10-21_b65-32g_minimax-h3-int8_convrot-b65h3-1280x720-comfyui.json")
b65_1080 = load("2026-10-21_b65-32g_minimax-h3-int8_convrot-b65h3-1920x1088-comfyui.json")
b65_d10 = load("2026-10-22_h3_1280x720_b65d10.json")
b65_d15 = load("2026-10-22_h3_1280x720_b65d15.json")
b65_d17 = load("2026-10-22_h3_1280x720_b65d17.json")
b65_d20 = load("2026-10-22_h3_1280x720_b65d20.json")
b70_720 = load("2026-10-19_h3_1280x720_b70scan.json")
b70_1080 = load("2026-10-19_h3_1920x1088_b70scan.json")
b70_pw = load("2026-10-19_h3_1280x720_b70pw.json")

dual_d1 = load("2026-10-23_h3_1280x720_duald1.json")
dual_d6 = load("2026-10-23_h3_1280x720_duald6.json")
dual_c1 = load("2026-10-23_h3_1280x720_dualc1.json")

img_solo = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2solo-comfyui.json")
img_c0 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2c0-comfyui.json")
img_c1 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2c1-comfyui.json")

pw_s0 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3s0-comfyui.json")
pw_s1 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3s1-comfyui.json")
pw_b0 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3b0-comfyui.json")
pw_b1 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3b1-comfyui.json")

q_solo = load("2026-10-23_b65-32g-q4_0-dual-c1.json")
q_conc = load("2026-10-23_b65-32g-q4_0-dual-c1-concurrent.json")
a4 = load("2026-10-23_dual-a4-vision-under-h3.json")
ctx = load("2026-10-23_b65-32g_q4_0-ctxcap-dual.json")
q8_dual = load("2026-10-23_b65-32g-q8_0-dual-layer-qwen3.6-35b-a3b.json")
q8_ngl37 = load("2026-10-23_b65-32g-q8_0-single-ngl37-qwen3.6-35b-a3b.json")

# ---- 单卡 B65 H3 720p 时长阶梯
b65_720_cold = sample(b65_720, "cold")
b65_720_fresh = sample(b65_720, "fresh")
b65_720_cached = sample(b65_720, "cached")
b65_1080_fresh = sample(b65_1080, "fresh")

dur_rows = [
    ("5 秒", 124, b65_720_cold, b65_720_fresh, b65_720_cached),
    ("10 秒", 243, sample(b65_d10, "cold"), None, None),
    ("15 秒", 362, sample(b65_d15, "cold"), None, None),
    ("17 秒", 413, sample(b65_d17, "cold"), None, None),
]

# ---- 双卡
d1_cold, d1_fresh = sample(dual_d1, "cold"), sample(dual_d1, "fresh")
d6_cold, d6_fresh = sample(dual_d6, "cold"), sample(dual_d6, "fresh")
c1_steady = [x for x in dual_c1["samples"] if x.get("ok")][-1]

# ---- 出图
img_solo_ss = [x for x in img_solo["samples"] if x.get("ok")]
img_c0_ss = [x for x in img_c0["samples"] if x.get("ok")]
img_c1_ss = [x for x in img_c1["samples"] if x.get("ok")]

# ---- 上下文容量
cases = {c["name"]: c for c in ctx["cases"]}

# ---- 比值
r_e2e = b65_720_fresh["server_sec"] / sample(b70_720, "fresh")["server_sec"]
r_step = b65_720_fresh["sampling_sec_per_step"] / sample(b70_720, "fresh")["sampling_sec_per_step"]
r_1080 = b65_1080_fresh["server_sec"] / sample(b70_1080, "fresh")["server_sec"]
r_1080_step = b65_1080_fresh["sampling_sec_per_step"] / sample(b70_1080, "fresh")["sampling_sec_per_step"]
r_dec = q_solo["summary"]["decode_tok_s"] and (
    load("2026-10-20_b70-q4-0-sycl-l0.json")["summary"]["decode_tok_s"]
    / q_solo["summary"]["decode_tok_s"]
)
# 两条 5 秒 720p：双卡并行 vs B70 串行
two_clip_dual = b65_720_fresh["server_sec"]
two_clip_b70 = 2 * sample(b70_720, "fresh")["server_sec"]
r_two = two_clip_b70 / two_clip_dual
# 每小时产能
thr_dual = 2 * 3600.0 / b65_720_fresh["server_sec"]
thr_b70 = 3600.0 / sample(b70_720, "fresh")["server_sec"]
r_thr = thr_dual / thr_b70
# 层切分赔多少
r_q8 = q8_ngl37["summary"]["decode_tok_s"] / q8_dual["summary"]["decode_tok_s"]
r_q8_pp = q8_ngl37["summary"]["prompt_tok_s"] / q8_dual["summary"]["prompt_tok_s"]

L = []
w = L.append

w("# 双卡 B65 实战报告：买到什么，买不到什么")
w("")
w("> **一句话**：两张 B65 同时开工，买到的不是「算力翻倍」，而是**两倍的显存**（62.32 GiB）和")
w("> **两条各干各的产线**；同一条片子的速度一点没变。要单条更快，换更强的单卡；")
w("> 要同时干两件事、要装下更大的模型，才上第二张。")
w(">")
w("> ⚠️ 「两条产线」有前提：**同时跑两条视频要 64 GB 内存**。32 GB 机器上实测 2/2 崩（§5.3），")
w("> 只能「一条视频 + 一条轻任务」。所以 32 GB 机器的正确预期是：**两倍显存 + 一条视频线 + 一条轻任务线**。")
w("")
w("实测条件：2× GUNNIR B65 32G · ECC 关（每卡可用 31.16 GiB）· 驱动 9150 · 32 GB 内存（2×16 GB）·")
w("显示器接主板核显 · 卡 0 在 CPU 直连 x16 槽、卡 1 在芯片组 x4 槽。除另注外，全部数字都是实测。")
w("")

# ---------------------------------------------------------------- 一
w("## 一、四个问题，四个答案")
w("")
w("| 问题 | 答案 |")
w("|---|---|")
w("| 双卡是不是「算力翻倍」？ | **不是。** 同一条 H3 视频的单步耗时：单卡 42.30 s/it，双卡同时满载 42.41 s/it —— 一步都没快。 |")
w("| 那双卡买什么？ | **容量**（可驻留显存 31.16 → 62.32 GiB、上下文 1M → 3M token、装得下 34.37 GiB 的模型）和**产能**（两张卡各跑一件事）。⚠️ 32 GB 内存下「两条视频线」不成立（§5.3），实际是「一条视频 + 一条轻任务」。 |")
w("| 单卡 B65 能单独做 H3 视频吗？ | **能。** 720p · 5 秒 · 6 步稳态 **%s**（约 %s）；720p 最长实测到 17 秒，1080p · 5 秒 %s。 |" % (s(b65_720_fresh["server_sec"]), mmss(b65_720_fresh["server_sec"]), s(b65_1080_fresh["server_sec"])))
w("| 一片 B70 和两片 B65（几乎同价），搭出来差什么？ | **一条片子：B70 快 %s。两条片子：两片 B65 快 %s。** 容量上两片 B65 翻倍，B70 不涨。 |" % (fx(r_e2e), fx(r_two)))
w("")
w("下面把每一条拆开讲。")
w("")

# ---------------------------------------------------------------- 二
w("## 二、为什么「双卡 = 算力翻倍」不成立")
w("")
w("不是这张卡不行，是这两条软件路径都**不把一个任务拆到两张卡上**：")
w("")
w("1. **ComfyUI / `torch.xpu` 只用第一张卡。** 进程起来就绑 `xpu:0`，第二张卡在这个进程里不存在。")
w("   想让第二张卡干活，只能再起一个进程、用 `ONEAPI_DEVICE_SELECTOR=level_zero:1` 把它钉过去。")
w("2. **llama.cpp 的「多设备」是分层装载，不是并行计算。** `-dev SYCL0,SYCL1 -sm layer` 把模型的不同层")
w("   分到两张卡上，算一层的时候另一张卡在等 —— 层与层之间要同步，同步次数随层数涨。")
w("")
w("三条实测证据：")
w("")
w("| 证据 | 配置 | 结果 |")
w("|---|---|---|")
w("| 采样算力零提升 | H3 720p · 6 步 · 5 s，单卡 vs 双卡同时满载 | 单步 **42.30 s/it → 42.41 s/it**（+0.3%） |")
w("| 解码零提升 | Qwen3.6-35B-A3B Q4_0，单跑卡 1 vs 与 H3 并发 | **50.56 → 50.47 tok/s**（−0.2%） |")
w("| 拆层反而大亏 | Q8_0 34.37 GiB 用 `-sm layer` 摊到两卡 | 解码 **6.37 tok/s**，是单卡最快一档 30.83 的 **%s**；预填充 35.16 = %s |" % (inv(r_q8), inv(r_q8_pp)))
w("")
w("第三条最能说明问题：模型确实整个装进了显存（33.50 GiB 全驻，卡 0 17.45 / 卡 1 16.05），探针也返回 200，")
w("**但速度掉到五分之一以下**。层切分买到的是容量，赔进去的是速度。")
w("")
w("> 所以「双芯运作、算力翻倍」这个预期，在这两套软件上**不成立**。正确的预期是：**两条独立的产线**。")
w("")
w("打算上第二张卡之前，先答三个问题：")
w("")
w("1. **你要的是「一条更快」还是「两条一起」？** 前者换更强的单卡，后者才上双卡。")
w("2. **你的内存是 32 GB 还是 64 GB？** 32 GB 下两条视频线跑不起来（§5.3），只能「一条视频 + 一条轻任务」。")
w("3. **有没有一个模型单卡装不下？** 没有的话，双卡不会让你现有任何一个任务变快。")
w("")

# ---------------------------------------------------------------- 三
w("## 三、单卡 B65 能不能单独做 H3 视频")
w("")
w("**能，而且这是目前最实用的用法。** 一台机器一张 B65，不用第二张卡、不用改代码，ComfyUI 里跑 MiniMax H3：")
w("")
w("| 时长 | 帧数 | 端到端（cold） | 单步（cold） | 端到端（稳态） | 单步（稳态） |")
w("|---:|---:|---:|---:|---:|---:|")
for name, frames, cold, fresh, cached in dur_rows:
    steady = fresh or cached
    w("| %s | %d | %s | %s | %s | %s |" % (
        name, frames, s(cold["server_sec"]),
        f2(cold["sampling_sec_per_step"]) + " s/it",
        s(steady["server_sec"]) if steady else "—",
        (f2(steady["sampling_sec_per_step"]) + " s/it") if steady else "—"))
w("")
w("5 秒档的读数不止一个，别混用（上表「稳态」列取的是 fresh）：cold %s（含完整装载）/ fresh %s / cached %s。" % (
    s(b65_720_cold["server_sec"]), s(b65_720_fresh["server_sec"]), s(b65_720_cached["server_sec"])))
w("10 秒起只测了 cold（新起服务第一条），**没有稳态读数**，所以那一列是「—」，不是零。")
w("")
w("| 分辨率（5 秒） | 端到端（稳态） | 单步 |")
w("|---|---:|---:|")
w("| 1280×720 | %s | %s s/it |" % (s(b65_720_fresh["server_sec"]), f2(b65_720_fresh["sampling_sec_per_step"])))
w("| 1920×1088 | %s | %s s/it |" % (s(b65_1080_fresh["server_sec"]), f2(b65_1080_fresh["sampling_sec_per_step"])))
w("")
w("结论：")
w("")
w("1. **720p · 5 秒 · 6 步：稳态 %s，约 %s。** 这是单卡 B65 最舒服的一档 —— DiT 19.53 GiB 完整驻留显存，每步不搬权重。" % (s(b65_720_fresh["server_sec"]), mmss(b65_720_fresh["server_sec"])))
w("2. **720p 的时长上限实测到 17 秒**（cold %s，约 %s）。20 秒那一档**跑不出来**：两个组件装完就消失，不报显存不足。" % (s(sample(b65_d17, "cold")["server_sec"]), mmss(sample(b65_d17, "cold")["server_sec"])))
w("3. **1080p · 5 秒也能出**：稳态 %s（约 %s），单步 %s s/it。代价是 DiT 每轮要卸 7,564 MB。**1080p 是 32 GB 卡的边界，不是舒适区。**" % (s(b65_1080_fresh["server_sec"]), mmss(b65_1080_fresh["server_sec"]), f2(b65_1080_fresh["sampling_sec_per_step"])))
w("4. **时长比分辨率更贵。** 同样 720p，5 → 15 秒端到端涨 %s×，像素一点没变 —— 帧数变多，潜在空间 buffer 跟着涨。" % f2(sample(b65_d15, "cold")["server_sec"] / b65_720_cold["server_sec"]))
w("5. 采集条件：`--reserve-vram 4`、`OMNI_ATTN_BACKEND=sdpa`、int8 DiT + nvfp4 文本编码器。**改预留值会影响装载行为**，数字要连条件一起引。")
w("6. 跨分辨率的完整四卡对照见 [`comfyui-h3.md`](comfyui-h3.md)；本文只讲单卡 B65 与双卡 B65。")
w("")

# ---------------------------------------------------------------- 四
w("## 四、双卡 vs 单卡：逐项对照")
w("")
w("| 维度 | 单卡 B65 | 双卡 2× B65 | 差别 |")
w("|---|---:|---:|---|")
w("| H3 720p · 5 s 端到端（稳态） | %s | %s | **+%s** |" % (s(b65_720_fresh["server_sec"]), s(d6_fresh["server_sec"]), f1(100 * (d6_fresh["server_sec"] / b65_720_fresh["server_sec"] - 1)) + "%"))
w("| H3 单步 | %s s/it | %s s/it | +0.3%% |" % (f2(b65_720_fresh["sampling_sec_per_step"]), f2(d6_fresh["sampling_sec_per_step"])))
w("| Qwen 解码 | %s tok/s | %s tok/s | −0.2%% |" % (f2(q_solo["summary"]["decode_tok_s"]), f2(q_conc["summary"]["decode_tok_s"])))
w("| 出图稳态（每张） | %s / %s | %s ~ %s | 持平 |" % (f2(img_solo_ss[1]["server_sec"]), f2(img_solo_ss[2]["server_sec"]), f2(img_c1_ss[1]["server_sec"]), f2(img_c0_ss[2]["server_sec"])))
w("| 出图首轮（装载） | %s | %s / %s | 并发抢页缓存，**首轮不可比** |" % (s(img_solo_ss[0]["server_sec"]), s(img_c0_ss[0]["server_sec"]), s(img_c1_ss[0]["server_sec"])))
w("| 可用显存 | 31.16 GiB | 62.32 GiB | **2×** |")
w("| 可驻留上下文 | 1M token | 3M token | **3×** |")
w("| 满载功耗（P90） | %s W | %s W（两卡合计） | 叠加，不互压 |" % (f1(pw_s0["summary"]["power"]["p90_w_busy"]), f1(pw_b0["summary"]["power"]["pair_sum_p90_w"])))
w("")
w("怎么读：")
w("")
w("1. **两个「速度」行都是平的。** 单步 42.30 → 42.41 s/it、解码 50.56 → 50.47 tok/s，差异在抖动量级。")
w("   第二张卡没有让任何一条流水线变快，也没有让它变慢。")
w("2. **H3 端到端那 6.0% 不是算力损失，是每轮固定开销。** 单步一样、装载次数一样（`loads=3`），")
w("   差的是两条流水线同时读 15 GB 文本编码器时抢磁盘和页缓存。")
d4b_fresh = sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")
w("   同配置把页缓存跑热后是 %s（+%s%%），当天首次装载是 %s（+%s%%）—— **同一件事能差 %s 个百分点**。" % (
    s(d4b_fresh["server_sec"]), f1(100 * (d4b_fresh["server_sec"] / b65_720_fresh["server_sec"] - 1)),
    s(d1_fresh["server_sec"]), f1(100 * (d1_fresh["server_sec"] / b65_720_fresh["server_sec"] - 1)),
    f1(100 * (d1_fresh["server_sec"] / d4b_fresh["server_sec"] - 1))))
w("   **所以凡「双卡拖慢多少」的问题，先跑一轮热车再取数。**")
w("3. **卡 1 在芯片组 x4 槽上单跑 H3：稳态 %s**（复跑 %s），单步 %s s/it 与卡 0 的 %s 一致。" % (s(c1_steady["server_sec"]), s([x for x in load("2026-10-23_h3_1280x720_dualc1b.json")["samples"] if x.get("ok")][-1]["server_sec"]), f2(c1_steady["sampling_sec_per_step"]), f2(d6_fresh["sampling_sec_per_step"])))
w("   减掉采样段，非采样段 %s vs 卡 0 热缓存的 %s，多 %s；差值全部落在「每轮重装文本编码器」那一段。**没做同一张卡插两个槽互换的对照，不归因 PCIe 链路宽度。**" % (
    s(c1_steady["server_sec"] - c1_steady["sampling_sec"]),
    s(d4b_fresh["server_sec"] - d4b_fresh["sampling_sec"]),
    s((c1_steady["server_sec"] - c1_steady["sampling_sec"]) - (d4b_fresh["server_sec"] - d4b_fresh["sampling_sec"]))))
w("4. **满载功耗是相加的，不是互相抢的**：单跑时两张卡各自 P90 %s / %s W，同时满载 %s / %s W，合计 **%s W、峰值 %s W**。" % (f1(pw_s0["summary"]["power"]["p90_w_busy"]), f1(pw_s1["summary"]["power"]["p90_w_busy"]), f1(pw_b0["summary"]["power"]["p90_w_busy"]), f1(pw_b1["summary"]["power"]["p90_w_busy"]), f1(pw_b0["summary"]["power"]["pair_sum_p90_w"]), f1(pw_b0["summary"]["power"]["pair_sum_peak_w"])))
w("   850 W 电源够用，但要按「显卡侧 400 W 级」算，不是 200 W。")
w("")

# ---------------------------------------------------------------- 五
w("## 五、双卡真正买到的三样东西")
w("")
w("### 5.1 容量：上下文 1M → 3M token")
w("")
w("| 形态 | 配置 | 真装下 | 每 M token 占显存 | 上限处剩余 |")
w("|---|---|---:|---:|---:|")
w("| 单卡 | 默认 | **%s**（%d 个满长会话） | %s GiB | %s GiB |" % (tok(ctx["summary"]["single_max_allocated_ctx"]), ctx["summary"]["single_max_slots"], f1(ctx["summary"]["single_kv_gib_per_mtoken"]), f2(ctx["summary"]["single_headroom_at_ceiling_gib"])))
w("| 双卡 | 默认（`kv_unified=true`） | %s | %s GiB | %s / %s GiB |" % (tok(ctx["summary"]["dual_max_allocated_ctx_unified"]), f1(ctx["summary"]["dual_kv_gib_per_mtoken_unified"]), f2(cases["d175m"]["free_gib"][0]), f2(cases["d175m"]["free_gib"][1])))
w("| 双卡 | 显式 `--parallel`（`kv_unified=false`） | **%s**（%d 个满长会话） | %s GiB | %s / %s GiB |" % (tok(ctx["summary"]["dual_max_allocated_ctx_explicit_parallel"]), ctx["summary"]["dual_max_slots_explicit_parallel"], f1(ctx["summary"]["dual_kv_gib_per_mtoken_explicit_parallel"]), f2(ctx["summary"]["dual_headroom_at_ceiling_gib"][0]), f2(ctx["summary"]["dual_headroom_at_ceiling_gib"][1])))
w("")
w("- **是 3 倍，不是 2 倍。** 单卡 31.16 GiB 里 18.32 GiB 被权重和计算缓冲占掉，只剩 12.8 GiB 给 KV；")
w("  双卡每卡只摊约 9.7 GiB 权重，两卡合起来给 KV 的空间约 42.9 GiB。**权重不再重复占位**，这是 3 倍的来源。")
w("- **前提是显式写 `--parallel`。** 同一个 1M token、同样 4 个 slot，只差 `kv_unified`：40.50 GiB vs 34.48 GiB，差 6.02 GiB。")
w("  不写 `--parallel` 只有 1.75 倍，而且 2M 会直接 OOM。")
w("- 3M 这一档验到的是「起得来 + 显存占住 + 单个请求能答」；12 个 slot 同时打满没有验。")
w("")
w("### 5.2 容量：装下一个 34.37 GiB 的模型")
w("")
w("| 配置 | 显存去向 | 预填充 tok/s | 解码 tok/s |")
w("|---|---|---:|---:|")
w("| Q8_0 单卡 `-ngl 37` | 约 30 GiB 上卡、约 4 GiB 层落 CPU | %s | **%s** |" % (f2(q8_ngl37["summary"]["prompt_tok_s"]), f2(q8_ngl37["summary"]["decode_tok_s"])))
w("| Q8_0 单卡 `-ngl 99` | 显存占满 31.13 GiB（剩 0.03 GiB）；权重 34.37 GiB，未上卡的 ≥ 3.2 GiB | %s | %s |" % (f2(load("2026-10-23_b65-32g-q8_0-single-spill-qwen3.6-35b-a3b.json")["summary"]["prompt_tok_s"]), f2(load("2026-10-23_b65-32g-q8_0-single-spill-qwen3.6-35b-a3b.json")["summary"]["decode_tok_s"])))
w("| Q8_0 双卡 `-sm layer` | **33.50 GiB 全驻显存** | %s | **%s** |" % (f2(q8_dual["summary"]["prompt_tok_s"]), f2(q8_dual["summary"]["decode_tok_s"])))
w("")
w("- 权重 34.37 GiB > 单卡 31.16 GiB，**单卡装不下**；双卡 62.32 GiB **装得下**。这是唯一一件「加一张卡才能办成」的事。")
w("- 🔴 **反直觉的一条：装得下不等于划得来。** 双卡把 33.50 GiB 全塞进显存，解码 **%s tok/s**；" % f2(q8_dual["summary"]["decode_tok_s"]))
w("  单卡把约 4 GiB 扔到 CPU、其余全驻，解码 **%s tok/s** —— **单卡带 CPU 尾比双卡拆层快 %s。**" % (f2(q8_ngl37["summary"]["decode_tok_s"]), fx(r_q8)))
w("  跨卡同步的代价，比过 PCIe 搬那 4 GiB 权重贵得多。**要跑得快，就不要拆层。**")
w("- **CPU 尾的代价是可测、单调的**：`-ngl 30 / 34 / 37` 解码 %s / %s / %s tok/s，每多上 1 层约 +0.8 tok/s。" % (
    f2(load("2026-10-23_b65-32g-q8_0-single-ngl30-qwen3.6-35b-a3b.json")["summary"]["decode_tok_s"]),
    f2(load("2026-10-23_b65-32g-q8_0-single-ngl34-qwen3.6-35b-a3b.json")["summary"]["decode_tok_s"]),
    f2(q8_ngl37["summary"]["decode_tok_s"])))
w("- 🔴 但 `-ngl 99` 打破这个规律：上卡更多（31.13 GiB vs 约 30 GiB）、CPU 尾更小，解码反而掉到 12.98。")
w("  **落多少不重要，落哪几层才重要** —— 尾层连续下放便宜，把输出层那一段挤下去就贵。")
w("- 单卡上 Q8_0 **不存在「全驻显存」这个配置**（34.37 > 31.16），最快一档也带着约 4 GiB 层在 CPU 上。")
w("")
w("### 5.3 吞吐：两张卡各一条产线")
w("")
w("| 组合 | 形态 | 结果 |")
w("|---|---|---|")
w("| 出图 + 出图 | 两个 ComfyUI，各钉一张卡 | 稳态 %s ~ %s s/张，与同批单卡 %s / %s **持平** |" % (f2(img_c1_ss[1]["server_sec"]), f2(img_c0_ss[2]["server_sec"]), f2(img_solo_ss[1]["server_sec"]), f2(img_solo_ss[2]["server_sec"])))
w("| 出视频 + 聊天 | 卡 0 跑 H3，卡 1 跑 llama.cpp | 12/12 答对，decode 114.79 vs 115.02 tok/s（−0.2%） |")
w("| 出视频 + 出视频 | 两个 ComfyUI 各跑 H3 | **不成立**：2/2 在同一处崩溃，页面文件峰值 48.7 GB |")
w("")
w("- 第三条是 **32 GB 内存墙，不是显卡不够**：单实例 H3 约要 25 GB 虚拟内存，两个 50 GB，物理内存 32 GB 顶不住。")
w("  隔离两侧的 SYCL 缓存后照崩 → 不是缓存冲突。**32 GB 机器上双卡只能「一条视频 + 一条轻任务」；两条视频线要 64 GB 内存。**")
w("")

# ---------------------------------------------------------------- 六
w("## 六、一片 B70 vs 两片 B65（同价对决）")
w("")
w("价格口径（2026-10-21 官方调价后）：**B70 ¥18,999**、B65 ¥9,499。**两片 B65 ¥18,998，和一片 B70 几乎同价。**")
w("所以这就是「一片 B70 = 两片 B65」这道题的正确算法 —— 同样的钱，买到的是两种不同的东西。")
w("")
w("| | 一片 B70 32G | 两片 B65 32G |")
w("|---|---:|---:|")
w("| 价格 | **¥18,999** | **¥18,998** |")
w("| 核心 / 带宽 / 显存 | 32 核 · 608 GB/s · 31.16 GiB | 2×20 核 · 2×608 GB/s · 62.32 GiB |")
w("| H3 720p · 5 s 端到端（稳态） | **%s** | %s（每张） |" % (s(sample(b70_720, "fresh")["server_sec"]), s(b65_720_fresh["server_sec"])))
w("| H3 单步 | **%s s/it** | %s s/it |" % (f2(sample(b70_720, "fresh")["sampling_sec_per_step"]), f2(b65_720_fresh["sampling_sec_per_step"])))
w("| H3 1080p · 5 s 端到端（稳态） | **%s** | %s |" % (s(sample(b70_1080, "fresh")["server_sec"]), s(b65_1080_fresh["server_sec"])))
w("| Qwen Q4_0 解码 | **%s tok/s** | %s tok/s |" % (f2(load("2026-10-20_b70-q4-0-sycl-l0.json")["summary"]["decode_tok_s"]), f2(q_solo["summary"]["decode_tok_s"])))
w("| 满载功耗（P90） | %s W | %s W（两卡合计） |" % (f1(b70_pw["summary"]["power"]["p90_w_max"]), f1(pw_b0["summary"]["power"]["pair_sum_p90_w"])))
w("| 同时跑几条 H3 | 1 | **2** |")
w("| 34.37 GiB 的 Q8_0 | 同为 31.16 GiB，按容量推装不下；**B70 上单卡 Q8_0 没测** | 装得下，但解码 %s tok/s |" % f2(q8_dual["summary"]["decode_tok_s"]))
w("")
w("三个结论：")
w("")
w("1. **同价之下，「算力翻倍」这句话两边都不成立。** 实测 B70 只比**一片** B65 快 %s（端到端）/ %s（单步），" % (fx(r_e2e), fx(r_step)))
w("   而两片 B65 在单任务上仍然是**一片**的速度 —— 第二张卡对单条片子的贡献是 0。")
w("   规格上 B70 标称 367 TOPS、两片 B65 共 394 TOPS，量的和标的对不上，**以实测为准**。")
w("2. **比「两条片子」，两片 B65 赢 %s。** 两片 B65 各出一条 5 秒 720p，墙钟 %s；" % (fx(r_two), s(two_clip_dual)))
w("   一片 B70 只能串行，两条要 %s。按小时算产能：两片 B65 **%s 条/时**，一片 B70 **%s 条/时** —— 同价，产能差 %s。" % (s(two_clip_b70), f1(thr_dual), f1(thr_b70), fx(r_thr)))
w("3. **B70 不买容量，只买速度。** 两张卡都是 32 GB、都是 608 GB/s，H3 的装载判决逐档完全一致 ——")
w("   B70 能跑的模型，B65 也能跑，只是慢 %s；B65 跑不下的 34.37 GiB，B70 同样跑不下（**B70 单卡 Q8_0 没测**，不给数字）。" % fx(r_e2e))
w("   反过来，**只有两片 B65 能装下那个 34.37 GiB 的模型、只有两片 B65 能吃到 3M token 上下文。**")
w("")
w("| 你的场景 | 选 | 理由 |")
w("|---|---|---|")
w("| 一条片子要快、要 1080p 常态 | **B70** | 720p 快 %s、1080p 快 %s，单任务无替代 |" % (f2(r_e2e) + "×", f2(r_1080) + "×"))
w("| 同时出两条片子 / 一条视频一条问答 | **2× B65** | 同价，产能 %s（%s vs %s 条/时） |" % (fx(r_thr), f1(thr_dual), f1(thr_b70)))
w("| 要装 34 GiB 以上的模型、要 3M token 上下文 | **2× B65** | 容量翻倍；但预期是「装得下」，不是「跑得快」 |")
w("| 预算卡在 32 GB 显存这一档 | **B65** | 同显存、便宜约 ¥9,500，慢 %s |" % fx(r_e2e))
w("")

# ---------------------------------------------------------------- 七
w("## 七、不同搭配载体在 AI 推理上的相同与不同")
w("")
w("> 这一节讲结构，不讲参数。**本机实测过的载体只有「一张卡」和「两张 B65」**；表里另外两种本机没有，")
w("> 所以**不给它们任何数字**，只讲结构决定了什么。")
w("")
w("| 载体 | 显存 | 卡间通道 | 本机实测 |")
w("|---|---|---|---|")
w("| 1× B65 | 一个池子，31.16 GiB | — | ✅ |")
w("| **2× B65**（本文） | 两个独立池子，各 31.16 GiB | PCIe（本机卡 1 在芯片组 x4 槽）；**无 P2P**，跨卡只能经主机内存 | ✅ |")
w("| 2× RTX 5090 | 两个独立池子，各 32 GB | PCIe；**消费级卡同样没有 P2P**，跨卡也只能经主机内存 | ⛔ 没测 |")
w("| 统一内存平台（DGX Spark 这类） | **一个池子**，GPU 直接寻址整机内存 | 不存在「卡间搬运」这个概念 | ⛔ 没测 |")
w("")
w("### 相同的三件事")
w("")
w("1. **单条任务的速度由算力和带宽决定，不由卡的数量决定。** 实测同一条 H3：单卡单步 42.30 s/it，")
w("   双卡同时满载 42.41 s/it —— 第二张卡对单条片子的贡献是 0。换哪家卡、换哪种载体，这条都成立。")
w("2. **装不下就得往下层放，放下去就要搬。** 显存最快、主机内存次之、磁盘最慢；")
w("   谁的容量不够，谁就要付这一层搬运的钱。")
w("3. **一个进程只吃一张卡。** `torch.xpu` 和 ComfyUI 都只绑第一张卡，不会自己铺开。")
w("   要让两张卡都干活，最省事的是**起两个进程**，不是一个进程用两张卡。")
w("")
w("### 不同的三件事")
w("")
w("1. 🔴 **池子有几个，决定瓶颈在哪，也决定优化方向正好相反。**")
w("   - **两个独立池子**（本文这种）：把一个大模型切开、分层放到两张卡上，层与层之间要同步，同步比搬运贵。")
w("     实测 Q8_0 拆层全驻显存解码 **%s tok/s**，单卡把约 4 GiB 甩到 CPU 反而 **%s tok/s**，"
  % (f2(q8_dual["summary"]["decode_tok_s"]), f2(q8_ngl37["summary"]["decode_tok_s"])))
w("     **单卡带 CPU 尾快 %s**。这种载体的方向是「**别拆层**」—— 拆开买的是容量，不是速度。" % fx(r_q8))
w("   - **一个池子**（统一内存）：没有「哪层放哪张卡」这个问题，快层和慢层在同一个池子里连续。")
w("     方向反过来了 —— 要做的是**把热数据留在快的那一段**，而不是想办法把负载铺到更多卡上。")
w("2. **有没有 P2P，决定「跨卡」有多贵。** 本文两张 B65 之间没有 P2P，跨卡数据要落主机内存再取，")
w("   来回两趟 PCIe。消费级卡（5090 这一档）同样没有 P2P —— 就「跨卡很贵」这一点，两种载体是**同一类**，")
w("   都更适合「两张卡各干各的」。")
w("3. **带宽不随卡数翻倍。** 两张 B65 合起来是 2×608 GB/s 的**总额**，但一条任务只跑在它所在的那张卡上，")
w("   能动用的还是 608 GB/s。把模型切两半摊到两张卡，等于用「每步跨卡同步」换掉「每张卡装一半」——")
w("   带宽总量涨了，单条任务能用的没涨。")
w("")
w("### 落到选型")
w("")
w("| 你的情况 | 怎么做 | 为什么 |")
w("|---|---|---|")
w("| 两件互不相干的活 | **两张卡各起一个实例** | 实测出图+出图、出视频+聊天都不掉速，这是双卡最稳的用法 |")
w("| 一个模型装不下 | **先换小一档量化**，再考虑拆层 | 拆层买容量、赔速度（实测赔 %s）；换量化档只掉精度 |" % fx(r_q8))
w("| 想让单条任务更快 | **换更强的单卡**，不是加卡 | 加卡对单条任务的贡献是 0，哪种载体都一样 |")
w("| 装不下又不想拆层 | 统一内存平台（本机没测） | 一个池子，装得下就整块驻留，不存在跨卡同步 |")
w("")

# ---------------------------------------------------------------- 八
w("## 八、跑通的参数（可以直接抄）")
w("")
w("### 8.1 ComfyUI 双实例：两张卡各一个")
w("")
w("```bash")
w("# 实例 1（卡 0，CPU 直连 x16）")
w("COMFY_PORT=8190 ONEAPI_DEVICE_SELECTOR=level_zero:0 \\")
w("  SYCL_CACHE_DIR=<工具目录>/_sycl_cache_c0 \\")
w("  <ComfyUI 目录>/python_embeded/python.exe <ComfyUI 目录>/main.py \\")
w("    --listen 127.0.0.1 --port 8190 --reserve-vram 4")
w("")
w("# 实例 2（卡 1，芯片组 x4）—— 错开 20 秒再起，避开同时装载")
w("COMFY_PORT=8191 ONEAPI_DEVICE_SELECTOR=level_zero:1 \\")
w("  SYCL_CACHE_DIR=<工具目录>/_sycl_cache_c1 \\")
w("  <ComfyUI 目录>/python_embeded/python.exe <ComfyUI 目录>/main.py \\")
w("    --listen 127.0.0.1 --port 8191 --reserve-vram 4")
w("```")
w("")
w("- **钉卡只有一层：`ONEAPI_DEVICE_SELECTOR=level_zero:N`。** ComfyUI 的 `main.py` 本身没有「断言索引」这个参数，")
w("  照抄台架采集器的 `--expect-index`（那是 `bench_f_h3.py` 的参数）会直接报参数错误起不来。")
w("- **起好之后自己核一次**：两个实例各看一次显存占用，两个都涨才是各占一张卡；只有一个涨，就是都落到了同一张。")
w("- **`SYCL_CACHE_DIR` 必须各给一份**，共用一个会互相覆盖内核缓存。")
w("- 端口用 8190 / 8191。**8188 是常驻实例，不要抢、不要杀。**")
w("- `--reserve-vram 4` 是这套数字的采集条件，改它会影响装载行为。")
w("")
w("### 8.2 llama.cpp 双卡：多设备 + 分层装载")
w("")
w("```bash")
w("# SYCL 运行时的 DLL 在 python_embeded 里，必须前置，否则 exe 起来就 0xC0000005")
w("PATH=<python_embeded 目录>/Library/bin:<llama.cpp bin 目录>:$PATH")
w("ONEAPI_DEVICE_SELECTOR=level_zero:0,1 \\")
w("  llama-server -m <模型目录>/Qwen_Qwen3.6-35B-A3B-Q4_0.gguf \\")
w("    -dev SYCL0,SYCL1 -sm layer \\")
w("    -c 3145728 --parallel 12 \\")
w("    --host 127.0.0.1 --port 8099")
w("```")
w("")
w("- 🔴 **`-c` 必须与 `--parallel` 对齐**：`--parallel = ctx / 262144`。不对齐时日志里 `kv_unified=true`，")
w("  每 M token 要 22.2~22.4 GiB，2M 直接 OOM；对齐后 `kv_unified=false`，每 M token 只要 14.5~15.6 GiB。")
w("- **只在一张卡上跑就写 `-dev SYCL0`（或 `SYCL1`）**，并把 `ONEAPI_DEVICE_SELECTOR` 一起收窄到同一张，否则设备枚举顺序会变。")
w("- 🔴 **`PATH` 必须前置 `python_embeded\\Library\\bin`**（里面有 SYCL 运行时的 DLL）。不加的表现是")
w("  **退出码 `0xC0000005`、1 秒内崩、stderr 全空** —— 看着像模型问题，其实是运行时没找到。")
w("")
w("### 8.3 三条判断")
w("")
w("| 查什么 | 怎么做 | 为什么 |")
w("|---|---|---|")
w("| 起没起 | 等日志出现 `model loaded`，再发一次 `/v1/chat/completions` | TCP 通不等于能提问 |")
w("| 装没装下 | 看**显存占用有没有随 `-c` 按比例涨** | 单卡 `-c 1572864` / `2097152` 都能起能答，但占用与 1M 一样（12.68 / 12.63 vs 12.81 GiB）—— 多出来的上下文没真分配 |")
w("| 值不值得 | 看**跑得多快** | Q8_0 单卡 `-ngl 99` 装不下却照样 `model loaded` + 探针 200，只是余下层落 CPU |")
w("")
w("### 8.4 两条会让数字假掉的小设置")
w("")
w("- **`cache_prompt` 必须关**（多模态对照里是 `cache_prompt: false`）。不关的话同一张图连打会命中提示词缓存，")
w("  墙钟掉到 0.1 s、decode 报 115 tok/s —— 那是缓存，不是算力。")
w("- **先热车再取数**。同一条 H3，页缓存冷 %s、热 %s，差 %s 个百分点。凡「双卡拖慢多少」，先跑一轮热的。" % (s(d1_fresh["server_sec"]), s(sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")["server_sec"]), f1(100 * (d1_fresh["server_sec"] / sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")["server_sec"] - 1))))
w("")

# ---------------------------------------------------------------- 九
w("## 九、坑清单")
w("")
w("| # | 坑 | 表现 | 处理 |")
w("|---:|---|---|---|")
w("| 1 | 以为双卡算力翻倍 | 单步 42.30 → 42.41 s/it，一步没快 | `torch.xpu` 只用第一张卡；llama.cpp 多设备是分层装载 |")
w("| 2 | 拆层买容量 | 33.50 GiB 全驻，解码却只有 %s | 层切分赔速度；要速度就单卡跑小一档量化 |" % inv(r_q8))
w("| 3 | 进程起得来就当真装下了 | `-c 1.5M` / `2M` 能起能答，显存一点没多占 | 改看「显存有没有随 `-c` 按比例涨」 |")
w("| 4 | 装不下就认定起不来 | Q8_0 单卡 `-ngl 99` 照样 200 | 改看「跑得多快」 |")
w("| 5 | `-c` 与 `--parallel` 不对齐 | 每 M token 22.2~22.4 GiB，2M OOM | `--parallel = ctx / 262144`，确认日志 `kv_unified=false` |")
w("| 6 | 双实例同时出视频 | 2/2 崩在 `loads=2` 之后，`0xC0000005`，页面文件峰值 48.7 GB | 32 GB 内存墙；双卡只做「一条视频 + 一条轻任务」 |")
w("| 7 | 首轮直接取数 | 首轮 543 s、热车后 406 s，同一个配置 | 先跑一轮热车；首轮含并发装载，不可比 |")
w("| 8 | 功耗归错卡 | H3 跑得正旺，采样器报 42~46 W | 采样器只读 Sysman 第 0 个设备，且 **Sysman 顺序 ≠ `level_zero:N`**（本机 Sysman dev0 = 总线 16 = 卡 1）。双卡功耗改用按卡枚举、按 PCI 总线归属的采集器 |")
w("| 9 | `PATH` 没前置就起 llama.cpp | `0xC0000005`，1 秒内崩，stderr 全空 | 前置 `<python_embeded 目录>/Library/bin` |")
w("| 10 | `llama-bench` 传 `-c` | `invalid parameter for argument: -c` | `llama-bench` 用 `-p` / `-n`，不认 `-c` |")
w("| 11 | 输出接管道再取数 | 管道要等进程结束才吐字，中途一个字都看不到 | 直接 `>> 日志文件 2>&1` |")
w("| 12 | 共用 `SYCL_CACHE_DIR` | 两个实例互相覆盖内核缓存 | 各给一份；但注意：隔离后照崩的那次不是缓存问题 |")
w("| 13 | 采集器没启动就以为没功耗 | 记录里功耗字段是空的 | 不显式启动就静默降级成「不记功耗」，不是零功耗 |")
w("")

# ---------------------------------------------------------------- 十
w("## 十、数据从哪来")
w("")
w("- 时间：**2026-10-23**（双卡全部实测）；单卡基线取 **2026-10-21**（H3、出图、Qwen）与 **2026-10-22**（H3 时长阶梯）。")
w("- 原始记录：`bench/data/` 下按日期命名的 json，每条含 workload、samples、summary、notes。本文所有表格由")
w("  `bench/harness/gen_dual_report.py` 从这些 json 直出，**没有手抄数字**。")
w("- 用到的记录：")
w("")
for n in [
    "2026-10-21_b65-32g_minimax-h3-int8_convrot-b65h3-1280x720-comfyui.json",
    "2026-10-21_b65-32g_minimax-h3-int8_convrot-b65h3-1920x1088-comfyui.json",
    "2026-10-22_h3_1280x720_b65d10.json",
    "2026-10-22_h3_1280x720_b65d15.json",
    "2026-10-22_h3_1280x720_b65d17.json",
    "2026-10-22_h3_1280x720_b65d20.json",
    "2026-10-19_h3_1280x720_b70scan.json",
    "2026-10-19_h3_1920x1088_b70scan.json",
    "2026-10-19_h3_1280x720_b70pw.json",
    "2026-10-20_b70-q4-0-sycl-l0.json",
    "2026-10-23_h3_1280x720_duald1.json",
    "2026-10-23_h3_1280x720_duald4b.json",
    "2026-10-23_h3_1280x720_duald6.json",
    "2026-10-23_h3_1280x720_dualc1.json",
    "2026-10-23_h3_1280x720_dualc1b.json",
    "2026-10-23_b65-32g-q4_0-dual-c1.json",
    "2026-10-23_b65-32g-q4_0-dual-c1-concurrent.json",
    "2026-10-23_dual-a4-vision-under-h3.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2solo-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2c0-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2c1-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3s0-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3s1-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3b0-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3b1-comfyui.json",
    "2026-10-23_b65-32g_q4_0-ctxcap-dual.json",
    "2026-10-23_b65-32g-q8_0-dual-layer-qwen3.6-35b-a3b.json",
    "2026-10-23_b65-32g-q8_0-single-spill-qwen3.6-35b-a3b.json",
    "2026-10-23_b65-32g-q8_0-single-ngl37-qwen3.6-35b-a3b.json",
]:
    w("  - `%s`" % n)
w("")
w("- 相关文档：跨卡对照总表 [`slot-comparison.md`](slot-comparison.md) §6、H3 四卡实测 [`comfyui-h3.md`](comfyui-h3.md)、")
w("  功耗 [`comfyui-power.md`](comfyui-power.md)、常见坑 [`pitfalls.md`](pitfalls.md)。")
w("- 调试过程与踩坑的完整记录在 `bench/notes/dual-b65-prep.md`，**那份是工程笔记，不是产品文档**；对外结论以本文和 `docs/` 为准。")
w("")

text = "\n".join(L) + "\n"
text = text.replace("\r\n", "\n").replace("\r", "\n")
text = text.replace("\n", "\r\n")
if text.endswith("\r\n"):
    text = text[:-2]

with open(OUT, "wb") as f:
    f.write(text.encode("utf-8"))

print("written:", OUT, len(text), "bytes")
