#!/usr/bin/env python
"""由 bench/data/*.json 直出「Vulkan / SYCL 解码倍数」双面板图。

左：倍数随「权重驻留状态」塌 —— 全驻 > 近全驻 > 卸专家；长上下文反向。
右：倍数逐卡不同，不随核心数或带宽外推（解码 vs 预填充两条）。
输出 docs/assets/vulkan-multiplier{,.en}.svg（纯 LF）。
"""
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "bench" / "data"
OUT = {l: ROOT / "docs" / "assets" / f"vulkan-multiplier{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_B60, C_B70, C_B50, C_PREF = "#2F6FBA", "#1B7F79", "#C2410C", "#7A5AA8"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")


def load(name):
    doc = json.loads((D / name).read_text(encoding="utf-8"))
    s = doc["summary"]
    return float(s["decode_tok_s"]), float(s["prompt_tok_s"])


def ratio(vf, sf):
    return load(vf)[0] / load(sf)[0]


# ---- 左：驻留阶梯（Vulkan ÷ SYCL 解码）----
STATES = ["全驻\n(-ncmoe 0 / IQ2_M)", "近全驻\n(Q3_K_S · 溢 514 MB)", "卸专家\n(-ncmoe 8 / Q4_0)"]
CURVE = {
    "B60": [ratio("2026-10-20_b60-q4-0-vulkan.json", "2026-10-20_b60-q4-0-sycl-ocl.json"),
            None,
            ratio("2026-10-20_b60-q4-0-vulkan-ncmoe8.json", "2026-10-20_b60-q4-0-sycl-ncmoe8-r3.json")],
    "B70": [ratio("2026-10-20_b70-q4-0-vulkan.json", "2026-10-20_b70-q4-0-sycl-ocl.json"),
            None,
            ratio("2026-10-20_b70-q4-0-vulkan-ncmoe8.json", "2026-10-20_b70-q4-0-sycl-ocl-ncmoe8.json")],
    "B50": [ratio("2026-10-22_b50-16g-iq2m-vulkan.json", "2026-10-22_b50-16g-iq2m-sycl-ocl.json"),
            ratio("2026-10-22_b50-16g-q3ks-vulkan.json", "2026-10-22_b50-16g-q3ks-sycl-ocl.json"),
            ratio("2026-10-22_b50-16g-q4-0-vulkan-ncmoe8.json", "2026-10-22_b50-16g-q4-0-sycl-ncmoe8.json")],
}

# ---- 右：逐卡倍数（解码 / 预填充）----
CARDS = [
    ("B50\n16 核", "2026-10-22_b50-16g-iq2m-vulkan.json", "2026-10-22_b50-16g-iq2m-sycl-ocl.json"),
    ("B60\n20 核", "2026-10-20_b60-q4-0-vulkan.json", "2026-10-20_b60-q4-0-sycl-ocl.json"),
    ("B65\n20 核", "2026-10-21_b65-q4-0-vulkan.json", "2026-10-21_b65-q4-0-base.json"),
    ("B70\n32 核", "2026-10-20_b70-q4-0-vulkan.json", "2026-10-20_b70-q4-0-sycl-ocl.json"),
]

TXT = {
    "zh": dict(
        l_title="倍数由「权重驻不驻留」决定",
        l_sub="Vulkan ÷ SYCL · 解码 tok/s · 同 build 11753 · 同参数只换后端",
        l_x="权重驻留状态", l_y="Vulkan ÷ SYCL",
        l_rev="长上下文 -c 65536 → 0.64×，反向",
        r_title="倍数逐卡量，不外推",
        r_x="卡（Xe2 核心数）", r_y="倍数",
        leg=("解码", "预填充"),
        foot="解码不跟核心数走，预填充跟核心数涨。判据是权重驻不驻留，不是负载类型 —— 按卡 + 按相位报倍数。"),
    "en": dict(
        l_title="The multiplier is set by weight residency",
        l_sub="Vulkan ÷ SYCL · decode tok/s · same build 11753 · same flags, backend swapped",
        l_x="Weight residency", l_y="Vulkan ÷ SYCL",
        l_rev="-c 65536 → 0.64×, reversed",
        r_title="Measure per card; do not extrapolate",
        r_x="Card (Xe2 cores)", r_y="Multiplier",
        leg=("Decode", "Prefill"),
        foot="Decode does not follow core count; prefill does. The criterion is weight residency, not workload type."),
}


def main():
    right = []
    for xlab, vf, sf in CARDS:
        vd, vp = load(vf)
        sd, sp = load(sf)
        right.append((xlab, vd / sd, vp / sp))

    for fam in FONT:
        try:
            plt.rcParams["font.family"] = fam
            import matplotlib.font_manager as fm
            if any(f.name == fam for f in fm.fontManager.ttflist):
                break
        except Exception:
            pass
    plt.rcParams["axes.unicode_minus"] = False

    marks = {"B60": ("o", C_B60), "B70": ("s", C_B70), "B50": ("^", C_B50)}
    n_state = len(STATES)

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.8, 4.6), dpi=96,
                                      gridspec_kw={"width_ratios": [1.15, 1]})
        fig.patch.set_facecolor("white")

        # ---------- 左 ----------
        ax.set_facecolor("white")
        # 逐点标签偏移（x 方向，y 方向），避免同档三条标签互相压住
        OFF = {"B60": [(0, 13), (0, 13)], "B70": [(0, -19), (-30, -5)],
               "B50": [(-34, -4), (0, -19), (30, -5)]}
        for card, (mk, col) in marks.items():
            ys = CURVE[card]
            pts = [(i, y) for i, y in enumerate(ys) if y is not None]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker=mk, ms=8, lw=2.0,
                    color=col, label=card, zorder=3)
            for k, (i, y) in enumerate(pts):
                dx, dy = OFF[card][k]
                ax.annotate(f"{y:.2f}×", (i, y), textcoords="offset points", xytext=(dx, dy),
                            ha="center", fontsize=9.5, color=col, weight="bold")
        ax.axhline(1.0, color="#B03A2E", lw=1.3, ls="--", zorder=1)
        ax.text(-0.40, 1.015, "1.0 = 无优势" if lang == "zh" else "1.0 = no gain",
                ha="left", va="bottom", fontsize=9, color="#B03A2E")
        # 反向点标注
        ax.annotate(t["l_rev"], xy=(1.97, 0.66), xytext=(1.05, 0.545),
                    fontsize=9, color=C_B50,
                    arrowprops=dict(arrowstyle="->", color=C_B50, lw=1.3))
        ax.set_xticks(range(n_state))
        ax.set_xticklabels(STATES, fontsize=9)
        ax.set_xlim(-0.45, n_state - 0.55)
        ax.set_ylim(0.45, 1.95)
        ax.set_xlabel(t["l_x"], fontsize=10, color=INK)
        ax.set_ylabel(t["l_y"], fontsize=10, color=INK)
        ax.set_title(t["l_title"], fontsize=12.5, color=INK, pad=14, weight="bold")
        ax.grid(axis="y", color=GRID, lw=0.9)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(MUTED)
        ax.legend(frameon=False, fontsize=9.5, loc="upper right", ncol=3,
                  columnspacing=1.0, handlelength=1.4)

        # ---------- 右 ----------
        ax2.set_facecolor("white")
        n = len(right)
        w = 0.34
        xs2 = list(range(n))
        dec = [r[1] for r in right]
        pre = [r[2] for r in right]
        ax2.bar([x - w / 2 for x in xs2], dec, w, color=C_B60, label=t["leg"][0])
        ax2.bar([x + w / 2 for x in xs2], pre, w, color=C_PREF, label=t["leg"][1])
        for x, d, p in zip(xs2, dec, pre):
            ax2.text(x - w / 2, d + 0.07, f"{d:.2f}×", ha="center", fontsize=9,
                     color=C_B60, weight="bold")
            ax2.text(x + w / 2, p + 0.07, f"{p:.2f}×", ha="center", fontsize=9,
                     color=C_PREF, weight="bold")
        ax2.set_xticks(xs2)
        ax2.set_xticklabels([r[0] for r in right], fontsize=9.5)
        ax2.set_ylim(0, 4.1)
        ax2.set_xlabel(t["r_x"], fontsize=10, color=INK)
        ax2.set_ylabel(t["r_y"], fontsize=10, color=INK)
        ax2.set_title(t["r_title"], fontsize=12.5, color=INK, pad=14, weight="bold")
        ax2.grid(axis="y", color=GRID, lw=0.9)
        ax2.set_axisbelow(True)
        for s in ("top", "right"):
            ax2.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax2.spines[s].set_color(MUTED)
        ax2.legend(frameon=False, fontsize=9.5, loc="upper left")

        fig.suptitle(t["l_sub"], fontsize=10, color=MUTED, y=0.975)
        fig.text(0.5, 0.018, t["foot"], ha="center", fontsize=9.2, color=INK)
        fig.tight_layout(rect=(0, 0.06, 1, 0.93))

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes")


if __name__ == "__main__":
    main()
