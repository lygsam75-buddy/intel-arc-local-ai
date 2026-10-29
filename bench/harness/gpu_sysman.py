# -*- coding: utf-8 -*-
"""用 Level Zero Sysman API 直接读显卡的权威状态：ECC、PCIe 链路、固件、板卡身份。

为什么要这个脚本（而不是看 IGS 界面）：
  - IGS 是 GUI，截图不能进仓库，也无法复现、无法随数据版本化。
  - Level Zero Sysman 是 **Intel 驱动自己暴露的编程接口**（ze_loader.dll），
    读出来的就是驱动内部值，一条命令可重放，能写进 JSON 的 env 段。
  - 覆盖 docs/test-rig.md 里三个靠注册表取不到的待补项：
      · ECC 实际状态（zesDeviceEccAvailable / Configurable / GetEccState）
      · PCIe 链路带宽协商结果（zesDevicePciGetProperties / GetState）
        → 直接给出 **negotiated width**，判定插的是主槽(x8)还是副槽(x4)
      · 固件版本（zesDeviceEnumFirmwares）→ VBIOS 若无别的来源

关于 stype 的探测：Level Zero 每个 struct 都带 `stype`（[in] 结构类型枚举），
但枚举值在不同 L0 版本间变过，本机没装 L0 头文件。所以本脚本对每个 struct 调用
**暴力试 stype=1..0x20**，取第一个返回 SUCCESS 的，并把命中的 stype 打出来。
命中的值一旦固定，就是本机驱动的 ground truth。

用法：
  python gpu_sysman.py            # 全部（ECC + PCIe + 固件 + 板卡身份）
  python gpu_sysman.py --raw      # 额外 hexdump 板卡属性原始字节（排查用）
"""
import ctypes
import sys

ZE_RESULT_SUCCESS = 0
ZES_STRING_PROPERTY_SIZE = 64

# ⚠️ Level Zero 的 `zes_device_ecc_state_t` 在两代规范里编号不同：
#     新（4 值）：0=UNAVAILABLE, 1=AVAILABLE, 2=ENABLED, 3=DISABLED
#     旧（3 值）：0=UNAVAILABLE, 1=ENABLED,   2=DISABLED
#   本机没装 L0 头文件，无法静态判定驱动用哪一代，所以**两个口径都打出来**。
#   最终判据用**物理容量**，不用枚举值——见文件末尾的「判据说明」。
ECC_STATE_NEW = {
    0: "UNAVAILABLE（驱动未实现/不支持）",
    1: "AVAILABLE（支持，但 R/W 未启用）",
    2: "ENABLED（已开启）",
    3: "DISABLED（已关闭）",
}
ECC_STATE_LEGACY = {
    0: "UNAVAILABLE（驱动未实现/不支持）",
    1: "ENABLED（已开启）",
    2: "DISABLED（已关闭）",
}
PCI_LINK = {
    0: "UNKNOWN",
    1: "GOOD",
    2: "QUALITY_ISSUES",
    3: "STABILITY_ISSUES",
}


# ---------------------------------------------------------------- structs
class zes_pci_address_t(ctypes.Structure):
    _fields_ = [("domain", ctypes.c_uint32), ("bus", ctypes.c_uint32),
                ("device", ctypes.c_uint32), ("function", ctypes.c_uint32)]


class zes_pci_speed_t(ctypes.Structure):
    _fields_ = [("gen", ctypes.c_int32), ("width", ctypes.c_int32),
                ("maxBandwidth", ctypes.c_int64)]


class zes_pci_properties_t(ctypes.Structure):
    _fields_ = [("stype", ctypes.c_uint32), ("pNext", ctypes.c_void_p),
                ("address", zes_pci_address_t), ("maxSpeed", zes_pci_speed_t),
                ("haveBandwidthCounters", ctypes.c_uint8),
                ("havePacketCounters", ctypes.c_uint8),
                ("haveReplayCounters", ctypes.c_uint8)]


class zes_pci_state_t(ctypes.Structure):
    _fields_ = [("stype", ctypes.c_uint32), ("pNext", ctypes.c_void_p),
                ("status", ctypes.c_uint32), ("speed", zes_pci_speed_t)]


class zes_device_ecc_properties_t(ctypes.Structure):
    _fields_ = [("stype", ctypes.c_uint32), ("pNext", ctypes.c_void_p),
                ("currentState", ctypes.c_uint32),
                ("pendingState", ctypes.c_uint8),
                ("pendingAction", ctypes.c_uint32)]


