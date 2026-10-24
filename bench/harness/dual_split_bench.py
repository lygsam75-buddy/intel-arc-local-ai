#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dual_split_bench.py —— 双卡分层装载的**解码速度**，以及 `-ts` / `-sm` 扫描。

为什么单独写这个脚本
--------------------
2026-10-23 那批把 Q8_0 双卡的 6.37 tok/s 写成了「双卡 `-sm layer` 拆层」的成绩，
但日志显示：**llama-bench 收到 `-dev SYCL0,SYCL1` 就按设备各跑一遍**
（记录里 `tensor_split: "0.00"`），6.37 其实是**卡 1（芯片组 x4 槽）单卡**的成绩。
真正双卡分层装载只有一次 llama-server 探针（200，没测速）。

llama-bench 的 `-dev` 语义是「逐设备各跑一遍」，**做不了合并的双卡跑**，
所以双卡拆层只能用 llama-server 量。本脚本做三件事：

1. `-sm layer` 三档 `-ts`：看 decode 随「卡 1 上的层数」怎么变
   —— 变 → 每层有固定跨设备开销；不变 → 开销在切点级，成因在别处；
2. `-sm row` 两档：细粒度切分能不能救（本 build 上直接加载失败，负结果照记）；
3. 单卡同口径对照（`-ngl 37` 全驻 / `-ngl 99`  spill / Q4_0 全驻），
   **同一套采集路径**，让「拆层 vs 不拆」是同口径比。

用法
----
    <python> dual_split_bench.py --run ts5050,solo37,solo99

环境变量：ARC_LLAMA_BIN（必填）、ARC_MODEL（Q8_0，必填）、
          ARC_MODEL_Q4（Q4_0，可选）、ARC_LLAMA_PORT（默认 8099）
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

# SYCL 运行时的 DLL 在 python_embeded/Library/bin 里，不前置会
# "error while loading shared libraries: ?" —— 十秒内失败且没有任何模型错误。
_p = os.path.dirname(os.path.abspath(sys.executable))
for _ in range(4):
    _cand = os.path.join(_p, 'Library', 'bin')
    if os.path.isdir(_cand):
        os.environ['PATH'] = _cand + os.pathsep + os.environ.get('PATH', '')
        break
    _p = os.path.dirname(_p)

# 预置跑法。cards=2 走 -dev SYCL0,SYCL1 + -sm/-ts；cards=1 只钉卡 0。
PRESETS = {
    'ts5050':  {'cards': 2, 'sm': 'layer', 'ts': '50,50'},
    'ts7030':  {'cards': 2, 'sm': 'layer', 'ts': '70,30'},
    'ts8515':  {'cards': 2, 'sm': 'layer', 'ts': '85,15'},
    'row':     {'cards': 2, 'sm': 'row',   'ts': '50,50'},
    'row7030': {'cards': 2, 'sm': 'row',   'ts': '70,30'},
    'solo37':  {'cards': 1, 'ngl': 37},
    'solo99':  {'cards': 1, 'ngl': 99},
    'solo_q4': {'cards': 1, 'ngl': 99, 'model': 'q4'},
}


def free_gib():
    import torch
    return [round(torch.xpu.mem_get_info(i)[0] / 2 ** 30, 2)
            for i in range(torch.xpu.device_count())]


