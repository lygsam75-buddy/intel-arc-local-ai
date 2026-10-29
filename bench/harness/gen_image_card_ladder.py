#!/usr/bin/env python
"""由 bench/data 各批 comfyui JSON 的 summary/timing_breakdown 直出「四卡阶梯」图：
三个负载（Qwen-Image 2.1 / Krea-2 Turbo / Music 3）× 四张卡，resident 稳态。
每卡两根柱：实心 = 交付 int8 档，斜纹 = 对比档（Qwen bf16 / Krea bf16 / Music fp16 DiT），
没有数字的格子不画柱也不配注（B60 Qwen bf16 未测、B50/B70 Krea bf16 不给数字）。
柱顶倍数 = 该卡交付档对 B70 交付档。数字取不到就报错。
输出 docs/assets/image-card-ladder{,.en}.svg（纯 LF）。
"""
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data"
OUT = {l: ROOT / "docs" / "assets" / f"image-card-ladder{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_INT8, C_ALT = "#2F6FBA", "#B9C6D8"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")
CARDS = ["B50", "B60", "B65", "B70"]

# 批号 → (卡, 负载, 档)。res_mean / 采样 / 固定全部从 JSON 取，不手抄。
BATCHES = {
    "qwen_i8": [("B50", "2026-10-16_b50-16g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json"),
                ("B60", "2026-10-20_b60-24g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json"),
                ("B65", "2026-10-21_b65-32g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json"),
                ("B70", "2026-10-17_b70-32g_qwen-image-2.1-int8_convrot-b70same-comfyui.json")],
    "qwen_b16": [("B50", "2026-10-16_b50-16g_qwen-image-2.1-bf16-comfyui.json"),
                 ("B65", "2026-10-21_b65-32g_qwen-image-2.1-bf16-b65q21b16-comfyui.json"),
                 ("B70", "2026-10-19_b70-32g_qwen-image-2.1-bf16-b70v2-comfyui.json")],
    "krea_i8": [("B50", "2026-10-16_b50-16g_krea-2-turbo-int8_convrot-int8fix-comfyui.json"),
                ("B60", "2026-10-20_b60-24g_krea-2-turbo-int8_convrot-b60k2-comfyui.json"),
                ("B65", "2026-10-21_b65-32g_krea-2-turbo-int8_convrot-b65k2-comfyui.json"),
                ("B70", "2026-10-17_b70-32g_krea-2-turbo-int8_convrot-b70k2base-comfyui.json")],
    "krea_b16": [("B65", "2026-10-21_b65-32g_krea-2-turbo-bf16-b65k2b16-comfyui.json"),
                 ("B70", "2026-10-19_b70-32g_krea-2-turbo-bf16-b70pw-comfyui.json")],
    "music": [("B50", "2026-10-16_b50-16g_minimax-music-3-int8_convrot-m3i8-comfyui.json"),
              ("B60", "2026-10-20_b60-24g_minimax-music-3-int8_convrot-b60m3-comfyui.json"),
              ("B65", "2026-10-21_b65-32g_minimax-music-3-int8_convrot-b65m3res2-comfyui.json"),
              ("B70", "2026-10-17_b70-32g_minimax-music-3-int8_convrot-b70m3tebf16-comfyui.json")],
    "music_fp16": [("B70", "2026-10-17_b70-32g_minimax-music-3-fp16-b70m3fp16teint8-comfyui.json")],
}

TXT = {
    "zh": dict(
        title="三个负载 · 四张卡：稳态耗时（实心 = 交付 int8 档，斜纹 = 对比档）",
        sub="ComfyUI int8fix 栈 · resident 轮 · 2026-10-16 至 22 · 秒/张（音乐为秒/首）",
        panels=["Qwen-Image 2.1 · 1280×720 · 25 步",
                "Krea-2 Turbo · 8 步",
                "Music 3 · 120 s · 30 步"],
        y="稳态耗时（秒）", star="*", div="÷B70",
        leg_i8="int8（交付档）", leg_alt="bf16 · fp16（对比档）",
        foot="* B50 的 Krea-2 是 1024×1024（16 GB 档交付形态），其余三卡 1280×720。倍数 = 该卡交付档 ÷ B70 交付档；"
             "Music 3 的 TE 档位逐卡不同（B50 / B60 为 int8 TE、B65 / B70 为 bf16 TE），对稳态无实质影响。"),
    "en": dict(
        title="Three workloads, four cards: steady-state time (solid = delivery int8, hatched = comparison)",
        sub="ComfyUI int8fix stack · resident rounds · 2026-10-16 to 22 · sec/image (sec/song for music)",
        panels=["Qwen-Image 2.1 · 1280x720 · 25 steps",
                "Krea-2 Turbo · 8 steps",
                "Music 3 · 120 s · 30 steps"],
        y="steady-state time (s)", star="*", div="/B70",
        leg_i8="int8 (delivery)", leg_alt="bf16 / fp16 (comparison)",
        foot="* B50's Krea-2 run is 1024x1024 (its 16 GB delivery form), the other three are 1280x720. "
             "Ratios are card delivery tier / B70 delivery tier; Music 3 TE tiers differ per card (int8 on B50/B60, "
             "bf16 on B65/B70) with no material effect on steady state."),
}


def load(card, fname):
    d = json.load(open(DATA / fname))
    s = d["summary"]
    res = s.get("resident_sec_mean")
    assert res, (fname, "no resident_sec_mean")
    runs = [r for r in d.get("timing_breakdown", {}).get("runs", [])
            if r.get("matched_sample", {}).get("role") == "resident"]
    samp = [r.get("sampling_sec") for r in runs if r.get("sampling_sec") is not None]
    assert samp, (fname, "no sampling_sec")
    return dict(res=float(res), samp=float(samp[0]), n=len(runs))


def parse():
    out = {}
    for key, lst in BATCHES.items():
        out[key] = {c: load(c, f) for c, f in lst}
    # B70 Qwen bf16 两个批次（v2 / pw）都收敛，取两批均值的均值，与文档口径 13.82 对齐
    d2 = json.load(open(DATA / "2026-10-19_b70-32g_qwen-image-2.1-bf16-b70pw-comfyui.json"))
    b70_b16 = (out["qwen_b16"]["B70"]["res"] + float(d2["summary"]["resident_sec_mean"])) / 2
    out["qwen_b16"]["B70"]["res"] = b70_b16
    q = out["qwen_i8"]
    assert (q["B50"]["res"], q["B60"]["res"], q["B65"]["res"], q["B70"]["res"]) == \
           (51.75, 18.06, 16.16, 10.62), q
    assert out["qwen_b16"]["B50"]["res"] == 87.34 and out["qwen_b16"]["B65"]["res"] == 22.91, out["qwen_b16"]
    assert abs(b70_b16 - 13.82) < 0.03, b70_b16
    k = out["krea_i8"]
    assert (k["B50"]["res"], k["B60"]["res"], k["B65"]["res"], k["B70"]["res"]) == \
           (57.88, 64.15, 8.73, 6.04), k
    assert out["krea_b16"]["B65"]["res"] == 167.47, out["krea_b16"]
    # B70 Krea-2 bf16：与 §3.0 主表同口径——b70pw 批去掉首轮后各轮均值（含 loads=3 的换提示词轮）
    dp = json.load(open(DATA / "2026-10-19_b70-32g_krea-2-turbo-bf16-b70pw-comfyui.json"))
    non_first = [float(sp["server_sec"]) for sp in dp.get("samples", [])
                 if sp.get("role") != "first" and sp.get("server_sec") is not None]
    k_b70 = sum(non_first) / len(non_first)
    out["krea_b16"]["B70"]["res"] = k_b70
    assert abs(k_b70 - 127.74) < 0.03, k_b70
    m = out["music"]
    assert (m["B50"]["res"], m["B60"]["res"], m["B65"]["res"], m["B70"]["res"]) == \
           (216.82, 145.37, 180.53, 61.95), m
    assert out["music_fp16"]["B70"]["res"] == 78.73, out["music_fp16"]
    return out


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

    d = parse()
    base = {"qwen": d["qwen_i8"]["B70"]["res"],
            "krea": d["krea_i8"]["B70"]["res"],
            "music": d["music"]["B70"]["res"]}

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, axes = plt.subplots(1, 3, figsize=(10.6, 4.7), dpi=96)
        fig.patch.set_facecolor("white")
        series = [
            ("qwen", [d["qwen_i8"][c]["res"] for c in CARDS],
             [d["qwen_b16"].get(c, {}).get("res") for c in CARDS]),
            ("krea", [d["krea_i8"][c]["res"] for c in CARDS],
             [d["krea_b16"].get(c, {}).get("res") for c in CARDS]),
            ("music", [d["music"][c]["res"] for c in CARDS],
             [None, None, None, d["music_fp16"]["B70"]["res"]]),
        ]
        for ax, (key, i8, alt), ptitle in zip(axes, series, t["panels"]):
            ax.set_facecolor("white")
            ax.grid(axis="y", color=GRID, lw=0.9)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                ax.spines[s].set_color(MUTED)
            ax.tick_params(labelsize=9)
            for i, (vi, va) in enumerate(zip(i8, alt)):
                ax.bar(i - 0.19, vi, width=0.34, color=C_INT8)
                star = t["star"] if (key == "krea" and CARDS[i] == "B50") else ""
                ax.text(i - 0.19, vi + 3.5, f"{vi:.2f}{star}", ha="center", fontsize=8.4,
                        color=INK)
                if va is not None:
                    ax.bar(i + 0.19, va, width=0.34, color=C_ALT, hatch="////",
                           edgecolor="white", lw=0.0)
                    ax.text(i + 0.19, va + 3.5, f"{va:.2f}", ha="center", fontsize=8.4,
                            color=MUTED)
            # 倍数行：该卡交付档 ÷ B70 交付档。行标（÷B70）单独占最上一行，
            # 倍数行再低一层——三者（柱值 / 倍数 / 行标）各占一层互不相压。
            for i, vi in enumerate(i8):
                ax.text(i, 236, f"{vi / base[key]:.2f}×", ha="center", va="center",
                        fontsize=9.4, color=INK, weight="bold")
            ax.text(-0.55, 251, t["div"], ha="left", va="center", fontsize=8.0, color=MUTED)
            ax.set_xticks(range(4))
            ax.set_xticklabels([f"{c}\n{gb} GB" for c, gb in zip(CARDS, ("16", "24", "32", "32"))])
            ax.set_xlim(-0.55, 3.55)
            ax.set_ylim(0, 264)
            ax.set_title(ptitle, fontsize=10.8, color=INK, pad=10, weight="bold")
        axes[0].set_ylabel(t["y"], fontsize=9.5, color=INK)

        fig.suptitle(t["title"], fontsize=12.6, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.92, t["sub"], ha="center", fontsize=9, color=MUTED)
        # 图例：两档柱体颜色标注（实心 = int8 交付档，斜纹 = bf16/fp16 对比档）
        fig.legend(handles=[
            Patch(facecolor=C_INT8, label=t["leg_i8"]),
            Patch(facecolor=C_ALT, hatch="////", edgecolor="white", lw=0.0, label=t["leg_alt"]),
        ], loc="upper center", bbox_to_anchor=(0.5, 0.878), ncol=2, frameon=False,
            fontsize=9, handlelength=1.6, handleheight=1.0, columnspacing=1.8)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.0,
                 color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.05, right=0.99, top=0.76, bottom=0.17, wspace=0.2)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes",
              {k: {c: round(v["res"], 2) for c, v in d[k].items()} for k in ("qwen_i8", "krea_i8", "music")})


if __name__ == "__main__":
    main()
