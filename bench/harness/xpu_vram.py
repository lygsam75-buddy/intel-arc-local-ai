#!/usr/bin/env python3
r"""按进程读真实显存 / 内存占用（Windows）。

为什么需要它：
  1. `llama-server` 的日志在 SYCL 后端上**报不出真实分配**——
     `SYCL0 model buffer size = 0.00 MiB`、`SYCL0 KV buffer size = 0.00 MiB`，
     模型明明 10.73 GiB（见 docs/pitfalls.md 4.5）。
  2. `bench/README.md` 把「显存峰值」列为必报指标，但之前**没有测量手段**，
     只能靠「能不能加载」这种布尔判断反推。

原理：Windows 的性能计数器 `\GPU Process Memory(*)\Dedicated Usage`
  按进程给出**独显显存**（不含共享内存），正是我们要的口径。
  `\GPU Process Memory(*)\Shared Usage` 另外给出被换到系统内存的部分——
  **这个值非零就说明显存不够、驱动在往主机内存溢出**，
  是判断「权重到底有没有真的驻留」的直接证据。
  物理内存侧用 `GetProcessMemoryInfo` 取工作集与**提交内存**（决定页面文件）。

为什么用 ctypes 而不是调 PowerShell：
  本机安全策略禁止从 Bash/Python 调 PowerShell（会被判为绕过校验），
  而 pdh.dll 是系统自带 API，Python 直接用没有这层问题，也不引入外部依赖。

用法:
  python xpu_vram.py                  # 列出当前所有进程的显存占用
  python xpu_vram.py --pid 1234       # 只看某个进程
  python xpu_vram.py --name llama     # 按进程名过滤
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import sys

PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2
ERROR_SUCCESS = 0

QUERY_DEDICATED = r"\GPU Process Memory(*)\Dedicated Usage"
QUERY_SHARED = r"\GPU Process Memory(*)\Shared Usage"


class PDH_FMT_COUNTERVALUE(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("longValue", ctypes.c_long),
                    ("doubleValue", ctypes.c_double),
                    ("largeValue", ctypes.c_longlong),
                    ("AnsiStringValue", ctypes.c_char_p),
                    ("WideStringValue", ctypes.c_wchar_p)]
    _fields_ = [("CStatus", wt.DWORD), ("u", _U)]


class PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p),
                ("FmtValue", PDH_FMT_COUNTERVALUE)]


def _read_counter_array(path):
    """返回 {实例名: 值}。用 PdhGetFormattedCounterArray 一次拿全实例。"""
    pdh = ctypes.WinDLL("pdh")
    # PDH 的返回值是 Win32 错误码，高位为 1 时（如 PDH_MORE_DATA = 0x800007D2）
    # ctypes 默认的 c_int 会当成负数，和常量比较永远不相等 ——
    # 实测踩过：rc 打印成 0x-7FFFF82E，判断恒失败。必须显式声明无符号。
    for fn in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
               "PdhGetFormattedCounterArrayW", "PdhCloseQuery"):
        try:
            getattr(pdh, fn).restype = ctypes.c_ulong
        except AttributeError:
            pass
    query = wt.HANDLE()
    counter = wt.HANDLE()

    if pdh.PdhOpenQueryW(None, ctypes.c_void_p(0), ctypes.byref(query)) != ERROR_SUCCESS:
        raise OSError("PdhOpenQuery 失败")
    try:
        if pdh.PdhAddEnglishCounterW(query, path, ctypes.c_void_p(0),
                                     ctypes.byref(counter)) != ERROR_SUCCESS:
            raise OSError("PdhAddEnglishCounter 失败：%s（该计数器在本机可能不存在）" % path)
        # GPU 计数器是速率型，要两次采样
        pdh.PdhCollectQueryData(query)
        ctypes.windll.kernel32.Sleep(600)
        if pdh.PdhCollectQueryData(query) != ERROR_SUCCESS:
            raise OSError("PdhCollectQueryData 失败")

        size = wt.DWORD(0)
        count = wt.DWORD(0)
        rc = pdh.PdhGetFormattedCounterArrayW(
            counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None)
        if rc not in (ERROR_SUCCESS, PDH_MORE_DATA):
            raise OSError("取缓冲区大小失败 rc=0x%08X" % rc)
        buf = ctypes.create_string_buffer(size.value)
        rc = pdh.PdhGetFormattedCounterArrayW(
            counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buf)
        if rc != ERROR_SUCCESS:
            raise OSError("取计数器数组失败 rc=0x%08X" % rc)

        items = ctypes.cast(buf, ctypes.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
        out = {}
        for i in range(count.value):
            it = items[i]
            if it.FmtValue.CStatus == 0:
                out[it.szName] = it.FmtValue.u.doubleValue
        return out
    finally:
        pdh.PdhCloseQuery(query)


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD),
                ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010


def process_mem(pid):
    """返回 (工作集 MB, 提交内存 MB, 累计硬缺页次数)。

    提交内存决定页面文件需求；
    **硬缺页次数（PageFaultCount）是判断"是不是真在换页"的直接证据** ——
    两次快照之间的增量就是这段区间内该进程触发的硬缺页。
    `vram_shared_mb` 只能说明"显存溢出到主机内存"，
    但溢出之后到底有没有继续被换到页面文件上，只有缺页计数说得清。
    """
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
                        False, pid)
    if not h:
        return None, None, None
    try:
        c = PROCESS_MEMORY_COUNTERS_EX()
        c.cb = ctypes.sizeof(c)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
                h, ctypes.byref(c), c.cb):
            return None, None, None
        return (round(c.WorkingSetSize / 1024**2, 1),
                round(c.PagefileUsage / 1024**2, 1),
                int(c.PageFaultCount))
    finally:
        k32.CloseHandle(h)


def _proc_name(pid):
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                          False, pid)
    if not h:
        return "-"
    try:
        buf = ctypes.create_unicode_buffer(512)
        sz = wt.DWORD(512)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                h, 0, buf, ctypes.byref(sz)):
            return buf.value.rsplit("\\", 1)[-1]
        return "-"
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def instance_pid(name):
    """实例名形如 pid_1234_luid_0x..._phys_0 → 取 1234。"""
    try:
        return int(name.split("_")[1])
    except (IndexError, ValueError):
        return None


def snapshot(name_filter=None, pid_filter=None):
    """返回按进程合并后的显存表。"""
    rows = {}
    for path, key in ((QUERY_DEDICATED, "vram_dedicated_mb"),
                      (QUERY_SHARED, "vram_shared_mb")):
        try:
            data = _read_counter_array(path)
        except OSError as e:
            print("[WARN] %s" % e, file=sys.stderr)
            continue
        for inst, val in data.items():
            p = instance_pid(inst)
            if p is None:
                continue
            if pid_filter is not None and p != pid_filter:
                continue
            rows.setdefault(p, {})[key] = round(val / 1024**2, 1)

    out = []
    for p, d in rows.items():
        ws, commit, faults = process_mem(p)
        out.append({"pid": p,
                    "name": _proc_name(p),
                    "vram_dedicated_mb": d.get("vram_dedicated_mb"),
                    "vram_shared_mb": d.get("vram_shared_mb"),
                    "ram_working_set_mb": ws,
                    "ram_commit_mb": commit,
                    "ram_page_faults": faults})
    out.sort(key=lambda r: -(r.get("vram_dedicated_mb") or 0))
    if name_filter:
        out = [r for r in out
               if name_filter.lower() in (r.get("name") or "").lower()]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int)
    ap.add_argument("--name", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = snapshot(a.name or None, a.pid)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print("%-8s %-22s %16s %14s %14s %14s"
          % ("pid", "name", "显存(独显)MB", "共享MB", "工作集MB", "提交MB"))
    for r in rows:
        flag = ""
        if r.get("vram_shared_mb") and r["vram_shared_mb"] > 512:
            flag = "  <== 显存溢出到主机内存"
        print("%-8s %-22s %16s %14s %14s %14s%s"
              % (r["pid"], r.get("name", "-"), r.get("vram_dedicated_mb"),
                 r.get("vram_shared_mb"), r.get("ram_working_set_mb"),
                 r.get("ram_commit_mb"), flag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
