#!/usr/bin/env python
"""MiniMax H3 三档驻留结构原理图（32 / 24 / 16 GB）。

「装得下」按组合算：DiT 19.53 GB + 32B 文本编码器。三列显示 DiT 块在卡内/主机侧的分布
（块高按 GiB 等比），卸载的代价是每轮一次的装载（≈1.9 s/GB），不是每步。
数据见 README 表；逐档拆解见 docs/comfyui-h3.md。
输出 docs/assets/h3-residency{,.en}.svg（纯 LF）。
"""
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = {l: ROOT / "docs" / "assets" / f"h3-residency{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED = "#2C2C2A", "#5F5E5A"
C_CARD, C_HOST, C_TE = "#2F6FBA", "#C2410C", "#7A5AA8"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

DIT = 19.53          # DiT 权重 GB（int8fix 栈）
TE = "32B 文本编码器"  # nvfp4 档，每轮装载一次
S = 0.1187           # 块高换算：3.7 单位 = 31.16 GiB，卡顶不要戳进主机区
COLS = [  # (卡名, 可见 GiB, 卡内 DiT GB, 卸载 GB, 下方标签)
    ("B70 · 31.16 GiB", 31.16, 19.53, 0.0, None),
    ("B60 · 23.33 GiB", 23.33, 15.83, 3.7, None),
    ("B50 · 15.51 GiB", 15.51, 6.53, 13.0, None),
]

TXT = {
    "zh": dict(title="「装得下」按组合算：DiT 19.53 GB ＋ 32B 文本编码器",
               sub="MiniMax H3 · 864×480 · 6 步 · 各档端到端与固定开销占比见上表",
               host="主机内存 / 页面文件", te="文本编码器\n每轮装载",
               spill="卸 {v:g} GB", oncard="DiT {v:g} GB 上卡", full="DiT 19.53 GB 全驻",
               conn="每轮搬运", card="卡",
               tags=["优化：省装载", "采样开始值钱", "优化翻转：压采样"],
               arrow="越往右：装载越重，优化的钱该花在采样上",
               foot="卸载的代价是每轮一次的装载（约 1.9 s/GB），不是每步；逐档拆解见 docs/comfyui-h3.md。"),
    "en": dict(title="\"Fits\" is judged per combination: DiT 19.53 GB + a 32B text encoder",
               sub="MiniMax H3 · 864×480 · 6 steps · end-to-end and fixed-overhead share per tier in the table above",
               host="Host RAM / page file", te="Text encoder\nloaded every run",
               spill="{v:g} GB offloaded", oncard="DiT {v:g} GB on card", full="DiT 19.53 GB fully resident",
               conn="per-run swap", card="card",
               tags=["Optimize: fewer loads", "Sampling starts to pay", "Priority flips: compress sampling"],
               arrow="Rightward: heavier loading — spend the tuning budget on sampling",
               foot="Offload costs one load per run (≈1.9 s/GB), not per step; per-tier breakdown in docs/comfyui-h3.md."),
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
        t = TXT[lang]
        fig, ax = plt.subplots(figsize=(9.4, 4.9), dpi=96)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")
        ax.set_xlim(0, 10.6)
        ax.set_ylim(0, 10.6)
        ax.axis("off")

        # 主机侧虚线区
        ax.add_patch(FancyBboxPatch((0.35, 5.95), 9.9, 3.35, boxstyle="round,pad=0.08",
                                    fc="#FCFCFB", ec=MUTED, lw=1.1, linestyle=(0, (4, 3))))
        ax.text(0.6, 8.95, t["host"], fontsize=9.5, color=MUTED, weight="bold")

        bases = 0.35, 5.45
        for i, (name, vram, oncard, spill, _) in enumerate(COLS):
            cx = 1.85 + i * 3.45
            x0 = cx - 1.25
            card_h = vram * S
            card_y = 1.95
            # 卡
            ax.add_patch(FancyBboxPatch((x0, card_y), 2.5, card_h, boxstyle="round,pad=0.06",
                                        fc="#F7F9FC", ec=INK, lw=1.4))
            # 卡内 DiT 块
            bh = oncard * S
            ax.add_patch(FancyBboxPatch((x0 + 0.18, card_y + 0.15), 2.14, bh,
                                        boxstyle="round,pad=0.04", fc="#D6E4F7", ec=C_CARD, lw=1.1))
            label = t["full"] if spill == 0 else t["oncard"].format(v=oncard)
            ax.text(cx, card_y + 0.15 + bh / 2, label, ha="center", va="center",
                    fontsize=8.6, color=INK, weight="bold")
            # 主机侧：卸载块 + 文本编码器块
            hy = 6.25
            if spill > 0:
                sh = spill * S
                ax.add_patch(FancyBboxPatch((x0 + 0.18, hy + 0.85), 2.14, sh,
                                            boxstyle="round,pad=0.04", fc="#FADBD3",
                                            ec=C_HOST, lw=1.1))
                ax.text(cx, hy + 0.85 + sh / 2, t["spill"].format(v=spill), ha="center",
                        va="center", fontsize=8.6, color=INK, weight="bold")
            ax.add_patch(FancyBboxPatch((x0 + 0.18, hy), 2.14, 0.72, boxstyle="round,pad=0.04",
                                        fc="#E8E0F2", ec=C_TE, lw=1.1))
            ax.text(cx, hy + 0.36, t["te"], ha="center", va="center", fontsize=7.8, color=INK)
            # 连接虚线（卡顶 ↔ 主机块底）
            ax.add_patch(FancyArrowPatch((cx, card_y + card_h), (cx, hy - 0.06),
                                         arrowstyle="<->", mutation_scale=11,
                                         color=MUTED, lw=1.3, linestyle=(0, (3, 2))))
            if i == 1:
                ax.text(cx + 0.15, (card_y + card_h + hy) / 2, t["conn"], fontsize=8,
                        color=MUTED, ha="left")
            # 卡名 + 下方标签
            ax.text(cx, 1.5, name, ha="center", fontsize=9.5, color=INK, weight="bold")
            ax.text(cx, 0.82, t["tags"][i], ha="center", fontsize=9.5,
                    color=C_HOST if i else C_CARD, weight="bold")

        # 底部方向箭头
        ax.add_patch(FancyArrowPatch((0.8, 0.3), (9.8, 0.3), arrowstyle="-|>",
                                     mutation_scale=15, color=MUTED, lw=1.4))
        ax.text(5.3, 0.02, t["arrow"], ha="center", fontsize=8.8, color=MUTED)

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.935, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9, color=INK)
        fig.subplots_adjust(left=0.01, right=0.99, top=0.87, bottom=0.06)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes")


if __name__ == "__main__":
    main()
