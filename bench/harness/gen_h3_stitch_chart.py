#!/usr/bin/env python
"""由 cards/B65-README.md 里那张 30 档实测表生成「效率 vs 单条时长」图。

不手抄数字：分辨率 / 时长 / 像素·帧 / 端到端全部从文档表格解析（`✅` 通过档，
`░` 判死档正则天然跳过），效率 = 像素·帧(M) ÷ 端到端分钟。表改了重跑本脚本即可。
（README 的汇总版只留主流分辨率，30 档全表的唯一出处是 B65 单卡页。）

输出 docs/assets/h3-stitch-efficiency{,.en}.svg（纯 LF）。
"""
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "cards" / "B65-README.md"
OUT_ZH = ROOT / "docs" / "assets" / "h3-stitch-efficiency.svg"
OUT_EN = ROOT / "docs" / "assets" / "h3-stitch-efficiency.en.svg"

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
COLORS = {"864×480": "#8A8880", "1280×720": "#2F6FBA",
          "1920×1088": "#E8873B", "2560×1440": "#0F766E"}
LABEL = {"zh": {"864×480": "480p", "1280×720": "720p",
                "1920×1088": "1080p", "2560×1440": "1440p"},
         "en": {"864×480": "480p", "1280×720": "720p",
                "1920×1088": "1080p", "2560×1440": "1440p"}}

TXT = {
    "zh": dict(
        title="镜头越长，每分钟出得越少 —— 长片靠接片",
        sub="B65 32G · MiniMax H3 · 6 步 · 30 档实测。纵轴 = 每分钟出多少 M「像素 × 帧」",
        xlabel="单条时长（秒）", ylabel="效率（M 像素·帧 / 分钟）",
        stitch="接片：5 段 × 5 秒 = 25 秒成片，效率仍是 13.0",
        foot="成本对「像素 × 帧」是超线性的（p ≈ 1.7），所以把长镜头拆成 5 秒段接起来，比硬生成一条省一半时间。",
    ),
    "en": dict(
        title="The longer the clip, the less you get per minute — stitch instead",
        sub="B65 32G · MiniMax H3 · 6 steps · 30 tiers measured. Y = M of pixels × frames per minute",
        xlabel="Clip length (s)", ylabel="Efficiency (M px·frames / min)",
        stitch="Stitching: five 5 s clips = a 25 s result, still at 13.0",
        foot="Cost is super-linear in pixels × frames (p ≈ 1.7), so five 5-second clips beat one long clip by about half.",
    ),
}


def parse():
    """从 B65 单卡页的 30 档表里取通过档：(分辨率, 时长秒, 一条要等分钟, 效率)。

    行格式：| 分辨率 | 帧数 | 时长 | 像素·帧 | DiT 卸载 | ✅ 端到端 |；
    `░` 判死行没有 `✅`，正则天然不匹配，会被跳过。
    """
    pat = re.compile(
        r"\|\s*\*{0,2}(\d+)×(\d+)\*{0,2}\s*\|"     # 分辨率
        r"\s*\*{0,2}[\d,]+\*{0,2}\s*\|"            # 帧数
        r"\s*\*{0,2}([\d.]+)\s*秒\*{0,2}\s*\|"     # 时长
        r"\s*\*{0,2}([\d.]+)\s*M\*{0,2}\s*\|"      # 像素·帧
        r"[^|]*\|"                                 # DiT 卸载
        r"\s*✅[^|]*?([\d,]+\.\d+)\s*s")            # 端到端
    out = []
    for m in pat.finditer(SRC.read_text(encoding="utf-8")):
        res = f"{m.group(1)}×{m.group(2)}"
        if res in COLORS:
            dur = float(m.group(3))
            px = float(m.group(4))
            e2e = float(m.group(5).replace(",", ""))
            mins = e2e / 60
            out.append((res, dur, mins, px / mins))
    return out


def main():
    pts = [p for p in parse() if p[1] >= 5]
    if len(pts) < 8:
        raise SystemExit(f"只解析到 {len(pts)} 个通过档，检查表格格式")
    # 中文字体
    for fam in ("Microsoft YaHei", "SimHei", "Noto Sans SC"):
        if any(f.name == fam for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = fam
            break
    plt.rcParams["axes.unicode_minus"] = False

    for lang, out in (("zh", OUT_ZH), ("en", OUT_EN)):
        t = TXT[lang]
        fig, ax = plt.subplots(figsize=(6.8, 3.9), dpi=96)
        ax.set_facecolor("white")
        fig.patch.set_facecolor("white")

        for res in COLORS:
            sub = sorted([p for p in pts if p[0] == res], key=lambda x: x[1])
            if not sub:
                continue
            xs = [p[1] for p in sub]
            ys = [p[3] for p in sub]
            if len(sub) >= 2:
                ax.plot(xs, ys, marker="o", ms=4.5, lw=1.6, color=COLORS[res],
                        label=LABEL[lang][res], zorder=3)
            else:
                ax.plot(xs, ys, marker="o", ms=5, ls="none", color=COLORS[res],
                        label=LABEL[lang][res], zorder=3)
            # 只在首末点标数，避免拥挤
            for idx in (0, len(sub) - 1):
                ax.annotate(f"{ys[idx]:.1f}", (xs[idx], ys[idx]),
                            textcoords="offset points", xytext=(0, 7),
                            ha="center", fontsize=8.5, color=COLORS[res], zorder=4)

        ax.axhline(13.0, color="#C2410C", lw=1.1, ls=(0, (4, 3)), zorder=2)
        ax.annotate(t["stitch"], xy=(34, 13.0), xytext=(34, 13.55),
                    fontsize=8.5, color="#C2410C", ha="center")

        ax.set_xlim(0, 53)
        ax.set_ylim(6, 14.2)
        ax.set_xlabel(t["xlabel"], fontsize=9, color=MUTED)
        ax.set_ylabel(t["ylabel"], fontsize=9, color=MUTED)
        ax.grid(axis="y", color=GRID, lw=1)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#B4B2A9")
        ax.tick_params(colors=MUTED, labelsize=8.5)
        ax.legend(frameon=False, fontsize=8.5, loc="lower left", ncol=4,
                  handlelength=1.2, columnspacing=1.2)

        fig.text(0.012, 0.975, t["title"], fontsize=11.5, weight="bold", color=INK, va="top")
        fig.text(0.012, 0.925, t["sub"], fontsize=8.2, color=MUTED, va="top")
        fig.text(0.012, 0.028, t["foot"], fontsize=8.2, color=MUTED, va="bottom")
        fig.subplots_adjust(left=0.085, right=0.985, top=0.845, bottom=0.20)
        fig.savefig(out, format="svg", transparent=False)
        plt.close(fig)
        p = Path(out)        # matplotlib 在 Windows 上写 CRLF，SVG 要纯 LF
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
        print(f"wrote {out.relative_to(ROOT)} ({p.stat().st_size} B) · {len(pts)} 个点")


if __name__ == "__main__":
    main()
