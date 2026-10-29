# -*- coding: utf-8 -*-
"""载体「三同 / 三异」结构原理图（§七 相同的三件事 / 不同的三件事）。

三同：单条速度看算力带宽、装不下往下层搬、一进程一卡 —— 换载体都成立。
三异：池子数量、有无 P2P、带宽怎么数 —— 由载体结构决定，图只给结构骨架，
推理链与实测数字留给正文文字。
锚点数字从 dual_data 直出（与 dual-b65-report 总表同源），禁止手抄。
输出 docs/assets/dual-b65-carriers-{same,diff}{,.en}.svg（纯 LF）。
"""
import io
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

from dual_data import *  # noqa: E401,E402,F401,F403

INK, MUTED = "#2C2C2A", "#5F5E5A"
C_A, C_A_LIGHT, C_BG = "#2F6FBA", "#D6E4F7", "#F7F9FC"
C_WARN, C_WARN_LIGHT = "#C2410C", "#FADBD3"
C_GREY = "#EDECE8"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

STEP_1 = f2(b65_720_fresh["sampling_sec_per_step"])   # 单卡单步
STEP_2 = f2(d6_fresh["sampling_sec_per_step"])        # 双卡单步
STEP_GAP = f1(100 * (d6_fresh["sampling_sec_per_step"] / b65_720_fresh["sampling_sec_per_step"] - 1))
DEC_SPLIT = f2(q8_s["ts5050"]["decode_tok_s"])        # 拆层全驻 35.14
DEC_SPILL = f2(q8_spill["decode_tok_s"])              # spill 13.80

