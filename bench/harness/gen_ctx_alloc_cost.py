#!/usr/bin/env python
"""由 docs/server-config.md §5.2/§7.1/§7.2 直出「-c 分配 vs 溢出 + 多模态等待」双面板图。

左：decode tok/s 对 `-c` 五档 —— B60（装得下）走平，B50（装不下）从 64K 起塌，
    B50 各点下方标共享溢出量（README 口径 B 同一术语）。
右：多模态首图 / 同图追问等待（冷态，log 刻度）。
数字取自 zh 文档表（中英同数），取不到就报错。
输出 docs/assets/ctx-alloc-cost{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "server-config.md"
OUT = {l: ROOT / "docs" / "assets" / f"ctx-alloc-cost{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_B60, C_B50 = "#1B7F79", "#C2410C"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")
TIERS = [16384, 32768, 65536, 131072, 262144]
LABELS = ["16K", "32K", "64K", "128K", "256K"]

TXT = {
    "zh": dict(title="`-c` 是容量旋钮：装得下走平，装不下看溢出",
               sub="Qwen3.6-35B-A3B · Q4_0 · llama-server 交付配置（B60 `-ncmoe 0` / B50 `-ncmoe 8`）",
               p1="decode（tok/s）", p2="多模态等待（秒 · 冷态 · log 刻度）",
               g1="首图（冷态）", g2="同图追问",
               spill="共享 {v:,} MB", span="全距 1.6%",
               l1="B60 24G（装得下）", l2="B50 16G（装不下）",
               foot="B60 五档全距 1.6%、共享溢出最高 566 MB；B50 从 64K 起塌、共享溢出涨到 7,160 MB"
                    " —— 决定速度的是溢出量，不是 `-c`。"),
    "en": dict(title="`-c` is a capacity knob: flat when it fits, spill when it doesn't",
               sub="Qwen3.6-35B-A3B · Q4_0 · llama-server delivery config (B60 `-ncmoe 0` / B50 `-ncmoe 8`)",
               p1="decode (tok/s)", p2="Multimodal wait (s · cold · log scale)",
               g1="First image (cold)", g2="Follow-up",
               spill="spill {v:,} MB", span="1.6% span",
               l1="B60 24G (fits)", l2="B50 16G (doesn't fit)",
               foot="B60 spans 1.6% across five tiers with spill capped at 566 MB; B50 collapses from 64K"
                    " as spill grows to 7,160 MB —\nspeed follows the spill, not the `-c` number."),
}


def cells(ln):
    return [c.strip() for c in ln.split("|")]


def fnum(s):
    return float(re.sub(r"[^\d.]", "", s.split("/")[0]))


def parse():
    t = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    sec71 = t.split("### 7.1")[1].split("### 7.2")[0]
    b60 = {}
    for ln in sec71.splitlines():
        c = cells(ln)
        if len(c) > 8 and c[1] in {str(x) for x in TIERS}:
            b60[int(c[1])] = (fnum(c[7]), int(re.sub(r"[^\d]", "", c[5])),
                              int(re.sub(r"[^\d]", "", c[6])))
    pair = {}
    for ln in sec71.splitlines():
        c = [x.replace("*", "") for x in cells(ln)]
        if len(c) == 5 and c[1] in {str(x) for x in TIERS} and re.fullmatch(r"[\d.]+", c[2] or ""):
            pair[int(c[1])] = (float(c[2]), float(c[3]))
    sec52 = t.split("### 5.2")[1].split("**结论**")[0]
    spill = {}
    for ln in sec52.splitlines():
        c = cells(ln)
        if len(c) > 6 and c[1] in {str(x) for x in TIERS}:
            spill[int(c[1])] = int(re.sub(r"[^\d]", "", c[4]))
    sec72 = t.split("### 7.2")[1].split("### 7.3")[0]
    first = follow = None
    for ln in sec72.splitlines():
        if "首张图墙钟" in ln:
            first = [float(x) for x in re.findall(r"\d+\.\d+", ln)][:2]
        if "同图追问" in ln:
            follow = [float(x) for x in re.findall(r"\d+\.\d+", ln)][:2]
    assert len(b60) == 5 and len(pair) == 4 and len(spill) == 4, (b60, pair, spill)
    assert first and follow and len(first) == 2 and len(follow) == 2, (first, follow)
    return b60, pair, spill, first, follow


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

    b60, pair, spill, first, follow = parse()
    # first = [B50, B60]，follow = [B50, B60]（表列序：B50 | B60）
    f50, f60 = first
    w50, w60 = follow
    assert f50 > f60 * 3 and w50 > w60, (first, follow)

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.2), dpi=96,
                                      gridspec_kw=dict(width_ratios=[1.25, 1]))
        fig.patch.set_facecolor("white")
        for a in (ax, ax2):
            a.set_facecolor("white")

        xs = list(range(5))
        ax.plot(xs, [b60[x][0] for x in TIERS], marker="o", ms=7, lw=2.1,
                color=C_B60, label=t["l1"])
        bx = [i for i, x in enumerate(TIERS) if x in pair]
        by = [pair[x][0] for x in TIERS if x in pair]
        ax.plot(bx, by, marker="o", ms=7, lw=2.1, color=C_B50, label=t["l2"])
        for i, x in enumerate(TIERS):
            if x in spill:
                ax.text(i, pair[x][0] - 4.6, t["spill"].format(v=spill[x]),
                        ha="center", fontsize=8.2, color=C_B50)
        ax.text(2, 56.5, t["span"], ha="center", fontsize=9.5, color=C_B60, weight="bold")
        ax.set_xticks(xs)
        ax.set_xticklabels(LABELS, fontsize=9.5)
        ax.set_xlim(-0.4, 4.4)
        ax.set_ylim(0, 64)
        ax.set_xlabel("`-c`", fontsize=10.5, color=INK)
        ax.set_title(t["p1"], fontsize=11.5, color=INK, pad=12, weight="bold")
        ax.grid(axis="y", color=GRID, lw=0.9)
        ax.set_axisbelow(True)
        ax.legend(frameon=False, fontsize=9, loc="lower left")
        ax.tick_params(labelsize=9)

        gx = [0, 1]
        w = 0.32
        ax2.bar([i - w / 2 for i in gx], [f60, w60], w, color=C_B60, label=t["l1"])
        ax2.bar([i + w / 2 for i in gx], [f50, w50], w, color=C_B50, label=t["l2"])
        for i, v in zip([i - w / 2 for i in gx], [f60, w60]):
            ax2.text(i, v * 1.18, f"{v:g}", ha="center", fontsize=9.5,
                     color=C_B60, weight="bold")
        for i, v in zip([i + w / 2 for i in gx], [f50, w50]):
            ax2.text(i, v * 1.18, f"{v:g}", ha="center", fontsize=9.5,
                     color=C_B50, weight="bold")
        ax2.set_yscale("log")
        ax2.set_ylim(0.1, 500)
        ax2.set_xticks(gx)
        ax2.set_xticklabels([t["g1"], t["g2"]], fontsize=9.5)
        ax2.set_title(t["p2"], fontsize=11.5, color=INK, pad=12, weight="bold")
        ax2.grid(axis="y", color=GRID, lw=0.9)
        ax2.set_axisbelow(True)
        ax2.legend(frameon=False, fontsize=9, loc="upper right")
        ax2.tick_params(labelsize=9)

        for a in (ax, ax2):
            for s in ("top", "right"):
                a.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                a.spines[s].set_color(MUTED)

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.90, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom",
                 fontsize=9.2, color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.06, right=0.985, top=0.72, bottom=0.19, wspace=0.24)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes")


if __name__ == "__main__":
    main()
