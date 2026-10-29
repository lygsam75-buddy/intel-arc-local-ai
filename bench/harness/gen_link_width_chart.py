#!/usr/bin/env python
"""由 bench/data/*.json 直出「链路宽度什么时候才算钱」图（负效益口径）。

B50 16G · Q4_0 · 同一份模型只改 `-ncmoe`：副槽 x4 相对主槽 x8 的吞吐变化。
柱高 = (x4 解码 ÷ x8 解码 - 1) x 100% —— 以主槽 x8 为 0 基准，负数 = 副槽丢掉的吞吐。
阴影 = 噪声带（副槽自己重复测的极差 13.9%）：柱落在带里 -> 槽位不值钱。
输出 docs/assets/link-width-when{,.en}.svg（纯 LF）。
"""
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "bench" / "data"
OUT = {l: ROOT / "docs" / "assets" / f"link-width-when{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_BAR, C_NOISE, C_MARK = "#2F6FBA", "#B8B4AA", "#B03A2E"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")
NOISE_PCT = 13.9   # 副槽自己重复测的极差（见 docs/slot-comparison.md）


def dec(name):
    doc = json.loads((D / name).read_text(encoding="utf-8"))
    return float(doc["summary"]["decode_tok_s"])


# (档位, 主槽 x8 文件, 副槽 x4 文件) —— 4/8 用同批 scan，5/6/7 用同批 fine
LADDER = [
    ("-ncmoe 4", "2026-10-15_b50-16g-ncmoe-scan-pcie5x8-ncmoe4.json",
     "2026-10-15_b50-16g-ncmoe-scan-pcie4x4-ncmoe4.json"),
    ("-ncmoe 5", "2026-10-15_b50-16g-ncmoe-fine-pcie5x8-ncmoe5.json",
     "2026-10-15_b50-16g-ncmoe-fine-pcie4x4-ncmoe5.json"),
    ("-ncmoe 6", "2026-10-15_b50-16g-ncmoe-fine-pcie5x8-ncmoe6.json",
     "2026-10-15_b50-16g-ncmoe-fine-pcie4x4-ncmoe6.json"),
    ("-ncmoe 7", "2026-10-15_b50-16g-ncmoe-fine-pcie5x8-ncmoe7.json",
     "2026-10-15_b50-16g-ncmoe-fine-pcie4x4-ncmoe7.json"),
    ("-ncmoe 8", "2026-10-15_b50-16g-ncmoe-scan-pcie5x8-ncmoe8.json",
     "2026-10-15_b50-16g-ncmoe-scan-pcie4x4-ncmoe8.json"),
]

TXT = {
    "zh": dict(
        title="装得下时槽位不值钱；权重一跨界搬运，链路宽度就变成倍数级",
        sub="B50 16G · Q4_0 · 同一份模型只改 `-ncmoe` · 柱 = 副槽 x4 相对主槽 x8 丢掉多少吞吐（0 = 主槽 x8）",
        x="-ncmoe（卸多少层专家到 CPU）", y="副槽 x4 相对主槽 x8 的吞吐变化",
        band="噪声带：副槽重复测极差 13.9%",
        l_lo="装得下：丢的在噪声里", l_hi="装不下：权重跨 PCIe",
        foot="先装得下，再谈带宽：装不进显存时比的是 CPU、内存带宽和 PCIe 通道，卡标称的带宽一个都用不上。"),
    "en": dict(
        title="Link width costs nothing while it fits; once weights cross PCIe it is multiplicative",
        sub="B50 16G · Q4_0 · same model, only `-ncmoe` changes · bar = throughput lost by the x4 slot against the x8 baseline (0 = x8)",
        x="-ncmoe (expert layers offloaded to CPU)", y="Throughput change, x4 slot vs x8",
        band="Noise band: 13.9% spread from repeats",
        l_lo="Fits: the loss is inside the noise", l_hi="Does not fit: weights cross PCIe",
        foot="Fit first, talk bandwidth second: when the model cannot fit in VRAM the contest is CPU, host memory and PCIe lanes — the card's rated bandwidth is unused."),
}


def main():
    labs, delta = [], []
    for lab, x8, x4 in LADDER:
        labs.append(lab)
        delta.append((dec(x4) / dec(x8) - 1) * 100)

    for fam in FONT:
        try:
            plt.rcParams["font.family"] = fam
            import matplotlib.font_manager as fm
            if any(f.name == fam for f in fm.fontManager.ttflist):
                break
        except Exception:
            pass
    plt.rcParams["axes.unicode_minus"] = False

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, ax = plt.subplots(figsize=(8.6, 4.5), dpi=96)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        ax.axhspan(-NOISE_PCT, 0, color=C_NOISE, alpha=0.30, zorder=1)
        ax.axhline(-NOISE_PCT, color=MUTED, lw=1.1, ls="--", zorder=2)
        ax.axhline(0, color=C_MARK, lw=1.4, zorder=2)

        xs = list(range(len(labs)))
        ax.bar(xs, delta, 0.56, color=C_BAR, zorder=3)
        for x, v in zip(xs, delta):
            ax.text(x, v - 4.2, f"{v:.0f}%" if v <= -10 else f"{v:.1f}%",
                    ha="center", va="top", fontsize=10.5, color=C_BAR, weight="bold")

        ax.text(0.02, 25, t["band"], ha="left", fontsize=9, color=MUTED)
        ax.annotate(t["l_lo"], xy=(4.32, delta[-1] / 2), xytext=(3.92, 20),
                    fontsize=10, color=C_MARK, ha="center",
                    arrowprops=dict(arrowstyle="->", color=C_MARK, lw=1.3))
        ax.annotate(t["l_hi"], xy=(-0.30, -42), xytext=(1.30, -84),
                    fontsize=10, color=C_BAR, ha="center",
                    arrowprops=dict(arrowstyle="->", color=C_BAR, lw=1.3))

        ax.set_xticks(xs)
        ax.set_xticklabels(labs, fontsize=10)
        ax.set_ylim(-95, 32)
        ax.set_xlabel(t["x"], fontsize=10.5, color=INK)
        ax.set_ylabel(t["y"], fontsize=10.5, color=INK)
        ax.set_title(t["title"], fontsize=13, color=INK, pad=16, weight="bold")
        ax.grid(axis="y", color=GRID, lw=0.9)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(MUTED)

        fig.suptitle(t["sub"], fontsize=10, color=MUTED, y=0.975)
        fig.text(0.5, 0.018, t["foot"], ha="center", fontsize=9.2, color=INK)
        fig.subplots_adjust(left=0.105, right=0.975, top=0.845, bottom=0.20)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes",
              " ".join(f"{l}:{s:.1f}%" for l, s in zip(labs, delta)))


if __name__ == "__main__":
    main()
