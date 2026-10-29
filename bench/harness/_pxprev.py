#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""画 B65 出视频的「像素 x 帧数 -> 端到端耗时」图（矢量 SVG，落 docs/assets/）。

为什么要改这张图（2026-10-25 18:00）：原来那张是「通过 / 失败」散点，用来替一句话
作证 ——「一个标量阈值就够」。**那句话是错的**：所谓「失败」全是被跑测器
`BENCH_STALL_SEC`（420 s 日志静默）掐掉的，卡当时还在 188 W 满载算。原图里那些
红叉不是墙，是跑测器的影子，继续摆着就是误导。

新图只讲一件站得住的事：**没有硬天花板，只有时间成本。**
  * x = px_frame_m（width x height x frames / 1e6）
  * y = 端到端墙钟分钟（server_s / 60）
  * 三个分辨率各一条线，**连起来是一条平滑上升的线，没有突变点** —— 这就是
    「分辨率不进判据、帧数只决定你等多久」的图形证据；
  * 灰竖带 = 已作废的「381~394 M 天花板」，图上明写 invalid；
  * 4 个没有有效耗时的档（当年被掐的那几个）放在 y=0 下方的独立条带里，
    空心灰点，标 retest pending —— 不编数字。

本文件只读 json、只写一张 svg，不改任何 md。

