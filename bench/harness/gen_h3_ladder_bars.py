#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""由 comfyui-capability.md 表 B 直出四卡阶梯堆叠柱图。

表 B 的 B-1 是端到端（含装载/编码/解码），B-2 是采样段（6 步合计）。
堆叠柱一图讲完：柱高 = 端到端（B-1），底部实色 = 采样段（B-2），
顶部浅色 = 固定开销（装载+编码+解码）。采样占比随分辨率涨的趋势直接可见。

数据从 comfyui-capability.md §2.2 表 B 解析，断言关键格。
输出 docs/assets/h3-ladder-bars{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOC = {"zh": ROOT / "docs" / "comfyui-capability.md",
       "en": ROOT / "docs" / "comfyui-capability.en.md"}
OUT = {l: ROOT / "docs" / "assets" / f"h3-ladder-bars{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
CARDS = [
    ("B70", "#7A5AA8", "32G"),
    ("B65", "#2F6FBA", "32G"),
    ("B60", "#1B7F79", "24G"),
    ("B50", "#C2410C", "16G"),
]
RES_LABELS = ["864×480", "1024×576", "1152×648", "1280×720", "1536×864", "1920×1088"]
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["font.sans-serif"] = list(FONT) + ["DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

# B-1 端到端（秒）—— 从表 B 解析
# B-2 采样段（秒）—— 从表 B 解析
# B50 是 cold 口径，其余是 fresh


def parse_table_b(path):
    """从 comfyui-capability.md 解析表 B 的 B-1 和 B-2 数据。"""
    text = path.read_text(encoding="utf-8")

    # B-1: 找到端到端表，解析每行的秒数
    b1 = {}
    b2 = {}
    p_vals = {}

    # B-1 行格式: | **B70 32G** · 31.16 GiB | fresh · 10-19 | **152.54 s**<br />DiT 完整 | ...
    b1_row = re.compile(
        r"\|\s*\*\*(B\d\d)\s+\d+G\*\*[^|]*\|[^|]*\|(.+)\|\s*$"
    )
    # B-2 行格式: | B70 32G · 31.16 GiB · fresh |  39.00 s · 25.6% | ...
    b2_row = re.compile(
        r"\|\s*(B\d\d)\s+\d+G[^|]*\|(.+)\|\s*\*\*([\d.]+)\*\*\s*\|\s*$"
    )

    section = None
    for line in text.splitlines():
        if "B-1 端到端" in line:
            section = "b1"
            continue
        if "B-2 采样段" in line:
            section = "b2"
            continue
        if line.startswith("####") or line.startswith("###"):
            if section:
                section = None
            continue

        if section == "b1":
            m = b1_row.match(line)
            if m:
                card = m.group(1)
                cells = m.group(2)
                vals = []
                for cell in cells.split("|"):
                    cell = cell.strip()
                    # 提取秒数: "152.54 s" or "未测"
                    num_m = re.search(r"([\d,]+\.?\d*)\s*s", cell)
                    if num_m:
                        vals.append(float(num_m.group(1).replace(",", "")))
                    else:
                        vals.append(None)
                b1[card] = vals

        elif section == "b2":
            m = b2_row.match(line)
            if m:
                card = m.group(1)
                cells = m.group(2)
                p_vals[card] = float(m.group(3))
                vals = []
                for cell in cells.split("|"):
                    cell = cell.strip()
                    num_m = re.search(r"([\d,]+\.?\d*)\s*s", cell)
                    if num_m:
                        vals.append(float(num_m.group(1).replace(",", "")))
                    else:
                        vals.append(None)
                b2[card] = vals

    return b1, b2, p_vals


def make_chart(b1, b2, p_vals, lang):
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(12.5, 5.2), gridspec_kw={"width_ratios": [3.2, 1.0]}
    )

    n_res = len(RES_LABELS)
    n_cards = len(CARDS)
    bar_w = 0.18
    x_base = list(range(n_res))

    # —— 左图：堆叠柱（采样 + 固定开销）——
    for ci, (card, color, cap) in enumerate(CARDS):
        offsets = [x + (ci - n_cards / 2 + 0.5) * bar_w for x in x_base]
        for ri in range(n_res):
            e2e = b1.get(card, [None] * n_res)[ri]
            samp = b2.get(card, [None] * n_res)[ri]
            if e2e is None:
                continue
            if samp is not None:
                overhead = e2e - samp
                ax1.bar(offsets[ri], samp, bar_w, color=color, edgecolor="white",
                        linewidth=0.5, zorder=3)
                ax1.bar(offsets[ri], overhead, bar_w, bottom=samp,
                        color=color, alpha=0.25, edgecolor="white",
                        linewidth=0.5, zorder=3)
            else:
                ax1.bar(offsets[ri], e2e, bar_w, color=color, edgecolor="white",
                        linewidth=0.5, zorder=3, alpha=0.5)

    ax1.set_xticks(x_base)
    ax1.set_xticklabels(RES_LABELS, fontsize=8.5, color=MUTED)
    ax1.set_ylabel("端到端耗时 (秒)" if lang == "zh" else "End-to-end time (s)",
                   fontsize=10, color=INK)
    ax1.set_title(
        "B-1 端到端 = 采样段 + 固定开销" if lang == "zh"
        else "B-1 End-to-end = Sampling + Fixed overhead",
        fontsize=11, color=INK, pad=10)
    ax1.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax1.set_axisbelow(True)
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax1.spines[s].set_color("#D1D5DB")

    # 图例
    from matplotlib.patches import Patch
    legend_items = []
    for card, color, cap in CARDS:
        legend_items.append(Patch(facecolor=color, edgecolor="white",
                                  label=f"{card} {cap}"))
    legend_items.append(Patch(facecolor=MUTED, alpha=0.25, edgecolor="white",
                              label="固定开销" if lang == "zh" else "Fixed overhead"))
    ax1.legend(handles=legend_items, loc="upper left", frameon=False, fontsize=8.5,
               ncol=2, borderpad=0.3)

    # 标注 p 值（放在左图右上空白区，不压标题也不压柱条）
    ax1.text(0.98, 0.96,
             f"采样段 p ≈ {p_vals.get('B50', 0):.2f} 至 {p_vals.get('B65', 0):.2f}（对像素）"
             if lang == "zh"
             else f"Sampling p ≈ {p_vals.get('B50', 0):.2f}–{p_vals.get('B65', 0):.2f} (vs pixels)",
             transform=ax1.transAxes, ha="right", va="top",
             fontsize=8.5, color=MUTED)

    # —— 右图：采样占比折线 ——
    for card, color, cap in CARDS:
        samp_pct = []
        for ri in range(n_res):
            e2e = b1.get(card, [None] * n_res)[ri]
            samp = b2.get(card, [None] * n_res)[ri]
            if e2e and samp:
                samp_pct.append(samp / e2e * 100)
            else:
                samp_pct.append(None)
        valid_x = [x_base[i] for i in range(n_res) if samp_pct[i] is not None]
        valid_y = [samp_pct[i] for i in range(n_res) if samp_pct[i] is not None]
        ax2.plot(valid_x, valid_y, marker="o", ms=5, lw=1.8, color=color,
                 mec="white", mew=1.2, zorder=3, label=f"{card} {cap}")

    ax2.set_xticks(x_base)
    ax2.set_xticklabels(RES_LABELS, fontsize=7, color=MUTED, rotation=30)
    ax2.set_ylabel("采样占比 (%)" if lang == "zh" else "Sampling share (%)",
                   fontsize=10, color=INK)
    ax2.set_title("B-2 采样占比" if lang == "zh" else "B-2 Sampling share",
                  fontsize=11, color=INK, pad=10)
    ax2.set_ylim(0, 100)
    ax2.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax2.set_axisbelow(True)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax2.spines[s].set_color("#D1D5DB")
    ax2.legend(loc="upper left", frameon=False, fontsize=8, borderpad=0.3)

    fig.tight_layout()
    matplotlib.rcParams["svg.hashsalt"] = "intel-arc-b-series"
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", facecolor="white", metadata={"Date": None})
    plt.close(fig)
    return buf.getvalue()


def main():
    # 数据从中文版解析（数字相同，英文版仅标签不同）
    b1, b2, p_vals = parse_table_b(DOC["zh"])
    assert b1.get("B70", [None])[0] == 152.54, f"B70 480p: {b1.get('B70')}"
    assert b1.get("B50", [None])[5] == 2259.86, f"B50 1080p: {b1.get('B50')}"
    assert b2.get("B70", [None])[0] == 39.00, f"B70 sampling: {b2.get('B70')}"

    for lang in ("zh", "en"):
        svg_bytes = make_chart(b1, b2, p_vals, lang)
        out = OUT[lang]
        out.write_bytes(svg_bytes.replace(b"\r\n", b"\n"))
        print(f"wrote {out.name} ({out.stat().st_size} B)")
    for card, _, _ in CARDS:
        print(f"  {card}: B-1={b1.get(card)}  B-2={b2.get(card)}  p={p_vals.get(card)}")


if __name__ == "__main__":
    main()
