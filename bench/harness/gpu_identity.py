"""读取当前在位显卡的硬件身份（AIB 口径）——设备 ID / 子系统 ID / 槽位拓扑 / 驱动版本。

为什么需要：Intel 走 AIB（板卡伙伴）模式，同一颗 GPU 由不同厂商做板，
**型号名可能相同，SUBSYS（子系统 ID）、VBIOS、功耗墙、显存颗粒都可能不同**。
跨卡对比时只写「Intel Arc Pro B50」不足以说明测的是哪块板子。

关键字段：
  - DEV_xxxx         GPU 芯片型号（同一芯片全品牌相同）
  - SUBSYS_vvvvdddd  板卡身份：vvvv = 板厂 PCI vendor id
                     （1EF7=GUNNIR/蓝戟, 1849=ASRock, 8086=Intel 自家参考设计）
                     dddd = 板型号编码（同芯片不同厂/不同批次不同，**AIB 差异就落在这里**）
  - REV_xx           硅修订
  - BiosString       VBIOS 版本（**本机注册表里取不到**，该字段恒为 None；
                     改用 Level Zero Sysman，见 bench/harness/gpu_sysman.py）
  - DriverVersion    驱动版本
  - LocationInformation  槽位路径（总线/设备/功能）
  - 上级链           父设备逐级回溯 → 判定「CPU 直连槽」还是「芯片组槽」

只用 winreg + ctypes，不需要管理员权限，不依赖 WMI / PowerShell。

用法：
  python gpu_identity.py            # 只在位设备（含上级链）
  python gpu_identity.py --all      # 含历史（已拔）设备，看装过什么
  python gpu_identity.py --topo     # 打印整棵在用 PCI 树（按总线排序）
"""
import ctypes, winreg, sys, re

cfg = ctypes.WinDLL("cfgmgr32")
CR_SUCCESS = 0
CM_GETIDLIST_FILTER_ENUMERATOR = 0x00000001
CM_GETIDLIST_FILTER_PRESENT = 0x00000100

DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
ENUM = r"SYSTEM\CurrentControlSet\Enum"

# 板厂 PCI vendor id -> 名字（写错不如不写，只列常见的）
VENDORS = {
    "8086": "Intel（参考设计）",
    "1EF7": "GUNNIR 蓝戟",
    "1849": "ASRock 华擎",
    "1DA2": "Sapphire 蓝宝石",
    "1ACC": "Acer 宏碁",
    "10B0": "AIB/其他",
}


def parse_subsys(devid: str):
    """从 VEN_8086&DEV_E212&SUBSYS_25221EF7&REV_00 拆出字段。"""
    out = {"dev": None, "subsys": None, "sub_vendor": None, "sub_model": None, "rev": None}
    for part in devid.split("&"):
        if part.startswith("DEV_"):
            out["dev"] = part[4:]
        elif part.startswith("SUBSYS_"):
            s = part[7:]
            out["subsys"] = s
            if len(s) == 8:
                out["sub_vendor"] = s[4:8]        # 低 4 位 = 板厂 vendor id
                out["sub_model"] = s[0:4]         # 高 4 位 = 板型号编码
        elif part.startswith("REV_"):
            out["rev"] = part[4:]
    return out


def read_key(path):
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
    except OSError:
        return None
    out = {}
    i = 0
    while True:
        try:
            n, v, _ = winreg.EnumValue(k, i)
        except OSError:
            break
        i += 1
        if isinstance(v, (str, int)):
            out[n] = v
    winreg.CloseKey(k)
    return out