class zes_firmware_properties_t(ctypes.Structure):
    _fields_ = [("stype", ctypes.c_uint32), ("pNext", ctypes.c_void_p),
                ("name", ctypes.c_char * ZES_STRING_PROPERTY_SIZE),
                ("version", ctypes.c_char * ZES_STRING_PROPERTY_SIZE)]


class zes_mem_state_t(ctypes.Structure):
    _fields_ = [("stype", ctypes.c_uint32), ("pNext", ctypes.c_void_p),
                ("health", ctypes.c_uint32),
                ("free", ctypes.c_uint64), ("size", ctypes.c_uint64)]


BOARD_PROPS_SIZE = 2048     # 足够容纳 zes_device_properties_t（≈768B），防越界写


def _load():
    try:
        lib = ctypes.WinDLL("ze_loader")
    except OSError as e:
        raise SystemExit(f"加载 ze_loader.dll 失败：{e}")
    lib.zeInit.argtypes = [ctypes.c_uint32]
    lib.zeInit.restype = ctypes.c_uint32
    lib.zesInit.argtypes = [ctypes.c_uint32]
    lib.zesInit.restype = ctypes.c_uint32
    for fn in ("zesDriverGet",):
        f = getattr(lib, fn)
        f.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p)]
        f.restype = ctypes.c_uint32
    for fn in ("zesDeviceGet", "zesDeviceEnumFirmwares", "zesDeviceEnumMemoryModules"):
        f = getattr(lib, fn)
        f.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
                      ctypes.POINTER(ctypes.c_void_p)]
        f.restype = ctypes.c_uint32
    for fn in ("zesDeviceGetProperties", "zesDevicePciGetProperties", "zesDevicePciGetState",
               "zesDeviceGetEccState", "zesFirmwareGetProperties", "zesMemoryGetState",
               "zesDeviceGetState"):
        f = getattr(lib, fn)
        f.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        f.restype = ctypes.c_uint32
    for fn in ("zesDeviceEccAvailable", "zesDeviceEccConfigurable"):
        f = getattr(lib, fn)
        f.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8)]
        f.restype = ctypes.c_uint32
    return lib


def probe_struct(lib, fn_name, handle, struct_cls):
    """暴力试 stype=1..0x20，返回 (命中的 stype, 结构体实例) 或 (None, None)。"""
    fn = getattr(lib, fn_name)
    for st in range(1, 0x21):
        obj = struct_cls()
        ctypes.memset(ctypes.byref(obj), 0, ctypes.sizeof(obj))
        obj.stype = st
        rc = fn(ctypes.c_void_p(handle), ctypes.byref(obj))
        if rc == ZE_RESULT_SUCCESS:
            return st, obj
    return None, None


def ascii_runs(buf, minlen=3):
    """从原始字节里捞出可打印字符串段（偏移, 文本），用于未知布局排查。"""
    out, cur, start = [], [], 0
    for i, b in enumerate(buf):
        if 32 <= b < 127:
            if not cur:
                start = i
            cur.append(chr(b))
        else:
            if len(cur) >= minlen:
                out.append((start, "".join(cur)))
            cur = []
    if len(cur) >= minlen:
        out.append((start, "".join(cur)))
    return out


def cstr_escaped(buf, start):
    """从 start 起按 C 字符串读到 NUL，非打印字节转义成 \\xNN（保留字面值，不美化）。"""
    out = []
    for i in range(start, len(buf)):
        c = buf[i]
        if c == 0:
            break
        out.append(chr(c) if 32 <= c < 127 else f"\\x{c:02x}")
    return "".join(out)


