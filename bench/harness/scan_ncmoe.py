#!/usr/bin/env python3
r"""扫描 llama.cpp 的 MoE 专家卸载切分点（-ncmoe / --n-cpu-moe），找 16 GB 档最优解。

为什么单独写这个脚本：
  - `-ncmoe N` = 前 N 层的**专家**放 CPU（attention / router / 共享专家仍在 GPU）。
    对比 `-ngl 999` 在显存不足时 llama.cpp 自动做的**整层** offload，
    只卸载专家的通信量小一个量级，是 16 GB 档的真正解法。
  - 实测（2026-10-15，B50 16G / PCIe 4.0 x4）：decode 在 r=1 与 r=3 下几乎一致
    （3.13 vs 3.06 tok/s），因为瓶颈是 PCIe 搬运带宽而非 SYCL JIT。
    **所以本扫描默认 r=1**，prompt 数字仅作参考，结论只看 decode。

用法:
  python scan_ncmoe.py --model <gguf> --bin <build/bin> \
      --device-selector opencl:1 --gpu "Intel Arc Pro B50 LP 16G" \
      --ncmoe 0,4,8,12,16,24,32,48

输出:
  - 每个切分点一份 arc-xpu-bench/1 JSON 到 --outdir
  - 结束时打印汇总表（decode 排序）
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA = "arc-xpu-bench/1"

BASE_ARGS = ["-ngl", "999", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0"]


def base_args(kv=None):
    """kv 形如 'q8_0'、'q4_0'、'f16'；None 时用默认 q8_0。"""
    if not kv:
        return list(BASE_ARGS)
    return ["-ngl", "999", "-fa", "on", "-ctk", kv, "-ctv", kv]


def die(msg, code=1):
    print("[ERR] " + msg, file=sys.stderr)
    sys.exit(code)


def run_one(bench, model, ncmoe, reps, pp, tg, extra_env, sycl_path, kv=None):
    args = [str(bench), "-o", "json", "-m", str(model)] + base_args(kv) + [
        "-ncmoe", str(ncmoe), "-p", str(pp), "-n", str(tg), "-r", str(reps)]
    env = dict(os.environ)
    if sycl_path:
        env["PATH"] = sycl_path + os.pathsep + env.get("PATH", "")
    if extra_env:
        env.update(extra_env)

    print("[CMD] " + " ".join(args))
    proc = subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-600:]
        print("[FAIL] ncmoe=%d 退出码 %d\n%s" % (ncmoe, proc.returncode, tail))
        return None

    blob = proc.stdout or ""
    i, j = blob.find("["), blob.rfind("]")
    if i < 0 or j < 0:
        print("[FAIL] ncmoe=%d 输出无 JSON" % ncmoe)
        return None
    try:
        rows = json.loads(blob[i:j + 1])
    except json.JSONDecodeError as e:
        print("[FAIL] ncmoe=%d JSON 解析失败: %s" % (ncmoe, e))
        return None
    return rows


def extract(rows):
    prompt_ts = decode_ts = None
    for r in rows:
        if r.get("n_depth", 0) != 0:
            continue
        if r.get("n_gen", 0) == 0 and r.get("n_prompt", 0) > 0:
            prompt_ts = r.get("avg_ts")
        elif r.get("n_gen", 0) > 0:
            decode_ts = r.get("avg_ts")
    out = {}
    if prompt_ts is not None:
        out["prompt_tok_s"] = round(float(prompt_ts), 2)
    if decode_ts is not None:
        out["decode_tok_s"] = round(float(decode_ts), 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--bin", required=True)
    ap.add_argument("--gpu", required=True)
    ap.add_argument("--driver", default="")
    ap.add_argument("--ecc", default="", choices=["", "on", "off"])
    ap.add_argument("--quant", default="")
    ap.add_argument("--device-selector", default="")
    ap.add_argument("--sycl-path", default="")
    ap.add_argument("--ncmoe", default="0,4,8,12,16,24,32,48")
    ap.add_argument("--kv", default="", help="KV cache 量化档（q8_0/q4_0/f16），"
                                            "覆盖默认的 -ctk/-ctv q8_0")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--pp", type=int, default=512)
    ap.add_argument("--tg", type=int, default=128)
    ap.add_argument("--tag", default="b50-ncmoe-scan")
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()

    bench = Path(a.bin) / "llama-bench.exe"
    if not bench.exists():
        bench = Path(a.bin) / "llama-bench"
    if not bench.exists():
        die("找不到 llama-bench：%s" % a.bin)

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    extra_env = {}
    if a.device_selector:
        extra_env["ONEAPI_DEVICE_SELECTOR"] = a.device_selector

    points = [int(x) for x in str(a.ncmoe).split(",") if x.strip()]
    results = []

    for ncmoe in points:
        rows = run_one(bench, a.model, ncmoe, a.reps, a.pp, a.tg,
                       extra_env, a.sycl_path, a.kv or None)
        if rows is None:
            results.append({"ncmoe": ncmoe, "ok": False})
            continue
        s = extract(rows)
        raw0 = rows[0] if rows else {}
        rec = {
            "schema": SCHEMA,
            "tag": "%s-ncmoe%d" % (a.tag, ncmoe),
            "date": dt.date.today().isoformat(),
            "source": "local",
            "env": {
                "gpu": a.gpu, "driver": a.driver, "ecc": a.ecc,
                "backend": "SYCL", "tool": "llama-bench",
                "device_selector": a.device_selector,
                "sycl_path": a.sycl_path,
            },
            "model": {
                "name": Path(a.model).stem,
                "quant": a.quant,
                "file": Path(a.model).name,
                "size_gib": round(Path(a.model).stat().st_size / (1024 ** 3), 2),
            },
            "ncmoe": ncmoe,
            "args": base_args(a.kv or None) + [
                "-ncmoe", str(ncmoe), "-p", str(a.pp), "-n", str(a.tg),
                "-r", str(a.reps)],
            "samples": [s] if s else [],
            "summary": s,
            "raw_meta": {
                "model_type": raw0.get("model_type"),
                "n_gpu_layers": raw0.get("n_gpu_layers"),
                "n_cpu_moe": raw0.get("n_cpu_moe"),
                "n_batch": raw0.get("n_batch"),
                "n_ubatch": raw0.get("n_ubatch"),
                "gpu_info": raw0.get("gpu_info"),
            },
            "status": "active",
            "notes": ("专家卸载切分点扫描，r=%d。B50 场景下 decode 稳态与 reps 无关"
                      "（实测 3.13 vs 3.06），prompt 仅作参考。" % a.reps),
        }
        out = outdir / ("%s_%s.json" % (rec["date"], rec["tag"]))
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print("[OK] ncmoe=%-3d decode=%s prompt=%s -> %s"
              % (ncmoe, s.get("decode_tok_s"), s.get("prompt_tok_s"), out.name))
        results.append({"ncmoe": ncmoe, "ok": True, **s})

    print("\n=== 汇总（按 decode 降序）===")
    ok = [r for r in results if r.get("ok") and r.get("decode_tok_s")]
    ok.sort(key=lambda r: -r["decode_tok_s"])
    print("%-8s %-12s %-12s" % ("ncmoe", "decode_tok_s", "prompt_tok_s"))
    for r in ok:
        print("%-8d %-12s %-12s" % (r["ncmoe"], r["decode_tok_s"],
                                    r.get("prompt_tok_s", "-")))
    bad = [r for r in results if not r.get("ok")]
    if bad:
        print("失败切分点: %s" % [r["ncmoe"] for r in bad])
    if not ok:
        die("全部切分点失败")
    return 0


if __name__ == "__main__":
    sys.exit(main())