图内一律不放中文（与 `gen_at_a_glance_chart.py` 同规矩）：ComfyUI 那套
python_embeded 的 matplotlib 只有 DejaVu Sans，出中文会变豆腐块。所以轴标题、
图例、标注全用英文 + 数字，中文解释交给 md 里的图注。
"""
import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(REPO, 'bench', 'data',
                   '2026-10-25_b65-32g-h3-px-frame-ceiling.json')
OUT = r'D:/WorkBuddy/2026-10-15-09-22-59/_pxframe_preview.png'

INK = '#1F2937'
MUTED = '#6B7280'
GRID = '#EEF0F3'
BAND = '#F3F4F6'
PEND = '#9CA3AF'

# 分辨率 -> 图例名 / 颜色（像素多的用暖色，眼睛容易顺着往上走）
SERIES = [('1280x720', '720p', '#0D9488'),
          ('1920x1088', '1080p', '#2563EB'),
          ('2560x1440', '1440p', '#EA580C')]

# 已作废的「天花板」区间（旧结论，留个墓碑在图上，免得有人翻旧图）
OLD_LO, OLD_HI = 380.6, 394.4

PEND_ROW = -4.2          # 待复核那条横带的 y 位置（分钟，负值 = 图下方的隔离条带）


def dur(s):
    """'5 秒' -> '5s'。图内禁中文，DejaVu Sans 没有汉字。"""
    return s.replace('秒', 's').replace(' ', '')


def main():
    d = json.load(open(SRC, encoding='utf-8'))
    ladder = d['ladder']

    ok = [p for p in ladder if p.get('server_s')]
    pend = [p for p in ladder if not p.get('server_s')]
    ymax = max(p['server_s'] for p in ok) / 60.0

    fig, ax = plt.subplots(figsize=(10.0, 5.0))

    # —— 已作废的天花板：灰带 + 斜线墓碑 ——
    ax.axvspan(OLD_LO, OLD_HI, color=BAND, zorder=0, lw=0)
    for x in (OLD_LO, OLD_HI):
        ax.axvline(x, color='#D1D5DB', lw=0.9, ls=(0, (4, 3)), zorder=1)
    ax.text((OLD_LO + OLD_HI) / 2.0, ymax * 0.055,
            'old "ceiling" %.0f-%.0f M\n= harness artifact\n(INVALID)' % (OLD_LO, OLD_HI),
            ha='center', va='bottom', fontsize=7.6, color='#B91C1C',
            linespacing=1.5, rotation=90)

    # —— 三条耗时曲线 ——
    for res, name, color in SERIES:
        pts = sorted([p for p in ok if p['resolution'] == res],
                     key=lambda p: p['px_frame_m'])
        if len(pts) < 2:
            continue
        xs = [p['px_frame_m'] for p in pts]
        ys = [p['server_s'] / 60.0 for p in pts]
        ax.plot(xs, ys, '-', color=color, lw=1.5, zorder=3, alpha=0.85,
                solid_capstyle='round')
        ax.scatter(xs, ys, s=54, c=color, edgecolors='white', linewidths=1.2,
                   zorder=4)

    # —— 没有有效耗时的档：单独条带，空心点，不编数字 ——
    ax.axhline(0, color='#D1D5DB', lw=0.9, zorder=1)
    if pend:
        # 只有一类能进这条带：跑完装载、死在别处的档。2026-10-25 起唯一的一条是
        # 1080p·15 秒（756 M）—— 撞主机提交内存，不是卡。
        p0 = min(pend, key=lambda p: p['px_frame_m'])
        ax.scatter([p['px_frame_m'] for p in pend], [PEND_ROW] * len(pend),
                   s=64, facecolors='none', edgecolors=PEND, linewidths=1.6,
                   marker='X', zorder=4)
        if p0.get('cause') == 'commit_limit_job_cap':
            label = ('no valid time:  %.0f M hit host commit memory\n'
                     '(100 GiB job cap, 0xC0000005; VRAM never reached)'
                     % p0['px_frame_m'])
        else:
            label = 'no valid time - retest pending'
        ax.text(p0['px_frame_m'] - 14, PEND_ROW, label,
                ha='right', va='center', fontsize=7.8, color=PEND, linespacing=1.5)

    # —— 最高实测点单独抬出来 ——
    top = max(ok, key=lambda p: p['px_frame_m'])
    ax.annotate('highest measured\n%d fr / %.0f M / %s\n%.0f min'
                % (top['frames'], top['px_frame_m'],
                   dur(top['duration']), top['server_s'] / 60.0),
                xy=(top['px_frame_m'], top['server_s'] / 60.0),
                xytext=(0, 9), textcoords='offset points',
                ha='right', va='bottom', fontsize=8.0, color=INK, linespacing=1.5,
                arrowprops=dict(arrowstyle='-', color=MUTED, lw=0.8,
                                shrinkA=1, shrinkB=4))

    # —— 左下角那句结论，替读者把三条线读成一条 ——
    ax.text(8, ymax * 0.62,
            'all three resolutions collapse onto one curve:\n'
            'resolution is not a variable, frame count only\n'
            'decides how long you wait',
            ha='left', va='center', fontsize=8.4, color=INK, linespacing=1.7)

    ax.set_xlim(0, 800)
    ax.set_ylim(PEND_ROW - 3.4, ymax * 1.16)
    ax.set_xticks(range(0, 801, 100))
    ax.set_yticks(range(0, int(ymax) + 1, 10))
    ax.tick_params(axis='both', labelsize=8.5, colors=MUTED)
    ax.set_xlabel('pixels x frames   (M px-frame)', fontsize=9.5, color=INK)
    ax.set_ylabel('end-to-end wall time   (min)', fontsize=9.5, color=INK)
    ax.grid(axis='y', color=GRID, lw=0.8, zorder=0)
    ax.grid(axis='x', color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color('#D1D5DB')

    handles = []
    for res, name, c in SERIES:
        pts = sorted([p for p in ok if p['resolution'] == res],
                     key=lambda p: p['px_frame_m'])
        label = '%s   up to %s' % (name, dur(pts[-1]['duration'])) if pts else name
        handles.append(Line2D([], [], marker='o', ls='-', ms=6, lw=1.5, color=c,
                              mfc=c, mec='white', label=label))
    handles.append(Line2D([], [], marker='o', ls='', ms=6, mfc='none',
                          mec=PEND, mew=1.4,
                          label='retest pending (no valid time)'))
    ax.legend(handles=handles, loc='upper left', frameon=False, fontsize=8.5,
              handletextpad=0.6, labelcolor=INK, ncol=1, borderpad=0.2)

    fig.tight_layout()
    # 两处会让每次重跑的字节都不一样：metadata 里的生成时间、matplotlib 随机生成的
    # 元素 id。两个都锁死，图才能进 git 且 diff 干净。
    matplotlib.rcParams['svg.hashsalt'] = 'intel-arc-b-series'
    fig.savefig(OUT, format='svg', facecolor='white', metadata={'Date': None})
    if '--png' in sys.argv:                       # 只为肉眼核对，不进仓库
        fig.savefig(sys.argv[sys.argv.index('--png') + 1], format='png', dpi=130,
                    facecolor='white')
    plt.close(fig)
    print('wrote %s (%d B)  有效耗时 %d 档 / 待复核 %d 档'
          % (OUT, os.path.getsize(OUT), len(ok), len(pend)))


if __name__ == '__main__':
    main()
