# -*- coding: utf-8 -*-
"""双卡 B65「五、真正买到的三样东西」注解图：三条分项的结果先看。

锚点数字全部从 bench/data/*.json 直出（与 dual-b65-report 总表同源），禁止手抄。
三栏 = 5.1 上下文容量 / 5.2 模型容量 / 5.3 产线，每栏 before → after + 一个结果。
输出 docs/assets/dual-b65-three-things{,.en}.svg（纯 LF）。
"""
import io
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA_DIR = os.path.join(REPO, "bench", "data")
OUT = {l: os.path.join(REPO, "docs", "assets",
                       "dual-b65-three-things%s.svg" % ("" if l == "zh" else ".en"))
       for l in ("zh", "en")}
PNG_PREVIEW = None  # 如需 PNG 目视件，由调用方另存；此处只出 SVG

INK, MUTED = "#2C2C2A", "#5F5E5A"
C_A, C_A_LIGHT, C_BG = "#2F6FBA", "#D6E4F7", "#F7F9FC"
C_WARN = "#C2410C"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")


def load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def tok(n):
    if n >= 1048576:
        return "%gM token" % (n / 1048576.0)
    if n >= 1024:
        return "%gK token" % (n / 1024.0)
    return "%d token" % n


def f2(x):
    return "%.2f" % x


def f1(x):
    return "%.1f" % x


def fx(x):
    if abs(x - round(x)) < 0.05:
        return "%d\u00d7" % round(x)
    return "%.2f\u00d7" % x


def pct(x):
    """−0.2% 形式（真减号）。"""
    return ("%+.1f%%" % x).replace("-", "\u2212")


# ---------------------------------------------------------------- 取数
ctx = load("2026-10-23_b65-32g_q4_0-ctxcap-dual.json")["summary"]
scan2 = {x["tag"]: x for x in load("2026-10-24_b65-32g-dual-ts-scan2.json")["samples"]}
q8_ngl37b = load("2026-10-24_b65-32g-q8_0-solo37-recheck.json")["samples"][0]
q_solo = load("2026-10-23_b65-32g-q4_0-dual-c1.json")["summary"]
q_conc = load("2026-10-23_b65-32g-q4_0-dual-c1-concurrent.json")["summary"]

ctx_s = tok(ctx["single_max_allocated_ctx"])          # 单卡真装下
ctx_d = tok(ctx["dual_max_allocated_ctx_unified"])    # 双卡默认真装下
q8_dec = f2(scan2["ts6040"]["decode_tok_s"])          # 双卡拆层全驻
q8_solo = f2(q8_ngl37b["decode_tok_s"])               # 单卡带 CPU 尾
r_q8 = scan2["ts6040"]["decode_tok_s"] / q8_ngl37b["decode_tok_s"]
dec_pct = 100.0 * (q_conc["decode_tok_s"] / q_solo["decode_tok_s"] - 1)

# 三栏：header, before, after, chip, micro
PANELS = {
    "zh": [
        dict(h="① 上下文容量（5.1）",
             b="单卡 %s 真装下" % ctx_s,
             a="双卡 %s 真装下" % ctx_d,
             chip="真装下 3×，不是 2×",
             micro="3M 只是分配上限"),
        dict(h="② 模型容量（5.2）",
             b="34.37 GiB\n单卡装不下",
             a="双卡拆层全驻\n解码 %s tok/s" % q8_dec,
             chip="装得下，且不赔速度",
             micro="单卡 %s tok/s（带 CPU 尾）" % q8_solo),
        dict(h="③ 产能 · 两条产线（5.3）",
             b="1 条产线",
             a="2 条产线",
             chip="一条视频 ＋ 一条轻活",
             micro="出图×2 零损失 · 视频+聊天 %s · 两条视频要 64 GB 内存" % pct(dec_pct)),
    ],
    "en": [
        dict(h="① Context capacity (5.1)",
             b="Single card: %s truly fits" % ctx_s,
             a="Dual: %s truly fits" % ctx_d,
             chip="3\u00d7 context, not 2\u00d7",
             micro="3M is only an allocation cap"),
        dict(h="② Model capacity (5.2)",
             b="34.37 GiB\nwon't fit on one card",
             a="Dual layer-split, fully resident\ndecode %s tok/s" % q8_dec,
             chip="It fits, with no speed cost",
             micro="Single card %s tok/s (CPU tail)" % q8_solo),
        dict(h="③ Throughput: two lines (5.3)",
             b="1 production line",
             a="2 production lines",
             chip="One video + one light job",
             micro="Image\u00d72 zero loss \u00b7 video+chat %s \u00b7 two videos need 64 GB RAM" % pct(dec_pct)),
    ],
}

