"""power_sampler.py — Intel Arc 显卡功耗采样器（Level Zero Sysman，无需安装任何东西）

原理
----
`zesPowerGetEnergyCounter` 给出**能耗计数器**（微焦 uJ）+ 硬件时间戳（微秒）。
两次采样求差即得该区间的**平均功率**，比厂商提供的瞬时功率读数稳得多，
而且不会因为读数抖动而虚高。

为什么要独立进程
----------------
采样必须能陪跑任何一个采集器（`bench_f_h3.py` / `sweep.py`），
而这些采集器本身已经在占端口、占显存。做成独立进程 + 只写 CSV 的好处：
**采样器怎么死（被 terminate、被沙箱回收）都不影响已经落盘的数据**，
采集器事后按时间窗口自己算统计，不依赖采样器配合。

用法
----
    # 陪跑：另开一个终端 / 后台
    <python> power_sampler.py --out p.csv --interval 1.0

    # 跑到 600 秒自动收工
    <python> power_sampler.py --out p.csv --duration 600

    # 立刻收工（采集器就是这么干的）
    touch p.stop

产出
----
    p.csv            t,iso,dom,w,e_uj,dt    每行 flush，被杀也不丢
    p.meta.json      设备/电源域清单（含 defaultLimit，用来认「整卡域」）
    p.summary.json   正常收工时写；被硬杀可能没有 → 以 CSV 为准
"""
import argparse
import ctypes as C
import json
import os
import sys
import time

os.environ.setdefault('ZES_ENABLE_SYSMAN', '1')

ZE_RES_SUCCESS = 0
STR_SIZE = 256


class ENERGY(C.Structure):
    _fields_ = [('energy', C.c_uint64), ('timestamp', C.c_uint64)]


class PW_PROPS(C.Structure):
    """zes_power_properties_t（ze_bool_t = uint8_t）。
    defaultLimit 是这一域的功率上限（mW）：整卡域会等于显卡 TBP（B70 = 290000）。
    """
    _fields_ = [
        ('stype', C.c_uint32),
        ('pNext', C.c_void_p),
        ('onSubdevice', C.c_uint8),
        ('subdeviceId', C.c_uint32),
        ('canControl', C.c_uint8),
        ('isEnergyThresholdSupported', C.c_uint8),
        ('defaultLimit', C.c_int32),
        ('minLimit', C.c_int32),
        ('maxLimit', C.c_int32),
    ]


def _load():
    for n in ('ze_loader.dll', r'C:\Windows\System32\ze_loader.dll'):
        try:
            return C.CDLL(n)
        except OSError:
            continue
    return None


