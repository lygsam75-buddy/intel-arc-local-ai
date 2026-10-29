# -*- coding: utf-8 -*-
"""power_probe_multi.py — 多张同型号卡时，按「每张卡各自的整卡电源域」同时采样功耗。

为什么不能直接用 `power_sampler.py`
----------------------------------
`power_sampler.py` 只枚举 `zesDeviceGet` 返回的 **第 0 个设备**（一个 `devs[0]`），
单卡机器上没影响；**双卡机器上它永远在采同一张卡**，而且：

- Sysman 的设备顺序 **不等于** SYCL / `ONEAPI_DEVICE_SELECTOR` 的 `level_zero:N` 顺序，
  也不等于 `torch.xpu` 的 `xpu:N`；
- 于是「H3 跑在卡 0，采到的却是卡 1 的空载 42 W」这种数会被当成「H3 只吃 42 W」写进结论。

本脚本做两件事：
1. **打印映射**：Sysman 设备序号 → PCI 总线号 → 整卡电源域（`defaultLimit` 最大的那个）；
2. **同时采样所有设备的整卡域**，CSV 每行带 `dev` 与 `bus`，两张卡的功耗一眼分开。

判断「哪张卡在跑」仍以 `ONEAPI_DEVICE_SELECTOR=level_zero:N` 下的
`torch.xpu.mem_get_info` 为准（设备级、跨进程可见），**本脚本只负责功耗归属**。

用法：
    <python> power_probe_multi.py --out p.csv --interval 1.0 --duration 60
    <python> power_probe_multi.py --out p.csv          # 一直采，直到出现 p.stop
"""
import argparse
import ctypes as C
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gpu_sysman import _load, probe_struct, zes_pci_properties_t  # noqa: E402
from power_sampler import ENERGY, PW_PROPS, ZE_RES_SUCCESS  # noqa: E402

os.environ.setdefault('ZES_ENABLE_SYSMAN', '1')