TXT = {
    "zh": dict(
        same=dict(
            title="载体在变，这三条不变",
            sub="换哪家卡、换哪种载体都成立",
            h1="① 单条速度 = 算力 + 带宽",
            bars=[("1 卡 · 1 条", STEP_1 + " s/it"), ("2 卡 · 1 条", STEP_2 + " s/it")],
            note1="≈ 一样快",
            tag1="卡数不改变单条速度",
            micro1="单步 %s vs %s s/it（+%s%%）" % (STEP_1, STEP_2, STEP_GAP),
            h2="② 装不下就往下层搬",
            tiers=[("显存", "最快"), ("主机内存", "次之"), ("磁盘", "最慢")],
            move="搬 = 花钱",
            tag2="容量不够的付搬运钱",
            micro2="spill 落主机后只剩 %s tok/s" % DEC_SPILL,
            h3="③ 一个进程只吃一张卡",
            procs=[("进程 A", "卡 0"), ("进程 B", "卡 1")],
            bad="× 一个进程不会自己铺开到两卡",
            tag3="要两卡干活 = 起两个进程",
            micro3="torch.xpu / ComfyUI 只绑 xpu:0",
            foot="图给结构骨架；实测数字见总表，推理见下文逐条。"),
        diff=dict(
            title="结构不同，这三条跟着变",
            sub="池子数量 · 有无 P2P · 带宽怎么数",
            h1="① 池子数量决定优化方向",
            two_pool="两个独立池子", one_pool="一个池子",
            lay_a="卡 0 · 层 0..k", lay_b="卡 1 · 层 k+1..",
            sync="同步", hot="快段 · 热数据", cool="慢段",
            tag1="两池拆层装 / 一池留热段",
            micro1="拆层全驻 %s · spill %s tok/s" % (DEC_SPLIT, DEC_SPILL),
            h2="② 有无 P2P 决定跨卡多贵",
            no_p2p="无 P2P 直连", host="主机内存",
            hop="来回两趟 PCIe",
            tag2="跨卡贵 → 两卡各干各的",
            micro2="B65 与 5090 同属无 P2P 一类",
            h3="③ 带宽不随卡数翻倍",
            tot="总额 2×608 GB/s", one_job="1 条任务",
            single="单条仍 608 GB/s",
            tag3="总额涨了，单条没涨",
            micro3="每步跨卡同步 ≠ 带宽翻倍",
            foot="未测载体（2×5090 / 统一内存）只给结构不给数字；数字见总表。"),
    ),
    "en": dict(
        same=dict(
            title="Carriers change; these three do not",
            sub="Any vendor, any carrier — the same three hold",
            h1="① One-job speed = compute + bandwidth",
            bars=[("1 card · 1 job", STEP_1 + " s/it"), ("2 cards · 1 job", STEP_2 + " s/it")],
            note1="≈ the same speed",
            tag1="Card count does not change one-job speed",
            micro1="per step %s vs %s s/it (+%s%%)" % (STEP_1, STEP_2, STEP_GAP),
            h2="② What does not fit moves down a tier",
            tiers=[("VRAM", "fastest"), ("Host RAM", "slower"), ("Disk", "slowest")],
            move="moving = paying",
            tag2="Whoever is short of capacity pays the move",
            micro2="spilling to host leaves %s tok/s" % DEC_SPILL,
            h3="③ One process eats one card",
            procs=[("Process A", "Card 0"), ("Process B", "Card 1")],
            bad="× one process never spreads over two cards",
            tag3="Two cards working = two processes",
            micro3="torch.xpu / ComfyUI bind xpu:0 only",
            foot="Structure only; measured figures in the summary table, reasoning item by item below."),
        diff=dict(
            title="Structure differs; these three follow it",
            sub="How many pools · P2P or not · how bandwidth counts",
            h1="① Pool count sets the direction",
            two_pool="Two independent pools", one_pool="One pool",
            lay_a="Card 0 · layers 0..k", lay_b="Card 1 · layers k+1..",
            sync="sync", hot="fast tier · hot data", cool="slow tier",
            tag1="Two pools: split to hold / one pool: keep hot data fast",
            micro1="layer split %s · spill %s tok/s" % (DEC_SPLIT, DEC_SPILL),
            h2="② P2P sets cross-card cost",
            no_p2p="no direct P2P", host="Host RAM",
            hop="two PCIe trips",
            tag2="Cross-card is dear — one job per card",
            micro2="B65 and 5090 are the same no-P2P class",
            h3="③ Bandwidth ≠ doubled per job",
            tot="Total 2×608 GB/s", one_job="1 job",
            single="one job still sees 608 GB/s",
            tag3="Total rises; per-job does not",
            micro3="sync every step ≠ doubled bandwidth",
            foot="Untested carriers (2×5090 / unified memory) get structure, no numbers; figures in the summary table."),
    ),
}

OUT = {}
for kind in ("same", "diff"):
    for lang in ("zh", "en"):
        OUT[(kind, lang)] = os.path.join(
            REPO, "docs", "assets",
            "dual-b65-carriers-%s%s.svg" % (kind, "" if lang == "zh" else ".en"))


def set_font():
    for fam in FONT:
        try:
            plt.rcParams["font.family"] = fam
            import matplotlib.font_manager as fm
            if any(f.name == fam for f in fm.fontManager.ttflist):
                return
        except Exception:
            pass
    plt.rcParams["axes.unicode_minus"] = False


def header(ax, cx, text):
    ax.add_patch(FancyBboxPatch((cx - 1.52, 8.55), 3.04, 0.8,
                                boxstyle="round,pad=0.07",
                                fc=C_A_LIGHT, ec=C_A, lw=1.2))
    ax.text(cx, 8.95, text, ha="center", va="center",
            fontsize=10.2, color=INK, weight="bold")


def box(ax, x, y, w, h, text, fc=C_BG, ec=MUTED, fs=8.4, bold=False, tc=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06",
                                fc=fc, ec=ec, lw=1.1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, weight="bold" if bold else "normal",
            linespacing=1.4)


def arrow(ax, p0, p1, color=C_A, style="-|>", dashed=False, lw=1.6):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=13,
                                 color=color, lw=lw,
                                 linestyle=(0, (3, 2)) if dashed else "solid"))


