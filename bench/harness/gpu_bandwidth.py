#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测显存带宽占用率（Level Zero Sysman 计数器差分）。

这个字段的两个坑（2026-10-26 全部查清，都踩过）
------------------------------------------------
`zesMemoryGetBandwidth` 返回的结构里有「读写计数器 + 带宽上限 + 时间戳」。
第一版脚本把带宽上限**当成每样本的分母**，结果报出「占用 331.8%」。

🔴 坑一：**单位换算错，读数偏大 4.8576%**
   实测 B60 报 478,150,656,000 B/s，B70 报 637.5 GB/s。
   而 456 × 2^20/10^6 = 478,150,656,000、608 × 2^20/10^6 = 637.534e9 —— **一分不差**。
   即驱动把「456 GB/s」当「456,000 MB/s」又按 MiB 乘了 2^20。
   → 正确值 = 读数 ÷ (2^20/10^6)。两块卡反算回来正好是规格 456 / 608。

🔴 坑二：**同一个字段在某些负载下会塌掉**
   B70 跑 Vulkan 解码时，50 个样本全报 79.7 GB/s；79.7 ÷ 1.048576 = 76.0 = **608/8**。
   而同期实测流量 280 GB/s，是它的 3.5 倍 —— **上限比实测还低，物理上不可能**。
   H3 出视频时同一字段报满值。结论：**这个字段不能当分母**，至少不能在解码期当。

本脚本的做法
------------
1. 分母用**规格值**（`--spec-bw`；不给就从第一个样本的修正读数取整）。
2. 每样本仍记录修正后的字段读数，最后报 min/max；一旦某样本低于规格 50%，直接
   打警告并计入 `unreliable_samples` —— 让「字段塌了」这件事在输出里看得见，
   而不是变成一行 336%。
3. `--warmup` 先空转等 GPU 进满载，避免把装载阶段当稳态。

