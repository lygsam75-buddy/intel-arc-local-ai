# -*- coding: utf-8 -*-
"""gpu_thermal.py —— 直读 Level Zero Sysman 的温度与风扇转速（与 IGS 面板同源）。

为什么不用截图 / 不用 HWiNFO
--------------------------
IGS 面板是 GUI，数字无法复现、无法写进数据件；HWiNFO 这类第三方工具要另装、
读数还要经过自己的换算。这张卡的驱动自己就暴露了 Sysman 接口，读出来的是
**驱动内部值**——和 IGS 风扇曲线页面显示的是同一个来源，但可以一条命令重放。

读的是只读量（温度 / 风扇），**不改任何设置**；调速仍在 IGS → 性能 → 调优里做。

用法：
    python gpu_thermal.py                      # 采 5 次 × 2 秒
    python gpu_thermal.py -n 30 -i 1           # 30 次 × 1 秒
    python gpu_thermal.py --json out.json      # 顺带落一份 JSON（带 bus 与时间戳）
"""
import argparse
import ctypes as C
import json
import os
import sys
import time

os.environ.setdefault('ZES_ENABLE_SYSMAN', '1')
ZE_RESULT_SUCCESS = 0

TEMP_TYPES = {
    0: 'GLOBAL',
    1: 'GPU',
    2: 'MEMORY',
    3: 'GPU_BOARD',
    4: 'GPU_BOARD_NEIGHBORHOOD',
}
FAN_UNITS = {0: ('RPM', 'rpm'), 1: ('PERCENT', '%')}


class zes_pci_address_t(C.Structure):
    _fields_ = [("domain", C.c_uint32), ("bus", C.c_uint32),
                ("device", C.c_uint32), ("function", C.c_uint32)]


class zes_pci_speed_t(C.Structure):
    _fields_ = [("gen", C.c_int32), ("width", C.c_int32),
                ("maxBandwidth", C.c_int64)]


class zes_pci_properties_t(C.Structure):
    _fields_ = [("stype", C.c_uint32), ("pNext", C.c_void_p),
                ("address", zes_pci_address_t), ("maxSpeed", zes_pci_speed_t),
                ("haveBandwidthCounters", C.c_uint8),
                ("havePacketCounters", C.c_uint8),
                ("haveReplayCounters", C.c_uint8)]


class zes_temp_properties_t(C.Structure):
    _fields_ = [("stype", C.c_uint32), ("pNext", C.c_void_p),
                ("type", C.c_uint32), ("onSubdevice", C.c_uint8),
                ("subdeviceId", C.c_uint32), ("maxTemperature", C.c_double)]


def load():
    try:
        lib = C.WinDLL("ze_loader")
    except OSError as e:
        raise SystemExit(f"加载 ze_loader.dll 失败：{e}")
    lib.zeInit.argtypes = [C.c_uint32]
    lib.zeInit.restype = C.c_uint32
    lib.zesInit.argtypes = [C.c_uint32]
    lib.zesInit.restype = C.c_uint32
    lib.zesDriverGet.argtypes = [C.POINTER(C.c_uint32), C.POINTER(C.c_void_p)]
    lib.zesDriverGet.restype = C.c_uint32
    for fn in ("zesDeviceGet", "zesDeviceEnumTemperatureSensors", "zesDeviceEnumFans",
               "zesDeviceEnumFanHandles"):
        if not hasattr(lib, fn):
            continue
        f = getattr(lib, fn)
        f.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.POINTER(C.c_void_p)]
        f.restype = C.c_uint32
    for fn in ("zesTemperatureGetProperties", "zesDevicePciGetProperties"):
        f = getattr(lib, fn)
        f.argtypes = [C.c_void_p, C.c_void_p]
        f.restype = C.c_uint32
    lib.zesTemperatureGetState.argtypes = [C.c_void_p, C.POINTER(C.c_double)]
    lib.zesTemperatureGetState.restype = C.c_uint32
    lib.zesFanGetState.argtypes = [C.c_void_p, C.c_uint32, C.POINTER(C.c_double)]
    lib.zesFanGetState.restype = C.c_uint32
    return lib


def probe_stype(fn, handle, struct_cls):
    """stype 在不同 L0 版本编号不同 —— 暴力试，取第一个 SUCCESS。"""
    for st in range(1, 0x21):
        obj = struct_cls()
        C.memset(C.byref(obj), 0, C.sizeof(obj))
        obj.stype = st
        if fn(C.c_void_p(handle), C.byref(obj)) == ZE_RESULT_SUCCESS:
            return st, obj
    return None, None


