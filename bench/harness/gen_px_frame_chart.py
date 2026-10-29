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
  * 四个分辨率各一条线（2026-10-26 补上 480p：51.4 M 与 502.6 M 两点，后者是 50 秒档），
    **连起来是一条平滑上升的线，没有突变点** —— 这就是
    「分辨率不进判据、帧数只决定你等多久」的图形证据；
  * 灰竖带 = 已作废的「381~394 M 天花板」，图上明写 invalid；
  * 没有有效耗时的档（2026-10-26 第八轮起是 6 个：578.6 / 582.5 / 614 / 685 / 721 / 756 M）
    放在 y=0 下方的独立条带里，灰叉 —— 不编数字。这六条**全部是 `XPU out of memory`（显存不够）**，
    不是算力、也不是主机，所以图上只写死在哪一步（578~614 M 跑十几分钟后死在注意力、685 M 起第 1 步就死）。

本文件只读 json、只写一张 svg，不改任何 md。

支持 `--lang zh`（默认）/ `--lang en`。中文版出 `b65-h3-px-frame.svg`，
英文版出 `b65-h3-px-frame.en.svg`。中文版用 `svg.fonttype='none'` + 微软雅黑
出 `<text>` 标签（浏览器渲染）；英文版用 path 烘焙。
"""
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(REPO, 'bench', 'data',
                   '2026-10-25_b65-32g-h3-px-frame-ceiling.json')

_LANG = 'zh'
if '--lang' in sys.argv:
    _LANG = sys.argv[sys.argv.index('--lang') + 1]
if _LANG == 'en':
    OUT = os.path.join(REPO, 'docs', 'cards', 'assets', 'b65-h3-px-frame.en.svg')
else:
    OUT = os.path.join(REPO, 'docs', 'cards', 'assets', 'b65-h3-px-frame.svg')

INK = '#1F2937'
MUTED = '#6B7280'
GRID = '#EEF0F3'
BAND = '#F3F4F6'
PEND = '#9CA3AF'

# 分辨率 -> 图例名 / 颜色（像素多的用暖色，眼睛容易顺着往上走）
# 第四项 = 线型。480p 只有 51.4 / 502.6 两个实测点、中间 450 M 一格没测。
# 两个端点各自都落在另三条线的曲线上，但**连线**会把中段抬到曲线上方、
# 看着像「480p 更慢」—— 那是插值假象。所以 480p 只画点、不画线。
SERIES = [('864x480', '480p', '#7C3AED', 'none'),
          ('1280x720', '720p', '#0D9488', '-'),
          ('1920x1088', '1080p', '#2563EB', '-'),
          ('2560x1440', '1440p', '#EA580C', '-')]

# 已作废的「天花板」区间（旧结论，留个墓碑在图上，免得有人翻旧图）
OLD_LO, OLD_HI = 380.6, 394.4

PEND_ROW = -6.2          # 待复核那条横带的 y 位置（分钟，负值 = 图下方的隔离条带）

# —— 双语标签 ——
LABELS = {
    'zh': {
        'old_ceiling': '旧「天花板」%.0f-%.0f M\n= 跑测器假象\n（已作废）',
        'no_valid': '无有效耗时：%.0f-%.0f M（%d 档）\n全是 XPU 显存 OOM，不是算力不足\n%s M 跑 16-18 分钟后死在注意力；%s M 起第 1 步死',
        'highest': '最高实测\n%d 帧 / %.0f M / %s\n%.0f 分钟',
        'collapse': '四个分辨率落在同一条曲线上\n（480p 只有两个实测点——都在线上）；\n分辨率不是变量，帧数只决定\n你等多久',
        'xlabel': '像素 × 帧数   (M px·帧)',
        'ylabel': '端到端耗时   (分钟)',
        'legend_fmt': '%s   最远 %s',
        'legend_480': '480p   最远 %s',
        'legend_480_note': '（2 点，仅散点）',
        'legend_720': '720p   最远 %s',
        'legend_1080': '1080p   最远 %s',
        'legend_1440': '1440p   最远 %s',
        'legend_oom': '无有效耗时（XPU OOM，非算力）',
    },
    'en': {
        'old_ceiling': 'old "ceiling" %.0f-%.0f M\n= harness artifact\n(INVALID)',
        'no_valid': 'no valid time:  %.0f-%.0f M (%d rungs)\nevery one is XPU out of memory (VRAM), none is compute\n%s M run 16-18 min and die in attention; %s M and up die in step 1',
        'highest': 'highest measured\n%d fr / %.0f M / %s\n%.0f min',
        'collapse': 'all four resolutions collapse onto one curve\n(480p shows only its two measured ends \u2014 both land on it);\nresolution is not a variable, frame count only\ndecides how long you wait',
        'xlabel': 'pixels x frames   (M px-frame)',
        'ylabel': 'end-to-end wall time   (min)',
        'legend_fmt': '%s   up to %s',
        'legend_480': '480p   up to %s',
        'legend_480_note': '  (2 pts, markers only)',
        'legend_720': '720p   up to %s',
        'legend_1080': '1080p   up to %s',
        'legend_1440': '1440p   up to %s',
        'legend_oom': 'no valid time (XPU OOM, not compute)',
    },
}
L = LABELS[_LANG]

# 中文版用 <text> 标签 + 微软雅黑；英文版保持 path 烘焙
if _LANG == 'zh':
    matplotlib.rcParams['svg.fonttype'] = 'none'
    matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    matplotlib.rcParams['axes.unicode_minus'] = False


def dur(s):
    if _LANG == 'en':
        return s.replace('秒', 's').replace(' ', '')
    return s  # 中文版保留「秒」


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
            L['old_ceiling'] % (OLD_LO, OLD_HI),
            ha='center', va='bottom', fontsize=7.6, color='#B91C1C',
            linespacing=1.5, rotation=90)

    # —— 三条耗时曲线 ——
    for res, name, color, dash in SERIES:
        pts = sorted([p for p in ok if p['resolution'] == res],
                     key=lambda p: p['px_frame_m'])
        if len(pts) < 2:
            continue
        xs = [p['px_frame_m'] for p in pts]
        ys = [p['server_s'] / 60.0 for p in pts]
        if len(pts) > 2 or dash != 'none':
            ax.plot(xs, ys, color=color, lw=1.5, zorder=3, alpha=0.85,
                    ls=dash, solid_capstyle='round', dash_capstyle='round')
        ax.scatter(xs, ys, s=54, c=color, edgecolors='white', linewidths=1.2,
                   zorder=4)

    # —— 没有有效耗时的档：单独条带，灰叉，不编数字 ——
    # 判据是「有没有真进采样」，用被测卡功耗均值（见数据件 reading.wall_now）。
    ax.axhline(0, color='#D1D5DB', lw=0.9, zorder=1)
    if pend:
        ms = sorted(p['px_frame_m'] for p in pend)
        lo, hi = ms[0], ms[-1]
        # 573 / 578 / 582 / 584 四档在 800 M 的轴上挤成一点，上下错开才数得清
        ys, prev, dy = [], None, 0.0
        for m in ms:
            if prev is not None and m - prev < 14:
                dy = 2.5 if dy <= 0 else -2.5
            else:
                dy = 0.0
            ys.append(PEND_ROW + dy)
            prev = m
        ax.scatter(ms, ys,
                   s=72, facecolors='none', edgecolors=PEND, linewidths=1.7,
                   marker='X', zorder=4)
        sampled = sorted(p['px_frame_m'] for p in pend
                         if p.get('cause') == 'vram_oom_attention')
        never = sorted(p['px_frame_m'] for p in pend
                       if p.get('cause') == 'vram_oom_int8')
        label = (L['no_valid']
                 % (lo, hi, len(pend),
                    ('%.0f-%.0f' % (sampled[0], sampled[-1])) if sampled else 'n/a',
                    ('%.0f' % never[0]) if never else 'n/a'))
        ax.text(8, PEND_ROW - 3.6, label,
                ha='left', va='center', fontsize=7.8, color=MUTED, linespacing=1.6)

    # —— 最高实测点单独抬出来 ——
    top = max(ok, key=lambda p: p['px_frame_m'])
    ax.annotate(L['highest']
                % (top['frames'], top['px_frame_m'],
                   dur(top['duration']), top['server_s'] / 60.0),
                xy=(top['px_frame_m'], top['server_s'] / 60.0),
                xytext=(0, 9), textcoords='offset points',
                ha='right', va='bottom', fontsize=8.0, color=INK, linespacing=1.5,
                arrowprops=dict(arrowstyle='-', color=MUTED, lw=0.8,
                                shrinkA=1, shrinkB=4))

    # —— 左下角那句结论，替读者把三条线读成一条 ——
    ax.text(8, ymax * 0.62,
            L['collapse'],
            ha='left', va='center', fontsize=8.4, color=INK, linespacing=1.7)

    ax.set_xlim(0, 800)
    ax.set_ylim(PEND_ROW - 13.0, ymax * 1.16)   # 底部留白：图注三行不许压到 x 轴刻度
    ax.set_xticks(range(0, 801, 100))
    ax.set_yticks(range(0, int(ymax) + 1, 10))
    ax.tick_params(axis='both', labelsize=8.5, colors=MUTED)
    ax.set_xlabel(L['xlabel'], fontsize=9.5, color=INK)
    ax.set_ylabel(L['ylabel'], fontsize=9.5, color=INK)
    ax.grid(axis='y', color=GRID, lw=0.8, zorder=0)
    ax.grid(axis='x', color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color('#D1D5DB')

    handles = []
    for res, name, c, dash in SERIES:
        pts = sorted([p for p in ok if p['resolution'] == res],
                     key=lambda p: p['px_frame_m'])
        label = L['legend_fmt'] % (name, dur(pts[-1]['duration'])) if pts else name
        if len(pts) == 2:
            if name == '480p':
                label += L['legend_480_note']
        handles.append(Line2D([], [], marker='o', ls=dash, ms=6, lw=1.5, color=c,
                              mfc=c, mec='white', label=label))
    handles.append(Line2D([], [], marker='X', ls='', ms=6.5, mfc='none',
                          mec=PEND, mew=1.5,
                          label=L['legend_oom']))
    ax.legend(handles=handles, loc='upper left', frameon=False, fontsize=8.5,
              handletextpad=0.6, labelcolor=INK, ncol=1, borderpad=0.2)

    fig.tight_layout()
    # 两处会让每次重跑的字节都不一样：metadata 里的生成时间、matplotlib 随机生成的
    # 元素 id。两个都锁死，图才能进 git 且 diff 干净。
    matplotlib.rcParams['svg.hashsalt'] = 'intel-arc-b-series'
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, format='svg', facecolor='white', metadata={'Date': None})
    # docs/**/assets/*.svg 一律纯 LF；Windows 上 matplotlib 默认写 CRLF
    _p = Path(OUT)
    _p.write_bytes(_p.read_bytes().replace(b'\r\n', b'\n'))
    if '--png' in sys.argv:                       # 只为肉眼核对，不进仓库
        fig.savefig(sys.argv[sys.argv.index('--png') + 1], format='png', dpi=130,
                    facecolor='white')
    plt.close(fig)
    print('wrote %s (%d B)  有效耗时 %d 档 / 待复核 %d 档'
          % (OUT, os.path.getsize(OUT), len(ok), len(pend)))


if __name__ == '__main__':
    main()