def list_devices(present_only=True):
    flags = CM_GETIDLIST_FILTER_ENUMERATOR | (CM_GETIDLIST_FILTER_PRESENT if present_only else 0)
    enumerator = ctypes.c_wchar_p("PCI")
    buf_len = ctypes.c_ulong(0)
    rc = cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(buf_len), enumerator, flags)
    if rc != CR_SUCCESS:
        raise SystemExit(f"CM_Get_Device_ID_List_SizeW rc={rc}")
    buf = ctypes.create_unicode_buffer(buf_len.value)
    rc = cfg.CM_Get_Device_ID_ListW(enumerator, buf, buf_len, flags)
    if rc != CR_SUCCESS:
        raise SystemExit(f"CM_Get_Device_ID_ListW rc={rc}")
    return [x for x in buf[:].split("\x00") if x]


# --- 上级链 / 全局拓扑（2026-10-16 起）---------------------------------------
# 判定「卡插在 CPU 直连槽还是芯片组槽」唯一可靠的办法是**回溯父设备**。
# ⚠️ 别用「根端口 ID」当判据：本机 B50 的根端口与**芯片组上行**的根端口
#    都是 `1022:14DB`（Granite Ridge 同一族端口，实例号不同：`...&0&09` vs `...&0&11`）。
#    真正的判据是**上级链里有没有 AMD 芯片组交换端口 `1022:43F4`/`43F5`**。
# 也别用「总线号大小」猜——总线路由是动态的，同一张卡换槽后总线号会变。
cfg.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p, ctypes.c_ulong]
cfg.CM_Locate_DevNodeW.restype = ctypes.c_uint32
cfg.CM_Get_Parent.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32, ctypes.c_ulong]
cfg.CM_Get_Parent.restype = ctypes.c_uint32
cfg.CM_Get_Device_IDW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong]
cfg.CM_Get_Device_IDW.restype = ctypes.c_uint32


def locate(devid):
    dn = ctypes.c_uint32(0)
    return dn.value if cfg.CM_Locate_DevNodeW(ctypes.byref(dn), devid, 0) == 0 else None


def parent_chain(devid, max_hop=6):
    """逐级回溯父设备，返回设备 ID 列表（从直接父开始，到 ACPI 根为止）。"""
    dn = locate(devid)
    if dn is None:
        return []
    out, cur = [], dn
    for _ in range(max_hop):
        par = ctypes.c_uint32(0)
        if cfg.CM_Get_Parent(ctypes.byref(par), cur, 0) != 0:
            break
        b = ctypes.create_unicode_buffer(512)
        if cfg.CM_Get_Device_IDW(par.value, b, 512, 0) != 0:
            break
        out.append(b.value)
        cur = par.value
    return out


def slot_verdict(chain):
    """按上级链判定槽位归属（CPU 直连 / 芯片组）。"""
    up = " ".join(chain).upper()
    if "VEN_1022&DEV_43F4" in up or "VEN_1022&DEV_43F5" in up:
        return "芯片组槽（上级链经 AMD 芯片组交换端口 1022:43F4/43F5）"
    if "VEN_1022&DEV_14" in up and "ACPI\\PNP0A08" in up:
        return "CPU 直连槽（上级链直达总线 0 的 CPU 根端口）"
    return ""


def parse_loc(li):
    """从 LocationInformation 尾部 '(bus,dev,fun)' 解析三要素。"""
    m = re.search(r"\((\d+),(\d+),(\d+)\)", str(li or ""))
    return tuple(map(int, m.groups())) if m else None


def print_topo():
    print("=== 在用 PCI 设备拓扑（按总线排序）===")
    rows = []
    for dev in list_devices(present_only=True):
        vals = read_key(f"{ENUM}\\{dev}") or {}
        pos = parse_loc(vals.get("LocationInformation"))
        if pos is None:
            continue
        vid = re.search(r"VEN_([0-9A-F]{4})", dev)
        did = re.search(r"DEV_([0-9A-F]{4})", dev)
        desc = str(vals.get("DeviceDesc", "")).split(";")[-1]
        rows.append((pos, f"{vid.group(1) if vid else '----'}:"
                          f"{did.group(1) if did else '----'}", desc))
    for (bus, dev, fun), idpair, desc in sorted(rows):
        print(f"  bus{bus:>3} dev{dev} fun{fun}  {idpair}  {desc}")


