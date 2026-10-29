#!/usr/bin/env python
"""由 docs/comfyui-h3.md §三 的「采样占比」表直出图（表本身来自 bench/data）。

x = 分辨率，y = 采样占端到端的比例，四条线 = 四张卡。
低分辨率卡在装载，高分辨率卡在算。
输出 docs/assets/h3-sampling-share{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOC = {"zh": ROOT / "docs" / "comfyui-h3.md", "en": ROOT / "docs" / "comfyui-h3.en.md"}
OUT = {l: ROOT / "docs" / "assets" / f"h3-sampling-share{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
SERIES = [("B70", "#7A5AA8"), ("B65", "#2F6FBA"), ("B60", "#1B7F79"), ("B50", "#C2410C")]
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

ROW = re.compile(r"^\|\s*(B\d\d)[^|]*\|(.+)\|\s*$")


def parse(path):
    """把 §三 的采样占比表读成 {卡: [值或 None]}，第一行是分辨率表头。"""
    head, rows = None, {}
    for ln in path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n"):
        if ln.startswith("| 卡 |") or ln.startswith("| Card |"):
            head = [c.strip() for c in ln.strip().strip("|").split("|")][1:]
            continue
        m = ROW.match(ln)
        if m and head:
            vals = []
            for c in m.group(2).split("|"):
                c = c.strip().replace("*", "")
                mm = re.search(r"([\d.]+)\s*%", c)
                vals.append(float(mm.group(1)) if mm else None)
            rows[m.group(1)] = vals
            if len(rows) == 4:
                break          # 只取「卡 | 分辨率」这一张表，别串到后面的表
    assert head and len(rows) == 4, (path, head, list(rows))
    return head, rows


TXT = {
    "zh": dict(title="低分辨率卡在装载，高分辨率卡在算",
               sub="MiniMax H3 · 6 步 · 5 秒（124 帧）· 采样段占端到端的比例",
               x="分辨率", y="采样占比（%）",
               foot="采样占比就是「换一张更快的卡」能拿到的上限：480p 只占 26 至 51%，端到端被固定开销封住；1080p 到 81 至 90%，才轮到算力说话。"),
    "en": dict(title="At low resolution the card is loading; at high resolution it is computing",
               sub="MiniMax H3 · 6 steps · 5 s (124 frames) · sampling as a share of end-to-end",
               x="Resolution", y="Sampling share (%)",
               foot="The sampling share is the ceiling on what a faster card can buy://nonly 26 to 51% at 480p, where fixed cost dominates; 81 to 90% at 1080p, where compute finally speaks."),
}


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

    for lang in ("zh", "en"):
        head, rows = parse(DOC[lang])
        t = TXT[lang]
        fig, ax = plt.subplots(figsize=(8.6, 4.5), dpi=96)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        xs = list(range(len(head)))
        ends = []
        for card, col in SERIES:
            ys = rows[card]
            pts = [(i, y) for i, y in enumerate(ys) if y is not None]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", ms=7,
                    lw=2.1, color=col, label=card)
            ends.append((pts[-1][1], pts[-1], col))
        # 线尾标签：按 y 从高到低等距排开（数据坐标），避免 81/85/87/90 挤成一堆
        ends.sort(key=lambda e: -e[0])
        top, step = ends[0][0] + 1.5, 3.2
        for k, (y, pt, col) in enumerate(ends):
            ax.text(pt[0] + 0.16, top - k * step, f"{y:.0f}%", fontsize=9.5,
                    color=col, weight="bold", va="center")

        ax.set_xticks(xs)
        ax.set_xticklabels(head, fontsize=9.5)
        ax.set_xlim(-0.4, len(head) - 0.45)
        ax.set_ylim(15, 100)
        ax.set_xlabel(t["x"], fontsize=10.5, color=INK)
        ax.set_ylabel(t["y"], fontsize=10.5, color=INK)
        ax.set_title(t["title"], fontsize=13, color=INK, pad=16, weight="bold")
        ax.grid(axis="y", color=GRID, lw=0.9)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(MUTED)
        ax.legend(frameon=False, fontsize=10, ncol=4, loc="upper left",
                  columnspacing=1.2, handlelength=1.5)

        fig.suptitle(t["sub"], fontsize=10, color=MUTED, y=0.975)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.2, color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.085, right=0.945, top=0.845, bottom=0.20)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes")


if __name__ == "__main__":
    main()
