#!/usr/bin/env python
"""由 README.zh-CN.md「聊天与文本」llama-bench 表 + docs/vram-16gb.md 带宽利用率行
直出「量化阶梯」双面板图。

左：三档量化 × B50/B60/B65 的 decode 分组柱状（B50 的 Q4_0 是卸专家运行，打斜纹），
    每组顶端标卡间差——档间差（每卡 +20% 上下）远小于卡间差（15~21 tok/s，16 核 vs 20 核）。
右：B50 带宽利用率——同一张卡 IQ2_M 全驻只用 19%，稠密 Qwen3-VL-4B 能用 68%，
    解释 16 GB 档为什么换量化不提速（算力受限，不是带宽受限）。
数字取不到就报错。输出 docs/assets/quant-ladder{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "README.zh-CN.md"
VRAM = ROOT / "docs" / "vram-16gb.md"
OUT = {l: ROOT / "docs" / "assets" / f"quant-ladder{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_B50, C_B60, C_B65 = "#C2410C", "#2F6FBA", "#1B7F79"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

TIERS = ["Q4_0", "Q3_K_S", "IQ2_M"]
CARDS = ["B50", "B60", "B65"]
CC = {"B50": C_B50, "B60": C_B60, "B65": C_B65}

TXT = {
    "zh": dict(
        title="量化阶梯：换档只挪窄带，卡间差远大于档间差",
        sub="Qwen3.6-35B-A3B · llama-bench -p 512 -n 128 -r 3 · decode tok/s · 2026-10-15 至 21",
        pa="三档量化 × 三张卡（decode tok/s）", pb="B50 为什么换档不提速：带宽只用了一成",
        pb1="B50 · IQ2_M 10.73 GiB\n全驻（35B MoE）", pb2="B50 · Qwen3-VL-4B\n稠密 · 全驻",
        pbx="占 224 GB/s 的百分比",
        gap="卡间差", hatch="卸专家运行（-ncmoe 8）",
        leg={"B50": "B50 16G", "B60": "B60 24G", "B65": "B65 32G"},
        foot="换量化档每张卡只动 +20% 上下，卡间差 15 至 21 tok/s（16 核 vs 20 核）；\n"
             "B50 不提速是因为带宽只用到 19%（同一张卡跑稠密能用 68%）——选档是选质量与余量，不是速度。"),
    "en": dict(
        title="Quant ladder: switching tiers moves a narrow band, card gaps dwarf it",
        sub="Qwen3.6-35B-A3B · llama-bench -p 512 -n 128 -r 3 · decode tok/s · 2026-10-15 to 21",
        pa="Three quant tiers x three cards (decode tok/s)", pb="Why B50 stays flat: bandwidth barely used",
        pb1="B50 · IQ2_M 10.73 GiB\nresident (35B MoE)", pb2="B50 · Qwen3-VL-4B\ndense · resident",
        pbx="% of 224 GB/s",
        gap="card gap", hatch="offloaded (-ncmoe 8)",
        leg={"B50": "B50 16G", "B60": "B60 24G", "B65": "B65 32G"},
        foot="Quant switches move each card ~20%; card gaps are 15-21 tok/s (16 vs 20 cores). "
             "B50 stays flat: 19% of bandwidth used (dense: 68%)."),
}


def parse():
    t = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    sec = t.split("## 聊天与文本")[1].split("### 口径 B")[0]
    data, sizes = {}, {}
    for ln in sec.splitlines():
        if not ln.startswith("|") or "Qwen3.6-35B-A3B" not in ln:
            continue
        c = [x.strip() for x in ln.split("|")[1:-1]]
        card = c[0].replace("*", "").split()[0]
        quant = c[2].replace("*", "")
        if card not in CARDS or "第二槽" in c[6]:
            continue                      # 副槽行归槽位图，不进阶梯
        sizes.setdefault(quant, float(c[3].split()[0]))
        assert abs(sizes[quant] - float(c[3].split()[0])) < 1e-9, (quant, c[3])
        row = dict(dec=float(c[4].replace("*", "").split()[0]),
                   off="卸载" in c[6] or "-ncmoe 8" in c[6])
        prev = data.get((card, quant))
        # 同档多行（B65 Q4_0 有全驻留与 -ncmoe 8 两行）：阶梯只取全驻留那条
        if prev is None or (prev["off"] and not row["off"]):
            data[(card, quant)] = row
    assert len(data) == 9, data
    for tier in TIERS:
        for card in CARDS:
            assert (card, tier) in data, (card, tier)
    assert sizes == {"Q4_0": 19.41, "Q3_K_S": 14.30, "IQ2_M": 10.73}, sizes
    assert data[("B50", "Q4_0")]["off"] and not data[("B60", "Q4_0")]["off"], data
    assert not data[("B65", "Q4_0")]["off"] and data[("B65", "Q4_0")]["dec"] == 53.09, data
    assert data[("B50", "Q4_0")]["dec"] == 37.6, data

    v = VRAM.read_text(encoding="utf-8").replace("\r\n", "\n")
    m1 = re.search(r"用到 224 GB/s 的 \*\*(\d+)%\*\*", v)
    m2 = re.search(r"能用掉 \*\*(\d+)%\*\*", v)
    assert m1 and m2, "vram-16gb 带宽利用率行取不到"
    return data, sizes, int(m1.group(1)), int(m2.group(1))


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

    data, sizes, bw_moe, bw_dense = parse()
    assert (bw_moe, bw_dense) == (19, 68), (bw_moe, bw_dense)

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.8, 4.6), dpi=96,
                                      gridspec_kw={"width_ratios": [1.62, 1]})
        fig.patch.set_facecolor("white")
        for a in (ax, ax2):
            a.set_facecolor("white")
            a.grid(axis="y", color=GRID, lw=0.9)
            a.set_axisbelow(True)
            for s in ("top", "right"):
                a.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                a.spines[s].set_color(MUTED)
            a.tick_params(labelsize=9)

        # 左：分组柱状
        w = 0.26
        for i, card in enumerate(CARDS):
            for j, tier in enumerate(TIERS):
                v = data[(card, tier)]
                x = j + (i - 1) * w
                ax.bar(x, v["dec"], width=w * 0.92, color=CC[card],
                       hatch="////" if v["off"] else None,
                       edgecolor="white" if v["off"] else "none", lw=0.0)
                ax.text(x, v["dec"] + 1.1, f"{v['dec']:.1f}", ha="center",
                        fontsize=8.6, color=INK)
        # 每组顶端：卡间差（B65 − B50）
        for j, tier in enumerate(TIERS):
            lo, hi = data[("B50", tier)]["dec"], data[("B65", tier)]["dec"]
            y = max(data[(c, tier)]["dec"] for c in CARDS) + 6.2
            x0, x1 = (j - w) + 0.02, (j + w) - 0.02
            ax.plot([x0, x1], [y, y], color=MUTED, lw=1.0)
            ax.plot([x0, x0], [y - 1.1, y], color=MUTED, lw=1.0)
            ax.plot([x1, x1], [y - 1.1, y], color=MUTED, lw=1.0)
            ax.text((x0 + x1) / 2, y + 1.0, f"{t['gap']} {hi - lo:.1f}", ha="center",
                    fontsize=8.8, color=MUTED)
        ax.set_xticks(range(3))
        ax.set_xticklabels([f"{tier}\n{sizes[tier]:.2f} GiB" for tier in TIERS])
        ax.set_ylim(0, 92)          # 顶部留白给图例，别压柱条与卡间差标注
        ax.set_ylabel("decode（tok/s）" if lang == "zh" else "decode (tok/s)",
                      fontsize=9.5, color=INK)
        ax.set_title(t["pa"], fontsize=11.5, color=INK, pad=12, weight="bold")
        ax.legend(handles=[Patch(facecolor=CC[c], label=t["leg"][c]) for c in CARDS] +
                          [Patch(facecolor="white", edgecolor=MUTED, hatch="////", label=t["hatch"])],
                  frameon=False, fontsize=8.6, loc="upper right", ncol=2,
                  bbox_to_anchor=(0.93, 1.0))   # 左移，让开右面板的纵轴长标签

        # 右：带宽利用率
        ys = [1, 0]
        ax2.barh(ys, [bw_moe, bw_dense], height=0.5, color=C_B50)
        for y, v in zip(ys, (bw_moe, bw_dense)):
            ax2.text(v + 1.6, y, f"{v}%", va="center", fontsize=11, color=INK, weight="bold")
        ax2.set_yticks(ys)
        ax2.set_yticklabels([t["pb1"], t["pb2"]], fontsize=8.8)
        ax2.set_xlim(0, 100)
        ax2.set_xlabel(t["pbx"], fontsize=9.5, color=INK)
        ax2.set_title(t["pb"], fontsize=11.5, color=INK, pad=12, weight="bold")
        ax2.grid(axis="x", color=GRID, lw=0.9)
        ax2.grid(axis="y", visible=False)

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.905, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.2,
                 color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.055, right=0.985, top=0.74, bottom=0.2, wspace=0.3)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes",
              f"bw={bw_moe}/{bw_dense}")


if __name__ == "__main__":
    main()
