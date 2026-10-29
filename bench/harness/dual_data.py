# -*- coding: utf-8 -*-
"""dual-b65 报告取数层：bench/data/*.json -> 数字、比值、格式化 helpers。

gen_dual_report.py（中文）与 gen_dual_report_en.py（英文）共用，两版数字同源。
表格与全部数字禁止手抄。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(REPO, "bench", "data")

# 参考价（人民币，2026-10-26 确认，与 README.zh-CN.md 价格表一致）
P_B65 = 9999
P_B70 = 18999
P_2B65 = 2 * P_B65


def yuan(n):
    return "{:,}".format(n)


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


def mmss_en(x):
    m = int(x // 60)
    sec = x - 60 * m
    return "%d min %02d s" % (m, round(sec))


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
q8_dual = load("2026-10-23_b65-32g-q8_0-dual-split-scan.json")
# 同一份扫描里的样本，按 tag 取；口径统一为 llama-server（见 measure）
q8_s = {x["tag"]: x for x in q8_dual["samples"]}
q8_ngl37 = q8_s["solo37"]          # 单卡 -ngl 37，全驻
q8_spill = q8_s["solo99"]          # 单卡 -ngl 99， spill 到 CPU
q8_row = q8_s["row"]               # -sm row，加载失败
q8_tensor = load("2026-10-24_b65-32g-q8_0-dual-tensor-scan.json")
q8_ts = {x["tag"]: x for x in q8_tensor["samples"]}

# 2026-10-24 晚第二批（scan2）：-ts 细扫 + Q4_0 档 + 同场次单卡基线
# 这五个 llama-server 调用与 solo_q4 / solo37 重跑发生在同一时段（17:37~17:47），
# 是「双卡 vs 单卡」目前最紧的同场次对照。
scan2 = {x["tag"]: x for x in load("2026-10-24_b65-32g-dual-ts-scan2.json")["samples"]}
q4_solo = load("2026-10-24_b65-32g-q4_0-solo.json")["samples"][0]                # 单卡 Q4_0 全驻
q8_ngl37b = load("2026-10-24_b65-32g-q8_0-solo37-recheck.json")["samples"][0]    # 同场次单卡 Q8_0 -ngl 37
q4_dual, q4_dual9 = scan2["ts5050_q4"], scan2["ts9010_q4"]           # 双卡 Q4_0 50,50 / 90,10
ts6040, ts8020, ts9010 = scan2["ts6040"], scan2["ts8020"], scan2["ts9010"]
ctx3m = load("2026-10-24_b65-32g-q4_0-ctx3m-probe.json")             # 3M 上下文事故 + 对照组
d2d_full = load("2026-10-24_b65-32g-q8_0-dual-dev2dev-scan.json")     # 16:10 场次
d2d_ts5050 = {x["tag"]: x for x in d2d_full["samples"]}["ts5050"]     # 同配置 50,50 = 37.29

# dev2dev 卡间拷贝路径三档（2026-10-24 晚）：0=SYCL 直拷 / 1=Level Zero 直拷 / 2=强制走主机内存
d2d = load("2026-10-24_b65-32g-q8_0-dual-dev2dev-scan.json")["summary"]
q8_t50 = q8_ts["tensor5050"]       # 双卡 -sm tensor 50,50
q8_t70 = q8_ts["tensor7030"]       # 双卡 -sm tensor 70,30
q8_t50p = q8_ts["tensor5050_pm0"]  # 同上 + GGML_SYCL_ENABLE_HOST_PINNED_MEM=0

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
d4b_fresh = sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")  # 热车后读数
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
# 层切分：双卡 vs 单卡（同一份 llama-server 扫描）
r_q8 = q8_s["ts5050"]["decode_tok_s"] / q8_ngl37["decode_tok_s"]      # 双卡 / 单卡全驻
r_q8_spill = q8_s["ts5050"]["decode_tok_s"] / q8_spill["decode_tok_s"]  # 双卡 / 单卡 spill
r_q8_pp = q8_s["ts5050"]["prefill_tok_s"] / q8_ngl37["prefill_tok_s"]
# 同场次版（scan2 场次 17:37~17:47）：双卡 60,40 vs 单卡 -ngl 37 vs 单卡 Q4_0 全驻
r_q8_same = ts6040["decode_tok_s"] / q8_ngl37b["decode_tok_s"]
r_q4_same = q4_dual["decode_tok_s"] / q4_solo["decode_tok_s"]
