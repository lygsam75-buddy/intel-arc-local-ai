#!/usr/bin/env python
"""由 docs/comfyui-h3.md §五 的功耗与电费数字直出「功耗悖论」图。

左：满载功率（B65 低约 30%）；右：一条 1080p·5 秒的耗电（B65 反而更高）。
耗电两数取自 docs/comfyui-power.md 的「B65 比 B70 更费电」行（中英同构，取不到就报错）；
B65/B70 的 P90 见该文件复验段与 B70 卡页，写死并注明出处。
输出 docs/assets/h3-power-paradox{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
POW = {"zh": ROOT / "docs" / "comfyui-power.md", "en": ROOT / "docs" / "comfyui-power.en.md"}
OUT = {l: ROOT / "docs" / "assets" / f"h3-power-paradox{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_B65, C_B70 = "#2F6FBA", "#7A5AA8"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

TXT = {
    "zh": dict(title="低功耗卡在「按任务计费」时不省电",
               sub="MiniMax H3 · 1280×720 · 5 秒（124 帧）· 6 步",
               l=("满载功率 P90（W）", "B65 低 30%"),
               r=("一条 5 秒 1080p 的耗电（kJ）", "B65 反而更贵"),
               leg=("B65 32G", "B70 32G"),
               foot="B65 功率比 B70 低三成，同一条片子慢 58%，乘出来耗电更高 —— 只有「按小时租机、卡长期空转」时低功耗才划算。"),
    "en": dict(title="A lower-power card does not save money when you bill per job",
               sub="MiniMax H3 · 1280×720 · 5 s (124 frames) · 6 steps",
               l=("Full-load power P90 (W)", "B65 is 30% lower"),
               r=("Energy per 5 s 1080p clip (kJ)", "B65 costs more"),
               leg=("B65 32G", "B70 32G"),
               foot="The B65 draws 30% less power but takes 58% longer on the same clip,\nso the energy comes out higher — low power only pays when you rent by the hour and the card idles."),
}


def main():
    p65 = 201.0   # B65 满载 P90 约 201 W（comfyui-power.md 复验三档 200.3/201.8/204.3 的量级）
    P70 = 290.0   # B70 满载 P90，见 docs/comfyui-power.md / B70 卡页
    vals = {}
    for lang in ("zh", "en"):
        t = POW[lang].read_text(encoding="utf-8")
        # 耗电两数取自「B65 比 B70 更费电」行（同一条 1080p · 5 秒，中英同一行内构）
        m = re.search(r"B65\s*\*\*([\d.]+)\s*kJ[^\n]*?B70\s+([\d.]+)\s*kJ", t)
        if not m:
            raise SystemExit(f"cannot find B65/B70 kJ line in {POW[lang].name}")
        vals[lang] = (p65, float(m.group(1)), float(m.group(2)))

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
        p65, e65, e70 = vals[lang]
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(8.8, 4.3), dpi=96)
        fig.patch.set_facecolor("white")

        for a, (title, data, note) in zip(
                (ax, ax2),
                ((t["l"][0], [p65, P70], t["l"][1]),
                 (t["r"][0], [e65, e70], t["r"][1]))):
            a.set_facecolor("white")
            xs = [0, 1]
            a.bar(xs, data, 0.5, color=[C_B65, C_B70])
            for x, v in zip(xs, data):
                a.text(x, v * 1.02, f"{v:.0f}", ha="center", fontsize=11,
                       color=C_B65 if x == 0 else C_B70, weight="bold")
            a.set_xticks(xs)
            a.set_xticklabels(t["leg"], fontsize=10)
            a.set_ylim(0, max(data) * 1.32)
            a.set_title(title, fontsize=11.5, color=INK, pad=12, weight="bold")
            a.text(0.5, max(data) * 1.16, note, ha="center", fontsize=10,
                   color=C_MARK if False else "#B03A2E", weight="bold")
            a.grid(axis="y", color=GRID, lw=0.9)
            a.set_axisbelow(True)
            for s in ("top", "right"):
                a.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                a.spines[s].set_color(MUTED)

        fig.suptitle(t["sub"], fontsize=10, color=MUTED, y=0.975)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.2, color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.075, right=0.97, top=0.80, bottom=0.19, wspace=0.28)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size,
              "P65", p65, "E65", e65, "E70", e70)


if __name__ == "__main__":
    main()
