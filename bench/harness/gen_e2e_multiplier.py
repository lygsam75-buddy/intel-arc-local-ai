#!/usr/bin/env python
"""由 README.zh-CN.md 表 4「B70 相对 B50」列 + 出视频表的单步行
直出「端到端倍数被固定开销摊薄」单面板图。

四条负载横条：解码 2.0×（无摊薄）· H3 出视频一对（单步 3.3× / 端到端 2.6×，
配对标注「固定开销摊薄」）· 出图 4.87× · 出音乐 ≈3.3×。
H3 的两个倍数同批自算（单步 22/6.6、端到端 399/152.5），与表内 2.6× 对账。
数字取不到就报错。输出 docs/assets/e2e-multiplier{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "README.zh-CN.md"
OUT = {l: ROOT / "docs" / "assets" / f"e2e-multiplier{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_STEP, C_E2E, C_ONE = "#1B7F79", "#2F6FBA", "#C2410C"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

TXT = {
    "zh": dict(
        title="端到端倍数 < 单步倍数：固定开销把卡间差摊薄",
        sub="B70 32G 相对 B50 16G · 同一批内横比 · 跨卡只比单步，端到端只比同批连跑 · 2026-10 口径",
        x="B70 相对 B50 的加速倍数",
        labs=["大模型解码\nQ4_0 · 全驻", "H3 出视频 · 单步\n864×480 · 6 步",
              "H3 出视频 · 端到端\n含装载与固定开销", "出图 Qwen\nint8 · 25 步",
              "出音乐 Music 3\nint8 · 30 步"],
        dilute="固定开销把 3.3× 摊到 2.6×\n（480p 装载主导）",
        note="H3 两根条同一批自算",
        foot="倍数要问「哪一段」：装得下且稳态计算主导的负载（出图出音乐）倍数不被摊薄；"
             "加载主导的 H3 端到端只剩单步的八成——跨卡比较先定口径，再比数字。"),
    "en": dict(
        title="End-to-end ratios sit below per-step ratios: fixed overhead dilutes the gap",
        sub="B70 32G vs B50 16G · within-batch only · cross-card: per-step only · 2026-10",
        x="Speed-up of B70 over B50",
        labs=["LLM decode\nQ4_0 · resident", "H3 video · per step\n864x480 · 6 steps",
              "H3 video · end to end\nincl. load & fixed", "Image · Qwen\nint8 · 25 steps",
              "Music 3\nint8 · 30 steps"],
        dilute="fixed overhead dilutes\n3.3x into 2.6x (load-bound)",
        note="H3 pair computed from one batch",
        foot="Ask which segment first: resident compute-bound loads (image, music) keep their ratio;\n"
             "loading-bound H3 end-to-end keeps only ~80% of the per-step ratio — fix the protocol, then compare."),
}


def parse():
    t = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")

    # 表 4：B70 相对 B50 列
    sec = t.split("## 表 4")[1].split("## 表 4b")[0]
    mult = {}
    for ln in sec.splitlines():
        if not ln.startswith("|") or "tok/s" not in ln and "s |" not in ln:
            continue
        c = [x.strip() for x in ln.split("|")[1:-1]]
        if len(c) < 6 or "×" not in c[5]:
            continue
        name = c[0]
        val = c[5].replace("*", "").replace("≈", "").replace("×", "")
        if "解码" in name:
            mult["decode"] = float(val)
        elif "出视频" in name:
            mult["video"] = float(val)
        elif "出图" in name:
            mult["image"] = float(val)
        elif "出音乐" in name:
            mult["music"] = float(val)
    assert mult == {"decode": 2.0, "video": 2.6, "image": 4.87, "music": 3.3}, mult

    # 出视频表：单步行（B50 22 s / B70 6.6 s）同批自算单步倍数
    h3 = t.split("## 出视频")[1].split("### 一条片子")[0]
    rows = {}
    for ln in h3.splitlines():
        if not ln.startswith("|") or "单步" not in ln and "端到端" not in ln:
            continue
        c = [x.strip().replace("*", "") for x in ln.split("|")[1:-1]]
        if c[0].startswith("采样 / 单步"):
            m70 = re.search(r"/\s*([\d.]+)\s*s", c[1])
            m50 = re.search(r"/\s*([\d.]+)\s*s", c[4])
            rows["step"] = (float(m50.group(1)), float(m70.group(1)))
        elif c[0].startswith("端到端"):
            m70 = re.search(r"([\d.]+)\s*s", c[1])
            m50 = re.search(r"([\d.]+)\s*s", c[4])
            rows["e2e"] = (float(m50.group(1)), float(m70.group(1)))
    assert rows["step"] == (22.0, 6.6), rows
    assert rows["e2e"] == (399.0, 152.5), rows
    step_mult = rows["step"][0] / rows["step"][1]
    e2e_mult = rows["e2e"][0] / rows["e2e"][1]
    assert abs(e2e_mult - 2.62) < 0.02 and abs(step_mult - 3.33) < 0.02, (e2e_mult, step_mult)
    # 与表内 2.6× 对账
    assert abs(e2e_mult - mult["video"]) < 0.05, (e2e_mult, mult["video"])
    return mult, step_mult, e2e_mult


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

    mult, step_mult, e2e_mult = parse()

    for lang in ("zh", "en"):
        t = TXT[lang]
        vals = [mult["decode"], step_mult, e2e_mult, mult["image"], mult["music"]]
        cols = [C_ONE, C_STEP, C_E2E, C_ONE, C_ONE]
        labels = t["labs"]
        ys = list(range(len(vals)))[::-1]   # 自上而下

        fig, ax = plt.subplots(figsize=(9.2, 3.9), dpi=96)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")
        ax.grid(axis="x", color=GRID, lw=0.9)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(MUTED)
        ax.tick_params(labelsize=9)

        ax.barh(ys, vals, height=0.55, color=cols, zorder=3)
        for y, v in zip(ys, vals):
            if abs(v - 3.3) < 0.01:
                lab = f"≈{v:.1f}×"
            else:
                lab = f"{v:.2f}×".replace(".00×", ".0×")
            ax.text(v + 0.08, y, lab, va="center", fontsize=9.5, color=INK,
                    weight="bold")
        ax.set_yticks(ys)
        ax.set_yticklabels(labels, fontsize=8.8)
        ax.set_xlim(0, max(vals) * 1.32)
        ax.set_xlabel(t["x"], fontsize=9.5, color=INK)

        # H3 一对：括注摊薄
        y_step, y_e2e = ys[1], ys[2]
        ax.annotate("", xy=(step_mult + 0.15, y_step), xytext=(step_mult + 0.15, y_e2e),
                    arrowprops=dict(arrowstyle="<->", color=MUTED, lw=1.1))
        ax.text(step_mult + 0.28, (y_step + y_e2e) / 2, t["dilute"], fontsize=8.6,
                color=MUTED, va="center", ha="left", linespacing=1.4)

        fig.suptitle(t["title"], fontsize=12.6, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.905, t["sub"], ha="center", fontsize=8.6, color=MUTED)
        fig.text(0.5, 0.012, t["foot"], ha="center", va="bottom", fontsize=9.0,
                 color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.185, right=0.97, top=0.80, bottom=0.28)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT),
              "decode", mult["decode"], "step", round(step_mult, 2),
              "e2e", round(e2e_mult, 2), "image", mult["image"], "music", mult["music"])


if __name__ == "__main__":
    main()