字段布局以行为为准，不以头文件为准
----------------------------------
本机驱动只填了前四个 uint64：offset 0 / 8 = 读、写累计字节，offset 16 = 带宽上限，
offset 24 = 微秒时间戳（2 s 增 2,005,616 µs 验证过），offset 32 起全 0。
标准头文件把 offset 16 写作 totalCounter、offset 32 写作 maxBandwidth，与本机不符。
"""
import argparse
import ctypes as C
import json
import os
import struct
import time

os.environ.setdefault('ZES_ENABLE_SYSMAN', '1')

# 驱动单位换算：读数 ÷ UNIT_FIX = bytes/s
UNIT_FIX = 2 ** 20 / 10 ** 6
SPEC_BW = {'B50': 224, 'B60': 456, 'B65': 608, 'B70': 608}


def load():
    lib = C.WinDLL("ze_loader")
    for nm, ats in [
        ('zesInit', [C.c_uint32]),
        ('zesDriverGet', [C.POINTER(C.c_uint32), C.POINTER(C.c_void_p)]),
        ('zesDeviceGet', [C.c_void_p, C.POINTER(C.c_uint32), C.POINTER(C.c_void_p)]),
        ('zesDeviceEnumMemoryModules', [C.c_void_p, C.POINTER(C.c_uint32), C.POINTER(C.c_void_p)]),
        ('zesMemoryGetBandwidth', [C.c_void_p, C.c_void_p]),
    ]:
        f = getattr(lib, nm)
        f.argtypes = ats
        f.restype = C.c_uint32
    return lib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', '--samples', type=int, default=60)
    ap.add_argument('-i', '--interval', type=float, default=1.0)
    ap.add_argument('--warmup', type=float, default=20.0, help='开始计数前先等 GPU 进满载')
    ap.add_argument('--spec-bw', type=float, default=0.0,
                    help='规格带宽 GB/s（224/456/608）；不给则从首个样本修正读数取整')
    ap.add_argument('--json', default=None)
    ap.add_argument('--dev', type=int, default=0)
    ap.add_argument('--label', default='')
    args = ap.parse_args()

    lib = load()
    lib.zesInit(0)
    n = C.c_uint32(0)
    lib.zesDriverGet(C.byref(n), None)
    drv = (C.c_void_p * n.value)()
    lib.zesDriverGet(C.byref(n), drv)
    nd = C.c_uint32(0)
    lib.zesDeviceGet(C.c_void_p(drv[0]), C.byref(nd), None)
    devs = (C.c_void_p * nd.value)()
    lib.zesDeviceGet(C.c_void_p(drv[0]), C.byref(nd), devs)
    print(f'Level Zero 枚举到 {nd.value} 个设备，使用 dev{args.dev}')
    nm = C.c_uint32(0)
    lib.zesDeviceEnumMemoryModules(C.c_void_p(devs[args.dev]), C.byref(nm), None)
    if nm.value == 0:
        raise SystemExit('没有显存模块句柄')
    mh = (C.c_void_p * nm.value)()
    lib.zesDeviceEnumMemoryModules(C.c_void_p(devs[args.dev]), C.byref(nm), mh)

    def snap():
        buf = C.create_string_buffer(160)
        C.memset(buf, 0, 160)
        struct.pack_into('<I', buf, 0, 1)
        if lib.zesMemoryGetBandwidth(C.c_void_p(mh[0]), buf) != 0:
            raise SystemExit('zesMemoryGetBandwidth 失败')
        raw = buf.raw
        # 0 读计数 / 8 写计数 / 16 带宽上限（单位见文件头）/ 24 微秒时间戳
        return (struct.unpack_from('<Q', raw, 0)[0], struct.unpack_from('<Q', raw, 8)[0],
                struct.unpack_from('<Q', raw, 16)[0], struct.unpack_from('<Q', raw, 24)[0])

    if args.warmup > 0:
        print(f'预热 {args.warmup:.0f} s，等 GPU 进满载后再计量')
        time.sleep(args.warmup)

    r0, w0, fld0, t0 = snap()
    fld_gb0 = fld0 / UNIT_FIX / 1e9
    print(f'字段读数 {fld0/1e9:.1f} GB/s -> 修正(÷{UNIT_FIX:.6f}) = {fld_gb0:.1f} GB/s')

    spec = args.spec_bw
    if not spec:
        spec = float(round(fld_gb0))
        near = min(SPEC_BW.items(), key=lambda kv: abs(kv[1] - spec))
        print(f'未给 --spec-bw，取首个样本修正读数取整 = {spec:.0f} GB/s'
              f'（最接近 {near[0]} 的规格 {near[1]}）')
    if spec <= 0:
        raise SystemExit('规格带宽无效，请显式给 --spec-bw')

    rows = []
    flds = [fld_gb0]
    unreliable = 0
    for k in range(args.samples):
        time.sleep(args.interval)
        r, w, fld, t = snap()
        dt = (t - t0) / 1e6
        if dt <= 0:
            continue
        rd = (r - r0) / dt
        wr = (w - w0) / dt
        tot = rd + wr
        fld_gb = fld / UNIT_FIX / 1e9
        flds.append(fld_gb)
        bad = fld_gb < spec * 0.5
        if bad:
            unreliable += 1
        pct = tot / (spec * 1e9) * 100.0
        rows.append({'dt_s': round(dt, 3), 'read_gb_s': round(rd / 1e9, 2),
                     'write_gb_s': round(wr / 1e9, 2), 'total_gb_s': round(tot / 1e9, 2),
                     'util_pct_vs_spec': round(pct, 1), 'field_gb_s': round(fld_gb, 1),
                     'field_unreliable': bad})
        flag = '  ← 字段塌了，高于本样本实测流量' if bad and tot / 1e9 > fld_gb else ''
        print(time.strftime('[%H:%M:%S]') +
              f' 读 {rd/1e9:7.2f} + 写 {wr/1e9:7.2f} = {tot/1e9:7.2f} GB/s'
              f'   占用(对规格 {spec:.0f}) {pct:5.1f}%   字段 {fld_gb:6.1f}{flag}')

    if rows:
        util = sorted(x['util_pct_vs_spec'] for x in rows)
        print(f'\n样本 {len(rows)} · 占用率(对规格 {spec:.0f} GB/s) 均 {sum(util)/len(util):.1f}% / '
              f'中位 {util[len(util)//2]:.1f}% / 峰 {util[-1]:.1f}%')
        nz = [x for x in rows if x['total_gb_s'] > 1.0]
        if nz:
            print(f'      总流量 >1 GB/s 的样本（{len(nz)} 个）：均 '
                  f'{sum(x["total_gb_s"] for x in nz)/len(nz):.1f} GB/s / '
                  f'峰 {max(x["total_gb_s"] for x in nz):.1f} GB/s')
        lo, hi = min(flds), max(flds)
        print(f'      字段(已修正)区间：{lo:.1f} ~ {hi:.1f} GB/s   '
              f'（相对规格 {spec:.0f} 是 {lo/spec*100:.0f}~{hi/spec*100:.0f}%）')
        if unreliable:
            print(f'      🔴 {unreliable}/{len(rows)} 个样本的字段低于规格 50% —— '
                  f'这些样本不能拿字段当分母，占用率一律按规格算')
        if hi > 0 and max(x['total_gb_s'] for x in rows) > hi:
            print(f'      🔴 实测峰值 {max(x["total_gb_s"] for x in rows):.1f} GB/s '
                  f'> 字段最高值 {hi:.1f} GB/s —— 字段不是上限，别当分母')

        if args.json:
            data = json.dumps({'schema': 'arc-xpu-bandwidth/1',
                               'label': args.label,
                               'device_index': args.dev,
                               'spec_bw_gb_s': spec,
                               'field_unit_fix': round(UNIT_FIX, 6),
                               'field_raw_note': '字段读数 ÷ 1.048576 = bytes/s；'
                                                 '本机驱动按 2^20/10^6 放大过（见脚本头注释）',
                               'samples': rows,
                               'field_gb_s_range': [round(lo, 1), round(hi, 1)],
                               'unreliable_samples': unreliable,
                               'util_mean_pct': round(sum(util) / len(util), 1),
                               'util_peak_pct': round(util[-1], 1)},
                              ensure_ascii=False, indent=2)
            open(args.json, 'wb').write((data + '\n').encode('utf-8'))
            print(f'JSON -> {args.json}')


if __name__ == '__main__':
    main()
