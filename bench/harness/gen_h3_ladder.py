#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 bench/data 生成「四张卡 × 分辨率」的 H3 阶梯表（markdown）。

为什么要脚本：2026-10-21 有一次照着报告 header 手抄 Krea-2 分辨率，
把 1280×720 抄成 1024×1024，连累 5 个文件 + 一条推理作废。
**表格里的数字只能来自 json，不能来自记忆。**

口径规则（写进表头注里，不靠读者猜）：
  * 时长只取 `duration_sec == 5.0`（10/15 s 那批是时长维度，不进阶梯）；
  * 端到端取 **fresh 单轮**（稳态）；B50 的 fresh 必 DEVICE_LOST → 只有 cold，
    单独标注，不与 fresh 并排比较；
  * 单步取 **采样段**（`sampling_sec_per_step`），不是端到端 ÷ 步数；
  * 同一 (卡, 分辨率) 有多个批次时，按 prefer 列表挑主批次，其余记进 `alt`。
"""
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RES = ['864x480', '1024x576', '1152x648', '1280x720', '1536x864', '1920x1088']

# 主批次：同一 (卡, 分辨率) 有多份时用它，其余作为旁证。
# 2026-10-27 起 B60 缺的三档有真机实测（b60-24g-h3-three-tiers-5s）：
# **真机优先**，b65r24（B65 + reserve 11.83 模拟 24 GB 预算）只作旁证。
PREFER = {
    ('b70', '864x480'): 'b70tdr',
    ('b70', '1024x576'): 'b70scan',
    ('b70', '1280x720'): 'b70scan',
    ('b70', '1536x864'): 'b70scan',
    ('b70', '1920x1088'): 'b70scan',
    ('b65', '*'): 'b65h3',
    ('b60', '*'): 'b60',
    ('b50', '*'): 'b50scan',
}
CARD_NAME = {'b50': 'B50 16G', 'b60': 'B60 24G', 'b65': 'B65 32G', 'b70': 'B70 32G'}
VRAM = {'b50': '15.51', 'b60': '23.33', 'b65': '31.16', 'b70': '31.16'}

# 24 GB 显存档补测（`--reserve-vram 11.83` → 可分配 19,798 MB，正好等于
# B60 的 23,894 − reserve 4）。tag 里带 `b65`，但显存档位按 B60 校准。
# ⚠️ 2026-10-27 起这三档有真 B60 实测（2026-10-27_b60-h3-three-tiers.json，
# tag b60-24g-h3-three-tiers-5s），**真机优先**；本模拟档只作旁证，
# 不再被 PREFER 选中。表格里模拟档尾随 `†` 仅当真机缺席时出现。
MARK_24G = 'b65r24'
CLASS_OVERRIDE = {'1024x576', '1152x648', '1536x864'}


def load():
    """→ {(card, res): {batch: {mode: sample}}}"""
    out = {}
    for f in sorted(glob.glob(os.path.join(REPO, 'bench/data/*h3*.json'))):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        # 24 GB 显存档补测 → 归到 b60 列（只对缺数的那三档生效）
        blob = (d.get('tag') or '') + os.path.basename(f)
        w = d.get('workload', {})
        if isinstance(w, str) and isinstance(d.get('tiers'), list):
            # 报告式 schema（tiers[]），如 2026-10-27_b60-h3-three-tiers.json
            card = next((c for c in CARD_NAME if c in blob.lower()), None)
            if not card:
                continue
            tag = (d.get('tag') or '').lower()
            batch = next((t for t in (tag.split('-')[-1], tag) if t), '')
            for key in PREFER_HITS(blob):
                batch = key
                break
            for t in d['tiers']:
                res = t.get('resolution') or ''
                if res not in RES:
                    continue
                slot = out.setdefault((card, res), {}).setdefault(batch, {})
                for kcal in ('cold', 'fresh', 'cached'):
                    kv = t.get(kcal) or {}
                    if kcal not in slot and kv.get('server_s'):
                        slot[kcal] = {'ok': True,
                                      'server_sec': kv.get('server_s'),
                                      'sampling_sec_per_step': kv.get('mean_sit_s')}
            continue
        if not isinstance(w, dict):
            continue
        res, dur = w.get('resolution'), w.get('duration_sec')
        if res not in RES or dur != 5.0:
            continue
        card = next((c for c in CARD_NAME if c in blob.lower()), None)
        if not card:
            continue
        # 24 GB 显存档补测 → 归到 b60 列（只对缺数的那三档生效）
        if MARK_24G in blob and res in CLASS_OVERRIDE:
            card = 'b60'
        # 批次名 = tag 尾段（b65h3 / b70scan / b60 …）
        tag = (d.get('tag') or '').lower()
        batch = next((t for t in (tag.split('-')[-1], tag) if t), '')
        for key in PREFER_HITS(blob):
            batch = key
            break
        slot = out.setdefault((card, res), {}).setdefault(batch, {})
        for s in d.get('samples', []):
            m = s.get('mode')
            if m and m not in slot:
                slot[m] = s
    return out


def PREFER_HITS(blob):
    """把 blobs 里出现的已知批次名按「长优先」吐出来。"""
    known = set(PREFER.values()) | {'b70pw', 'b70tdr', 'b70scan', 'b65h3', 'b60',
                                    'b50scan', 'b70fixed', MARK_24G}
    return sorted([k for k in known if k != '*' and k in blob], key=len, reverse=True)


def pick(card, res, data, prefer_batch=None):
    """→ (端到端, 单步, 口径, 批次名) 或 None。"""
    cand = data.get((card, res))
    if not cand:
        return None
    want = prefer_batch or PREFER.get((card, res)) or PREFER.get((card, '*'))
    order = [want] if want in cand else []
    order += [b for b in cand if b not in order]
    for b in order:
        modes = cand[b]
        for kcal in ('fresh', 'cold'):
            s = modes.get(kcal)
            if s and s.get('ok'):
                return (s.get('server_sec'), s.get('sampling_sec_per_step'),
                        kcal, b, modes)
    return None


def main():
    data = load()
    lines = []
    hdr = '| 分辨率 | 像素 | ' + ' | '.join(CARD_NAME[c] for c in ('b70', 'b65', 'b60', 'b50')) + ' |'
    sep = '|---|---:|' + '---:|' * 4
    lines += [hdr, sep]
    for res in RES:
        w, h = res.split('x')
        px = int(w) * int(h)
        cells = []
        for card in ('b70', 'b65', 'b60', 'b50'):
            r = pick(card, res, data)
            if not r:
                cells.append('未测')
                continue
            end, step, basis, batch, modes = r
            tag = '' if basis == 'fresh' else ' *(cold)*'
            if batch == MARK_24G:
                tag += ' †'
            e = format(round(end, 2), ',.2f')      # 四位数加千分位，与正文其余表一致
            if step:
                cells.append('**%s s**%s<br>%.2f s/步' % (e, tag, step))
            else:
                cells.append('**%s s**%s' % (e, tag))
        lines.append('| %s | %s | %s |' % (res.replace('x', '×'), format(px, ','), ' | '.join(cells)))
    print('\n'.join(lines))
    print()
    # 采样占比
    print('采样段占比（单步 × 步数 ÷ 端到端）：')
    print()
    print('| 卡 | ' + ' | '.join(r.replace('x', '×') for r in RES) + ' |')
    print('|---|' + '---:|' * len(RES))
    for card in ('b70', 'b65', 'b60', 'b50'):
        vals = []
        for res in RES:
            r = pick(card, res, data)
            if not r or not r[1] or not r[0]:
                vals.append('未测')
                continue
            share = r[1] * 6 / r[0] * 100
            vals.append('%.1f%%%s' % (share, ' †' if r[3] == MARK_24G else ''))
        print('| %s · %s GiB | %s |' % (CARD_NAME[card], VRAM[card], ' | '.join(vals)))


if __name__ == '__main__':
    main()