def tag(ax, cx, text, y=3.3):
    ax.text(cx, y, text, ha="center", va="center",
            fontsize=9.6, color=C_A, weight="bold")


def micro(ax, cx, text, y=2.62, color=MUTED):
    ax.text(cx, y, text, ha="center", va="center", fontsize=7.7, color=color)


def gpu_card(ax, x, y, w=0.9, h=0.48, fc="#3E4C63"):
    """涡轮显卡矢量小图：机身 + 涡轮风扇 + 出风栅 + 挡板 + 金手指。"""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.03",
                                fc=fc, ec=INK, lw=0.9, zorder=3))
    ax.add_patch(FancyBboxPatch((x + 0.07, y + h - 0.12), w - 0.14, 0.05,
                                boxstyle="round,pad=0.01", fc="#5A6B85",
                                ec="none", zorder=4))
    fx, fy, r = x + w * 0.32, y + h / 2, min(0.16, h * 0.34)
    ax.add_patch(Circle((fx, fy), r, fc="#8FA8C8", ec=INK, lw=0.8, zorder=4))
    ax.add_patch(Circle((fx, fy), r * 0.4, fc=INK, ec="none", zorder=5))
    for a in (0.6, 2.7, 4.8):
        ax.plot([fx + r * 0.45 * math.cos(a), fx + r * 0.88 * math.cos(a)],
                [fy + r * 0.45 * math.sin(a), fy + r * 0.88 * math.sin(a)],
                color=INK, lw=0.8, zorder=5)
    for k in range(3):
        yy = y + 0.12 + k * (h - 0.24) / 2
        ax.plot([x + w - 0.26, x + w - 0.12], [yy, yy], color="#8FA8C8",
                lw=0.9, zorder=4)
    ax.add_patch(Rectangle((x + w - 0.05, y + 0.04), 0.07, h - 0.08,
                           fc="#B8B8B8", ec=INK, lw=0.6, zorder=4))
    ax.add_patch(FancyBboxPatch((x + 0.22, y - 0.08), w * 0.52, 0.08,
                                boxstyle="round,pad=0.01", fc="#D4AF37",
                                ec="#A8842A", lw=0.6, zorder=2))

def draw_same(ax, t):
    for i in range(3):
        cx = 1.85 + i * 3.45
        header(ax, cx, t["h%d" % (i + 1)])

        if i == 0:  # 单条速度 = 算力 + 带宽（涡轮卡 + 数值带单位）
            for j, (lab, val) in enumerate(t["bars"]):
                y = 6.75 - j * 1.62
                if j == 0:
                    gpu_card(ax, cx - 1.36, y - 0.02, w=0.8, h=0.58)
                else:
                    gpu_card(ax, cx - 1.22, y + 0.18, w=0.56, h=0.44, fc="#4E5D75")
                    gpu_card(ax, cx - 1.36, y - 0.12, w=0.56, h=0.44)
                ax.text(cx - 0.95, y - 0.48, lab, ha="center", va="center",
                        fontsize=7.6, color=MUTED)
                ax.add_patch(FancyBboxPatch((cx - 0.3, y), 1.0, 0.42,
                                            boxstyle="round,pad=0.04",
                                            fc=C_A_LIGHT, ec=C_A, lw=1.1))
                ax.text(cx + 1.45, y + 0.21, val, ha="right", va="center",
                        fontsize=7.8, color=INK, weight="bold")
            ax.text(cx, 4.25, t["note1"], ha="center", va="center",
                    fontsize=8.8, color=C_A)
            tag(ax, cx, t["tag1"])
            micro(ax, cx, t["micro1"])

        elif i == 1:  # 装不下就往下层搬（三级拉开，栏头留出空气）
            cols = [(C_A_LIGHT, C_A), (C_WARN_LIGHT, C_WARN), (C_GREY, MUTED)]
            for j, ((fc, ec), (name, spd)) in enumerate(zip(cols, t["tiers"])):
                y = 6.75 - j * 1.5
                box(ax, cx - 1.15, y, 1.7, 0.6, name, fc=fc, ec=ec, bold=True)
                ax.text(cx + 0.85, y + 0.3, spd, ha="center", va="center",
                        fontsize=8.0, color=ec)
                if j < 2:
                    arrow(ax, (cx - 0.3, y - 0.02), (cx - 0.3, y - 0.42),
                          color=MUTED, lw=1.3)
                    if j == 1:
                        ax.text(cx + 0.12, y - 0.24, t["move"], ha="left",
                                va="center", fontsize=7.6, color=C_WARN)
            tag(ax, cx, t["tag2"])
            micro(ax, cx, t["micro2"])

        else:  # 一进程一卡（两行拉开，栏头留出空气）
            for j, (proc, card) in enumerate(t["procs"]):
                y = 6.75 - j * 1.62
                box(ax, cx - 1.3, y, 1.1, 0.6, proc, fc=C_BG, ec=MUTED, bold=True)
                arrow(ax, (cx - 0.12, y + 0.3), (cx + 0.18, y + 0.3))
                box(ax, cx + 0.22, y, 1.1, 0.6, card, fc=C_A_LIGHT, ec=C_A, bold=True)
            ax.text(cx, 4.35, t["bad"], ha="center", va="center",
                    fontsize=7.9, color=C_WARN)
            tag(ax, cx, t["tag3"])
            micro(ax, cx, t["micro3"])


