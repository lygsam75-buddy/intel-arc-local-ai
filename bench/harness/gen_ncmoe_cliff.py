#!/usr/bin/env python
"""由 docs/vram-16gb.md「完整曲线」三张表 + README.zh-CN.md llama-bench 表 +
bench/data 两个 -ncmoe 8 JSON 直出「卸专家」双面板曲线。

左：装不下（B50 · Q4_0 19.41 GiB > 15.51 GiB）——断崖：-ncmoe 0 只有 4.14
    （裸 -ngl 999 退化成整层卸载），卸到 8 层才回到 37.74，差 9 倍。
右：装得下——缓坡：IQ2_M / Q3_K_S 全程平缓（最多 −29%），B60 / B65 的 Q4_0
    卸 8 层也是纯亏（52.43→44.40 / 53.09→45.84，两点实测）。
数字取不到就报错。输出 docs/assets/ncmoe-cliff{,.en}.svg（纯 LF）。
"""
import io
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "README.zh-CN.md"
VRAM = ROOT / "docs" / "vram-16gb.md"
OUT = {l: ROOT / "docs" / "assets" / f"ncmoe-cliff{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_Q4, C_IQ2, C_Q3 = "#C2410C", "#2F6FBA", "#1B7F79"
C_OTHER = "#5F5E5A"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

TXT = {
    "zh": dict(
        title="卸专家：装不下是断崖，装得下是缓坡",
        sub="B50 16G · Qwen3.6-35B-A3B · llama-bench decode tok/s · 横轴 = -ncmoe（前 N 层专家放 CPU）",
        pa="装不下：Q4_0 19.41 GiB > 15.51 GiB → 断崖",
        pb="装得下：IQ2_M / Q3_K_S → 缓坡（B60 / B65 同形）",
        a0="4.14 = 裸 -ngl 999\n退化成整层卸载", a8="卸到 8 层：37.74",
        lq4="B50 · Q4_0 19.41 GiB（主槽 x8）", liq2="B50 · IQ2_M 10.73 GiB",
        lq3="B50 · Q3_K_S 14.30 GiB", lo="B60 / B65 · Q4_0（24 / 32 GB，装得下）",
        x="-ncmoe（前 N 层专家放 CPU）", y="decode（tok/s）",
        foot="拐点在「权重体积 vs 可用显存」那一刻：10.73 与 14.30 GiB 全程缓坡（最多 −29%），"
             "19.41 GiB 断崖——0 层 4.14，卸到 8 层才回到 37.74。"),
    "en": dict(
        title="Offloading experts: a cliff when it does not fit, a ramp when it does",
        sub="B50 16G · Qwen3.6-35B-A3B · llama-bench decode tok/s · x = -ncmoe (first N expert layers on CPU)",
        pa="Does not fit: Q4_0 19.41 GiB > 15.51 GiB -> cliff",
        pb="Fits: IQ2_M / Q3_K_S -> ramp (B60 / B65 same shape)",
        a0="4.14 = bare -ngl 999\ndegrades to whole-layer offload", a8="offload to 8 layers: 37.74",
        lq4="B50 · Q4_0 19.41 GiB (primary x8)", liq2="B50 · IQ2_M 10.73 GiB",
        lq3="B50 · Q3_K_S 14.30 GiB", lo="B60 / B65 · Q4_0 (24 / 32 GB, fits)",
        x="-ncmoe (first N expert layers on CPU)", y="decode (tok/s)",
        foot="The kink is at weights vs free VRAM: 10.73/14.30 GiB ramp (worst -29%), "
             "19.41 GiB cliff - 4.14 at 0 layers, 37.74 only at 8."),
}


def rows(block):
    """把一个 markdown 块里的两行表格解析成 (轴, 值)。"""
    xs = ys = None
    for ln in block.splitlines():
        if not ln.startswith("|"):
            continue
        cells = [c.replace("*", "").strip() for c in ln.split("|")[1:-1]]
        vals = [float(c) for c in cells if re.fullmatch(r"\d+(?:\.\d+)?", c)]
        if not vals:
            continue
        if xs is None:
            xs = vals
        else:
            ys = vals
            break
    assert xs and ys and len(xs) == len(ys), block[:200]
    return xs, ys


def parse():
    v = VRAM.read_text(encoding="utf-8").replace("\r\n", "\n")
    sec = v.split("**完整曲线**")[1].split("**结论**")[0]
    iq2 = rows(sec.split("IQ2_M")[1].split("Q3_K_S")[0])
    q3 = rows(sec.split("Q3_K_S")[1].split("Q4_0")[0])
    q4 = rows(sec.split("Q4_0")[1])
    assert iq2[0] == [0, 2, 4, 8, 16, 32] and q3[0] == [0, 2, 4, 8], (iq2, q3)
    assert q4[0] == [0, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32], q4
    assert (q4[1][0], max(q4[1]), q4[0][q4[1].index(max(q4[1]))]) == (4.14, 37.74, 8), q4
    assert (iq2[1][0], iq2[1][-1]) == (45.99, 32.45), iq2
    assert q3[1][0] == 37.99, q3
    assert max(q4[1]) / q4[1][0] > 8.5, "Q4_0 断崖应差 9 倍"
    assert (iq2[1][0] - iq2[1][-1]) / iq2[1][0] < 0.30, "装得下最多 -29%"

    # B60 / B65 的 Q4_0 两点（ncmoe 0 全驻留 → 8 人为卸）
    t = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    tab = t.split("## 聊天与文本")[1].split("### 口径 B")[0]
    b60_0 = b65_0 = b65_8 = None
    for ln in tab.splitlines():
        if not ln.startswith("|") or "Qwen3.6-35B-A3B" not in ln:
            continue
        c = [x.strip() for x in ln.split("|")[1:-1]]
        card = c[0].replace("*", "").split()[0]
        if c[2].replace("*", "") != "Q4_0":
            continue
        dec = float(c[4].replace("*", "").split()[0])
        if card == "B60" and "全驻留" in c[6]:
            b60_0 = dec
        elif card == "B65" and "全驻留" in c[6]:
            b65_0 = dec
        elif card == "B65" and "-ncmoe 8" in c[6]:
            b65_8 = dec
    d = json.load(open(ROOT / "bench" / "data" / "2026-10-20_b60-q4-0-ncmoe8.json"))
    b60_8 = float(d["summary"]["decode_tok_s"])
    assert (b60_0, b60_8) == (52.43, 44.4), (b60_0, b60_8)
    assert (b65_0, b65_8) == (53.09, 45.84), (b65_0, b65_8)
    assert 0.14 < 1 - b60_8 / b60_0 < 0.16 and 0.13 < 1 - b65_8 / b65_0 < 0.15, "卸 8 层应 -15% / -14%"
    return iq2, q3, q4, (b60_0, b60_8), (b65_0, b65_8)


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

    iq2, q3, q4, b60, b65 = parse()

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.8, 4.5), dpi=96)
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
            a.set_xlabel(t["x"], fontsize=9.5, color=INK)
            a.set_ylabel(t["y"], fontsize=9.5, color=INK)
            a.set_ylim(0, 62)
            a.set_xlim(-1.5, 34)

        # 左：断崖
        ax.plot(q4[0], q4[1], marker="o", ms=6, lw=2.2, color=C_Q4)
        ax.annotate(t["a0"], xy=(0, 4.14), xytext=(2.2, 12.5), fontsize=8.8, color=INK,
                    arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
        ax.annotate(t["a8"], xy=(8, 37.74), xytext=(11.5, 44.5), fontsize=9, color=INK,
                    weight="bold",
                    arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
        ax.annotate("", xy=(8, 37.74), xytext=(8, 4.14),
                    arrowprops=dict(arrowstyle="<->", color=C_Q4, lw=1.2, alpha=0.65))
        ax.text(8.6, 20, "9×" if lang == "en" else "9 倍", fontsize=11, color=C_Q4, weight="bold")
        ax.set_title(t["pa"], fontsize=11.5, color=INK, pad=12, weight="bold")
        ax.legend(handles=[plt.Line2D([], [], color=C_Q4, marker="o", label=t["lq4"])],
                  frameon=False, fontsize=8.8, loc="lower right")

        # 右：缓坡 + B60/B65 两点
        ax2.plot(*iq2, marker="o", ms=5.5, lw=2.1, color=C_IQ2)
        ax2.plot(*q3, marker="s", ms=5.5, lw=2.1, color=C_Q3)
        for (v0, v8), lab in ((b60, "B60"), (b65, "B65")):
            ax2.plot([0, 8], [v0, v8], ls="--", lw=1.6, color=C_OTHER, marker="D", ms=5.5,
                     mfc="white", mec=C_OTHER)
        ax2.annotate(f"B65 {b65[1]:.2f}", xy=(8, b65[1]), xytext=(10.2, 50.5),
                     fontsize=8.6, color=INK,
                     arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))
        ax2.annotate(f"B60 {b60[1]:.2f}", xy=(8, b60[1]), xytext=(10.2, 39.5),
                     fontsize=8.6, color=INK,
                     arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))
        ax2.text(32, 34.2, "−29%", fontsize=9, color=C_IQ2, weight="bold", ha="center",
                 va="bottom")
        ax2.text(0.5, 56.0, f"{b65[0]:.2f}", fontsize=8.6, color=INK, ha="left", va="bottom")
        ax2.text(0.5, 49.6, f"{b60[0]:.2f}", fontsize=8.6, color=INK, ha="left", va="top")
        ax2.set_title(t["pb"], fontsize=11.5, color=INK, pad=12, weight="bold")
        ax2.legend(handles=[plt.Line2D([], [], color=C_IQ2, marker="o", label=t["liq2"]),
                            plt.Line2D([], [], color=C_Q3, marker="s", label=t["lq3"]),
                            plt.Line2D([], [], color=C_OTHER, ls="--", marker="D", mfc="white",
                                       label=t["lo"])],
                   frameon=False, fontsize=8.4, loc="lower left")

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.905, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.2,
                 color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.055, right=0.985, top=0.74, bottom=0.19, wspace=0.22)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes",
              f"cliff={q4[1][0]}->{max(q4[1])} b60={b60} b65={b65}")


if __name__ == "__main__":
    main()