def display_class_info():
    """显卡类键：驱动版本 + VBIOS。"""
    info = {}
    try:
        ck = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DISPLAY_CLASS)
    except OSError:
        return info
    j = 0
    while True:
        try:
            sub = winreg.EnumKey(ck, j)
        except OSError:
            break
        j += 1
        if not sub.isdigit():
            continue
        vals = read_key(DISPLAY_CLASS + "\\" + sub) or {}
        desc = str(vals.get("DriverDesc", ""))
        if "Intel" not in desc:
            continue
        info[sub] = {
            "desc": desc,
            "driver": vals.get("DriverVersion"),
            "provider": vals.get("ProviderName"),
            "vbios": vals.get("HardwareInformation.BiosString") or vals.get("BiosString"),
            "instance": vals.get("DeviceInstance"),
        }
    winreg.CloseKey(ck)
    return info


def main():
    want_all = "--all" in sys.argv
    if "--topo" in sys.argv:
        print_topo()
        return
    ids = list_devices(present_only=not want_all)
    # 注册表里的 ConfigFlags 不是可靠的「在位」判据（同槽位换卡会留下残缺 Enum 项，
    # 且 ConfigFlags 仍为 0）。--all 模式必须再取一次 present 集合来交叉核对，
    # 否则会把幽灵项标成「在位」。
    present = set(list_devices(present_only=True)) if want_all else set(ids)
    cls = display_class_info()

    print(f"=== PCI 设备（{'含历史' if want_all else '仅在位'}）: {len(ids)} 个 ===")
    print()

    n = 0
    for dev in ids:
        parts = dev.split("\\")
        if len(parts) < 3:
            continue
        devid, inst = parts[1], parts[2]
        f = parse_subsys(devid)
        if f["dev"] is None:
            continue
        vals = read_key(f"{ENUM}\\{dev}") or {}
        desc = str(vals.get("DeviceDesc", "")).split(";")[-1]
        # 只要独显级别（名字带 Arc / Graphics），排除音频等附属功能
        if not any(t in desc for t in ("Arc", "Graphics", "Display")):
            continue
        n += 1
        cfgflags = vals.get("ConfigFlags")
        vendor_name = VENDORS.get(f["sub_vendor"], f["sub_vendor"])
        print(f"[{n}] {desc}")
        print(f"    设备 ID      : PCI\\{devid}")
        print(f"    芯片 DEV     : {f['dev']}    REV {f['rev']}")
        print(f"    SUBSYS       : {f['subsys']}  -> 板厂 {f['sub_vendor']} ({vendor_name})"
              f" · 板型号编码 {f['sub_model']}")
        print(f"    位置         : {vals.get('LocationInformation')}  实例 {inst}")
        chain = parent_chain(dev)
        for hop, p in enumerate(chain):
            print(f"    上级链 ↑{hop}   : {p}")
        verdict = slot_verdict(chain)
        if verdict:
            print(f"    槽位判定     : {verdict}")
        if want_all:
            state = "✅ 在位" if dev in present else "🕓 历史（已不在位，仅注册表残留）"
        else:
            state = "✅ 在位"
        print(f"    在位状态     : {state}")
        if cfgflags is not None:
            print(f"    ConfigFlags  : {cfgflags}"
                  + ("  ⚠ 含已移除标记" if int(cfgflags) & 1 else "  （注册表值，不作为在位判据）"))
        for sub, ci in cls.items():
            if ci.get("instance") and dev.upper().startswith(str(ci["instance"]).upper()):
                print(f"    驱动         : {ci['driver']}  ({ci['provider']})")
                print(f"    VBIOS        : {ci['vbios']}")
        print()

    if n == 0:
        print("（没有匹配到 Arc/Graphics 设备）")


if __name__ == "__main__":
    main()
