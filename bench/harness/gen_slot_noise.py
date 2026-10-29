#!/usr/bin/env python
"""由 docs/slot-comparison.md §3.2 配对表 + §3.3 离散度表 + §3.2 污染样本注
直出「副槽结论」单面板图：推荐工作点 -ncmoe 8 上，主槽 4 个干净样本
（极差/均值 1.6%）对副槽 3 个（13.9%），配对槽位差只有 −2.9%——
副槽自身的波动比槽位差还大 4.8 倍，x4 与 x8 在这个噪声水平下分不出差别。
污染样本 25.67（页面文件换入）以灰叉标出、不采用。
数字取不到就报错。输出 docs/assets/slot-noise{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "slot-comparison.md"
OUT = {l: ROOT / "docs" / "assets" / f"slot-noise{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_PRI, C_SEC, C_BAD = "#2F6FBA", "#C2410C", "#9A9891"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

TXT = {
    "zh": dict(
        title="副槽结论：槽位差 −2.9%，副槽自己的极差 13.9%",
        sub="B50 16G · Q4_0 19.41 GiB · -ncmoe 8（推荐工作点）· -r 3 干净样本 · decode tok/s · 2026-10-15",
        lpri="主槽 x8\nPCIE1 CPU 直连", lsec="副槽 x4\nPCIE2 芯片组",
        rng="极差/均值", gap="槽位差 −2.9%", bad="25.67 = 污染样本\n（页面文件换入）不采用",
        x="decode（tok/s）",
        foot="副槽重复测一次，波动比两个槽之间的差还大 4.8 倍——这个噪声水平下，x4 与 x8 统计上分不出差别。"),
    "en": dict(
        title="Second slot: the -2.9% slot gap is smaller than the slot's own 13.9% spread",
        sub="B50 16G · Q4_0 19.41 GiB · -ncmoe 8 (recommended working point) · -r 3 clean samples · decode tok/s · 2026-10-15",
        lpri="Primary x8\nPCIE1 CPU-attached", lsec="Second x4\nPCIE2 chipset",
        rng="range/mean", gap="slot gap -2.9%", bad="25.67 = polluted sample\n(pagefile swap) excluded",
        x="decode (tok/s)",
        foot="One repeat on the second slot swings 4.8x more than the gap between slots - at this noise, x4 and x8 are indistinguishable."),
}


def parse():
    t = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    s33 = t.split("### 3.3")[1].split("## 4")[0]
    lanes = {}
    for ln in s33.splitlines():
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.split("|")[1:-1]]
        if c[0] in ("主槽 x8", "副槽 x4") and c[0] not in lanes:
            vals = [float(v) for v in c[1].split("/")]
            rng = float(c[2].replace("*", "").replace("%", ""))
            lanes[c[0]] = (vals, rng)
    assert set(lanes) == {"主槽 x8", "副槽 x4"}, lanes
    (pv, pr), (sv, sr) = lanes["主槽 x8"], lanes["副槽 x4"]
    assert len(pv) == 4 and len(sv) == 3, lanes
    for vals, rng in lanes.values():
        got = (max(vals) - min(vals)) / (sum(vals) / len(vals)) * 100
        assert abs(got - rng) < 0.06, (vals, got, rng)
    assert (pr, sr) == (1.6, 13.9), (pr, sr)

    # 配对口径：-ncmoe 8 上 主槽 37.74 对 副槽 36.66 → −2.9%
    s32 = t.split("### 3.2")[1].split("### 3.3")[0]
    row = next(ln for ln in s32.splitlines()
               if ln.startswith("|") and "**8**" in ln and "36.66" in ln)
    c = [x.strip().replace("*", "") for x in row.split("|")[1:-1]]
    pri, sec = float(c[1]), float(c[2].split("（")[0])
    delta = (sec / pri - 1) * 100
    assert (pri, sec) == (37.74, 36.66), (pri, sec)
    assert abs(delta + 2.9) < 0.06, delta
    assert abs(sr / abs(delta) - 4.8) < 0.15, "副槽极差应为槽位差的 4.8 倍"

    pol = next(ln for ln in s32.splitlines() if "污染样本" in ln and "25.67" in ln)
    m = re.search(r"`-ncmoe 8`\s*=\s*([\d.]+)", pol)
    assert m and abs(float(m.group(1)) - 25.67) < 1e-9, pol
    return pv, sv, pri, sec, float(m.group(1))


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

    pv, sv, pri, sec, bad = parse()

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, ax = plt.subplots(figsize=(9.2, 3.9), dpi=96)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")
        ax.grid(axis="x", color=GRID, lw=0.9)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(MUTED)
        ax.tick_params(labelsize=9)
        ax.set_xlabel(t["x"], fontsize=9.5, color=INK)

        for y, vals, col, rng in ((1, pv, C_PRI, 1.6), (0, sv, C_SEC, 13.9)):
            ax.plot([min(vals), max(vals)], [y, y], color=col, lw=1.4, alpha=0.45)
            ax.plot(vals, [y] * len(vals), "o", ms=8, color=col, zorder=3)
            mean = sum(vals) / len(vals)
            ax.plot([mean, mean], [y - 0.09, y + 0.09], color=col, lw=2.0, zorder=3)
            ax.text(max(vals) + 0.45, y, f"{t['rng']} {rng}%", va="center",
                    fontsize=9.2, color=col, weight="bold")
        # 配对槽位差：主槽 37.74 对 副槽 36.66
        ax.plot([pri, sec], [1, 0], ls="--", lw=1.3, color=MUTED, zorder=2)
        ax.plot([pri], [1], "o", ms=11, mfc="none", mec=INK, mew=1.4, zorder=4)
        ax.plot([sec], [0], "o", ms=11, mfc="none", mec=INK, mew=1.4, zorder=4)
        ax.text(pri + 0.5, 0.5, t["gap"], fontsize=9.4, color=INK, weight="bold",
                va="center")
        # 污染样本
        ax.plot([bad], [0], "x", ms=9, mew=2.0, color=C_BAD, zorder=3)
        ax.text(bad, -0.4, t["bad"], fontsize=8.4, color=C_BAD, ha="center", va="top",
                linespacing=1.4)

        ax.set_yticks([1, 0])
        ax.set_yticklabels([t["lpri"], t["lsec"]], fontsize=9.2)
        ax.set_ylim(-1.05, 1.55)
        ax.set_xlim(23.5, 41.5)

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.905, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.2,
                 color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.115, right=0.98, top=0.72, bottom=0.24)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes",
              f"pri={pv} sec={sv} gap={sec/pri-1:+.3f} bad={bad}")


if __name__ == "__main__":
    main()