def enum_handles(fn, dev):
    n = C.c_uint32(0)
    if fn(C.c_void_p(dev), C.byref(n), None) != ZE_RESULT_SUCCESS or n.value == 0:
        return []
    arr = (C.c_void_p * n.value)()
    if fn(C.c_void_p(dev), C.byref(n), arr) != ZE_RESULT_SUCCESS:
        return []
    return list(arr)


def read_once(lib, dev):
    """→ dict(temps={type: C}, fans={idx: (rpm, pct)}, bus=int, pcie=str)"""
    out = {'temps': {}, 'fans': {}, 'bus': None, 'pcie': None}
    p = zes_pci_properties_t()
    C.memset(C.byref(p), 0, C.sizeof(p))
    if lib.zesDevicePciGetProperties(C.c_void_p(dev), C.byref(p)) == ZE_RESULT_SUCCESS:
        out['bus'] = int(p.address.bus)
        out['pcie'] = f"Gen{p.maxSpeed.gen} x{p.maxSpeed.width}"
    for h in enum_handles(lib.zesDeviceEnumTemperatureSensors, dev):
        _, pr = probe_stype(lib.zesTemperatureGetProperties, h, zes_temp_properties_t)
        name = TEMP_TYPES.get(pr.type, f'TYPE{pr.type}') if pr else 'UNKNOWN'
        val = C.c_double(0.0)
        if lib.zesTemperatureGetState(C.c_void_p(h), C.byref(val)) == ZE_RESULT_SUCCESS:
            out['temps'][name] = round(val.value, 1)
    fanfn = (lib.zesDeviceEnumFanHandles if hasattr(lib, 'zesDeviceEnumFanHandles')
             else lib.zesDeviceEnumFans)
    for i, h in enumerate(enum_handles(fanfn, dev)):
        rpm = C.c_double(-1.0)
        pct = C.c_double(-1.0)
        lib.zesFanGetState(C.c_void_p(h), 0, C.byref(rpm))   # 0 = RPM
        lib.zesFanGetState(C.c_void_p(h), 1, C.byref(pct))   # 1 = PERCENT
        out['fans'][i] = (round(rpm.value), round(pct.value, 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', '--samples', type=int, default=5)
    ap.add_argument('-i', '--interval', type=float, default=2.0)
    ap.add_argument('--json', default=None)
    ap.add_argument('--dev', type=int, default=0, help='Sysman 设备序号（默认 0）')
    args = ap.parse_args()

    lib = load()
    lib.zeInit(0)
    lib.zesInit(0)
    ndrv = C.c_uint32(0)
    if lib.zesDriverGet(C.byref(ndrv), None) != ZE_RESULT_SUCCESS or ndrv.value == 0:
        raise SystemExit('没有 ZES 驱动（确认 ZES_ENABLE_SYSMAN=1）')
    drv = (C.c_void_p * ndrv.value)()
    lib.zesDriverGet(C.byref(ndrv), drv)

    ndev = C.c_uint32(0)
    if lib.zesDeviceGet(C.c_void_p(drv[0]), C.byref(ndev), None) != ZE_RESULT_SUCCESS \
            or ndev.value == 0:
        raise SystemExit('该驱动下没有设备')
    devs = (C.c_void_p * ndev.value)()
    lib.zesDeviceGet(C.c_void_p(drv[0]), C.byref(ndev), devs)
    if args.dev >= ndev.value:
        raise SystemExit(f'只有 {ndev.value} 个设备，要不了 dev={args.dev}')
    dev = devs[args.dev]

    rows = []
    for k in range(args.samples):
        r = read_once(lib, dev)
        r['t'] = time.strftime('%H:%M:%S')
        rows.append(r)
        temps = ' '.join(f'{k2}={v}℃' for k2, v in r['temps'].items()) or '（无传感器）'
        fans = ' '.join(f'fan{i}={rpm}rpm/{pct}%' for i, (rpm, pct) in r['fans'].items()) or '（无风扇句柄）'
        print(f"[{r['t']}] bus={r['bus']} {r['pcie']}  {temps}  {fans}")
        if k < args.samples - 1:
            time.sleep(args.interval)

    if args.json:
        data = json.dumps({'schema': 'arc-xpu-thermal/1', 'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                           'device': args.dev, 'samples': rows},
                          ensure_ascii=False, indent=2)
        open(args.json, 'wb').write(data.encode('utf-8'))
        print(f'→ {args.json}')


if __name__ == '__main__':
    main()
