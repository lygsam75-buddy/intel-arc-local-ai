#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""commit_ceiling_probe.py —— 零 GPU 风险的「commit 天花板」探针。

为什么不用 GPU 跑
----------------
「3M 装载会不会被拦」这个问题，本质是操作系统的算术：
    进程最多能提交的 commit = commit limit − 已被别的东西占用的量
只要这个值低于 3M 的需求（实测 86.02 GiB），它就一定被拦。

拿 llama-server 去试，风险在「它失败之后会不会重试到把整机顶穿」；
而这个工具只做一件事：**向内核申请 commit，看在哪里停**。不碰显存、不碰模型、不落盘。

怎么做到不伤机器
----------------
1. `VirtualAlloc(MEM_COMMIT)` 只计 commit，**不 touch 页面就不分配物理页、不写页面文件**；
2. 每步之后读 `GlobalMemoryStatusEx`，**剩余可用 commit 低于 `--guard-gib` 就停并释放**；
3. 达到 `--target-gib` 也停（说明「这个量提交得到」，就不再往上试）。

用法
----
    python commit_ceiling_probe.py --target-gib 86 --guard-gib 6

预期（32 GB 物理 + 48 GB 固定页面文件）：limit ≈ 80 GiB，能提交到约 limit−16−6；
**到不了 86 GiB** → 3M 必被拦，不需要拿 GPU 赌。
"""
import argparse
import ctypes
import json
import os
import time

MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]


def mem_status():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return {}
    limit, avail = m.ullTotalPageFile, m.ullAvailPageFile
    used = limit - avail
    return {
        'commit_limit_gib': round(limit / 2 ** 30, 2),
        'committed_gib': round(used / 2 ** 30, 2),
        'avail_commit_gib': round(avail / 2 ** 30, 2),
        'commit_frac': round(used / limit, 3) if limit else None,
        'ram_free_gib': round(m.ullAvailPhys / 2 ** 30, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target-gib', type=float, default=86.0,
                    help='想验证「能不能提交到这么多」（3M 档实测需求 86.02 GiB）')
    ap.add_argument('--guard-gib', type=float, default=6.0,
                    help='剩余可用 commit 低于这个值就停手（留给系统，别把机器逼死）')
    ap.add_argument('--step-gib', type=float, default=1.0)
    ap.add_argument('--out', default='')
    a = ap.parse_args()

    k32 = ctypes.windll.kernel32
    k32.VirtualAlloc.restype = ctypes.c_void_p
    k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]
    k32.VirtualFree.restype = ctypes.c_bool
    k32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]

    start = mem_status()
    step = int(a.step_gib * 2 ** 30)
    guard = int(a.guard_gib * 2 ** 30)
    target = int(a.target_gib * 2 ** 30)

    blocks, total = [], 0
    verdict = 'unknown'
    t0 = time.time()
    try:
        while True:
            st = mem_status()
            if st['avail_commit_gib'] * 2 ** 30 < guard + step:
                verdict = 'guard_stop'          # 已经贴近系统底线，停手
                break
            if total + step > target:
                verdict = 'target_reached'      # 这个量提交得到
                break
            p = k32.VirtualAlloc(None, step, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
            if not p:
                verdict = 'alloc_failed'        # 内核已经不给（commit limit 撞到）
                break
            blocks.append(p)
            total += step
    finally:
        for p in blocks:
            k32.VirtualFree(p, 0, MEM_RELEASE)

    end = mem_status()
    rec = {
        'schema': 'arc-xpu-capacity/1',
        'tag': 'commit-ceiling-probe',
        'date': time.strftime('%Y-%m-%d'),
        'source': 'commit_ceiling_probe.py',
        'target_gib': a.target_gib, 'guard_gib': a.guard_gib, 'step_gib': a.step_gib,
        'allocated_gib': round(total / 2 ** 30, 2),
        'verdict': verdict,
        'elapsed_s': round(time.time() - t0, 1),
        'mem_before': start,
        'mem_at_stop': mem_status(),
        'mem_after_release': end,
        'note': '只计 commit（MEM_COMMIT 但不 touch 页面），不碰显存、不写页面文件；'
                '剩余可用 commit 低于 guard 即停手并释放全部块。',
    }
    txt = json.dumps(rec, ensure_ascii=False, indent=2)
    if a.out:
        open(a.out, 'wb').write((txt.replace('\n', '\r\n')).rstrip('\r\n').encode('utf-8'))
    print(txt)
    print('\n[判定] %s：本次最多提交 %.2f GiB；目标 %.2f GiB → %s' % (
        verdict, rec['allocated_gib'], a.target_gib,
        '够不到，必被拦' if verdict in ('guard_stop', 'alloc_failed') else '能提交到（说明拦不住）'))


if __name__ == '__main__':
    main()