def draw_diff(ax, t):
    for i in range(3):
        cx = 1.85 + i * 3.45
        header(ax, cx, t["h%d" % (i + 1)])

        if i == 0:  # 池子数量（上下两组拉开行距）
            ax.text(cx, 7.82, t["two_pool"], ha="center", va="center",
                    fontsize=8.6, color=C_A, weight="bold")
            box(ax, cx - 1.32, 6.82, 1.18, 0.78, t["lay_a"], fc=C_A_LIGHT, ec=C_A, fs=7.4)
            box(ax, cx + 0.14, 6.82, 1.18, 0.78, t["lay_b"], fc=C_A_LIGHT, ec=C_A, fs=7.4)
            arrow(ax, (cx - 0.08, 7.21), (cx + 0.08, 7.21), style="<->", lw=1.4)
            ax.text(cx, 6.55, t["sync"], ha="center", va="center",
                    fontsize=7.6, color=C_WARN)
            ax.text(cx, 5.5, t["one_pool"], ha="center", va="center",
                    fontsize=8.6, color=INK, weight="bold")
            box(ax, cx - 1.32, 4.0, 2.64, 0.9, "", fc=C_BG, ec=MUTED)
            ax.add_patch(FancyBboxPatch((cx - 1.26, 4.06), 1.15, 0.78,
                                        boxstyle="round,pad=0.04",
                                        fc=C_A_LIGHT, ec=C_A, lw=1.1))
            ax.text(cx - 0.68, 4.45, t["hot"], ha="center", va="center",
                    fontsize=7.4, color=INK)
            ax.text(cx + 0.55, 4.45, t["cool"], ha="center", va="center",
                    fontsize=7.6, color=MUTED)
            tag(ax, cx, t["tag1"])
            micro(ax, cx, t["micro1"])

        elif i == 1:  # 无 P2P（卡行与主机内存拉开）
            box(ax, cx - 1.35, 6.92, 1.15, 0.75, "Card 0" if t["host"] == "Host RAM" else "卡 0",
                fc=C_A_LIGHT, ec=C_A, bold=True)
            box(ax, cx + 0.2, 6.92, 1.15, 0.75, "Card 1" if t["host"] == "Host RAM" else "卡 1",
                fc=C_A_LIGHT, ec=C_A, bold=True)
            ax.add_patch(FancyArrowPatch((cx - 0.12, 7.28), (cx + 0.12, 7.28),
                                         arrowstyle="-|>", mutation_scale=11,
                                         color=MUTED, lw=1.2, linestyle=(0, (2, 2))))
            ax.text(cx, 7.82, t["no_p2p"], ha="center", va="center",
                    fontsize=8.2, color=C_WARN, weight="bold")
            ax.text(cx + 0.02, 7.26, "×", ha="center", va="center",
                    fontsize=11, color=C_WARN, weight="bold")
            box(ax, cx - 0.85, 4.55, 1.7, 0.75, t["host"], fc=C_WARN_LIGHT,
                ec=C_WARN, bold=True, fs=8.2)
            arrow(ax, (cx - 0.95, 6.85), (cx - 0.5, 5.4), color=C_WARN, lw=1.5)
            arrow(ax, (cx + 0.5, 5.4), (cx + 0.95, 6.85), color=C_WARN, lw=1.5)
            ax.text(cx, 4.1, t["hop"], ha="center", va="center",
                    fontsize=7.9, color=C_WARN)
            tag(ax, cx, t["tag2"])
            micro(ax, cx, t["micro2"])

        else:  # 带宽不翻倍（卡行与任务条拉开）
            ax.text(cx, 7.82, t["tot"], ha="center", va="center",
                    fontsize=8.8, color=INK, weight="bold")
            box(ax, cx - 1.32, 6.6, 1.2, 0.9, "608 GB/s\n×2 汇总" if "×2" in t["tot"] else "608 GB/s",
                fc=C_A_LIGHT, ec=C_A, fs=7.8, bold=True)
            box(ax, cx + 0.12, 6.6, 1.2, 0.9, "608 GB/s\n×2 汇总" if "×2" in t["tot"] else "608 GB/s",
                fc=C_A_LIGHT, ec=C_A, fs=7.8, bold=True)
            # 单条任务只在一张卡上
            ax.add_patch(FancyBboxPatch((cx - 1.22, 5.9), 1.0, 0.3,
                                        boxstyle="round,pad=0.04",
                                        fc=INK, ec=INK, lw=0.8))
            ax.text(cx - 0.72, 6.05, t["one_job"], ha="center", va="center",
                    fontsize=7.2, color="white")
            ax.text(cx, 5.35, t["single"], ha="center", va="center",
                    fontsize=8.2, color=C_WARN, weight="bold")
            tag(ax, cx, t["tag3"])
            micro(ax, cx, t["micro3"])