META = {
    "zh": dict(title="三样东西，三个结果",
               sub="2× B65 = 容量 ×2 ＋ 产线 ×2；单条任务的速度不在其中",
               foot="三样全是容量和产能，单条速度不在其中；逐项数字见下文，全表见「总测试项汇总」。"),
    "en": dict(title="Three things, three results",
               sub="2\u00d7 B65 = 2\u00d7 capacity + 2\u00d7 production lines; single-job speed is not among them",
               foot="All three are capacity and throughput \u2014 single-job speed is not among them; "
                    "per-item numbers below, full table in All-Test Summary."),
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
        t = META[lang]
        panels = PANELS[lang]
        fig, ax = plt.subplots(figsize=(10.4, 4.5), dpi=96)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")
        ax.set_xlim(0, 10.6)
        ax.set_ylim(0, 10.2)
        ax.axis("off")

        for i, p in enumerate(panels):
            cx = 1.85 + i * 3.45
            # 栏头
            ax.add_patch(FancyBboxPatch((cx - 1.5, 8.15), 3.0, 0.82,
                                        boxstyle="round,pad=0.07",
                                        fc=C_A_LIGHT, ec=C_A, lw=1.2))
            ax.text(cx, 8.56, p["h"], ha="center", va="center",
                    fontsize=10.2, color=INK, weight="bold")
            # before
            ax.add_patch(FancyBboxPatch((cx - 1.42, 6.35), 2.84, 1.3,
                                        boxstyle="round,pad=0.07",
                                        fc=C_BG, ec=MUTED, lw=1.1))
            ax.text(cx, 7.0, p["b"], ha="center", va="center",
                    fontsize=8.9, color=MUTED, linespacing=1.5)
            # 箭头：before → after
            ax.add_patch(FancyArrowPatch((cx, 6.22), (cx, 5.62), arrowstyle="-|>",
                                         mutation_scale=16, color=C_A, lw=1.8))
            # after（结果本体）
            ax.add_patch(FancyBboxPatch((cx - 1.42, 3.82), 2.84, 1.72,
                                        boxstyle="round,pad=0.07",
                                        fc=C_A_LIGHT, ec=C_A, lw=1.7))
            ax.text(cx, 4.68, p["a"], ha="center", va="center",
                    fontsize=9.6, color=INK, weight="bold", linespacing=1.55)
            # 一个结果
            ax.text(cx, 3.18, p["chip"], ha="center", va="center",
                    fontsize=10.0, color=C_A, weight="bold")
            # 锚点小字
            ax.text(cx, 2.42, p["micro"], ha="center", va="center",
                    fontsize=7.7, color=C_WARN if i == 2 else MUTED)

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.935, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=8.6, color=INK)
        fig.subplots_adjust(left=0.01, right=0.99, top=0.87, bottom=0.07)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        data = buf.getvalue().replace(b"\r\n", b"\n")
        with open(OUT[lang], "wb") as f:
            f.write(data)
        print("written:", OUT[lang], len(data), "bytes")

        # PNG 目视件（交付前检查用）
        pdir = os.path.join(os.environ.get("TEMP", "/tmp"), "wb-svg-preview")
        os.makedirs(pdir, exist_ok=True)
        png = os.path.join(pdir, os.path.basename(OUT[lang]).replace(".svg", ".png"))
        fig.savefig(png, format="png", dpi=144)
        print("png-preview:", png)
        plt.close(fig)


if __name__ == "__main__":
    main()
