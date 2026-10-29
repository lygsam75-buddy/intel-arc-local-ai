#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dual_ctx_probe.py —— 双卡「3M 上下文」到底跑不跑得动。

背景
----
2026-10-23 的容量记录（`b65-32g_q4_0-ctxcap-dual`）只证明了一件事：
`-c 3145728 --parallel 12`（`kv_unified=false`）**能分配成功**，每卡只剩 0.19 / 0.22 GiB 余量。
但「分配得下」不等于「跑得动」——本脚本补这一刀：

1. 在 3M 分配状态下发一个**短请求**（19 token prompt / 128 token 生成），
   看 decode 还正不正常、有没有 OOM / DEVICE_LOST；
2. 再发一个**长 prompt**，看 prefill 速度与是否崩；
3. 全程记录装载耗时、显存余量、失败行，以及**主机提交内存**（防整机卡死的关键量）。

判据
----
- 短请求跑不动 → **3M 只是纸面容量**，对外不能报 3M；
- 短请求能跑、长 prompt 崩 → 报「3M 分配上限，实测可用要到 X」；
- 都跑得动 → 报出实测速度，3M 可对外。

⚠️ 2026-10-24 事故后的硬性安全护栏
------------------------------
第一轮实测（`-c 3145728 --parallel 12` + 长 prompt）**把整机跑成静默卡死**：
prefill 停在 8192/10240 token，GPU 空转、CPU 空转 14 分钟，
进程私有内存 73 GB、整机提交 91.79 / 95.11 GiB（96.6%），
最后无蓝屏、无 minidump、无 WATCHDOG dump，只能手动重启。

根因不是「卡不够快」，是**主机侧提交内存被顶到上限**：3M 上下文把两卡显存吃到
只剩 0.19 GiB，prefill 需要的临时计算缓冲分配不下来，SYCL/Level Zero 的失败路径
不报错、退化成重试，重试又把主机提交量继续往上顶，直到内核也分配不出内存 → 整机挂。

所以本脚本新增两条护栏，**长请求跑之前先看账**：

1. `--max-commit-frac`（默认 0.90）：提交量超过 commit limit 的这个比例，**不发长请求**，
   直接记 `skipped_commit_ceiling`。宁可少拿一个数，不再赔一台机器。
2. 每个阶段都记 `mem.commit_frac`，用来事后复盘到底是哪一步把内存顶穿的。

第三条护栏（2026-10-24 晚加）：`--job-commit-gib`
------------------------------------------------
前两条都是「先看账、不发货」，但**没有封住进程本身**——一旦进程开始重试，它可以把整机吃满。
`--job-commit-gib 62` 用 Job Object 的 `ProcessMemoryLimit` 给 llama-server 一个**内核级 commit 硬上限**：
超限的分配直接失败、进程报错退出，不存在「无限重试」这条路。

验证方式（已自检）：1.5 GiB 的 job 里 `bytearray(3 GiB)` → `MemoryError`，进程退出，整机无感。

⚠️ 64 位下 `CreateJobObjectW` / `OpenProcess` 必须声明 `restype = HANDLE`，
否则句柄按 `c_int` 截断、`AssignProcessToJobObject` 静默返回 False（这是本文件的踩坑点）。

用法
----
    <python> dual_ctx_probe.py --ctx 3145728 --parallel 12 \
        --model <Q4_0 gguf> --bin <bin> --port 8099 --out <json>

    # 单卡对照（隔离「长 prompt 本身」与「3M 分配」两个变量）：
    <python> dual_ctx_probe.py --ctx 262144 --parallel 1 --single 1 ...

环境变量：ARC_LLAMA_BIN / ARC_MODEL_Q4 / ARC_LLAMA_PORT 可作为默认值。
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request

# SYCL 运行时的 DLL 在 python_embeded/Library/bin，不前置会 "error while loading shared libraries: ?"
_p = os.path.dirname(os.path.abspath(sys.executable))
for _ in range(4):
    _cand = os.path.join(_p, 'Library', 'bin')
    if os.path.isdir(_cand):
        os.environ['PATH'] = _cand + os.pathsep + os.environ.get('PATH', '')
        break
    _p = os.path.dirname(_p)


