#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 `docs/at-a-glance{,.en}.md` 第 3、4 节的柱状图（中英共用同一张图，矢量 SVG）。

为什么是脚本：一页纸里的数字只能来自 `bench/data`，不能手抄。
本文件只做「读 json → 画图 → 落 docs/assets/」，不改任何 md。

图内文字一律用数字 / 卡型号 / 单位，**不放解释性中文**——
否则中英两版要么用不了同一张图，要么得画两份。

图 1（§3 多大的模型装得进显存）：x = 四张卡，每组三根 = 三档量化（由浅到深＝体积由小到大），
  y = tok/s。B50 的 Q4_0 那根加斜纹：16 GB 装不下，要卸到内存。
  B70 的两档小模型没有实测 → 留空 + 灰色 `not measured`，**不推算**。
图 2（§4 出一条 5 秒视频要等多久）：x = 四张卡，每组三根 = 三档分辨率，y = 分钟。
"""
import json
import os
import re
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # bench/harness -> 仓库根
DATA = os.path.join(REPO, 'bench', 'data')
OUT = os.path.join(REPO, 'docs', 'assets')

sys.path.insert(0, HERE)
import gen_h3_ladder as L                                   # noqa: E402

CARDS = ['b50', 'b60', 'b65', 'b70']
CARD_LABEL = {'b50': 'B50\n16 GB', 'b60': 'B60\n24 GB',
              'b65': 'B65\n32 GB', 'b70': 'B70\n32 GB'}
COLOR = {'b50': '#64748B', 'b60': '#2563EB', 'b65': '#0D9488', 'b70': '#EA580C'}
# 组内三根由浅到深（浅＝小模型 / 低分辨率，深＝大模型 / 高分辨率）
SHADE = [0.52, 0.76, 1.00]
INK = '#1F2937'
MUTED = '#9CA3AF'
GRID = '#E5E7EB'

# ----------------------------------------------------------------------------
# §3 数据来源：每格一个文件，decode_tok_s 直取
# ----------------------------------------------------------------------------
QUANT_FILES = [
    ('b50', '2026-10-15_b50-16g-iq2m-ncmoe-pcie5x8-ncmoe0.json', 10.73),
    ('b50', '2026-10-15_b50-16g-q3ks-ncmoe-pcie5x8-ncmoe0.json', 14.30),
    ('b50', '2026-10-15_b50-16g-ncmoe8-final-pcie5x8-ncmoe8.json', 19.41),
    ('b60', '2026-10-20_b60-iq2m-base.json', 10.73),
    ('b60', '2026-10-20_b60-q3ks-base.json', 14.30),
    ('b60', '2026-10-20_b60-q4-0-base.json', 19.41),
    ('b65', '2026-10-21_b65-iq2m-base.json', 10.73),
    ('b65', '2026-10-21_b65-q3ks-base.json', 14.30),
    ('b65', '2026-10-21_b65-q4-0-base.json', 19.41),
    # B70 只测过 Q4_0（两档小模型未测，不给推算值）
    ('b70', '2026-10-15_b70-32g_qwen3.6-35b-a3b-q4_0-sycl-r3.json', 19.41),
]


def read_quant():
    """→ {(card, size): tok_s}，并核对文件里的 size_gib 与预期一致。"""
    out = {}
    for card, name, size in QUANT_FILES:
        p = os.path.join(DATA, name)
        d = json.load(open(p, encoding='utf-8'))
        got = d['model']['size_gib']
        assert abs(got - size) < 0.02, '%s: size %.2f != %.2f' % (name, got, size)
        out[(card, size)] = d['summary']['decode_tok_s']
    return out


# ----------------------------------------------------------------------------
# 画图
# ----------------------------------------------------------------------------
def shade(hex_color, t):
    """t=0 白，t=1 原色。"""
    h = hex_color.lstrip('#')
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return tuple((1 - t) + (c / 255.0) * t for c in rgb)


def axes_style(ax, ylabel):
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color('#D1D5DB')
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK, labelsize=9, length=0)
    ax.set_ylabel(ylabel, color='#4B5563', fontsize=9.5, labelpad=6)


def label_bars(ax, xs, ys, text_fn, dy):
    for x, y in zip(xs, ys):
        if y is None:
            continue
        ax.text(x, y + dy, text_fn(y), ha='center', va='bottom',
                fontsize=8.4, color=INK, fontweight='medium')


def save_svg(fig, path, w_in, h_in, dpi=200):
    """存成 SVG，并把根元素的 width/height 写成像素尺寸。

    matplotlib 默认给的是 `width="504pt"` —— GitHub 会按这个 pt 值显示，
    图会比原来的 1400 px 小一半。viewBox 不变，只改显示尺寸。
    """
    # 两处会让每次重跑的字节都不一样：metadata 里的生成时间、matplotlib 随机生成的
    # id（clip-path 之类）。两样都锁掉，才有「重跑 sha 不变」。
    matplotlib.rcParams['svg.hashsalt'] = 'intel-arc-b-series'
    fig.savefig(path, format='svg', facecolor='white', metadata={'Date': None})
    s = open(path, encoding='utf-8').read()
    m = re.search(r'<svg([^>]*)>', s)
    attrs = re.sub(r'\s(?:width|height)="[^"]*"', '', m.group(1))
    s = s.replace(m.group(0),
                  '<svg%s width="%d" height="%d">' % (attrs, round(w_in * dpi), round(h_in * dpi)),
                  1)
    open(path, 'w', encoding='utf-8', newline='\n').write(s)


def main():
    os.makedirs(OUT, exist_ok=True)

    # ---------------- §3 ----------------
    q = read_quant()
    sizes = sorted({s for (_, s) in q})
    labels = ['%.1f GB' % s for s in sizes]
    assert len(sizes) == 3, sizes

    fig, ax = plt.subplots(figsize=(7.0, 3.45), dpi=200)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    w, n = 0.23, 3
    for gi, card in enumerate(CARDS):
        for si, size in enumerate(sizes):
            v = q.get((card, size))
            x = gi + (si - 1) * w
            if v is None:
                # 没实测就不画柱、也不推算：只在原位留一个灰 n/a
                ax.text(x, 2.0, 'n/a', ha='center', va='bottom',
                        fontsize=7.4, color=MUTED, zorder=4)
                continue
            hatched = (card == 'b50' and size == sizes[-1])
            ax.bar(x, v, width=w * 0.92, color=shade(COLOR[card], SHADE[si]),
                   edgecolor='white' if hatched else 'none',
                   hatch='///' if hatched else None, zorder=3)
            ax.text(x, v + 1.0, '%d' % round(v), ha='center', va='bottom',
                    fontsize=8.4, color=INK)

    ax.set_xticks(range(len(CARDS)))
    ax.set_xticklabels([CARD_LABEL[c] for c in CARDS], color=INK, fontsize=9)
    ax.set_xlim(-0.5, len(CARDS) - 0.5)
    ax.set_ylim(0, max(q.values()) * 1.19)
    axes_style(ax, 'tok/s')
    handles = [Patch(facecolor=shade('#475569', s), edgecolor='none', label=l)
               for s, l in zip(SHADE, labels)]
    handles.append(Patch(facecolor='white', edgecolor='#64748B', hatch='///',
                         label='spills to RAM'))
    ax.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.5, 1.02),
              ncol=4, frameon=False, fontsize=8.6, handlelength=1.1,
              handleheight=0.9, columnspacing=1.4, labelcolor=INK)
    fig.tight_layout(pad=0.4)
    p = os.path.join(OUT, 'at-a-glance-vram.svg')
    save_svg(fig, p, 7.0, 3.45)
    plt.close(fig)
    print('  ->', os.path.relpath(p, REPO))

    # ---------------- §4 ----------------
    h3 = L.load()
    RES3 = [('864x480', '480p\n864×480'),
            ('1280x720', '720p\n1280×720'),
            ('1920x1088', '1080p\n1920×1088')]
    mins, basis = {}, {}
    for card in CARDS:
        for res, _ in RES3:
            r = L.pick(card, res, h3)
            assert r, (card, res)
            end, step, kcal, batch, modes = r
            mins[(card, res)] = end / 60.0
            basis[(card, res)] = kcal
        # 口径断言：B50 只可能是冷启动单次，其余三张必须是稳态
        want = 'cold' if card == 'b50' else 'fresh'
        assert basis[(card, RES3[0][0])] == want, (card, basis[(card, RES3[0][0])])

    fig, ax = plt.subplots(figsize=(7.0, 3.45), dpi=200)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    for gi, card in enumerate(CARDS):
        for si, (res, _) in enumerate(RES3):
            v = mins[(card, res)]
            x = gi + (si - 1) * w
            ax.bar(x, v, width=w * 0.92, color=shade(COLOR[card], SHADE[si]),
                   edgecolor='none', zorder=3)
            ax.text(x, v + 0.35, '%.1f' % v, ha='center', va='bottom',
                    fontsize=8.4, color=INK)
    ax.set_xticks(range(len(CARDS)))
    ax.set_xticklabels([CARD_LABEL[c] for c in CARDS], color=INK, fontsize=9)
    ax.set_xlim(-0.5, len(CARDS) - 0.5)
    ax.set_ylim(0, max(mins.values()) * 1.14)
    axes_style(ax, 'minutes')
    handles = [Patch(facecolor=shade('#475569', s), edgecolor='none', label=l.replace('\n', ' '))
               for s, l in zip(SHADE, [l for _, l in RES3])]
    ax.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.5, 1.02),
              ncol=3, frameon=False, fontsize=8.8, handlelength=1.1,
              handleheight=0.9, columnspacing=1.8, labelcolor=INK)
    fig.tight_layout(pad=0.4)
    p = os.path.join(OUT, 'at-a-glance-video.svg')
    save_svg(fig, p, 7.0, 3.45)
    plt.close(fig)
    print('  ->', os.path.relpath(p, REPO))

    print('\n核对（tok/s / 分钟）：')
    for card in CARDS:
        print('  %s  quant %s' % (card, ' '.join(
            '%.2f' % q[(card, s)] if (card, s) in q else '-' for s in sizes)))
    for card in CARDS:
        print('  %s  video %s' % (card, ' '.join('%.2f' % mins[(card, r)] for r, _ in RES3)))


if __name__ == '__main__':
    main()
