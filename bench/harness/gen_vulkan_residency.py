#!/usr/bin/env python
"""「换后端」原理图：Vulkan 的收益只兑现在权重全驻显存时。

左：-ncmoe 0，权重全在卡上 —— 瓶颈是内核效率，Vulkan 1.5–1.7×。
右：-ncmoe 8，专家在主机 —— 每 token 跨 PCIe，瓶颈变成搬运，倍数塌回 1.1×。
结构性示意（框与箭头），数据见 README 表与 docs/server-config.md §8.5–8.6。
输出 docs/assets/vulkan-residency{,.en}.svg（纯 LF）。
"""
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = {l: ROOT / "docs" / "assets" / f"vulkan-residency{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED = "#2C2C2A", "#5F5E5A"
C_CARD, C_HOST, C_PCIE = "#2F6FBA", "#C2410C", "#B03A2E"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

TXT = {
    "zh": dict(title="Vulkan 的收益只兑现在权重全驻显存时",
               sub="同一个 llama.cpp build、同一条交付命令行，只换后端",
               p1="全驻：-ncmoe 0", p2="卸专家：-ncmoe 8",
               gpu="GPU · Xe2 核心", host="主机内存",
               w_all="权重 19.4 GB\n全在卡上", w_res="驻留权重", w_exp="专家权重 ≈3.8 GB",
               none="无权重搬运", pcie="每 token 都要跨 PCIe 搬专家",
               tag1="Vulkan / SYCL ≈ 1.5–1.7×", t1="瓶颈：内核效率",
               tag2="≈ 1.1×，长上下文甚至 0.64×", t2="瓶颈：PCIe 搬运（优势消失）",
               foot="逐卡倍数（1.22 / 1.68 / 1.68 / 1.52）与预填充（2.6–3.1×）见上表；机制详见 docs/server-config.md §8.5–8.6。"),
    "en": dict(title="Vulkan's gain only pays when weights stay resident",
               sub="Same llama.cpp build, same delivery command line — only the backend changes",
               p1="Resident: -ncmoe 0", p2="Experts offloaded: -ncmoe 8",
               gpu="GPU · Xe2 cores", host="Host RAM",
               w_all="19.4 GB of weights,\nall on card", w_res="Resident weights",
               w_exp="Expert weights ≈3.8 GB",
               none="no weight traffic", pcie="every token crosses PCIe",
               tag1="Vulkan / SYCL ≈ 1.5–1.7×", t1="bottleneck: kernel efficiency",
               tag2="≈ 1.1×, 0.64× at long context", t2="bottleneck: PCIe streaming (advantage gone)",
               foot="Per-card multipliers (1.22 / 1.68 / 1.68 / 1.52) and prefill (2.6–3.1×) in the table above; "
                    "mechanism in docs/server-config.md §8.5–8.6."),
}


def panel(ax, t, offload):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # 显卡
    ax.add_patch(FancyBboxPatch((0.4, 3.1), 4.5, 5.3, boxstyle="round,pad=0.08",
                                fc="white", ec=INK, lw=1.4))
    ax.text(2.65, 7.95, t["gpu"], ha="center", fontsize=10, color=INK, weight="bold")
    # 主机
    ax.add_patch(FancyBboxPatch((6.1, 3.1), 3.5, 5.3, boxstyle="round,pad=0.08",
                                fc="white", ec=MUTED, lw=1.2, linestyle=(0, (4, 3))))
    ax.text(7.85, 7.95, t["host"], ha="center", fontsize=10, color=MUTED, weight="bold")

    if not offload:
        ax.add_patch(FancyBboxPatch((0.85, 3.55), 3.6, 3.3, boxstyle="round,pad=0.06",
                                    fc="#D6E4F7", ec=C_CARD, lw=1.2))
        ax.text(2.65, 5.2, t["w_all"], ha="center", va="center", fontsize=9.5, color=INK)
        ax.add_patch(FancyBboxPatch((6.5, 5.4), 2.7, 1.4, boxstyle="round,pad=0.06",
                                    fc="#F4F4F2", ec=MUTED, lw=1.0, linestyle=(0, (3, 3))))
        ax.text(7.85, 6.1, "—", ha="center", va="center", fontsize=13, color=MUTED)
        ax.plot([5.05, 5.95], [4.6, 4.6], ls=(0, (3, 3)), color=MUTED, lw=1.2)
        ax.text(5.5, 4.15, t["none"], ha="center", fontsize=8.6, color=MUTED)
        ax.text(5.0, 2.05, t["tag1"], ha="center", fontsize=12.5, color=C_CARD, weight="bold")
        ax.text(5.0, 1.15, t["t1"], ha="center", fontsize=9.5, color=MUTED)
    else:
        ax.add_patch(FancyBboxPatch((0.85, 5.35), 3.6, 1.5, boxstyle="round,pad=0.06",
                                    fc="#D6E4F7", ec=C_CARD, lw=1.2))
        ax.text(2.65, 6.1, t["w_res"], ha="center", va="center", fontsize=9.5, color=INK)
        ax.add_patch(FancyBboxPatch((6.5, 4.7), 2.7, 2.15, boxstyle="round,pad=0.06",
                                    fc="#FADBD3", ec=C_HOST, lw=1.2))
        ax.text(7.85, 5.78, t["w_exp"], ha="center", va="center", fontsize=9.5, color=INK)
        ax.add_patch(FancyArrowPatch((5.0, 6.1), (6.45, 6.1), arrowstyle="<->",
                                     mutation_scale=16, color=C_PCIE, lw=2.2))
        ax.text(5.72, 7.1, t["pcie"], ha="center", fontsize=8.8, color=C_PCIE, weight="bold")
        ax.text(5.0, 2.05, t["tag2"], ha="center", fontsize=12.5, color=C_PCIE, weight="bold")
        ax.text(5.0, 1.15, t["t2"], ha="center", fontsize=9.5, color=MUTED)

    ax.text(5.0, 9.35, t["p1"] if not offload else t["p2"], ha="center",
            fontsize=11.5, color=INK, weight="bold")


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
        fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.6), dpi=96)
        fig.patch.set_facecolor("white")
        for ax, off in zip(axes, (False, True)):
            ax.set_facecolor("white")
            panel(ax, t, off)
        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.925, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom",
                 fontsize=9, color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.01, right=0.99, top=0.84, bottom=0.10, wspace=0.06)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes")


if __name__ == "__main__":
    main()