def enumerate_domains():
    """→ (ze, [domain_handle, ...], {"device":…, "domains":[…], "card": idx})

    失败返回 (None, [], {})，调用方据此降级（不采集功耗，但跑测照跑）。
    """
    ze = _load()
    if ze is None:
        return None, [], {}
    for s in ('zeInit', 'zesInit', 'zesDriverGet', 'zesDeviceGet',
              'zesDeviceEnumPowerDomains', 'zesPowerGetEnergyCounter',
              'zesPowerGetProperties'):
        if not hasattr(ze, s):
            return None, [], {}
    ze.zeInit.argtypes = [C.c_uint32]
    if ze.zeInit(0) != ZE_RES_SUCCESS or ze.zesInit(0) != ZE_RES_SUCCESS:
        return None, [], {}

    n = C.c_uint32(0)
    if ze.zesDriverGet(C.byref(n), None) != ZE_RES_SUCCESS or n.value == 0:
        return None, [], {}
    drv = (C.c_void_p * n.value)()
    ze.zesDriverGet(C.byref(n), drv)

    dn = C.c_uint32(0)
    if ze.zesDeviceGet(C.c_void_p(drv[0]), C.byref(dn), None) != ZE_RES_SUCCESS \
            or dn.value == 0:
        return None, [], {}
    devs = (C.c_void_p * dn.value)()
    ze.zesDeviceGet(C.c_void_p(drv[0]), C.byref(dn), devs)

    pn = C.c_uint32(0)
    if ze.zesDeviceEnumPowerDomains(C.c_void_p(devs[0]), C.byref(pn), None) \
            != ZE_RES_SUCCESS or pn.value == 0:
        return None, [], {}
    pw = (C.c_void_p * pn.value)()
    ze.zesDeviceEnumPowerDomains(C.c_void_p(devs[0]), C.byref(pn), pw)

    meta, handles, card, best = [], [], None, -2 ** 31
    for k in range(pn.value):
        p = PW_PROPS()
        C.memset(C.byref(p), 0, C.sizeof(p))
        rc = ze.zesPowerGetProperties(C.c_void_p(pw[k]), C.byref(p))
        d = {'i': k,
             'default_limit_mw': int(p.defaultLimit) if rc == ZE_RES_SUCCESS else None,
             'min_limit_mw': int(p.minLimit) if rc == ZE_RES_SUCCESS else None,
             'max_limit_mw': int(p.maxLimit) if rc == ZE_RES_SUCCESS else None,
             'can_control': int(p.canControl) if rc == ZE_RES_SUCCESS else None}
        # 采样前先确认这个域的能耗计数器真的能读（有的域固定返回 0，属于不支持）
        e = ENERGY()
        d['energy_ok'] = (ze.zesPowerGetEnergyCounter(C.c_void_p(pw[k]),
                                                      C.byref(e)) == ZE_RES_SUCCESS)
        meta.append(d)
        if d['energy_ok']:
            handles.append(pw[k])
        else:
            handles.append(None)
        if d['default_limit_mw'] is not None and d['default_limit_mw'] > best:
            best, card = d['default_limit_mw'], k

    return ze, handles, {'device': {'index': 0, 'num_power_domains': pn.value},
                         'domains': meta, 'card': card}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='输出 csv 前缀（不带扩展名也行）')
    ap.add_argument('--interval', type=float, default=1.0)
    ap.add_argument('--duration', type=float, default=0.0, help='0 = 一直跑到 stop 文件')
    a = ap.parse_args()

    base = os.path.splitext(a.out)[0]
    if base.endswith('.csv'):
        base = base[:-4]
    csv_path = base + '.csv'
    meta_path = base + '.meta.json'
    stop_path = base + '.stop'
    if os.path.exists(stop_path):
        os.remove(stop_path)

    ze, handles, meta = enumerate_domains()
    if ze is None or not any(h for h in handles):
        print('[power] ❌ Level Zero Sysman 不可用，不采集功耗', flush=True)
        return 2

    meta['started'] = time.time()
    meta['interval_sec'] = a.interval
    meta['interpreter'] = sys.executable
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print('[power] 设备 %d 个电源域，整卡域 = %s（defaultLimit=%s mW）'
          % (len(handles), meta['card'],
             (meta['domains'][meta['card']]['default_limit_mw']
              if meta['card'] is not None else '?')), flush=True)

    e = ENERGY()
    prev = {}
    for k, h in enumerate(handles):
        if h is None:
            continue
        if ze.zesPowerGetEnergyCounter(C.c_void_p(h), C.byref(e)) == ZE_RES_SUCCESS:
            prev[k] = (e.energy, e.timestamp)

    t_start = time.time()
    fh = open(csv_path, 'w', encoding='utf-8', newline='')
    fh.write('t,iso,dom,w,e_uj,dt_sec\n')
    fh.flush()
    nsamp = 0
    try:
        while True:
            time.sleep(a.interval)
            now = time.time()
            iso = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))
            for k, h in enumerate(handles):
                if h is None:
                    continue
                if ze.zesPowerGetEnergyCounter(C.c_void_p(h), C.byref(e)) \
                        != ZE_RES_SUCCESS:
                    continue
                p = prev.get(k)
                if p is None:
                    prev[k] = (e.energy, e.timestamp)
                    continue
                dE = e.energy - p[0]
                dt = (e.timestamp - p[1]) / 1e6
                prev[k] = (e.energy, e.timestamp)
                if dt <= 0 or dE < 0:      # 计数器回绕 / 时钟异常 → 这一拍作废
                    continue
                fh.write('%.3f,%s,%d,%.1f,%d,%.3f\n'
                         % (now, iso, k, dE / 1e6 / dt, e.energy, dt))
                nsamp += 1
            fh.flush()                      # 每轮 flush：被硬杀也不丢已采数据
            if os.path.exists(stop_path):
                break
            if a.duration and time.time() - t_start >= a.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        fh.close()
        try:
            if os.path.exists(stop_path):
                os.remove(stop_path)
        except OSError:
            pass

    print('[power] 收工：%d 条样本 / %.1f s'
          % (nsamp, time.time() - t_start), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