def wait_loaded(logpath, proc, timeout=900):
    """等 'model loaded'；**进程提前退出要立刻算失败**，不能白等满超时。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False
        if os.path.exists(logpath):
            with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
                if 'model loaded' in f.read():
                    return True
        time.sleep(2)
    return False


def ask(port, max_tokens):
    body = json.dumps({
        "messages": [{"role": "user", "content": "用三句话解释什么是张量并行。"}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "cache_prompt": False,
    }).encode()
    req = urllib.request.Request('http://127.0.0.1:%d/v1/chat/completions' % port,
                                 data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    t = d.get('timings') or {}
    return {
        'decode_tok_s': round(t.get('predicted_per_second', 0.0), 2),
        'decode_n': t.get('predicted_n'),
        'prefill_tok_s': round(t.get('prompt_per_second', 0.0), 2),
        'prefill_n': t.get('prompt_n'),
    }


def kill(proc):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                       capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_one(tag, cfg, model_q8, model_q4, bin_, port, reps, max_tokens, logdir):
    model = model_q4 if cfg.get('model') == 'q4' else model_q8
    if cfg['cards'] == 2:
        sel, dev = 'level_zero:0,1', 'SYCL0,SYCL1'
    else:
        sel, dev = 'level_zero:0', 'SYCL0'

    args = [os.path.join(bin_, 'llama-server.exe'), '-m', model,
            '-ngl', str(cfg.get('ngl', 99)),
            '-c', '4096', '-ctk', 'q8_0', '-ctv', 'q8_0', '-fa', 'on',
            '--host', '127.0.0.1', '--port', str(port), '--no-warmup', '-t', '6']
    if cfg['cards'] == 2:
        args += ['-dev', dev, '-sm', cfg['sm'], '-ts', cfg['ts']]
    else:
        args += ['-dev', dev]

    env = dict(os.environ, ONEAPI_DEVICE_SELECTOR=sel)
    logpath = os.path.join(logdir, 'dsb_%s.log' % tag)
    before = free_gib()
    log = open(logpath, 'w', encoding='utf-8')
    proc = subprocess.Popen(args, cwd=bin_, env=env, stdout=log, stderr=subprocess.STDOUT)
    ok = wait_loaded(logpath, proc)
    time.sleep(3)
    after = free_gib() if ok else None

    rec = {
        'tag': tag, 'cards': cfg['cards'],
        'device_selector': sel, 'dev': dev,
        'ngl': cfg.get('ngl', 99), 'ctx': 4096, 'ctk': 'q8_0', 'ctv': 'q8_0', 'fa': 'on',
        'model': os.path.basename(model),
        'loaded': ok,
        'free_before_gib': before, 'free_after_gib': after,
        'log': os.path.basename(logpath),
    }
    if cfg['cards'] == 2:
        rec['split_mode'] = cfg['sm']
        rec['tensor_split'] = cfg['ts']
    if ok:
        rec['used_gib'] = [round(b - f, 2) for b, f in zip(before, after)]
        rec['used_total_gib'] = round(sum(rec['used_gib']), 2)
        try:
            runs = [ask(port, max_tokens) for _ in range(reps)]
            rec['runs'] = runs
            vals = sorted(r['decode_tok_s'] for r in runs)
            rec['decode_tok_s'] = vals[len(vals) // 2]
            rec['decode_min'] = vals[0]
            rec['decode_max'] = vals[-1]
            rec['prefill_tok_s'] = sorted(r['prefill_tok_s'] for r in runs)[len(runs) // 2]
        except Exception as e:                      # noqa: BLE001
            rec['probe_http'] = 'ERR %s' % e
    else:
        tail = ''
        with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                low = line.lower()
                if ('out_of_device_memory' in low or 'out_of_resources' in low
                        or 'error' in low or 'assert' in low):
                    tail = line.strip()
        rec['failure'] = tail or '(进程退出，日志无 OOM 行)'

    kill(proc)
    log.close()
    time.sleep(5)
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    return rec


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True,
                   help='逗号分隔的 tag，来自 %s' % ','.join(sorted(PRESETS)))
    p.add_argument('--model', default=os.environ.get('ARC_MODEL', ''))
    p.add_argument('--model-q4', default=os.environ.get('ARC_MODEL_Q4', ''))
    p.add_argument('--bin', default=os.environ.get('ARC_LLAMA_BIN', ''))
    p.add_argument('--port', type=int,
                   default=int(os.environ.get('ARC_LLAMA_PORT', 8099)))
    p.add_argument('--reps', type=int, default=3)
    p.add_argument('--max-tokens', type=int, default=128)
    p.add_argument('--logdir', default=os.getcwd())
    p.add_argument('--out', default='')
    a = p.parse_args()

    if not a.bin or not os.path.isdir(a.bin):
        sys.exit('请设置 ARC_LLAMA_BIN=<llama.cpp 的 build/bin>')
    if not a.model or not os.path.isfile(a.model):
        sys.exit('请设置 ARC_MODEL=<Q8_0 gguf 路径>')

    recs = []
    for tag in [t.strip() for t in a.run.split(',') if t.strip()]:
        if tag not in PRESETS:
            print('skip unknown tag: %s' % tag, flush=True)
            continue
        cfg = PRESETS[tag]
        if cfg.get('model') == 'q4' and not a.model_q4:
            print('skip %s: 未设置 ARC_MODEL_Q4' % tag, flush=True)
            continue
        print('=== %s ===' % tag, flush=True)
        recs.append(run_one(tag, cfg, a.model, a.model_q4, a.bin, a.port,
                            a.reps, a.max_tokens, a.logdir))
    if a.out:
        with open(a.out, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(recs, f, ensure_ascii=False, indent=2)
        print('written:', a.out)


if __name__ == '__main__':
    main()
