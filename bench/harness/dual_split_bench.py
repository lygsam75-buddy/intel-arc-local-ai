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
所以双卡拆层只能用 llama-server 量。本脚本做五件事：

1. `-sm layer` 三档 `-ts`：看 decode 随「卡 1 上的层数」怎么变
   —— 变 → 每层有固定跨设备开销；不变 → 开销在切点级，成因在别处；
2. `-sm row` 两档：细粒度切分能不能救（本 build 上直接加载失败，负结果照记）；
3. `-sm tensor` 两档（2026-10-24 新增）：张量并行。官方文档明说只对 2 卡优化，
   >2 卡退化成通用 all-reduce；`-fa on` 是硬前提（脚本所有跑法都已开）。
   这是「4 卡联机」问题的正主，先确认 2 卡能不能跑通、跑起来什么数；
4. `GGML_SYCL_ENABLE_HOST_PINNED_MEM=0`（2026-10-24 新增，issue #27888 关键开关）：
   回 layer 做同口径对照，看它是否改变速度/稳定性；tensor 裸跑失败时也用它救；
5. 单卡同口径对照（`-ngl 37` 全驻 / `-ngl 99`  spill / Q4_0 全驻），
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
# pinned: '0'/'1' -> 显式设置 GGML_SYCL_ENABLE_HOST_PINNED_MEM（issue #27888 的关键开关）；
#         缺省 -> 不设该变量，用 build 默认值。
PRESETS = {
    'ts5050':  {'cards': 2, 'sm': 'layer', 'ts': '50,50'},
    'ts7030':  {'cards': 2, 'sm': 'layer', 'ts': '70,30'},
    'ts8515':  {'cards': 2, 'sm': 'layer', 'ts': '85,15'},
    'row':     {'cards': 2, 'sm': 'row',   'ts': '50,50'},
    'row7030': {'cards': 2, 'sm': 'row',   'ts': '70,30'},
    'solo37':  {'cards': 1, 'ngl': 37},
    'solo99':  {'cards': 1, 'ngl': 99},
    'solo_q4': {'cards': 1, 'ngl': 99, 'model': 'q4'},
    # --- 2026-10-24 多卡调研后的新增项（bench/notes/multi-gpu-research.md §3）---
    # 张量并行：官方文档明说只对 2 卡优化，>2 卡退化成通用 all-reduce；
    # 必须 -fa on（--flash-attn off 配 -sm tensor 建 context 时直接被拒）。
    'tensor5050': {'cards': 2, 'sm': 'tensor', 'ts': '50,50'},
    'tensor7030': {'cards': 2, 'sm': 'tensor', 'ts': '70,30'},
    # issue #27888（B50+A770 混架构）的稳定配置关键开关，回到 layer 做同口径对照
    'ts5050_pm0': {'cards': 2, 'sm': 'layer', 'ts': '50,50', 'pinned': '0'},
    # 若 tensor5050 裸跑失败，用同一个开关救
    'tensor5050_pm0': {'cards': 2, 'sm': 'tensor', 'ts': '50,50', 'pinned': '0'},
    # --- 2026-10-24 晚：dev2dev 拷贝路径三档对照（llama.cpp 新增 Level Zero 直拷）---
    # GGML_SYCL_DEV2DEV_MEMCPY: 0=SYCL peer(P2P) / 1=Level Zero 直拷 / 2=host 中转
    # 判据：0 与 2 若一致 -> P2P 没生效，一直在走 host；1 单独更快 -> L0 直拷是真解法。
    'tensor5050_l0': {'cards': 2, 'sm': 'tensor', 'ts': '50,50', 'dev2dev': '1'},
    'tensor5050_fw': {'cards': 2, 'sm': 'tensor', 'ts': '50,50', 'dev2dev': '2'},
    'ts5050_l0':     {'cards': 2, 'sm': 'layer',  'ts': '50,50', 'dev2dev': '1'},
    'ts5050_fw':     {'cards': 2, 'sm': 'layer',  'ts': '50,50', 'dev2dev': '2'},
    # --- 2026-10-24 晚（第二批）：补两条缺口 ---
    # (a) -ts 曲线更细：已有 50/50 35.14、70/30 36.44、85/15 37.30，中间补 60/40、80/20，
    #     再补 90/10 看是否还有线性空间、还是会在某一档见顶。
    'ts6040':  {'cards': 2, 'sm': 'layer', 'ts': '60,40'},
    'ts8020':  {'cards': 2, 'sm': 'layer', 'ts': '80,20'},
    'ts9010':  {'cards': 2, 'sm': 'layer', 'ts': '90,10'},
    # (b) Q4_0 档双卡：之前双卡只跑过 Q8_0（34.37 GiB），Q4_0（20.8 GB）完全没跑。
    #     单卡 Q4_0 全驻已有同口径 31.46，这条补「双卡拆层 vs 单卡全驻」在小模型上的差距。
    'ts5050_q4': {'cards': 2, 'sm': 'layer', 'ts': '50,50', 'model': 'q4'},
    'ts9010_q4': {'cards': 2, 'sm': 'layer', 'ts': '90,10', 'model': 'q4'},
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


def run_one(tag, cfg, model_q8, model_q4, bin_, port, reps, max_tokens, logdir,
            pinned='auto', dev2dev='auto'):
    model = model_q4 if cfg.get('model') == 'q4' else model_q8
    pinned = cfg.get('pinned', pinned)
    dev2dev = cfg.get('dev2dev', dev2dev)
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
    if pinned in ('0', '1'):
        env['GGML_SYCL_ENABLE_HOST_PINNED_MEM'] = pinned
    if dev2dev in ('0', '1', '2'):
        env['GGML_SYCL_DEV2DEV_MEMCPY'] = dev2dev
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
        'pinned_mem': pinned,
        'dev2dev_memcpy': dev2dev,
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
    p.add_argument('--pinned-mem', default='auto', choices=['auto', '0', '1'],
                   help='GGML_SYCL_ENABLE_HOST_PINNED_MEM：auto=不设（build 默认），'
                        '0/1=显式关/开。预置里带 pinned 的以此为准')
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
                            a.reps, a.max_tokens, a.logdir, a.pinned_mem))
    if a.out:
        # 🔴 必须包成 arc-xpu-bench/1 外壳：registry_audit.py 对裸 list 直接崩
        #    （2026-10-24 踩过，4 个文件害得审计跑不完）
        doc = {
            'schema': 'arc-xpu-bench/1',
            'tag': os.path.splitext(os.path.basename(a.out))[0],
            'date': time.strftime('%Y-%m-%d'),
            'source': 'local',
            'env': {
                'os': 'Windows-11-10.0.26300-SP0',
                'cpu': 'AMD Ryzen 5 9600X 6-Core',
                'gpu': '2x Intel Arc Pro B65 32G',
                'vram_visible_gib': 31.16,
                'driver': '9150',
                'ecc': 'off',
                'engine': 'llama.cpp',
                'backend': 'SYCL',
                'cpu_threads': 6,
                'card0': 'CPU 直连 x16',
                'card1': '芯片组 x4',
            },
            'model': {
                'name': 'Qwen3.6-35B-A3B',
                'quant': 'Q8_0' if a.model.endswith('Q8_0.gguf') else 'Q4_0',
                'file': os.path.basename(a.model),
            },
            'measure': {
                'harness': 'llama-server /v1/chat/completions',
                'prompt_tokens': 19,
                'gen_tokens': a.max_tokens,
                'reps': a.reps,
                'statistic': 'median',
                'ctx': 4096,
                'ctk': 'q8_0',
                'ctv': 'q8_0',
                'fa': 'on',
            },
            'samples': recs,
        }
        txt = json.dumps(doc, ensure_ascii=False, indent=2).replace('\n', '\r\n')
        open(a.out, 'wb').write(txt.rstrip('\r\n').encode('utf-8'))
        print('written:', a.out)


if __name__ == '__main__':
    main()
