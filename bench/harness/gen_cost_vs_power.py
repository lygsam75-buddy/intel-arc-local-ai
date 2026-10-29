#!/usr/bin/env python
"""由 README.zh-CN.md 表 1b ③「出一条 5 秒 1080p 视频」行 + 表 3「满载」行
直出「功耗低 ≠ 单条更便宜」双面板图。

左：满载 P90（B60 151~154 / B65 201~204 / B70 290 W）——功耗随档位上行。
右：出一条 5 秒 1080p 视频的电费（3.5 / 4.7 / 4.3 分钱）——B65 功耗低三成反而最贵。
两面板同一卡序，右面板峰顶标出反转。B50 没测，不进图。
数字取不到就报错。输出 docs/assets/cost-vs-power{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "README.zh-CN.md"
OUT = {l: ROOT / "docs" / "assets" / f"cost-vs-power{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_B60, C_B65, C_B70 = "#2F6FBA", "#1B7F79", "#C2410C"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

CARDS = ["B60", "B65", "B70"]
CC = {"B60": C_B60, "B65": C_B65, "B70": C_B70}

TXT = {
    "zh": dict(
        title="功耗低 ≠ 单条更便宜：B65 省三成电，一条 1080p 反而贵 9%",
        sub="同机同栈 · 6 步 · 5 秒 1080p 端到端含装载 · 电费按 0.7 元/度 · 2026-10 口径",
        pa="满载 P90（W）", pb="出一条 5 秒 1080p 视频的电费（分钱）",
        flip="B65 功耗低 30%，\n单条反而贵 9%",
        y1="P90（W）", y2="分钱 / 条",
        foot="按任务计费时低功耗卡不省钱：B65 的 200 W 墙只省「挂着的时间」，"
             "出一条 1080p（240 kJ）比 B70（218.6 kJ）更贵——慢，就是贵。"),
    "en": dict(
        title="Lower power is not cheaper per clip: B65 draws 30% less, costs 9% more",
        sub="Same rig, same stack · 6 steps · 5 s clip · 1080p end-to-end incl. loading · ¥0.7/kWh · 2026-10",
        pa="Full-load P90 (W)", pb="Electricity per 5 s 1080p clip (fen)",
        flip="B65: 30% less power,\nyet 9% costlier per clip",
        y1="P90 (W)", y2="fen per clip",
        foot="Billed per task a lower-power card does not save money: the B65's 200 W wall saves idle time only;\n"
             "one 1080p clip (240 kJ) costs more than the B70 (218.6 kJ) — slower is pricier."),
}


def parse():
    t = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")

    # 表 1b ③：「出一条 5 秒 1080p 视频」行 —— 取分钱数字
    sec = t.split("③ 钱")[1].split("## 一条硬顺序")[0]
    row = next(ln for ln in sec.splitlines() if "1080p" in ln and "分钱" in ln)
    cells = [x.strip() for x in row.split("|")[1:-1]]
    cost = {}
    for card, cell in zip(("B50", "B60", "B65", "B70"), cells[1:]):
        m = re.search(r"([\d.]+)\s*分钱", cell)
        if m:
            cost[card] = float(m.group(1))
    assert cost == {"B60": 3.5, "B65": 4.7, "B70": 4.3}, cost

    # 表 3：「满载」行 —— 取 P90 区间中点
    sec3 = t.split("## 表 3")[1].split("## 表 4")[0]
    row = next(ln for ln in sec3.splitlines() if ln.startswith("| 满载"))
    cells = [x.strip() for x in row.split("|")[1:-1]]
    p90 = {}
    for card, cell in zip(("B50", "B60", "B65", "B70"), cells[1:]):
        ms = re.findall(r"(\d+(?:\.\d+)?)\s*(?:至|-|–)\s*(\d+(?:\.\d+)?)\s*W", cell)
        if ms:
            lo, hi = float(ms[0][0]), float(ms[0][1])
            p90[card] = (lo + hi) / 2
        else:
            m = re.search(r"(\d+(?:\.\d+)?)\s*W", cell)
            if m:
                p90[card] = float(m.group(1))
    assert abs(p90["B60"] - 152.4) < 0.2 and abs(p90["B65"] - 202.5) < 0.2 \
        and abs(p90["B70"] - 290.0) < 0.5, p90

    # 反转幅度自算
    flip_p = (1 - p90["B65"] / p90["B70"]) * 100
    flip_c = (cost["B65"] / cost["B70"] - 1) * 100
    assert abs(flip_p - 30.2) < 1.5, flip_p
    assert abs(flip_c - 9.3) < 1.5, flip_c
    return p90, cost


def main():
    for fam in FONT:
        try:
            plt.rcParams["font.family"] = fam
            import matplotlib.font_manager as fm
            if any(f.name == fam for f in fm.fontManager.ttflist):
                break
        except Exception:
            pass
    plt.rcParams["axes.unicode_minus"] = False

    p90, cost = parse()

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.9), dpi=96)
        fig.patch.set_facecolor("white")
        for ax, key, lab in ((ax1, "p90", t["pa"]), (ax2, "cost", t["pb"])):
            ax.set_facecolor("white")
            ax.grid(axis="y", color=GRID, lw=0.9)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                ax.spines[s].set_color(MUTED)
            ax.tick_params(labelsize=9)
            ax.set_title(lab, fontsize=10.5, color=INK, pad=8)

        vals = [p90[c] for c in CARDS]
        ax1.bar(CARDS, vals, width=0.52, color=[CC[c] for c in CARDS], zorder=3)
        for x, v in zip(range(3), vals):
            ax1.text(x, v + 5, f"{v:.0f}", ha="center", fontsize=9.5,
                     color=INK, weight="bold")
        ax1.set_ylim(0, max(vals) * 1.22)
        ax1.set_ylabel(t["y1"], fontsize=9.5, color=INK)

        vals = [cost[c] for c in CARDS]
        ax2.bar(CARDS, vals, width=0.52, color=[CC[c] for c in CARDS], zorder=3)
        for x, v in zip(range(3), vals):
            ax2.text(x, v + 0.12, f"{v:.1f}", ha="center", fontsize=9.5,
                     color=INK, weight="bold")
        ax2.set_ylim(0, max(vals) * 1.35)
        ax2.set_ylabel(t["y2"], fontsize=9.5, color=INK)
        ax2.annotate(t["flip"], xy=(1, vals[1]), xytext=(1.28, vals[1] * 1.18),
                     fontsize=8.8, color=C_B65, weight="bold", ha="left",
                     arrowprops=dict(arrowstyle="->", color=C_B65, lw=1.2))

        fig.suptitle(t["title"], fontsize=12.6, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.905, t["sub"], ha="center", fontsize=8.6, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.2,
                 color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.085, right=0.97, top=0.80, bottom=0.26,
                            wspace=0.28)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), "ok")


if __name__ == "__main__":
    main()
