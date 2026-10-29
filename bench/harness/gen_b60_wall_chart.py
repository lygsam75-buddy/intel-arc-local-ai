#!/usr/bin/env python
"""由 bench/data/2026-10-27_b60-bs-power-wall-144w.json 生成「达标率」柱状图。

达标率 = TF 用时 ÷ BS 用时（TF = 100%）。
输出 docs/cards/assets/b60-wall-recovery{,.en}.svg（纯 LF）。
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data" / "2026-10-27_b60-bs-power-wall-144w.json"
OUT_ZH = ROOT / "docs" / "cards" / "assets" / "b60-wall-recovery.svg"
OUT_EN = ROOT / "docs" / "cards" / "assets" / "b60-wall-recovery.en.svg"

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_120, C_144, C_TF = "#E8873B", "#2F6FBA", "#C2410C"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

TXT = {
    "zh": dict(title="出厂 120 W 只跑到 TF 的八成，拉满 144 W 就是 TF",
               sub="B60 BS · MiniMax H3 · 6 步 · 720p · 柱高 = TF 用时 ÷ BS 用时（TF = 100%）",
               leg=("出厂 120 W", "拉满 144 W"), ylab="BS 达到 TF 的百分比",
               foot="拉满后两条柱都顶到 100%：差距来自功耗墙，不是芯片。每片电 +6%，一条省 1.3 至 4.5 分钟。"),
    "en": dict(title="At the factory wall the BS runs at ~80% of the TF; pull it to 144 W and it IS the TF",
               sub="B60 BS · MiniMax H3 · 6 steps · 720p · bar height = TF time ÷ BS time (TF = 100%)",
               leg=("Factory 120 W", "Pulled to 144 W"), ylab="BS as % of TF",
               foot="Both bars reach 100%: the gap came from the power wall, not the chip. +6% energy per clip, saves 1.3–4.5 minutes."),
}


def main():
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    groups = []
    for t in doc["tiers"]:
        tf = t["tf_same_tier"]["server_s"]
        groups.append((t["label_zh"], t["label_en"],
                       tf / t["factory_120w"]["server_s"] * 100,
                       tf / t["pulled_144w"]["server_s"] * 100))

    for fam in FONT:
        try:
            plt.rcParams["font.family"] = fam
            import matplotlib.font_manager as fm
            if any(f.name == fam for f in fm.fontManager.ttflist):
                break
        except Exception:
            pass
    plt.rcParams["axes.unicode_minus"] = False

    for lang, out in (("zh", OUT_ZH), ("en", OUT_EN)):
        t = TXT[lang]
        fig, ax = plt.subplots(figsize=(6.8, 3.9), dpi=96)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        n = len(groups)
        xs = range(n)
        w = 0.32
        b1 = [g[2] for g in groups]
        b2 = [g[3] for g in groups]
        ax.bar([x - w / 2 for x in xs], b1, w, color=C_120, label=t["leg"][0], zorder=3)
        ax.bar([x + w / 2 for x in xs], b2, w, color=C_144, label=t["leg"][1], zorder=3)
        ax.axhline(100, color=C_TF, lw=1.2, ls=(0, (4, 3)), zorder=2)  # 图例里的 TF = 100%
        ax.plot([], [], color=C_TF, lw=1.2, ls=(0, (4, 3)), label="TF = 100%")

        for x, v in zip(xs, b1):
            ax.annotate(f"{v:.0f}%", (x - w / 2, v), textcoords="offset points",
                        xytext=(0, 5), ha="center", fontsize=9, weight="bold", color=INK)
        for x, v in zip(xs, b2):
            ax.annotate(f"{v:.0f}%", (x + w / 2, v), textcoords="offset points",
                        xytext=(0, 5), ha="center", fontsize=9, weight="bold", color=INK)

        ax.set_xticks(list(xs))
        ax.set_xticklabels([g[0] if lang == "zh" else g[1] for g in groups], fontsize=9)
        ax.set_ylim(0, 150)
        ax.set_yticks([0, 25, 50, 75, 100, 125])
        ax.set_ylabel(t["ylab"], fontsize=9, color=MUTED)
        ax.grid(axis="y", color=GRID, lw=1)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=8.5)
        ax.legend(frameon=False, fontsize=9, loc="upper right", bbox_to_anchor=(1.0, 1.02))

        fig.text(0.012, 0.975, t["title"], fontsize=11.5, weight="bold", color=INK, va="top")
        fig.text(0.012, 0.922, t["sub"], fontsize=8.2, color=MUTED, va="top")
        fig.text(0.012, 0.028, t["foot"], fontsize=8.2, color=MUTED, va="bottom")
        fig.subplots_adjust(left=0.085, right=0.985, top=0.85, bottom=0.16)
        fig.savefig(out, format="svg", transparent=False)
        plt.close(fig)
        p = Path(out)
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
        print(f"wrote {out.relative_to(ROOT)} ({p.stat().st_size} B)")


if __name__ == "__main__":
    main()
