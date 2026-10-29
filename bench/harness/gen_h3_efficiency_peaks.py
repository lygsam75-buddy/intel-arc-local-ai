#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""由 comfyui-h3.md §一 的四卡 × 六档表直出效率峰图。

效率 = 像素 × 帧 ÷ 端到端分钟（M/min）。四条曲线，★ 标各卡时效峰。
一眼看出：小卡峰在低分辨率、大卡峰在高分辨率。

数据从 comfyui-h3.md §一 解析，断言关键格。
输出 docs/assets/h3-efficiency-peaks{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOC = {"zh": ROOT / "docs" / "comfyui-h3.md",
       "en": ROOT / "docs" / "comfyui-h3.en.md"}
OUT = {l: ROOT / "docs" / "assets" / f"h3-efficiency-peaks{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
CARDS = [
    ("B70", "#7A5AA8", "32G"),
    ("B65", "#2F6FBA", "32G"),
    ("B60", "#1B7F79", "24G"),
    ("B50", "#C2410C", "16G"),
]
RES = [
    ("864×480", 414_720),
    ("1024×576", 589_824),
    ("1152×648", 746_496),
    ("1280×720", 921_600),
    ("1536×864", 1_327_104),
    ("1920×1088", 2_088_960),
    ("2560×1440", 3_686_400),
]
FRAMES = 124  # 5 秒
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["font.sans-serif"] = list(FONT) + ["DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

# 表 B 的端到端秒数（None = 未测 / OOM）
E2E = {
    "B70": [152.54, 182.57, None, 276.68, 444.98, 841.55, None],
    "B65": [198.12, 370.31, 352.31, 394.06, 721.76, 1326.17, 3554.99],
    "B60": [203.03, 250.86, 307.42, 427.31, 653.40, 1327.67, None],
    "B50": [283.82, 375.18, 487.22, 669.19, 1268.67, 2259.86, None],
}
# ★ 标记的效率峰（从原文表取）
PEAKS = {"B70": 3, "B65": 3, "B60": 2, "B50": 1}  # 索引到 RES


def calc_efficiency(px, e2e_s):
    """效率 M/min = 像素 × 帧 ÷ 端到端分钟。"""
    if e2e_s is None:
        return None
    return (px * FRAMES / 1e6) / (e2e_s / 60.0)


def main():
    data = {}
    for card, _, _ in CARDS:
        data[card] = [calc_efficiency(RES[i][1], E2E[card][i]) for i in range(len(RES))]

    # 断言关键格
    assert abs(data["B70"][3] - 24.78) < 0.1, f'B70 720p eff: {data["B70"][3]}'
    assert abs(data["B50"][1] - 11.70) < 0.1, f'B50 576p eff: {data["B50"][1]}'
    assert data["B70"][2] is None, 'B70 1152 should be None'

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    fig.subplots_adjust(top=0.88)
    x = list(range(len(RES)))

    for ci, (card, color, cap) in enumerate(CARDS):
        vals = data[card]
        valid_x = [x[i] for i in range(len(RES)) if vals[i] is not None]
        valid_y = [vals[i] for i in range(len(RES)) if vals[i] is not None]
        ax.plot(valid_x, valid_y, marker="o", ms=6, lw=2.0, color=color,
                mec="white", mew=1.2, zorder=3, label=f"{card} {cap}")

        # ★ 标峰
        pi = PEAKS[card]
        pv = vals[pi]
        if pv is not None:
            ax.plot(pi, pv, marker="*", ms=16, color=color, mec="white",
                    mew=1.2, zorder=5)
            offset = 2.5 if ci % 2 == 0 else -4.5
            ax.annotate(f"{pv:.1f}", xy=(pi, pv), xytext=(0, offset),
                        textcoords="offset points", ha="center",
                        fontsize=9, fontweight="bold", color=color)

    ax.set_xticks(x)
    ax.set_xticklabels([r[0] for r in RES], fontsize=8.5, color=MUTED, rotation=15)
    ax.set_ylabel("效率 (M/min)" if True else "Efficiency (M/min)",
                  fontsize=10, color=INK)
    # 双语标题在 make_chart 里设

    ax.set_ylim(0, 30)
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#D1D5DB")
    ax.legend(loc="upper right", frameon=False, fontsize=9, borderpad=0.3)

    fig.tight_layout()
    matplotlib.rcParams["svg.hashsalt"] = "intel-arc-b-series"

    for lang in ("zh", "en"):
        if lang == "zh":
            fig.suptitle("各卡时效峰：小卡峰在低分辨率，大卡峰在高分辨率",
                         fontsize=11.5, color=INK, y=0.98)
            ax.set_ylabel("效率 (M/min)", fontsize=10, color=INK)
        else:
            fig.suptitle("Efficiency peaks: smaller cards peak at lower resolutions",
                         fontsize=11.5, color=INK, y=0.98)
            ax.set_ylabel("Efficiency (M/min)", fontsize=10, color=INK)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg", facecolor="white", metadata={"Date": None})
        out = OUT[lang]
        out.write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        print(f"wrote {out.name} ({out.stat().st_size} B)")

    plt.close(fig)
    for card, _, _ in CARDS:
        effs = data[card]
        peak_i = PEAKS[card]
        print(f"  {card}: peak {RES[peak_i][0]} = {effs[peak_i]:.1f} M/min  "
              f"(all: {[f'{e:.1f}' if e else '—' for e in effs]})")


if __name__ == "__main__":
    main()
