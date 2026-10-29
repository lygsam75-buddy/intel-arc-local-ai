#!/usr/bin/env python
"""由 bench/data 各批 comfyui JSON 的 timing_breakdown.runs 直出「resident 轮拆解」图：
采样段（实心）vs 装载 / 固定开销（斜纹），两个负载（Qwen-Image 2.1 / Krea-2 Turbo int8）× 四张卡。
跨卡差落在哪一段，一眼可见：装得下 → 采样占 85 至 93%；装不下 → 装载吃掉 44%（B50 Qwen）
到 88%（B60 Krea-2）。数字取不到就报错。输出 docs/assets/image-sample-vs-load{,.en}.svg（纯 LF）。
"""
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data"
OUT = {l: ROOT / "docs" / "assets" / f"image-sample-vs-load{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_SAMP, C_LOAD = "#1B7F79", "#D8D5CE"
E_LOAD = "#9A9891"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")
CARDS = ["B50", "B60", "B65", "B70"]

FILES = {
    "qwen": {"B50": "2026-10-16_b50-16g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json",
             "B60": "2026-10-20_b60-24g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json",
             "B65": "2026-10-21_b65-32g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json",
             "B70": "2026-10-17_b70-32g_qwen-image-2.1-int8_convrot-b70same-comfyui.json"},
    "krea": {"B50": "2026-10-16_b50-16g_krea-2-turbo-int8_convrot-int8fix-comfyui.json",
             "B60": "2026-10-20_b60-24g_krea-2-turbo-int8_convrot-b60k2-comfyui.json",
             "B65": "2026-10-21_b65-32g_krea-2-turbo-int8_convrot-b65k2-comfyui.json",
             "B70": "2026-10-17_b70-32g_krea-2-turbo-int8_convrot-b70k2base-comfyui.json"},
}

TXT = {
    "zh": dict(
        title="resident 轮拆解：采样段 vs 装载 / 固定开销",
        sub="int8 档 · 稳态 = 两次 resident 的均值 · 秒",
        panels=["Qwen-Image 2.1 · 1280×720 · 25 步", "Krea-2 Turbo · 8 步"],
        samp="采样段", load="装载 / 固定开销", star="*",
        a50="每轮卸 3,837.8 MB\n文本编码器", a60="每轮重搬 12.6 GB DiT",
        y="resident 轮耗时（秒）",
        foot="装得下的卡采样占 80 至 93%（B60 / B65 / B70 的 Qwen、B65 / B70 的 Krea-2）；"
             "装不下就差在这里——B50 的 Qwen 采样只占 56%、B60 的 Krea-2 只占 12%。* B50 Krea-2 为 1024×1024。"),
    "en": dict(
        title="Resident-round split: sampling vs loading / fixed overhead",
        sub="int8 tier · steady state = mean of two resident rounds · seconds",
        panels=["Qwen-Image 2.1 · 1280x720 · 25 steps", "Krea-2 Turbo · 8 steps"],
        samp="sampling", load="loading / fixed", star="*",
        a50="3,837.8 MB of TE\nshed every round", a60="12.6 GB DiT\nre-loaded every round",
        y="resident round (s)",
        foot="Cards that fit are 80-93% sampling (B60/B65/B70 Qwen, B65/B70 Krea-2); the ones that do not fit "
             "lose it here - B50 Qwen is 56% sampling, B60 Krea-2 just 12%. * B50 Krea-2 is 1024x1024."),
}


def parse():
    out = {}
    for key, per in FILES.items():
        out[key] = {}
        for card, fname in per.items():
            d = json.load(open(DATA / fname))
            runs = [r for r in d["timing_breakdown"]["runs"]
                    if r.get("matched_sample", {}).get("role") == "resident"]
            samp = [r["sampling_sec"] for r in runs]
            assert len(runs) >= 1 and all(s is not None for s in samp), (fname, runs)
            # 柱总高用 summary 登记值（与文档表一致），装载段 = 总高 − 采样段
            tot = float(d["summary"]["resident_sec_mean"])
            sm = sum(samp) / len(samp)
            out[key][card] = dict(samp=sm, tot=tot)
            out[key][card]["other"] = tot - sm
    q, k = out["qwen"], out["krea"]
    for got, want in (([q[c]["tot"] for c in CARDS], [51.75, 18.06, 16.16, 10.62]),
                      ([k[c]["tot"] for c in CARDS], [57.88, 64.15, 8.73, 6.04])):
        assert all(abs(a - b) < 0.02 for a, b in zip(got, want)), (got, want)
    assert [q[c]["samp"] for c in CARDS] == [29, 16, 15, 9], q
    assert [k[c]["samp"] for c in CARDS] == [15.5, 8, 7, 5], k  # B50 Krea 两轮 16 / 15
    # 采样占比口径：装得下 80~93%，装不下 56% / 12%
    assert 0.80 < q["B60"]["samp"] / q["B60"]["tot"] < 0.93
    assert 0.80 < q["B65"]["samp"] / q["B65"]["tot"] < 0.93
    assert 0.80 < q["B70"]["samp"] / q["B70"]["tot"] < 0.93
    assert 0.80 < k["B65"]["samp"] / k["B65"]["tot"] < 0.93
    assert 0.80 < k["B70"]["samp"] / k["B70"]["tot"] < 0.93
    assert abs(q["B50"]["samp"] / q["B50"]["tot"] - 0.56) < 0.01
    assert abs(k["B60"]["samp"] / k["B60"]["tot"] - 0.125) < 0.01
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

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, axes = plt.subplots(1, 2, figsize=(9.8, 4.5), dpi=96)
        fig.patch.set_facecolor("white")
        for ax, key, ptitle in zip(axes, ("qwen", "krea"), t["panels"]):
            ax.set_facecolor("white")
            ax.grid(axis="y", color=GRID, lw=0.9)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                ax.spines[s].set_color(MUTED)
            ax.tick_params(labelsize=9)
            for i, c in enumerate(CARDS):
                v = d[key][c]
                ax.bar(i, v["samp"], width=0.56, color=C_SAMP)
                ax.bar(i, v["other"], width=0.56, bottom=v["samp"], color=C_LOAD,
                       hatch="////", edgecolor=E_LOAD, lw=0.0)
                ax.text(i, v["tot"] + 1.6, f"{v['tot']:.2f}" + (t["star"] if key == "krea" and c == "B50" else ""),
                        ha="center", fontsize=9, color=INK, weight="bold")
                pct = v["other"] / v["tot"] * 100
                if v["other"] > 6:
                    ax.text(i, v["samp"] + v["other"] / 2, f"{pct:.0f}%", ha="center",
                            va="center", fontsize=8.8, color=INK)
            ax.set_xticks(range(4))
            ax.set_xticklabels([f"{c}\n{gb} GB" for c, gb in zip(CARDS, ("16", "24", "32", "32"))])
            ax.set_xlim(-0.6, 3.6)
            ax.set_ylim(0, 74)
            ax.set_title(ptitle, fontsize=11.2, color=INK, pad=10, weight="bold")
        axes[0].set_ylabel(t["y"], fontsize=9.5, color=INK)
        axes[0].legend(handles=[plt.Line2D([], [], color=C_SAMP, lw=7, label=t["samp"]),
                                plt.Line2D([], [], color=C_LOAD, lw=7, label=t["load"])],
                       frameon=False, fontsize=9, loc="upper right")
        # 两个锚点注释：装载段的来源
        axes[0].annotate(t["a50"], xy=(0, 40), xytext=(0.62, 58), fontsize=8.6, color=INK,
                         arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
        axes[1].annotate(t["a60"], xy=(1, 46), xytext=(1.75, 63), fontsize=8.6, color=INK,
                         arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.9, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.0,
                 color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.055, right=0.99, top=0.76, bottom=0.19, wspace=0.2)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes",
              {k: {c: (round(v["samp"], 1), round(v["other"], 1)) for c, v in d[k].items()}
               for k in d})


if __name__ == "__main__":
    main()
