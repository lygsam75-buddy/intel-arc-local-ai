#!/usr/bin/env python
"""由 docs/comfyui-image.md §3.3b 直出「采样提速 ≠ 端到端快」2×2 饼图。

每个饼 = 一个配置的端到端时间构成：采样（蓝）vs 装载/重载（灰）。
采样秒数 = 步数 × 表中速率：Music 3 按 s/it 相乘；Krea-2 表值按 it/s 相除
（其表头写 s/it，但 int8 端到端 6.00 s 只有按 it/s 才互洽，代码里有断言把关）。
装载 = 端到端 − 采样。全部数字取自文档，取不到就报错。
输出 docs/assets/int8-e2e-pie{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOC = {"zh": ROOT / "docs" / "comfyui-image.md", "en": ROOT / "docs" / "comfyui-image.en.md"}
OUT = {l: ROOT / "docs" / "assets" / f"int8-e2e-pie{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED = "#2C2C2A", "#5F5E5A"
C_SAMP, C_LOAD = "#2F6FBA", "#C9C8C4"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

TXT = {
    "zh": dict(title="采样快 29–32%，端到端却可能更慢",
               sub="int8 采样提速三个模型同落 1.29–1.32× · 每个饼 = 端到端时间的构成",
               e2e="端到端 {v} s", samp="采样", load="装载与重载",
               names=["Krea-2 bf16（装不下）", "Krea-2 int8（驻留）",
                      "Music 3 fp16（loads 1）", "Music 3 int8（loads 3）"],
               foot="Krea-2 的 19× 与 Music 3 int8 的慢 60% 都来自「装不下」，不是「量化」"
                    "（int8 Music 3 取 208–220 s 的中值）—— 先按显存选档位，再谈量化收益。"),
    "en": dict(title="Sampling is 29–32% faster, yet end-to-end can be slower",
               sub="int8 sampling speedup lands at 1.29–1.32× on three models · each pie = end-to-end time split",
               e2e="end-to-end {v} s", samp="Sampling", load="Loading / reload",
               names=["Krea-2 bf16 (never fits)", "Krea-2 int8 (resident)",
                      "Music 3 fp16 (loads 1)", "Music 3 int8 (loads 3)"],
               foot="Krea-2's 19× and Music 3 int8's 60% slowdown both come from \"does not fit\", not quantization\n"
                    "(Music 3 int8 uses the 208–220 s midpoint) — pick the tier by VRAM first, then talk quantization."),
}


def grab(text, pat, label):
    m = re.search(pat, text)
    if not m:
        raise SystemExit(f"cannot find {label}")
    return [float(x) for x in m.groups()]


def parse(path):
    t = path.read_text(encoding="utf-8")
    row_k = next(ln for ln in t.splitlines() if "Krea-2 Turbo" in ln and "1.165" in ln)
    row_m = next(ln for ln in t.splitlines() if "MiniMax Music 3" in ln and "2.30" in ln)
    kf, ki = grab(row_k, r"bf16\s*\*\*([\d.]+)\*\*\s*\|\s*\*\*([\d.]+)\*\*", "Krea-2 rates")
    mf, mi = grab(row_m, r"fp16 DiT\s*\*\*([\d.]+)\*\*\s*\|\s*\*\*([\d.]+)\*\*", "Music rates")
    ks = grab(row_k, r"(\d+)\s*(?:步|steps)", "Krea-2 steps")[0]
    ms = grab(row_m, r"(\d+)\s*(?:步|steps)", "Music steps")[0]
    if "，是 int8（" in t:      # zh 正文
        kb, kie = grab(t, r"端到端 ([\d.]+) s，是 int8（([\d.]+) s）的", "Krea-2 e2e")
        m_lo, m_hi, m_fp = grab(
            t, r"端到端 \*\*([\d.]+) 至 ([\d.]+) s，反而比 fp16 的 ([\d.]+) s 慢", "Music e2e")
    else:                       # en 正文
        kb, kie = grab(t, r"([\d.]+) s end-to-end, \*\*19×\*\* int8 \(([\d.]+) s\)", "Krea-2 e2e")
        m_lo, m_hi, m_fp = grab(
            t, r"\*\*([\d.]+) to ([\d.]+) s end-to-end, 60% slower than fp16's ([\d.]+) s",
            "Music e2e")
    return kf, ki, mf, mi, ks, ms, kb, kie, m_lo, m_hi, m_fp


def fmt(v):
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return s


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
        kf, ki, mf, mi, ks, ms, kb, kie, m_lo, m_hi, m_fp = parse(DOC[lang])
        t = TXT[lang]
        m_mid = (m_lo + m_hi) / 2
        panels = [  # (标题, 端到端 s, 采样 s)
            (t["names"][0], kb, ks / kf),      # Krea-2 表值按 it/s 相除
            (t["names"][1], kie, ks / ki),
            (t["names"][2], m_fp, ms * mf),    # Music 3 按 s/it 相乘
            (t["names"][3], m_mid, ms * mi),
        ]
        assert ks / ki < kie, "Krea-2 表值须按 it/s 才能与 int8 端到端互洽"
        assert all(samp < e2e for _, e2e, samp in panels), panels
        assert kb > kie * 10, "Krea-2 bf16/int8 端到端应差一个量级（19×）"

        def pct(p):
            return f"{p:.0f}%" if p >= 8 else ""   # <8% 的窄片不标，避免挤出饼外

        fig, axes = plt.subplots(2, 2, figsize=(8.8, 6.0), dpi=96)
        fig.patch.set_facecolor("white")
        for ax, (name, e2e, samp) in zip(axes.flat, panels):
            ax.set_facecolor("white")
            load = e2e - samp
            wedges, _, autos = ax.pie(
                [samp, load], colors=[C_SAMP, C_LOAD], startangle=90, counterclock=False,
                autopct=pct, pctdistance=0.62,
                wedgeprops=dict(edgecolor="white", linewidth=1.5))
            autos[0].set_color("white")
            autos[1].set_color(INK)
            for at in autos:
                at.set_fontsize(9.5)
                at.set_weight("bold")
            ax.set_title(f"{name}\n" + t["e2e"].format(v=fmt(e2e)),
                         fontsize=10, color=INK, pad=8, weight="bold")

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.932, t["sub"], ha="center", fontsize=9.5, color=MUTED)
        fig.legend(handles=[Patch(facecolor=C_SAMP), Patch(facecolor=C_LOAD)],
                   labels=[t["samp"], t["load"]], loc="lower center",
                   bbox_to_anchor=(0.5, 0.085), ncol=2, frameon=False, fontsize=9.5)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom",
                 fontsize=9.2, color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.02, right=0.98, top=0.82, bottom=0.17,
                            hspace=0.38, wspace=0.02)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes")


if __name__ == "__main__":
    main()
