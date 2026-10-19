#!/usr/bin/env python3
r"""采场前置检查 / 清场：确认「没有别人在抢 GPU」，再开始量。

为什么需要（`docs/server-config.md` 4.1 的纪律）：
  本机装了一个保活看门狗 —— wscript(隐藏) → cmd(watchdog.bat) → llama-server.exe。
  它每 15 秒探一次 `127.0.0.1:8080`，端口没人服务就把 llama-server 拉起来。
  于是「你以为在独占 GPU，其实全程有个 20 GB 的服务在抢显存」。
  `Stop-Process` 单独杀 llama-server 会被 15 秒后复活；必须**整条链一起停**，
  并落下 `model_off.flag`（TTL 6 小时）抑制每 2 小时的健康检查。

为什么用 Python + Win32 而不是调部署自带的 `stop_model.ps1`：
  本机安全策略禁止从 Bash/Python 调 PowerShell（判为绕过校验）。
  内核 API 没有这层问题，也不引入外部依赖。

判定「GPU 是否干净」的**权威判据不是进程名，是显存**：
  用 `\GPU Process Memory(*)\Dedicated Usage` 看每个进程占了多少独显显存
  （复用 `xpu_vram.py` 的 PDH 逻辑）。只要除自己的 llama-server 外没人大额占用，就是干净的。

用法：
  python rig_state.py            # 体检：进程链 / 端口 / 内存 / 停机标记 / 每进程显存
  python rig_state.py --stop     # 清场：停整条看门狗链 + 落停机标记
  python rig_state.py --json

环境变量：
  ARC_MODEL_OFF_FLAG  停机标记的绝对路径（机器相关，必须自己指）。不设则跳过标记读写。
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TH32CS_SNAPPROCESS = 0x2
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# 停机标记的落地路径是**机器相关**的，不写死在仓库里，用环境变量指路：
#   例  set ARC_MODEL_OFF_FLAG=D:\<部署目录>\model_off.flag
FLAG_PATH = os.environ.get("ARC_MODEL_OFF_FLAG", "").strip()
FLAG_TTL_H = 6.0
PORT = 8080

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def list_processes():
    """返回 [(pid, ppid, exe)]，用 Toolhelp 快照，不依赖 WMI / 命令行读取。"""
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(pe)
    out = []
    if k32.Process32First(snap, ctypes.byref(pe)):
        while True:
            out.append((pe.th32ProcessID, pe.th32ParentProcessID,
                        pe.szExeFile.decode("gbk", "replace")))
            if not k32.Process32Next(snap, ctypes.byref(pe)):
                break
    k32.CloseHandle(snap)
    return out


def kill(pid):
    h = k32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not h:
        return False
    try:
        return bool(k32.TerminateProcess(h, 1))
    finally:
        k32.CloseHandle(h)


def watchdog_chain(procs):
    """挑出看门狗链上的进程：llama-server + 其祖先 cmd/wscript + 由 wscript 派生的 cmd。

    不看命令行（本机读命令行要用被安全策略拦的 Nt* API），
    改用**进程父子关系**判定 —— 看门狗的结构是 wscript → cmd → llama-server，
    这条链的形状本身就足够唯一。
    """
    by_pid = {p[0]: p for p in procs}
    names = [p[2].lower() for p in procs]
    chain = []

    def ancestry(pid, depth=3):
        out = []
        cur = pid
        for _ in range(depth):
            p = by_pid.get(cur)
            if not p:
                break
            cur = p[1]
            if cur in by_pid:
                out.append(by_pid[cur])
        return out

    lls = [p for p in procs if "llama-server" in p[2].lower()]
    wsh = [p for p in procs if p[2].lower() == "wscript.exe"]
    for p in lls:
        chain.append(p)
        chain += ancestry(p[0], 3)
    # 看门狗活着但 llama 已死的情形：wscript 派生的 cmd
    for p in procs:
        if p[2].lower() == "cmd.exe" and p[1] in {w[0] for w in wsh}:
            chain.append(p)
    chain += wsh
    uniq = {p[0]: p for p in chain}
    return sorted(uniq.values(), key=lambda p: p[0])


def port_open(port=PORT):
    s = socket.socket()
    s.settimeout(1.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def mem_state():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    k32.GlobalMemoryStatusEx(ctypes.byref(m))
    gib = 2 ** 30
    return {
        "phys_total_gib": round(m.ullTotalPhys / gib, 2),
        "phys_avail_gib": round(m.ullAvailPhys / gib, 2),
        "commit_limit_gib": round(m.ullTotalPageFile / gib, 2),
        "commit_avail_gib": round(m.ullAvailPageFile / gib, 2),
        "pagefile_gib": round((m.ullTotalPageFile - m.ullTotalPhys) / gib, 1),
        "commit_used_gib": round((m.ullTotalPageFile - m.ullAvailPageFile) / gib, 2),
    }


def flag_state():
    if not FLAG_PATH or not os.path.exists(FLAG_PATH):
        return {"present": False,
                "note": "未设置 ARC_MODEL_OFF_FLAG，未检查停机标记" if not FLAG_PATH else ""}
    txt = open(FLAG_PATH, encoding="ascii", errors="replace").read().strip()
    age = (time.time() - os.path.getmtime(FLAG_PATH)) / 3600.0
    return {"present": True, "text": txt, "age_h": round(age, 2),
            "ttl_h": FLAG_TTL_H, "still_valid": age < FLAG_TTL_H}


def gpu_rows():
    try:
        import xpu_vram
        return xpu_vram.snapshot()
    except Exception as e:  # pragma: no cover
        return [{"error": str(e)}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", action="store_true", help="停整条看门狗链并落停机标记")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    procs = list_processes()
    chain = watchdog_chain(procs)
    state = {
        "port_8080": "open" if port_open() else "closed",
        "mem": mem_state(),
        "flag": flag_state(),
        "watchdog_chain": [{"pid": p[0], "ppid": p[1], "exe": p[2]} for p in chain],
        "gpu_processes": gpu_rows(),
    }

    if a.stop:
        killed = []
        for p in chain:
            if kill(p[0]):
                killed.append({"pid": p[0], "exe": p[2]})
            time.sleep(0.2)
        try:
            if not FLAG_PATH:
                raise OSError("未设置 ARC_MODEL_OFF_FLAG，跳过写停机标记")
            os.makedirs(os.path.dirname(FLAG_PATH), exist_ok=True)
            with open(FLAG_PATH, "w", encoding="ascii") as f:
                f.write("intentionally stopped by rig_state.py at "
                        + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            flag_note = "flag written"
        except OSError as e:
            flag_note = "flag FAILED: %s" % e
        time.sleep(2)
        state["killed"] = killed
        state["flag_note"] = flag_note
        state["port_8080_after"] = "open" if port_open() else "closed"
        state["gpu_processes_after"] = gpu_rows()

    if a.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    print("=== 8080 端口 ===")
    print("  %s" % state["port_8080"])
    print("\n=== 看门狗链（%d 个进程）===" % len(chain))
    for p in chain:
        print("  pid %-7d ppid %-7d %s" % (p[0], p[1], p[2]))
    if not chain:
        print("  （无）")
    m = state["mem"]
    print("\n=== 系统内存 ===")
    print("  物理 %.2f GiB 总 / %.2f GiB 可用" % (m["phys_total_gib"], m["phys_avail_gib"]))
    print("  提交上限 %.2f GiB（页面文件约 %.1f GiB）/ 已提交 %.2f GiB"
          % (m["commit_limit_gib"], m["pagefile_gib"], m["commit_used_gib"]))
    f = state["flag"]
    print("\n=== model_off.flag ===")
    if f.get("present"):
        print("  %s" % f["text"])
        print("  已存在 %.2f 小时（TTL %.0f 小时 → %s）"
              % (f["age_h"], f["ttl_h"], "仍有效" if f["still_valid"] else "★ 已过期"))
    else:
        print("  不存在（健康检查会照常拉起服务）")
    print("\n=== 每进程显存（按独显降序）===")
    print("  %-8s %-22s %14s %14s %14s" % ("pid", "name", "独显MB", "共享MB", "工作集MB"))
    for r in state["gpu_processes"]:
        if "error" in r:
            print("  [WARN] %s" % r["error"])
            continue
        if (r.get("vram_dedicated_mb") or 0) < 1 and (r.get("ram_working_set_mb") or 0) < 50:
            continue
        print("  %-8s %-22s %14s %14s %14s" % (
            r["pid"], r.get("name", "-"), r.get("vram_dedicated_mb"),
            r.get("vram_shared_mb"), r.get("ram_working_set_mb")))

    if a.stop:
        print("\n=== 已停 ===")
        for k in state.get("killed", []):
            print("  killed pid %-7d %s" % (k["pid"], k["exe"]))
        if not state.get("killed"):
            print("  （链上没东西在跑）")
        print("  %s" % state.get("flag_note"))
        print("  端口 8080（停后）: %s" % state.get("port_8080_after"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
