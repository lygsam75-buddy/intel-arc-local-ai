#!/usr/bin/env python3
"""采集 Intel Arc / XPU 上的 llama.cpp 基准，产出 arc-xpu-bench/1 格式的 JSON。

设计原则：
  - 只跑 llama-bench，不自己实现计时（避免引入计时偏差）
  - 硬件/软件口径必须随数据一起落盘，否则跨记录无法比较
  - 不静默吞错：llama-bench 返回非 0 或输出无法解析，直接报错退出

用法:
  python xpu_bench.py \\
      --model <模型目录>/Qwen_Qwen3.6-35B-A3B-Q4_0.gguf \\
      --tag b70-32g_qwen3.6-35b-a3b-q4_0-sycl \\
      --bin <llama.cpp>/build/bin \\
      --backend SYCL \\
      --gpu "Intel Arc Pro B70 32G" \\
      -- -ngl 999 -fa on -ctk q8_0 -ctv q8_0 -c 4096

  --dry-run   只打印将要执行的命令，不真跑
  --outdir    输出目录，默认 ../data

注意：
  - `--` 之后的参数原样透传给 llama-bench
  - 采集结果一律视为「本机实测」，source 固定为 local
"""

import argparse
import datetime as dt
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "arc-xpu-bench/1"


def die(msg, code=1):
    print("[ERR] " + msg, file=sys.stderr)
    sys.exit(code)


def find_bench(bindir):
    """在给定目录里找 llama-bench / llama-cli。"""
    bindir = Path(bindir)
    for name in ("llama-bench.exe", "llama-bench"):
        p = bindir / name
        if p.exists():
            return p
    die("在 %s 下没找到 llama-bench（Windows 是 llama-bench.exe）。"
        "请用 --bin 指向 llama.cpp 的 build/bin 目录。" % bindir)


def probe_env():
    """尽力探测环境。探不到的留空，绝不编造。"""
    env = {
        "os": platform.platform(),
        "cpu": platform.processor() or "",
    }
    try:
        import torch  # noqa
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            props = torch.xpu.get_device_properties(0)
            env["gpu"] = props.name
            env["vram_visible_gib"] = round(props.total_memory / (1024 ** 3), 2)
            env["torch"] = torch.__version__
    except Exception:
        pass
    try:
        total = os.cpu_count()
        env["cpu_threads"] = total
    except Exception:
        pass
    return env


def get_version(bench, sycl_path=""):
    """读 llama-bench 版本字符串。注意：也要带 SYCL PATH，否则进程直接崩、拿不到输出。"""
    try:
        run_env = dict(os.environ)
        if sycl_path:
            run_env["PATH"] = sycl_path + os.pathsep + run_env.get("PATH", "")
        out = subprocess.run(
            [str(bench), "--version"],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace", env=run_env,
        )
        blob = (out.stdout or "") + (out.stderr or "")
        m = re.search(r"version:\s*(\S+.*)", blob)
        return m.group(1).strip() if m else blob.strip()[:200]
    except Exception as e:
        return "unknown (%s)" % e


def parse_model_size_gib(path, fallback=None):
    """模型体积按 GiB 记 —— 与显存口径（GiB）保持一致，避免单位混淆。"""
    try:
        return round(Path(path).stat().st_size / (1024 ** 3), 2)
    except Exception:
        return fallback


def run_bench(bench, model, args, dry_run=False, extra_env=None, sycl_path=""):
    cmd = [str(bench), "-o", "json", "-m", str(model)] + list(args)
    print("[CMD] " + " ".join(cmd))
    if extra_env:
        print("[ENV] " + " ".join("%s=%s" % kv for kv in sorted(extra_env.items())))
    if dry_run:
        return None
    run_env = dict(os.environ)
    if sycl_path:
        run_env["PATH"] = sycl_path + os.pathsep + run_env.get("PATH", "")
    if extra_env:
        run_env.update(extra_env)
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=run_env,
    )
    if proc.returncode != 0:
        die("llama-bench 退出码 %d\n--- stderr ---\n%s" % (proc.returncode, proc.stderr))
    blob = proc.stdout or ""
    # llama-bench 的 JSON 是数组；有时前面混有日志行，取第一个 '[' 开始
    i = blob.find("[")
    j = blob.rfind("]")
    if i < 0 or j < 0:
        die("llama-bench 输出里找不到 JSON 数组。原始输出：\n%s" % blob[:2000])
    try:
        return json.loads(blob[i:j + 1])
    except json.JSONDecodeError as e:
        die("解析 llama-bench JSON 失败：%s\n%s" % (e, blob[i:i + 2000]))


