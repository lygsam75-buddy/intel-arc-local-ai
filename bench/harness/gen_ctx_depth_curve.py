#!/usr/bin/env python
"""由 README.zh-CN.md「长上下文 §② 真填满」表直出 decode / prefill 对深度的双面板曲线。

左：decode tok/s 对深度（log 横轴），叠加 ms/token 线性拟合的反演曲线（虚线），
    端点标 decode 比值 1.16× / 1.36×。
右：prefill tok/s 对深度，端点标 0.88× / 1.73×（交叉在 3 万 token 附近）。
拟合斜率由表内 6 点自行最小二乘算出（断言与文档口径 0.66× 一致），
数字取不到就报错。输出 docs/assets/ctx-depth-curve{,.en}.svg（纯 LF）。
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "README.zh-CN.md"
OUT = {l: ROOT / "docs" / "assets" / f"ctx-depth-curve{'' if l == 'zh' else '.en'}.svg"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
C_B65, C_B50 = "#2F6FBA", "#C2410C"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")

# 已登记的拟合口径（test-registry T-07 / vram-16gb.md D.2）：ms/token = a + b × 深度。
# 不在图里重新拟合——图注数字必须与登记口径一致。
FIT65 = (20.32, 0.000198)   # 残差 4.7%，截距 = 49.2 tok/s 上限
FIT50 = (22.95, 0.000298)   # 残差 2.4%，截距 = 43.6 tok/s 上限
assert FIT65[1] / FIT50[1] < 0.67, "斜率比应为 0.66× 口径"

TXT = {
    "zh": dict(title="长上下文真填满：decode 对深度是直线，差距随深度拉大",
               sub="Qwen3.6-35B-A3B · B65 Q4_0（全驻留）/ B50 IQ2_M（卸专家）· 各自交付档 · log 横轴",
               p1="decode（tok/s）· 斜率比 {r}×", p2="prefill（tok/s）· 约 3 万 token 交叉",
               l1="B65 · Q4_0", l2="B50 · IQ2_M", x="填充深度（token）",
               foot="权重搬运进截距、注意力进斜率 —— 换量化档动截距不动斜率；"
                    "B65 斜率 {b65}、B50 {b50} ms/token。"),
    "en": dict(title="Filled long context: decode vs depth is a straight line, the gap widens",
               sub="Qwen3.6-35B-A3B · B65 Q4_0 (resident) / B50 IQ2_M (experts offloaded) · each card's delivery tier · log x",
               p1="decode (tok/s) · slope ratio {r}×", p2="prefill (tok/s) · crossing near 30k tokens",
               l1="B65 · Q4_0", l2="B50 · IQ2_M", x="Filled depth (tokens)",
               foot="Weights stream into the intercept, attention into the slope — quant moves the intercept, not the slope; B65 0.000198 vs B50 0.000298 ms/token."),
}


def parse():
    t = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    sec = t.split("### 长上下文")[1].split("## 六")[0]
    depths = b65d = b50d = b65p = b50p = None
    for ln in sec.splitlines():
        if ln.startswith("|") and "实测深度" in ln:
            depths = [float(x.replace(",", "")) for x in ln.split("|")[2:-1]]
        elif b65d is None and "B65" in ln and "decode" in ln:
            b65d = [float(x.replace(",", "").replace("*", "").strip()) for x in ln.split("|")[2:-1]]
        elif b65p is None and "B65" in ln and "prefill" in ln:
            b65p = [float(x.replace(",", "").replace("*", "").strip()) for x in ln.split("|")[2:-1]]
        elif b50d is None and "B50" in ln and "decode" in ln:
            b50d = [float(x.replace(",", "").replace("*", "").strip()) for x in ln.split("|")[2:-1]]
        elif b50p is None and "B50" in ln and "prefill" in ln:
            b50p = [float(x.replace(",", "").replace("*", "").strip()) for x in ln.split("|")[2:-1]]
    assert depths and len(depths) == 6, depths
    for v in (b65d, b50d, b65p, b50p):
        assert v and len(v) == 6, v
    return np.array(depths), b65d, b50d, b65p, b50p


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

    d, b65d, b50d, b65p, b50p = parse()
    # 拟合残差把关：登记式子必须能贴住表内 6 点
    for (a, b), ms in ((FIT65, b65d), (FIT50, b50d)):
        res = max(abs((a + b * dd) * v / 1000 - 1) for dd, v in zip(d, ms))
        assert res < 0.055, (a, b, res)
    b65s, b50s = f"{FIT65[1]:.6f}", f"{FIT50[1]:.6f}"
    ratio = FIT65[1] / FIT50[1]

    for lang in ("zh", "en"):
        t = TXT[lang]
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.2, 4.3), dpi=96)
        fig.patch.set_facecolor("white")
        for a in (ax, ax2):
            a.set_facecolor("white")
            a.set_xscale("log")
            a.set_xlabel(t["x"], fontsize=10, color=INK)
            a.grid(axis="y", color=GRID, lw=0.9)
            a.set_axisbelow(True)
            for s in ("top", "right"):
                a.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                a.spines[s].set_color(MUTED)
            a.tick_params(labelsize=9)

        # 左：decode + 拟合虚线
        xf = np.linspace(d[0], d[-1], 100)
        ax.plot(d, b65d, marker="o", ms=6.5, lw=2.1, color=C_B65)
        ax.plot(d, b50d, marker="o", ms=6.5, lw=2.1, color=C_B50)
        ax.plot(xf, 1000 / (FIT65[0] + FIT65[1] * xf), ls="--", lw=1.2, color=C_B65, alpha=0.55)
        ax.plot(xf, 1000 / (FIT50[0] + FIT50[1] * xf), ls="--", lw=1.2, color=C_B50, alpha=0.55)
        ax.text(d[0] * 1.55, (b65d[0] + b50d[0]) / 2 - 0.8, f"{b65d[0] / b50d[0]:.2f}×",
                fontsize=9.5, color=INK, weight="bold")
        ax.text(d[-1] * 0.86, (b65d[-1] + b50d[-1]) / 2, f"{b65d[-1] / b50d[-1]:.2f}×",
                fontsize=9.5, color=INK, weight="bold", ha="right")
        ax.set_title(t["p1"].format(r=f"{ratio:.2f}"), fontsize=11.5, color=INK,
                     pad=12, weight="bold")
        ax.set_ylim(0, 60)
        ax.legend(handles=[plt.Line2D([], [], color=C_B65, marker="o", label=t["l1"]),
                           plt.Line2D([], [], color=C_B50, marker="o", label=t["l2"])],
                  frameon=False, fontsize=9, loc="upper right")

        # 右：prefill 交叉
        ax2.plot(d, b65p, marker="o", ms=6.5, lw=2.1, color=C_B65, label=t["l1"])
        ax2.plot(d, b50p, marker="o", ms=6.5, lw=2.1, color=C_B50, label=t["l2"])
        ax2.text(d[0] * 1.12, (b65p[0] + b50p[0]) / 2, f"{b65p[0] / b50p[0]:.2f}×",
                 fontsize=9.5, color=INK, weight="bold")
        ax2.text(d[-1] * 0.86, (b65p[-1] + b50p[-1]) / 2, f"{b65p[-1] / b50p[-1]:.2f}×",
                 fontsize=9.5, color=INK, weight="bold", ha="right")
        ax2.set_title(t["p2"], fontsize=11.5, color=INK, pad=12, weight="bold")
        ax2.set_ylim(0, 700)
        ax2.legend(frameon=False, fontsize=9, loc="upper right")

        fig.suptitle(t["title"], fontsize=13, color=INK, weight="bold", y=1.0)
        fig.text(0.5, 0.905, t["sub"], ha="center", fontsize=9, color=MUTED)
        fig.text(0.5, 0.012, t["foot"].format(b65=b65s, b50=b50s), ha="center",
                 va="bottom", fontsize=9.2, color=INK, linespacing=1.5)
        fig.subplots_adjust(left=0.06, right=0.985, top=0.74, bottom=0.18, wspace=0.22)

        buf = io.BytesIO()
        fig.savefig(buf, format="svg")
        OUT[lang].write_bytes(buf.getvalue().replace(b"\r\n", b"\n"))
        plt.close(fig)
        print(OUT[lang].relative_to(ROOT), OUT[lang].stat().st_size, "bytes",
              f"slope65={FIT65[1]:.6f} slope50={FIT50[1]:.6f} ratio={ratio:.3f}")


if __name__ == "__main__":
    main()
