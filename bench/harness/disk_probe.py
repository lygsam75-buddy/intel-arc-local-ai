#!/usr/bin/env python3
r"""量一块磁盘的顺序带宽与随机读延迟——判断它能不能当 Strata 的 SSD 层。

为什么分两个指标：
  - **顺序带宽**决定「首次装载模型」的等待时间（35–70 GB 一次性读入），慢一次就完事。
  - **随机 4K 延迟**决定「mmap 的 n-gram 表」和 **swap** 的代价。
    这两个是**每个 token / 每次换页**都要付的，慢就是持续慢。
  Strata 在 32 GB 内存机器上必然要用 swap，所以随机延迟比顺序带宽更关键。

用法（需要管理员权限，只读不写）:
  python disk_probe.py --drive 2 --seq-mb 2048 --rand-ios 2000
  python disk_probe.py --drive 1 --seq-mb 1024 --rand-ios 1000   # 做对照

安全说明：只以只读方式打开 \\.\PhysicalDriveN，不做任何写入。
"""

import argparse
import ctypes
import os
import random
import statistics
import sys
import time

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.restype = ctypes.c_void_p
kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32,
                                 ctypes.c_uint32, ctypes.c_void_p,
                                 ctypes.c_uint32, ctypes.c_uint32,
                                 ctypes.c_void_p]


def open_drive(n):
    path = "\\\\.\\PhysicalDrive%d" % n
    h = kernel32.CreateFileW(path, GENERIC_READ,
                             FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                             OPEN_EXISTING, 0, None)
    if not h or h == INVALID_HANDLE_VALUE:
        err = ctypes.get_last_error()
        raise OSError("打不开 %s（错误 %d）——需要管理员权限" % (path, err))
    return h


def size_of(n):
    path = "\\\\.\\PhysicalDrive%d" % n
    h = kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             None, OPEN_EXISTING, 0, None)
    if not h or h == INVALID_HANDLE_VALUE:
        return None
    size = ctypes.c_longlong(0)
    ret = ctypes.c_ulong(0)
    ok = kernel32.DeviceIoControl(ctypes.c_void_p(h), 0x00070000,
                                  None, 0, ctypes.byref(size),
                                  ctypes.sizeof(size), ctypes.byref(ret), None)
    kernel32.CloseHandle(ctypes.c_void_p(h))
    return size.value if ok else None


def read_at(h, offset, size):
    """pread 语义：定位后读。用 SetFilePointerEx + ReadFile。"""
    pos = ctypes.c_longlong(offset)
    newpos = ctypes.c_longlong(0)
    if not kernel32.SetFilePointerEx(ctypes.c_void_p(h), pos,
                                     ctypes.byref(newpos), 0):
        raise OSError("seek 失败 offset=%d" % offset)
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_ulong(0)
    ok = kernel32.ReadFile(ctypes.c_void_p(h), buf, size,
                           ctypes.byref(got), None)
    if not ok:
        raise OSError("读失败 offset=%d（错误 %d）"
                      % (offset, ctypes.get_last_error()))
    return got.value


def seq_test(h, total_mb, chunk_mb):
    total = total_mb * 1024 * 1024
    chunk = chunk_mb * 1024 * 1024
    done = 0
    t0 = time.perf_counter()
    while done < total:
        n = read_at(h, done, min(chunk, total - done))
        if n == 0:
            break
        done += n
    dt = time.perf_counter() - t0
    return {
        "bytes": done,
        "seconds": round(dt, 3),
        "mb_per_s": round(done / 1024 / 1024 / dt, 1),
    }


def rand_test(h, ios, block, span_gb):
    """随机 4K 读，模拟 swap / mmap 的访问形态。"""
    max_off = span_gb * 1024 * 1024 * 1024
    offs = [random.randrange(0, max_off, block) for _ in range(ios)]
    lats = []
    t0 = time.perf_counter()
    for off in offs:
        s = time.perf_counter()
        read_at(h, off, block)
        lats.append((time.perf_counter() - s) * 1e6)   # µs
    wall = time.perf_counter() - t0
    lats.sort()
    return {
        "ios": ios,
        "block_bytes": block,
        "iops": round(ios / wall, 0),
        "avg_lat_us": round(statistics.mean(lats), 1),
        "p50_lat_us": round(lats[len(lats) // 2], 1),
        "p95_lat_us": round(lats[int(len(lats) * 0.95)], 1),
        "mb_per_s": round(ios * block / 1024 / 1024 / wall, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive", type=int, required=True,
                    help="PhysicalDrive 编号（见 Get-PhysicalDisk 的 DeviceId）")
    ap.add_argument("--label", default="")
    ap.add_argument("--seq-mb", type=int, default=2048)
    ap.add_argument("--chunk-mb", type=int, default=8)
    ap.add_argument("--rand-ios", type=int, default=2000)
    ap.add_argument("--rand-block", type=int, default=4096)
    ap.add_argument("--rand-span-gb", type=int, default=32)
    a = ap.parse_args()

    if os.name != "nt":
        print("[ERR] 仅支持 Windows")
        return 1

    print("=== PhysicalDrive%d %s ===" % (a.drive, a.label))
    try:
        h = open_drive(a.drive)
    except OSError as e:
        print("[ERR] %s" % e)
        return 1

    try:
        sz = size_of(a.drive)
        if sz:
            print("容量: %.1f GB" % (sz / 1024 ** 3))

        print("\n[1] 顺序读 %d MB（块 %d MB）..." % (a.seq_mb, a.chunk_mb))
        s = seq_test(h, a.seq_mb, a.chunk_mb)
        print("     %.1f MB/s   用时 %.2f s"
              % (s["mb_per_s"], s["seconds"]))

        print("\n[2] 随机 %d B 读 %d 次（跨度 %d GB）..."
              % (a.rand_block, a.rand_ios, a.rand_span_gb))
        r = rand_test(h, a.rand_ios, a.rand_block, a.rand_span_gb)
        print("     IOPS %.0f   平均 %.1f µs   p50 %.1f µs   p95 %.1f µs   %.1f MB/s"
              % (r["iops"], r["avg_lat_us"], r["p50_lat_us"],
                 r["p95_lat_us"], r["mb_per_s"]))

        print("\n=== 汇总 ===")
        print("顺序带宽      : %.1f MB/s" % s["mb_per_s"])
        print("随机 4K IOPS  : %.0f" % r["iops"])
        print("随机 4K 平均延迟: %.1f µs" % r["avg_lat_us"])
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