def extract_samples(rows):
    """把 llama-bench 的行整理成 samples。

    llama-bench 每行区分 prompt 处理（n_prompt>0, n_gen=0）和生成（n_gen>0）。
    这里按 n_depth==0 取，产出 prompt_tok_s / decode_tok_s。
    """
    prompt_ts, decode_ts = None, None
    for r in rows:
        if r.get("n_depth", 0) != 0:
            continue
        if r.get("n_gen", 0) == 0 and r.get("n_prompt", 0) > 0:
            prompt_ts = r.get("avg_ts")
        elif r.get("n_gen", 0) > 0:
            decode_ts = r.get("avg_ts")
    s = {}
    if prompt_ts is not None:
        s["prompt_tok_s"] = round(float(prompt_ts), 2)
    if decode_ts is not None:
        s["decode_tok_s"] = round(float(decode_ts), 2)
    return s


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--model", required=True, help="GGUF 模型路径")
    ap.add_argument("--tag", required=True, help="记录标签，用于文件名")
    ap.add_argument("--bin", required=True, help="llama.cpp build/bin 目录")
    ap.add_argument("--backend", required=True, help="SYCL / Vulkan / HIP / CUDA")
    ap.add_argument("--gpu", default="", help="GPU 型号（探测不到时手工填）")
    ap.add_argument("--driver", default="", help="驱动版本")
    ap.add_argument("--ecc", default="", choices=["", "on", "off"], help="ECC 状态")
    ap.add_argument("--quant", default="", help="量化档，如 Q4_0")
    ap.add_argument("--outdir", default="", help="输出目录，默认 ../data")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pp", type=int, default=512,
                    help="llama-bench -p 预填充长度，默认 512")
    ap.add_argument("--tg", type=int, default=128,
                    help="llama-bench -n 解码生成长度，默认 128")
    ap.add_argument("--reps", type=int, default=3,
                    help="llama-bench -r 重复次数，默认 3")
    ap.add_argument("--device-selector", default="",
                    help="ONEAPI_DEVICE_SELECTOR，如 level_zero:0 / opencl:0")
    ap.add_argument("--sycl-path",
                    default=os.environ.get("ARC_SYCL_PATH", "").strip(),
                    help="跑 llama-bench 前 prepend 到 PATH 的 SYCL 运行时目录"
                         "（多个用 %s 分隔）。"
                         "不加这个目录 llama-bench 会以 0xC0000005 直接崩。"
                         "可用环境变量 ARC_SYCL_PATH 预设，传空字符串则禁用。"
                         % os.pathsep)
    ap.add_argument("pass_args", nargs=argparse.REMAINDER,
                    help="-- 之后原样透传给 llama-bench")
    a = ap.parse_args()

    passthru = a.pass_args
    if passthru and passthru[0] == "--":
        passthru = passthru[1:]

    here = Path(__file__).resolve().parent
    outdir = Path(a.outdir) if a.outdir else (here.parent / "data")
    outdir.mkdir(parents=True, exist_ok=True)

    bench = find_bench(a.bin)
    print("[i] llama-bench: %s" % bench)
    print("[i] backend: %s" % a.backend)

    env = probe_env()
    if a.gpu:
        env["gpu"] = a.gpu
    if a.driver:
        env["driver"] = a.driver
    if a.ecc:
        env["ecc"] = a.ecc
    env["engine"] = "llama.cpp"
    env["engine_version"] = get_version(bench, a.sycl_path)
    env["backend"] = a.backend

    bench_args = list(passthru) + ["-p", str(a.pp), "-n", str(a.tg), "-r", str(a.reps)]
    extra_env = {}
    if a.device_selector:
        extra_env["ONEAPI_DEVICE_SELECTOR"] = a.device_selector
        env["device_selector"] = a.device_selector

    env["sycl_path"] = a.sycl_path

    rows = run_bench(bench, a.model, bench_args, dry_run=a.dry_run,
                     extra_env=extra_env, sycl_path=a.sycl_path)
    if a.dry_run:
        print("[i] dry-run，未执行。")
        return

    sample = extract_samples(rows)
    record = {
        "schema": SCHEMA,
        "tag": a.tag,
        "date": dt.date.today().isoformat(),
        "source": "local",
        "env": env,
        "model": {
            "name": Path(a.model).stem,
            "quant": a.quant,
            "file": Path(a.model).name,
            "size_gib": parse_model_size_gib(a.model),
        },
        "args": bench_args,
        "raw": rows,
        "samples": [sample] if sample else [],
        "summary": sample,
        "notes": "",
    }

    out = outdir / ("%s_%s.json" % (record["date"], a.tag))
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] 写入 %s" % out)
    if sample:
        print("[i] prompt %s tok/s · decode %s tok/s"
              % (sample.get("prompt_tok_s"), sample.get("decode_tok_s")))
    print("[!] 记得回头核对：显存口径(GiB)、驱动版本、ECC 状态是否都填了。")


if __name__ == "__main__":
    main()