def free_gib():
    import torch
    return [round(torch.xpu.mem_get_info(i)[0] / 2 ** 30, 2)
            for i in range(torch.xpu.device_count())]


def mem_status():
    """GlobalMemoryStatusEx：ullTotalPageFile = RAM + 页面文件 = commit limit；
    ullAvailPageFile = 还能提交的量。这两个数就是「会不会整机卡死」的判据。"""
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return {}
    limit, avail = m.ullTotalPageFile, m.ullAvailPageFile
    used = limit - avail
    return {
        'commit_limit_gib': round(limit / 2 ** 30, 2),
        'committed_gib': round(used / 2 ** 30, 2),
        'commit_frac': round(used / limit, 3) if limit else None,
        'ram_free_gib': round(m.ullAvailPhys / 2 ** 30, 2),
    }


def kill(proc):
    if proc is None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


def job_with_commit_limit(limit_gib):
    """把子进程关进 Job Object，给**进程 commit 一个硬上限**（返回 (job_handle, limit_bytes)）。

    为什么需要它
    ------------
    2026-10-24 17:00 那次整机静默卡死的机理：3M 分配失败时 SYCL / Level Zero **不报错、退化成重试**，
    重试一路吃主机提交内存，直到内核也分不出 → 整机挂，连 dump 都来不及写。
    光靠「页面文件设小一点」不够——那只是把上限提前，重试仍然可能把系统推到极限。

    Job Object 的 ProcessMemoryLimit 是内核层硬限额：进程一超就**分配直接失败**，
    不存在「无限重试」这条路。风险从「整机」缩到「一个进程」。

    关掉时传 0；非 Windows 直接返回 None。
    """
    if not limit_gib or os.name != 'nt':
        return None, 0
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [('ReadOperationCount', ctypes.c_ulonglong),
                    ('WriteOperationCount', ctypes.c_ulonglong),
                    ('OtherOperationCount', ctypes.c_ulonglong),
                    ('ReadTransferCount', ctypes.c_ulonglong),
                    ('WriteTransferCount', ctypes.c_ulonglong),
                    ('OtherTransferCount', ctypes.c_ulonglong)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                    ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD),
                    ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t),
                    ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t),
                    ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD)]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ('IoInfo', IO_COUNTERS),
                    ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t),
                    ('PeakJobMemoryUsed', ctypes.c_size_t)]

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    # 64 位下不声明 restype，HANDLE 会按 c_int 被截断 → Assign 静默失败（踩过）
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                            ctypes.c_void_p, wintypes.DWORD]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError('CreateJobObjectW 失败: %d' % ctypes.get_last_error())
    limit = int(limit_gib * 2 ** 30)
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    # 0x100 = JOB_OBJECT_LIMIT_PROCESS_MEMORY, 0x200 = JOB_OBJECT_LIMIT_JOB_MEMORY
    info.BasicLimitInformation.LimitFlags = 0x100 | 0x200
    info.ProcessMemoryLimit = limit
    info.JobMemoryLimit = limit
    JobObjectExtendedLimitInformation = 9
    if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                       ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError('SetInformationJobObject 失败: %d' % ctypes.get_last_error())
    return job, limit


def assign_to_job(job, pid):
    """把已起来的子进程放进 job。失败不致命（只是护栏没生效），返回布尔。"""
    if not job or os.name != 'nt':
        return False
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    PROCESS_ALL_ACCESS = 0x1F0FFF
    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h:
        return False
    try:
        return bool(k32.AssignProcessToJobObject(job, h))
    finally:
        k32.CloseHandle(h)