def build(kind, lang):
    t = TXT[lang][kind]
    fig, ax = plt.subplots(figsize=(10.4, 5.0), dpi=96)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 10.6)
    ax.set_ylim(0, 10.2)
    ax.axis("off")
    (draw_same if kind == "same" else draw_diff)(ax, t)
    fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=0.955)
    fig.text(0.5, 0.885, t["sub"], ha="center", fontsize=9, color=MUTED)
    fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=8.6, color=INK)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.87, bottom=0.07)

    buf = io.BytesIO()
    fig.savefig(buf, format="svg")
    data = buf.getvalue().replace(b"\r\n", b"\n")
    with open(OUT[(kind, lang)], "wb") as f:
        f.write(data)
    print("written:", OUT[(kind, lang)], len(data), "bytes")

    pdir = os.path.join(os.environ.get("TEMP", "/tmp"), "wb-svg-preview")
    os.makedirs(pdir, exist_ok=True)
    png = os.path.join(pdir, os.path.basename(OUT[(kind, lang)]).replace(".svg", ".png"))
    fig.savefig(png, format="png", dpi=144)
    print("png-preview:", png)
    plt.close(fig)


def main():
    set_font()
    plt.rcParams["axes.unicode_minus"] = False
    for kind in ("same", "diff"):
        for lang in ("zh", "en"):
            build(kind, lang)


if __name__ == "__main__":
    main()