def main():
    raw = "--raw" in sys.argv
    lib = _load()

    rc = lib.zeInit(0)
    if rc != ZE_RESULT_SUCCESS:
        print(f"zeInit rc={rc}（核心 L0 初始化失败，可能本机驱动未提供 L0）")
    rc = lib.zesInit(0)
    if rc != ZE_RESULT_SUCCESS:
        raise SystemExit(f"zesInit rc={rc}（本机驱动未提供 Sysman）")

    n = ctypes.c_uint32(0)
    p = ctypes.c_void_p()
    lib.zesDriverGet(ctypes.byref(n), None)
    drivers = (ctypes.c_void_p * n.value)()
    lib.zesDriverGet(ctypes.byref(n), drivers)
    print(f"=== Level Zero Sysman ===")
    print(f"driver 数: {n.value}")
    if n.value == 0:
        raise SystemExit("没有 L0 driver")

    total = 0
    for di in range(n.value):
        dcnt = ctypes.c_uint32(0)
        lib.zesDeviceGet(ctypes.c_void_p(drivers[di]), ctypes.byref(dcnt), None)
        devs = (ctypes.c_void_p * dcnt.value)()
        lib.zesDeviceGet(ctypes.c_void_p(drivers[di]), ctypes.byref(dcnt), devs)
        for k in range(dcnt.value):
            total += 1
            h = devs[k]
            print(f"\n--- [driver {di}] 设备 {k} ---")

            # ---- 板卡身份（原始缓冲 + stype 探测）----
            # ⚠️ 与固件结构体一样，本机驱动的 `zes_device_properties_t` **布局也与规范不符**
            #    （按偏移读会读出 `brandName : 2]` 这种垃圾）。所以同样走「可打印字符串段」，
            #    把段偏移一起打出来，让人能核对，而不是给一个看起来像型号的错值。
            st, got = None, None
            for cand in range(1, 0x21):
                buf = ctypes.create_string_buffer(BOARD_PROPS_SIZE)
                ctypes.memset(buf, 0, BOARD_PROPS_SIZE)
                ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))[0] = cand
                r = lib.zesDeviceGetProperties(ctypes.c_void_p(h), buf)
                if r == ZE_RESULT_SUCCESS:
                    st, got = cand, buf
                    break
            if st is not None:
                print(f"    [GetProperties stype=0x{st:x}]")
                runs = ascii_runs(bytes(got[:BOARD_PROPS_SIZE]), minlen=4)
                if runs:
                    print("    可打印字段段（本机驱动布局与公开规范不符，故按段读）:")
                    for o, t in runs:
                        print(f"       @{o:4d}  {t}")
                else:
                    print("    （无可打印字段）")
            else:
                print("    GetProperties: 全部 stype 都失败")

            # ---- ECC ----
            av = ctypes.c_uint8(0xFF)
            cf = ctypes.c_uint8(0xFF)
            rc_a = lib.zesDeviceEccAvailable(ctypes.c_void_p(h), ctypes.byref(av))
            rc_c = lib.zesDeviceEccConfigurable(ctypes.c_void_p(h), ctypes.byref(cf))
            print(f"    ECC 可用 (EccAvailable)   : rc={rc_a} "
                  f"-> {'✅ 支持' if av.value else '❌ 不支持'}")
            print(f"    ECC 可配 (EccConfigurable): rc={rc_c} "
                  f"-> {'✅ 可配置' if cf.value else '❌ 不可配置'}")
            st, ec = probe_struct(lib, "zesDeviceGetEccState", h, zes_device_ecc_properties_t)
            if st is not None:
                cur = ec.currentState
                print(f"    [GetEccState stype=0x{st:x}]")
                print(f"    原始 currentState        : {cur}")
                print(f"      按 4 值枚举读          : {ECC_STATE_NEW.get(cur, '未知')}")
                print(f"      按 3 值枚举读          : {ECC_STATE_LEGACY.get(cur, '未知')}")
                print(f"    pendingAction            : {ec.pendingAction}"
                      f"（0 = NONE，即无待生效变更，状态已落定）")
            else:
                print("    GetEccState: 全部 stype 都失败")

            # ---- PCIe 链路 ----
            st, pc = probe_struct(lib, "zesDevicePciGetProperties", h, zes_pci_properties_t)
            if st is not None:
                a = pc.address
                print(f"    [PciGetProperties stype=0x{st:x}]")
                print(f"    PCI 地址                 : domain {a.domain} · "
                      f"总线 {a.bus} · 设备 {a.device} · 功能 {a.function}")
                print(f"    最大链路                 : PCIe Gen{pc.maxSpeed.gen} "
                      f"x{pc.maxSpeed.width} · {pc.maxSpeed.maxBandwidth/1e9:.2f} GB/s")
            else:
                print("    PciGetProperties: 全部 stype 都失败")
            st, ps = probe_struct(lib, "zesDevicePciGetState", h, zes_pci_state_t)
            if st is not None:
                print(f"    [PciGetState stype=0x{st:x}]")
                print(f"    链路状态                 : {PCI_LINK.get(ps.status, ps.status)}")
                if ps.speed.gen == 0 and ps.speed.width == 0:
                    # 本机 Intel Windows 驱动不上报链路计数 → 返回全 0。
                    # 别把 0 写成「协商成 x0」，也别据此算带宽。
                    print(f"    ★ 实际协商               : ⚠ 驱动未上报"
                          f"（返回全 0 / status=UNKNOWN，本机拿不到实际协商宽度）")
                else:
                    print(f"    ★ 实际协商               : PCIe Gen{ps.speed.gen} "
                          f"x{ps.speed.width} · {ps.speed.maxBandwidth/1e9:.2f} GB/s")
            else:
                print("    PciGetState: 全部 stype 都失败")

            # ---- 固件（VBIOS 的来源）----
            # ⚠️ 本机驱动**没有按公开规范布局**写 `zes_firmware_properties_t`
            #    （按规范 name 应在 offset 16，实测首个字符串落在 offset 25）。
            #    所以这里不赌偏移，直接按「可打印字符串段」取：第 1 段=固件名，第 2 段=版本。
            fc = ctypes.c_uint32(0)
            r = lib.zesDeviceEnumFirmwares(ctypes.c_void_p(h), ctypes.byref(fc), None)
            print(f"    固件数 (EnumFirmwares rc={r}): {fc.value}")
            if fc.value:
                fw = (ctypes.c_void_p * fc.value)()
                lib.zesDeviceEnumFirmwares(ctypes.c_void_p(h), ctypes.byref(fc), fw)
                for j in range(fc.value):
                    buf = ctypes.create_string_buffer(256)
                    ctypes.memset(buf, 0, 256)
                    ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))[0] = 1
                    rc = lib.zesFirmwareGetProperties(ctypes.c_void_p(fw[j]), buf)
                    runs = ascii_runs(bytes(buf[:256]))
                    if not runs:
                        print(f"      · 固件[{j}] 无可打印字符串（rc={rc}）")
                        continue
                    nm = runs[0][1]
                    # 版本按 C 字符串读到底（**不裁掉非打印字节**）：
                    # 例：GFX 的版本字面值是 `BMG_\x15_21.1182`，中间那个 0x15 是驱动写出来的，
                    # 别把它"修"成 `BMG__21.1182` —— 那就成了编数据。
                    vs = cstr_escaped(bytes(buf[:256]), runs[1][0]) if len(runs) > 1 else "(空)"
                    tag = ""
                    if nm.strip().lower() == "optionrom":
                        tag = "   ★ 这一条就是 VBIOS（注册表取不到的那个字段）"
                    elif nm.strip().lower() == "gfx":
                        tag = "   （GSC 固件，需 HECI 通道；通道打不开时版本为 unknown）"
                    print(f"      · 固件[{j}] {nm:12s} = {vs}{tag}")
                    if raw:
                        print(f"          [raw] 段偏移: "
                              + ", ".join(f"@{o}:{t[:40]}" for o, t in runs))

            # ---- 显存（交叉验证 ECC 状态下的可用容量）----
            mc = ctypes.c_uint32(0)
            r = lib.zesDeviceEnumMemoryModules(ctypes.c_void_p(h), ctypes.byref(mc), None)
            if r == ZE_RESULT_SUCCESS and mc.value:
                mm = (ctypes.c_void_p * mc.value)()
                lib.zesDeviceEnumMemoryModules(ctypes.c_void_p(h), ctypes.byref(mc), mm)
                tot = 0
                for j in range(mc.value):
                    st, ms = probe_struct(lib, "zesMemoryGetState", mm[j], zes_mem_state_t)
                    if st is not None:
                        tot += ms.size
                        print(f"    显存模块[{j}] health={ms.health} "
                              f"free={ms.free/2**20:.0f} MiB size={ms.size/2**20:.0f} MiB")
                        if raw:
                            b = ctypes.create_string_buffer(64)
                            ctypes.memset(b, 0, 64)
                            ctypes.cast(b, ctypes.POINTER(ctypes.c_uint32))[0] = 1
                            lib.zesMemoryGetState(ctypes.c_void_p(mm[j]), b)
                            print(f"          [raw] {b.raw[:48].hex(' ')}")
                print(f"    → 显存合计 {tot/2**30:.2f} GiB ({tot/1e6:.0f} MB)")
                print(f"       与 torch.xpu total_memory 对照（差 = ECC/驱动保留）")
    print(f"\n共 {total} 个 L0 设备")
    print("""
── 判据说明（ECC 别只看枚举值）────────────────────────────────────
Intel 驱动 **ECC 出厂默认 = 关闭，需人工开启**（IGS → Graphics → ECC）。
所以正常情况下读到的就应该是「关闭」；读到「开启」反而要怀疑是不是枚举口径串了。

两层证据，按可信度排序：
  1) 物理容量（最硬）：ECC 开 → 可见显存明显缩水（B70 对照：31.16 GiB → 27.25 GiB，−12.5%）。
     本机 B50 可见 15881.88 MB / 标称 16 GB = 关闭态特征；
     若为开启态，可见容量应落在 ~13.6 GiB。
  2) Sysman currentState：两代枚举编号有歧义（见文件顶部注释），**只作旁证**。

→ 结论写法：先说「ECC 关闭」，再附 Sysman 原始值 + 容量数字。""")


if __name__ == "__main__":
    main()