def pick_card_domain(ze, dev):
    """→ [(domain_index, domain_handle, default_limit_mw), ...]（只取能读能耗的域）

    整卡域的特征是 `defaultLimit` 最大（B65 = 200000 mW）。子域给 -1，直接排除。
    """
    pn = C.c_uint32(0)
    if ze.zesDeviceEnumPowerDomains(C.c_void_p(dev), C.byref(pn), None) != ZE_RES_SUCCESS \
            or pn.value == 0:
        return []
    pw = (C.c_void_p * pn.value)()
    if ze.zesDeviceEnumPowerDomains(C.c_void_p(dev), C.byref(pn), pw) != ZE_RES_SUCCESS:
        return []
    out = []
    for k in range(pn.value):
        p = PW_PROPS()
        C.memset(C.byref(p), 0, C.sizeof(p))
        if ze.zesPowerGetProperties(C.c_void_p(pw[k]), C.byref(p)) != ZE_RES_SUCCESS:
            continue
        e = ENERGY()
        if ze.zesPowerGetEnergyCounter(C.c_void_p(pw[k]), C.byref(e)) != ZE_RES_SUCCESS:
            continue
        out.append((k, pw[k], int(p.defaultLimit)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='CSV 前缀（.csv 可带可不带）')
    ap.add_argument('--interval', type=float, default=1.0)
    ap.add_argument('--duration', type=float, default=0.0, help='0 = 一直采到 stop 文件')
    a = ap.parse_args()

    base = os.path.splitext(a.out)[0]
    if base.endswith('.csv'):
        base = base[:-4]
    csv_path, meta_path, stop_path = base + '.csv', base + '.meta.json', base + '.stop'
    if os.path.exists(stop_path):
        os.remove(stop_path)

    ze = _load()
    if ze is None:
        print('[probe] ❌ ze_loader.dll 不可用', flush=True)
        return 2
    if ze.zeInit(0) != ZE_RES_SUCCESS or ze.zesInit(0) != ZE_RES_SUCCESS:
        print('[probe] ❌ zeInit/zesInit 失败', flush=True)
        return 2

    n = C.c_uint32(0)
    if ze.zesDriverGet(C.byref(n), None) != ZE_RES_SUCCESS or n.value == 0:
        print('[probe] ❌ 没有 L0 driver', flush=True)
        return 2
    drv = (C.c_void_p * n.value)()
    ze.zesDriverGet(C.byref(n), drv)

    devs = []
    for di in range(n.value):
        dn = C.c_uint32(0)
        if ze.zesDeviceGet(C.c_void_p(drv[di]), C.byref(dn), None) != ZE_RES_SUCCESS:
            continue
        arr = (C.c_void_p * dn.value)()
        ze.zesDeviceGet(C.c_void_p(drv[di]), C.byref(dn), arr)
        for k in range(dn.value):
            bus = None
            st, pc = probe_struct(ze, 'zesDevicePciGetProperties', arr[k],
                                  zes_pci_properties_t)
            if st is not None:
                bus = int(pc.address.bus)
            doms = pick_card_domain(ze, arr[k])
            card = max(doms, key=lambda t: t[2]) if doms else None
            devs.append({'dev': k, 'bus': bus,
                         'card_dom': card[0] if card else None,
                         'handle': card[1] if card else None,
                         'limit_mw': card[2] if card else None,
                         'domains': [d[0] for d in doms]})

    print('[probe] Sysman 设备 → PCI 总线 → 整卡电源域', flush=True)
    for d in devs:
        print('        dev %d → 总线 %-3s → 域 %-2s（defaultLimit %s mW）'
              % (d['dev'], d['bus'], d['card_dom'], d['limit_mw']), flush=True)
    if sum(1 for d in devs if d['handle']) < 2:
        print('[probe] ⚠ 能采到整卡域的设备不足 2 个，双卡功耗无法叠加', flush=True)

    meta = {'interval_sec': a.interval, 'started': time.time(),
            'interpreter': sys.executable,
            'devices': [{k: v for k, v in d.items() if k != 'handle'} for d in devs],
            'note': 'dev 是 Sysman 序号，不是 xpu:N；认卡看 bus'}
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    e = ENERGY()
    prev = {}
    for d in devs:
        if d['handle'] is None:
            continue
        if ze.zesPowerGetEnergyCounter(C.c_void_p(d['handle']), C.byref(e)) == ZE_RES_SUCCESS:
            prev[d['dev']] = (e.energy, e.timestamp)

    fh = open(csv_path, 'w', encoding='utf-8', newline='')
    fh.write('t,iso,dev,bus,w,e_uj,dt_sec\n')
    fh.flush()
    nsamp = 0
    t0 = time.time()
    try:
        while True:
            time.sleep(a.interval)
            now = time.time()
            iso = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))
            for d in devs:
                if d['handle'] is None or d['dev'] not in prev:
                    continue
                if ze.zesPowerGetEnergyCounter(C.c_void_p(d['handle']), C.byref(e)) \
                        != ZE_RES_SUCCESS:
                    continue
                p = prev[d['dev']]
                dE, dt = e.energy - p[0], (e.timestamp - p[1]) / 1e6
                prev[d['dev']] = (e.energy, e.timestamp)
                if dt <= 0 or dE < 0:      # 计数器回绕 / 时钟异常 → 这一拍作废
                    continue
                fh.write('%.3f,%s,%d,%s,%.1f,%d,%.3f\n'
                         % (now, iso, d['dev'], d['bus'], dE / 1e6 / dt, e.energy, dt))
                nsamp += 1
            fh.flush()
            if os.path.exists(stop_path):
                break
            if a.duration and time.time() - t0 >= a.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        fh.close()

    print('[probe] 收工：%d 条样本 / %.1f s' % (nsamp, time.time() - t0), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