def wait_loaded(logpath, proc, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False, round(time.time() - t0, 1)
        if os.path.exists(logpath):
            with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
                if 'model loaded' in f.read():
                    return True, round(time.time() - t0, 1)
        time.sleep(3)
    return False, round(time.time() - t0, 1)


def chat(port, text, max_tokens, timeout):
    body = json.dumps({
        'messages': [{'role': 'user', 'content': text}],
        'max_tokens': max_tokens,
        'temperature': 0.0,
        'cache_prompt': False,
    }).encode()
    req = urllib.request.Request('http://127.0.0.1:%d/v1/chat/completions' % port,
                                 data=body, headers={'Content-Type': 'application/json'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    wall = round(time.time() - t0, 2)
    t = d.get('timings') or {}
    return {
        'wall_s': wall,
        'decode_tok_s': round(t.get('predicted_per_second', 0.0), 2),
        'decode_n': t.get('predicted_n'),
        'prefill_tok_s': round(t.get('prompt_per_second', 0.0), 2),
        'prefill_n': t.get('prompt_n'),
    }


def tail_error(logpath):
    hits = []
    if not os.path.exists(logpath):
        return hits
    with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            low = line.lower()
            if any(k in low for k in ('out_of_device_memory', 'out_of_resources',
                                      'device_lost', 'error', 'assert', 'abort')):
                hits.append(line.strip()[:300])
    return hits[-6:]


def dump(rec, path):
    if not path:
        return
    # 🔴 必须包 dict 外壳：registry_audit.py 对裸 list 直接崩（2026-10-24 踩过）
    doc = {'schema': 'arc-xpu-capacity/1', 'tag': rec.get('tag', 'dual_ctx_probe'),
           'date': time.strftime('%Y-%m-%d'), 'source': 'local', 'cases': [rec]}
    txt = json.dumps(doc, ensure_ascii=False, indent=2).replace('\n', '\r\n')
    open(path, 'wb').write(txt.rstrip('\r\n').encode('utf-8'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ctx', type=int, default=3145728)
    ap.add_argument('--parallel', type=int, default=12)
    ap.add_argument('--single', type=int, default=0,
                    help='1 = 单卡对照（SYCL0），隔离「长 prompt」与「大分配」两个变量')
    ap.add_argument('--model', default=os.environ.get('ARC_MODEL_Q4', ''))
    ap.add_argument('--bin', default=os.environ.get('ARC_LLAMA_BIN', ''))
    ap.add_argument('--port', type=int, default=int(os.environ.get('ARC_LLAMA_PORT', 8099)))
    ap.add_argument('--long-prompt-tokens', type=int, default=32000)
    ap.add_argument('--short-gen', type=int, default=128)
    ap.add_argument('--long-gen', type=int, default=32)
    ap.add_argument('--load-timeout', type=int, default=2400)
    ap.add_argument('--long-timeout', type=int, default=900,
                    help='长 prompt 单次请求超时（秒）。第一轮死机教训：别用 3600，太长=干等')
    ap.add_argument('--max-commit-frac', type=float, default=0.90,
                    help='提交量占 commit limit 超过这个比例就不发长请求')
    ap.add_argument('--load-only', type=int, default=0,
                    help='1 = 只起到 model loaded 就退，不发任何请求。用于验证「分配会不会被 commit limit 拦住」')
    ap.add_argument('--job-commit-gib', type=float, default=0,
                    help='给 llama-server 的进程 commit 设硬上限（GiB，0=关闭）。'
                         '跑 3M 这类必失败的大分配时用它：超限分配直接失败、进程退出，'
                         '不走「分配失败→无限重试→顶穿整机」那条路')
    ap.add_argument('--logdir', default='.')
    ap.add_argument('--out', default='')
    a = ap.parse_args()

    if not a.bin or not os.path.isdir(a.bin):
        sys.exit('请设置 ARC_LLAMA_BIN')
    if not a.model or not os.path.isfile(a.model):
        sys.exit('请设置 ARC_MODEL_Q4')

    tag = 'dual_ctx%d_par%d%s' % (a.ctx, a.parallel, '_single' if a.single else '')
    logpath = os.path.join(a.logdir, 'dcp_%s.log' % tag)
    args = [os.path.join(a.bin, 'llama-server.exe'), '-m', a.model,
            '-ngl', '99', '-c', str(a.ctx), '--parallel', str(a.parallel),
            '-ctk', 'q8_0', '-ctv', 'q8_0', '-fa', 'on',
            '--host', '127.0.0.1', '--port', str(a.port), '--no-warmup', '-t', '6']
    if a.single:
        dev, sm, ts, sel = 'SYCL0', None, None, 'level_zero:0'
        args += ['-dev', dev]
    else:
        dev, sm, ts, sel = 'SYCL0,SYCL1', 'layer', '50,50', 'level_zero:0,1'
        args += ['-dev', dev, '-sm', sm, '-ts', ts]
    env = dict(os.environ, ONEAPI_DEVICE_SELECTOR=sel)

    rec = {
        'tag': tag,
        'ctx': a.ctx, 'parallel': a.parallel, 'single': bool(a.single),
        'model': os.path.basename(a.model),
        'dev': dev, 'split_mode': sm, 'tensor_split': ts,
        'source': 'dual_ctx_probe.py',
        'window_tokens': a.ctx // a.parallel,
        'log': os.path.basename(logpath),
    }
    before = free_gib()
    rec['free_before_gib'] = before
    rec['mem_before'] = mem_status()

    # 🔴 硬护栏：给进程 commit 封顶。超限分配直接失败，不走「失败→重试→顶穿整机」那条路。
    job, job_limit = job_with_commit_limit(a.job_commit_gib)
    rec['job_commit_limit_gib'] = a.job_commit_gib or None

    log = open(logpath, 'w', encoding='utf-8')
    t_start = time.time()
    proc = subprocess.Popen(args, cwd=a.bin, env=env, stdout=log, stderr=subprocess.STDOUT)
    if job:
        rec['job_assigned'] = assign_to_job(job, proc.pid)
        rec['job_commit_limit_bytes'] = job_limit
    ok, dt = wait_loaded(logpath, proc, a.load_timeout)
    rec['loaded'] = ok
    rec['load_s'] = dt

    if not ok:
        rec['failure'] = '装载失败/超时'
        rec['errors'] = tail_error(logpath)
    elif a.load_only:
        rec['load_only'] = True
        rec['mem_after_load'] = mem_status()
        rec['errors'] = tail_error(logpath)
        rec['alive_after'] = proc.poll() is None
    else:
        time.sleep(3)
        rec['free_after_gib'] = free_gib()
        rec['used_gib'] = [round(b - f, 2) for b, f in zip(rec['free_before_gib'], rec['free_after_gib'])]
        rec['mem_after_load'] = mem_status()

        # 1) 短请求：3M 分配状态下还能不能正常出 token
        try:
            rec['short'] = chat(a.port, '用三句话解释什么是张量并行。', a.short_gen, 900)
        except Exception as e:                                   # noqa: BLE001
            rec['short'] = {'error': str(e)[:300]}
        rec['mem_after_short'] = mem_status()
        dump(rec, a.out)            # 🔴 每阶段落盘：长请求可能把机器跑挂，先把已得的留下

        # 2) 长 prompt：先看提交内存账，超线就不发（2026-10-24 死机护栏）
        cur = mem_status()
        if cur.get('commit_frac') is not None and cur['commit_frac'] >= a.max_commit_frac:
            rec['long'] = {'skipped': 'commit_ceiling',
                           'commit_frac': cur['commit_frac'],
                           'committed_gib': cur['committed_gib'],
                           'commit_limit_gib': cur['commit_limit_gib']}
        else:
            unit = '第五代显卡的内存带宽决定了长上下文推理的速度上限，这一点在本地部署时尤其明显。'
            reps = max(1, a.long_prompt_tokens // max(1, len(unit) // 2))
            long_text = ('请先通读下面的材料，然后回答最后一句问题。\n' + unit * reps +
                         '\n\n问题：上面这段材料反复讲的核心是什么？一句话回答。')
            try:
                rec['long'] = chat(a.port, long_text, a.long_gen, a.long_timeout)
            except Exception as e:                               # noqa: BLE001
                rec['long'] = {'error': str(e)[:300]}
        rec['errors'] = tail_error(logpath)
        rec['alive_after'] = proc.poll() is None
        rec['mem_after_long'] = mem_status()

    rec['wall_s'] = round(time.time() - t_start, 1)
    kill(proc)
    if job:
        try:
            ctypes.windll.kernel32.CloseHandle(job)
        except Exception:                                        # noqa: BLE001
            pass
    log.close()
    dump(rec, a.out)
    print(json.dumps(rec, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
