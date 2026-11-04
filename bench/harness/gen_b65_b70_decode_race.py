#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B65 vs B70 解码速度实时对比 —— 动图版。

用真实实测速度（B65 89.27 / B70 115.56 tok/s）跑一条 500 token 回复，
两条进度条以真实速率填充，结尾给出「九千块买回多少秒」。

输出 docs/assets/b65-b70-decode-race{,.en}.gif（知乎/公众号可直接贴）。
速度取自 bench/data/2026-10-21_b65-q4-0-vulkan.json 与 2026-10-20_b70-q4-0-vulkan.json。
"""
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = {l: ROOT / "docs" / "assets" / f"b65-b70-decode-race{'' if l == 'zh' else '.en'}.gif"
       for l in ("zh", "en")}

INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"
B65_C, B70_C = "#2F6FBA", "#C2410C"
B65_L, B70_L = "#E6F1FB", "#FAECE7"
FONT = ("Microsoft YaHei", "SimHei", "Noto Sans SC")
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["font.sans-serif"] = list(FONT) + ["DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

SPD_A, SPD_B = 89.27, 115.56          # tok/s，实测
TOTAL = 500                            # token 数
PRICE_DELTA = 9000                     # 价差（元）
FPS = 10
T_END = TOTAL / SPD_A + 0.6            # 让 B65 跑完再收尾


def frame_data(t):
    a = min(TOTAL, t * SPD_A)
    b = min(TOTAL, t * SPD_B)
    return a, b


def make(lang):
    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    fig.subplots_adjust(left=0.06, right=0.97, top=0.86, bottom=0.14)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    is_zh = lang == "zh"
    ttl = "九千块买到的解码加速，到底有多快" if is_zh else "What ¥9,000 buys you in decode speed"
    lbl_a = "B65  ¥9,999  ·  89.27 tok/s" if is_zh else "B65  ¥9,999  ·  89.27 tok/s"
    lbl_b = "B70  ¥18,999  ·  115.56 tok/s"
    fig.text(0.5, 0.945, ttl, ha="center", va="top", fontsize=15,
             fontweight="500", color=INK, transform=fig.transFigure)

    # 两条进度条
    y_a, y_b, h = 0.62, 0.40, 0.105
    bar_x0, bar_w = 0.18, 0.70

    ax.add_patch(plt.Rectangle((bar_x0, y_a), bar_w, h, facecolor=B65_L, ec="none"))
    ax.add_patch(plt.Rectangle((bar_x0, y_b), bar_w, h, facecolor=B70_L, ec="none"))
    fill_a = ax.add_patch(plt.Rectangle((bar_x0, y_a), 0, h, facecolor=B65_C, ec="none"))
    fill_b = ax.add_patch(plt.Rectangle((bar_x0, y_b), 0, h, facecolor=B70_C, ec="none"))

    ax.text(bar_x0 - 0.015, y_a + h / 2, lbl_a, ha="right", va="center",
            fontsize=11, color=INK, fontweight="500")
    ax.text(bar_x0 - 0.015, y_b + h / 2, lbl_b, ha="right", va="center",
            fontsize=11, color=INK, fontweight="500")

    tok_a = ax.text(bar_x0 + bar_w / 2, y_a + h / 2, "", ha="center", va="center",
                    fontsize=12, color="white", fontweight="500")
    tok_b = ax.text(bar_x0 + bar_w / 2, y_b + h / 2, "", ha="center", va="center",
                    fontsize=12, color="white", fontweight="500")
    sec = ax.text(bar_x0 + bar_w + 0.015, 0.51, "", ha="left", va="center",
                  fontsize=11, color=MUTED)

    # 底部结论
    t_a, t_b = TOTAL / SPD_A, TOTAL / SPD_B
    save = t_a - t_b
    n_reply = round(PRICE_DELTA / save)
    if is_zh:
        lead = (f"一条 {TOTAL} token 回复：B65 {t_a:.2f} 秒，B70 {t_b:.2f} 秒，"
                f"省下 {save:.2f} 秒。")
        tail = f"要靠解码省回九千块，约需 {n_reply:,} 条这样的回复。"
    else:
        lead = (f"A {TOTAL}-token reply: B65 {t_a:.2f} s, B70 {t_b:.2f} s, "
                f"saving {save:.2f} s.")
        tail = (f"To earn back ¥9,000 in decode time alone takes about "
                f"{n_reply:,} such replies.")
    fig.text(0.5, 0.115, lead, ha="center", va="center", fontsize=12.5,
             color=INK, fontweight="500", transform=fig.transFigure)
    fig.text(0.5, 0.052, tail, ha="center", va="center", fontsize=11,
             color=MUTED, transform=fig.transFigure)

    def update(frame):
        t = frame / FPS
        a, b = frame_data(t)
        fill_a.set_width(bar_w * a / TOTAL)
        fill_b.set_width(bar_w * b / TOTAL)
        tok_a.set_text(f"{int(a)} / {TOTAL}")
        tok_b.set_text(f"{int(b)} / {TOTAL}")
        sec.set_text(f"{t:.2f} s")
        return fill_a, fill_b, tok_a, tok_b, sec

    n_frames = int(T_END * FPS)
    anim = FuncAnimation(fig, update, frames=n_frames, blit=False, interval=1000 // FPS)

    import os as _os
    import tempfile as _tf
    tmp = _os.path.join(_tf.gettempdir(), "race_%s.gif" % lang)
    anim.save(tmp, writer=PillowWriter(fps=FPS), dpi=110)
    plt.close(fig)
    with open(tmp, "rb") as _f:
        data = _f.read()
    _os.remove(tmp)
    return data


for lang in ("zh", "en"):
    data = make(lang)
    out = OUT[lang]
    out.write_bytes(data)
    print(f"wrote {out.name} ({len(data)//1024} KB)")


def main():
    print("done")


if __name__ == "__main__":
    main()
