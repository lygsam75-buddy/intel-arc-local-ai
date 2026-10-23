#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ctx_capacity_probe.py — 量「这个模型 + 这个 KV 类型，最多能装多大的上下文」。

为什么单独写一个
----------------
`run_ctx_ceiling.sh`（B50 16G 那轮）问的是「-c 能开到多少、KV 花多少显存」，
它假设「分配几乎不花钱」。**双卡这批把这个假设推翻了**，而且撞上两个新坑：

1. `-c` 与 `--parallel` 不对齐时（不写 `--parallel`），llama-server 用 4 个 slot 且
   `kv_unified=true`；把 `-c` 写大，日志里 n_ctx_slot 会被 cap 到 262144，
   但**分配行为不一样** —— 2M 会在权重上传阶段 OOM，写对 `--parallel` 就能装。
2. **进程起得来 ≠ 装得下**：单卡 `-c 1572864 / 2097152` 都能起、也能答，
   但显存占用跟 1M 一样 → 多出来的上下文没真分配。

所以本脚本只做一件事：**给一组参数，把「起没起来 + 各卡剩余 + 能不能答」记下来**，
判据交给上层（判据是「显存按比例涨」，不是「进程起来了」）。

用法
----
    <python> ctx_capacity_probe.py --model <模型目录>/x.gguf --cards 2 \
        --ctx 3145728 --parallel 12 --name p12 --out cap.json

环境变量（与仓库其它脚本一致，不写死本机路径）：
    ARC_LLAMA_BIN   llama.cpp 的 build/bin（必填）
    ARC_PYTHON      跑本脚本的解释器（默认 sys.executable）
    ARC_LLAMA_PORT  默认 8099
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

# SYCL / oneMKL 的 DLL 在 python_embeded 的 Library\bin 里；不导出 PATH 会报
# "error while loading shared libraries: ?" —— 表现是十秒内失败、且没有任何模型错误。
# 从解释器目录往上找 python_embeded\Library\bin（便携包布局），找不到就算了。
_p = os.path.dirname(os.path.abspath(sys.executable))
for _ in range(4):
    _cand = os.path.join(_p, 'Library', 'bin')
    if os.path.isdir(_cand):
        os.environ['PATH'] = _cand + os.pathsep + os.environ.get('PATH', '')
        break
    _p = os.path.dirname(_p)

TOTAL_SELECTOR = {1: ('level_zero:0', ''), 2: ('level_zero:0,1', 'SYCL0,SYCL1')}


def free_gib():
    """→ [xpu:0 剩余, xpu:1 剩余, ...]（设备级、跨进程可见）"""
    import torch
    return [round(torch.xpu.mem_get_info(i)[0] / 2 ** 30, 2)
            for i in range(torch.xpu.device_count())]


def wait_loaded(logpath, timeout=600):
    """llama-server 的 TCP 端口通了 ≠ 能提问（加载中回 503），要等日志出现 model loaded。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(logpath):
            with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
                if 'model loaded' in f.read():
                    return True
        time.sleep(2)
    return False


def probe(port):
    body = json.dumps({"messages": [{"role": "user", "content": "只回两个字：收到"}],
                       "max_tokens": 16, "cache_prompt": False}).encode()
    req = urllib.request.Request('http://127.0.0.1:%d/v1/chat/completions' % port,
                                 data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status
    except Exception as e:                       # noqa: BLE001
        return 'ERR %s' % e


def kill(proc):
    """Windows 上 terminate() 偶尔留下句柄，统一走 taskkill /F（不杀别的 llama-server）。"""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                       capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--bin', default=os.environ.get('ARC_LLAMA_BIN', ''))
    p.add_argument('--cards', type=int, choices=(1, 2), required=True)
    p.add_argument('--ctx', type=int, required=True)
    p.add_argument('--parallel', type=int, default=0,
                   help='0 = 不写（走 llama-server 默认 4 个 slot + kv_unified=true）')
    p.add_argument('--ctk', default='q8_0')
    p.add_argument('--ctv', default='q8_0')
    p.add_argument('--name', default='')
    p.add_argument('--out', default='')
    p.add_argument('--logdir', default='')
    p.add_argument('--port', type=int, default=int(os.environ.get('ARC_LLAMA_PORT', 8099)))
    a = p.parse_args()

    if not a.bin or not os.path.isdir(a.bin):
        sys.exit('请设置 ARC_LLAMA_BIN=<llama.cpp 的 build/bin>')
    name = a.name or ('c%d_%d%s' % (a.cards, a.ctx,
                                    '' if not a.parallel else '_p%d' % a.parallel))
    logdir = a.logdir or os.getcwd()
    logpath = os.path.join(logdir, 'ctxcap_%s.log' % name)

    sel, dev = TOTAL_SELECTOR[a.cards]
    args = [os.path.join(a.bin, 'llama-server.exe'), '-m', a.model,
            '-ngl', '99', '-c', str(a.ctx), '-ctk', a.ctk, '-ctv', a.ctv,
            '--host', '127.0.0.1', '--port', str(a.port), '--no-warmup', '-t', '6']
    if a.parallel:
        args += ['--parallel', str(a.parallel)]
    if dev:
        args += ['-dev', dev, '-sm', 'layer']

    env = dict(os.environ, ONEAPI_DEVICE_SELECTOR=sel)
    before = free_gib()
    log = open(logpath, 'w', encoding='utf-8')
    proc = subprocess.Popen(args, cwd=a.bin, env=env, stdout=log, stderr=subprocess.STDOUT)

    ok = wait_loaded(logpath)
    time.sleep(3)
    after = free_gib() if ok else None
    code = probe(a.port) if ok else None

    kill(proc)
    log.close()
    time.sleep(5)

    rec = {
        'name': name,
        'cards': a.cards,
        'device_selector': sel,
        'ctx_tokens': a.ctx,
        'parallel': a.parallel or None,
        'ctk': a.ctk, 'ctv': a.ctv,
        'ok': ok,
        'free_before_gib': before,
        'free_after_gib': after,
        'probe_http': code,
        'log': os.path.basename(logpath),
    }
    if ok:
        rec['used_gib'] = [round(b - f, 2) for b, f in zip(before, after)]
        rec['used_total_gib'] = round(sum(rec['used_gib']), 2)
    else:
        tail = ''
        with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if 'OUT_OF_DEVICE_MEMORY' in line or 'OUT_OF_RESOURCES' in line:
                    tail = line.strip()
        rec['failure'] = tail or '(进程退出，日志无 OOM 行)'

    print(json.dumps(rec, ensure_ascii=False, indent=2))
    if a.out:
        with open(a.out, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
