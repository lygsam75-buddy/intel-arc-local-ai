#!/usr/bin/env python
"""由 docs/comfyui-power.md §3（B70 五档分辨率功耗）与 §3b（B60 三档）
直出「P90 不随分辨率变，变的是占空比」双面板图。

左：P90 vs 分辨率——B70 恒定 290.1~291.1 W（五档差 1 W）、B60 恒定 150~154 W
    （墙的 75~77%，随分辨率略降），两条平线对各自功耗墙（290 / 200 W）。
右：B70 占空比随分辨率 32% → 86%——功率不变，变的是「卡有多少时间真在干活」。
结论：满载贴墙是「装得下」的副作用；B60 装不下、装载段不在满载，所以吃不到墙。
数字取不到就报错。输出 docs/assets/power-duty{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "comfyui-power.md"
OUT = {l: ROOT / "docs" / "assets" / f"power-duty{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_B70, C_B60, C_WALL = "#C2410C", "#2F6FBA", "#9A9891"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

RES = ["864×480", "1024×576", "1280×720", "1536×864", "1920×1088"]
RES_EN = ["864×480", "1024×576", "1280×720", "1536×864", "1920×1088"]
SHORT = {"864×480": "480", "1024×576": "576", "1280×720": "720",
         "1536×864": "864", "1920×1088": "1088"}

TXT = {
    "zh": dict(
        title="P90 不随分辨率变，变的是占空比——贴墙是「装得下」的副作用",
        sub="MiniMax H3 · 6 步 · 5 秒 124 帧 · 整卡电源域能耗计数器 1 s 窗口积分 · 2026-10 口径",
        pa="满载 P90（W）——两条平线", pb="B70 占空比（%）：卡有多少时间真在干活",
        w70="290 W 墙", w60="200 W 墙",
        y1="P90（W）", x="分辨率（像素行）",
        s70="B70 290.1~291.1 W", s60="B60 150.5~154.3 W",
        duty="装载段不在满载 →\n占空比才是变的那个",
        foot="B70 五档 P90 差 1 W、占空比 32%→86%；B60 装不下、每轮搬权重，吃不到墙——"
             "贴墙是「装得下」的副作用。"),
    "en": dict(
        title="P90 does not move with resolution — the duty cycle does",
        sub="MiniMax H3 · 6 steps · 5 s / 124 frames · whole-card energy counter, 1 s window · 2026-10",
        pa="Full-load P90 (W) — two flat lines", pb="B70 duty cycle (%): real work per run",
        w70="290 W wall", w60="200 W wall",
        y1="P90 (W)", x="Resolution (pixel rows)",
        s70="B70 290.1-291.1 W", s60="B60 150.5-154.3 W",
        duty="Loading is not full load →\nthe duty cycle is what moves",
        foot="B70: five rungs differ by 1 W while duty climbs 32%→86%.\n"
             "The B60 moves weights every round and never reaches its wall — pinned to the wall is a side effect of fitting."),
}


def parse():
    t = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")

    # §3 B70 表
    s3 = t.split("## 3. H3 视频")[1].split("## 3b")[0]
    b70 = {}
    for ln in s3.splitlines():
        if not ln.startswith("|") or "×" not in ln:
            continue
        c = [x.strip() for x in ln.split("|")[1:-1]]
        if c[0] not in RES:
            continue
        p90 = float(re.search(r"(\d+\.\d+)\s*W", c[6]).group(1))
        duty = float(c[8].replace("%", ""))
        b70[c[0]] = (p90, duty)
    assert set(b70) == set(RES), b70
    assert abs(b70["864×480"][0] - 290.3) < 0.05 and abs(b70["1920×1088"][0] - 291.1) < 0.05, b70
    assert (b70["864×480"][1], b70["1920×1088"][1]) == (32, 86), b70

    # §3b B60 表（三档，P90 为区间）
    s3b = t.split("## 3b")[1].split("## 3c")[0]
    b60 = {}
    for ln in s3b.splitlines():
        if not ln.startswith("|") or "×" not in ln:
            continue
        c = [x.strip() for x in ln.split("|")[1:-1]]
        if c[0] not in ("864×480", "1280×720", "1920×1088"):
            continue
        ms = re.findall(r"(\d+\.\d+)\s*至\s*(\d+\.\d+)\s*W", c[4])
        assert ms, ln
        b60[c[0]] = (float(ms[0][0]) + float(ms[0][1])) / 2
    assert set(b60) == {"864×480", "1280×720", "1920×1088"}, b60
    assert abs(b60["864×480"] - 154.0) < 0.1 and abs(b60["1920×1088"] - 151.8) < 0.1, b60

    # 平线断言：五档 P90 极差 1 W 内
    span = max(v[0] for v in b70.values()) - min(v[0] for v in b70.values())
    assert span < 1.1, span
    return b70, b60


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

    b70, b60 = parse()

    for lang, reses in (("zh", RES), ("en", RES_EN)):
        t = TXT[lang]
        xs = list(range(len(reses)))
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.9), dpi=96)
        fig.patch.set_facecolor("white")
        for ax in (ax1, ax2):
            ax.set_facecolor("white")
            ax.grid(axis="y", color=GRID, lw=0.9)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                ax.spines[s].set_color(MUTED)
            ax.tick_params(labelsize=8.6)
            ax.set_xticks(xs)
            ax.set_xticklabels([SHORT[r] for r in reses], fontsize=8.6)
            ax.set_xlabel(t["x"], fontsize=9, color=INK)

        # 左：两条平线 + 墙
        ax1.axhline(290, color=C_WALL, lw=1.1, ls="--", zorder=1)
        ax1.axhline(200, color=C_WALL, lw=1.1, ls="--", zorder=1)
        y70 = [b70[r][0] for r in reses]
        ax1.plot(xs, y70, "o-", color=C_B70, lw=1.8, ms=6, zorder=3)
        y60 = [b60.get(r) for r in reses]
        xs60 = [x for x, v in zip(xs, y60) if v]
        ax1.plot(xs60, [v for v in y60 if v], "s-", color=C_B60, lw=1.8, ms=5.5,
                 zorder=3)
        ax1.set_xlim(-0.35, 4.5)
        # 墙标签贴右缘、画在轴内
        ax1.text(4.45, 296, t["w70"], fontsize=8.2, color=C_WALL,
                 ha="right", va="bottom")
        ax1.text(4.45, 206, t["w60"], fontsize=8.2, color=C_WALL,
                 ha="right", va="bottom")
        # 序列标签贴线首，不越出面板
        ax1.text(0, 312, t["s70"], fontsize=8.6, color=C_B70, weight="bold")
        ax1.text(0, 118, t["s60"], fontsize=8.6, color=C_B60, weight="bold")
        ax1.set_ylim(0, 355)
        ax1.set_ylabel(t["y1"], fontsize=9.5, color=INK)
        ax1.set_title(t["pa"], fontsize=10.5, color=INK, pad=8)

        # 右：B70 占空比
        duty = [b70[r][1] for r in reses]
        ax2.bar(xs, duty, width=0.55, color=C_B70, zorder=3)
        for x, v in zip(xs, duty):
            ax2.text(x, v + 2, f"{v:.0f}%", ha="center", fontsize=8.8,
                     color=INK, weight="bold")
        ax2.set_ylim(0, 118)
        ax2.set_title(t["pb"], fontsize=10.5, color=INK, pad=8)
        ax2.annotate(t["duty"], xy=(2, duty[2]), xytext=(1.35, duty[2] + 26),
                     fontsize=8.6, color=MUTED, ha="left",
                     arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.1))

        fig.suptitle(t["title"], fontsize=12.6, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.905, t["sub"], ha="center", fontsize=8.6, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.0,
                 color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.075, right=0.97, top=0.80, bottom=0.30,
                            wspace=0.26)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), "ok")


if __name__ == "__main__":
    main()
