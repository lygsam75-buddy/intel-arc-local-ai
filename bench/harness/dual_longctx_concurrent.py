#!/usr/bin/env python3
r"""双卡独立产线 · 长上下文并发单流测量（对照 intel/llm-scaler#773 TP4 c=2 塌 95%）。

形态：两个 llama-server 进程各钉一张 B65（-dev Vulkan1 / Vulkan2），
两卡**同刻**发同深度长 prompt 请求，各记单流 decode tok/s 与 prefill tok/s。
与单卡独占基线（2026-11-04_b65-32g-q4_0-longctx-vk.json）对比得并发回退 %。

为什么要单独脚本而不是跑两个 longctx_probe.py：
  两个独立进程的请求时序会错开（加载时间不同），decode 段可能不重叠。
  本脚本等两个 server 都 ready 后用线程同刻 POST，保证并发真实。

用法:
  python dual_longctx_concurrent.py --bin <build/bin> \
      --model <gguf> \
      --depths 32768,131072 --outdir bench/data --logdir bench/logs

判据（对照 #773）：他们 TP4 c=2 单流 72.91→3.56（−95%）；
  我们独立产线若各卡相对独占回退 ≤5% 即“零损失”结论成立。
"""

import argparse
import datetime as dt
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from longctx_probe import build_prompt, post, wait_ready, kill_tree, host_mem, parse_log  # noqa: E402

SCHEMA = "arc-xpu-dual-longctx/1"


def start_server(srv, model, dev, port, ctx, server_args, logpath):
    cmd = [str(srv), "-m", model, "-ngl", "999", "-ncmoe", "0",
           "-c", str(ctx), "--host", "127.0.0.1", "--port", str(port),
           "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-dev", dev]
    fh = open(logpath, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
    return proc, fh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--quant", default="Q4_0")
    ap.add_argument("--ctx", type=int, default=131072)
    ap.add_argument("--depths", default="32768,131072")
    ap.add_argument("--n-predict", type=int, default=128)
    ap.add_argument("--timeout", type=int, default=5400)
    ap.add_argument("--ports", default="8099,8100")
    ap.add_argument("--devs", default="Vulkan1,Vulkan2")
    ap.add_argument("--tag", default="dual-longctx")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--logdir", required=True)
    a = ap.parse_args()

    srv = Path(a.bin) / "llama-server.exe"
    model = str(a.model)
    devs = a.devs.split(",")
    ports = [int(x) for x in a.ports.split(",")]
    depths = [int(x) for x in a.depths.split(",") if x.strip()]
    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    logdir = Path(a.logdir); logdir.mkdir(parents=True, exist_ok=True)
    ram = host_mem()
    print("[ENV] RAM %s GiB · commit limit %s GiB" % ram, flush=True)

    procs, fhs, logs = [], [], []
    for i, (dev, port) in enumerate(zip(devs, ports)):
        log = logdir / ("%s_%s-c%d-%s.log" % (dt.date.today().isoformat(), a.tag, i, dev))
        proc, fh = start_server(srv, model, dev, port, a.ctx, "", log)
        procs.append(proc); fhs.append(fh); logs.append(log)
        t0 = time.time()
        ok = wait_ready(port, 600, proc)
        print("[C%d] %s port %d ready=%s in %.1fs" % (i, dev, port, ok, time.time()-t0), flush=True)
        if not ok:
            for p in procs: kill_tree(p)
            for f in fhs: f.close()
            sys.exit("[FAIL] card %d server not ready" % i)

    rec = {
        "schema": SCHEMA, "tag": a.tag,
        "date": dt.date.today().isoformat(), "source": "local",
        "env": {"gpu": "2x Intel Arc Pro B65 32G", "driver": "32.0.101.9150",
                "ecc": "off", "backend": "Vulkan", "tool": "llama-server",
                "ram_gb": ram[0], "commit_limit_gb": ram[1],
                "slots": "bus3=CPU直连x16 / bus16=芯片组x4"},
        "model": {"name": Path(model).stem, "quant": a.quant,
                  "size_gib": round(Path(model).stat().st_size / 1024**3, 2)},
        "ctx_size": a.ctx, "ncmoe": 0,
        "server_args": "-fa on -ctk q8_0 -ctv q8_0 -dev %s" % "/".join(devs),
        "concurrency": "independent pipelines (one process per card)",
        "points": [],
        "logs": [str(x) for x in logs],
    }

    try:
        for d in depths:
            prompt = build_prompt(d)
            results = [None, None]
            errors = [None, None]

            def hit(idx):
                payload = {"prompt": prompt, "n_predict": a.n_predict,
                           "stream": False, "cache_prompt": False}
                url = "http://127.0.0.1:%d/completion" % ports[idx]
                try:
                    body, wall = post(url, payload, a.timeout)
                    results[idx] = (body, wall)
                except Exception as e:
                    errors[idx] = str(e)[:200]

            print("  -> 并发深度 %d（prompt %d 字符，两卡同刻）…" % (d, len(prompt)), flush=True)
            ths = [threading.Thread(target=hit, args=(i,)) for i in range(2)]
            t_wall0 = time.time()
            for t in ths: t.start()
            for t in ths: t.join()
            t_wall = time.time() - t_wall0

            for i in range(2):
                if errors[i]:
                    print("     [C%d ERR] %s" % (i, errors[i]), flush=True)
                    rec["points"].append({"target_tokens": d, "card": i,
                                          "dev": devs[i], "error": errors[i]})
                    continue
                body, wall = results[i]
                tim = body.get("timings") or {}
                pt = {
                    "target_tokens": d, "card": i, "dev": devs[i],
                    "prompt_chars": len(prompt),
                    "wall_s": round(wall, 2),
                    "prompt_n": tim.get("prompt_n"),
                    "prompt_tok_s": round(tim["prompt_per_second"], 2)
                    if tim.get("prompt_per_second") else None,
                    "predicted_n": tim.get("predicted_n"),
                    "decode_tok_s": round(tim["predicted_per_second"], 2)
                    if tim.get("predicted_per_second") else None,
                    "prefill_s": round(tim["prompt_ms"] / 1000, 1)
                    if tim.get("prompt_ms") else None,
                    "concurrent_wall_s": round(t_wall, 2),
                }
                rec["points"].append(pt)
                print("     [C%d %s] prefill %s tok/s · decode %s tok/s"
                      % (i, devs[i], pt["prompt_tok_s"], pt["decode_tok_s"]), flush=True)

            out = outdir / ("%s_%s.json" % (rec["date"], a.tag))
            out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            print("     saved -> %s" % out, flush=True)
    finally:
        for p in procs: kill_tree(p)
        for f in fhs:
            try: f.close()
            except Exception: pass

    rec["log_scan"] = [parse_log(str(x)) for x in logs]
    out = outdir / ("%s_%s.json" % (rec["date"], a.tag))
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[DONE] %s" % out, flush=True)


if __name__ == "__main__":
    main()
