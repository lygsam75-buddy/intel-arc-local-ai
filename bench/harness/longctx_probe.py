#!/usr/bin/env python3
r"""量「上下文真的塞满之后」的速度（长上下文 probe）。

为什么 ctx_sweep.py 不够：
  它只发 ~50 token 的 prompt，所以量的是「**分配** 262144 的 KV 要付多少代价」。
  实测答案是：不用付（4096→262144 只掉 1.6%）。但那**不等于**长上下文可用——
  注意力成本随**实际深度**增长，必须真的把 KV 填到 N 个 token 上再量 decode。

本脚本对每个目标深度做**一次**请求：
  1. 先把 N 个 token 的前缀喂进去（prefill）—— 得 prompt_per_second
  2. 紧接着生成 128 个 token —— 得 predicted_per_second，此时 KV 深度 = N

关键细节：必须 `cache_prompt: false`。
  llama-server 默认缓存 prompt 前缀，若连续发「同前缀 + 更长尾巴」的请求，
  第二次只算增量，prefill 数会被严重高估（假快）。关掉才是干净的全量 prefill。

x 轴用服务端回传的**实测 prompt_n**（不是我们以为的那个数），因为中英混排的
token 比例不可靠。

用法:
  python longctx_probe.py --bin <build/bin> --model <gguf> --ctx 262144 \
      --depths 512,8192,32768,65536,131072 --outdir bench/data --logdir bench/logs
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCHEMA = "arc-xpu-longctx/1"

# 约 2000 字的合成技术文本，重复拼接到目标长度。
# 说明：合成重复文本只用于**测速**，不用于质量评估；重复不会改变
# 「读多少字节权重 / 算多少注意力」这两个决定速度的量。
SEED = (
    "本地推理的性能取决于三个相互独立的量：显存容量决定权重能否全部驻留，"
    "显存带宽决定权重读完一遍要多长时间，算力决定每读一个权重能做多少次乘加。"
    "MoE 架构把参数量做大的同时只激活一小部分专家，所以对带宽的压力小于同等参数量的稠密模型。"
    "混合注意力把大多数层换成线性注意力、只保留少数全注意力层，KV 缓存的增长被压缩了几倍。"
    "上下文变长时，注意力计算量随深度增长，而权重读取量不变，所以深上下文会让解码变慢。"
    "量化的作用是在质量、体积和速度之间取一个点，低比特权重更小但反量化需要额外算力。"
    "专家卸载把一部分专家放到主机内存，用 PCIe 换取显存，代价是每次前向都要过一次总线。"
)


# 长上下文的 prompt 必须**以真实指令收尾**。
# 2026-10-15 第一次跑没加，纯重复文本让模型立刻吐 EOS：
# 深度 31304 只生成 6 个 token、62654 只 11 个、125356 只 3 个 ——
# 首 token 开销没被摊薄，算出来的 decode 偏低且不可信。
# 加上收尾指令后生成长度回到百 token 量级，decode 才可信。
TAIL = "\n\n上面这段材料的核心观点是什么？请用不少于 150 字展开说明。"


def build_prompt(target_tokens, chars_per_token=1.6):
    """按字符数近似凑到目标 token 数；实际 token 数以服务端回传为准。"""
    need = int(target_tokens * chars_per_token)
    reps = max(1, need // len(SEED) + 1)
    parts = []
    for i in range(reps):
        parts.append("第%d段。" % (i + 1))
        parts.append(SEED)
        if sum(len(p) for p in parts) >= need:
            break
    txt = "".join(parts)
    if need < len(txt):
        txt = txt[:need]
    return txt + TAIL


def post(url, payload, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8", "replace"))
    return body, time.perf_counter() - t0


def wait_ready(port, timeout, proc):
    url = "http://127.0.0.1:%d/health" % port
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code != 503:
                return False
        except Exception:
            pass
        time.sleep(2)
    return False


def kill_tree(proc):
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=20)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=10)
        except Exception:
            pass


def parse_log(path):
    txt = ""
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    keep = [ln for ln in txt.splitlines()
            if any(s in ln.lower() for s in
                   ("kv buffer", "compute buffer", "model buffer", "flash_attn",
                    "recurrent", "offloaded", "failed to", "out of memory",
                    "n_ctx", "abort", "context shift", "shift"))]
    return {"lines": txt.count("\n"), "key_lines": keep[-80:]}


def host_mem():
    """返回 (物理内存 GiB, 提交上限 GiB)。
    提交上限 = 物理内存 + 页面文件（Windows 的 ullTotalPageFile 定义如此），
    不是页面文件本身的大小 —— 命名成 pagefile_gb 会误导。Windows 上没有 os.sysconf，
    用它会把 ram_gb 静默记成 None —— 而 ram_gb 是必填项。"""
    try:
        import ctypes

        class MSX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MSX()
        st.dwLength = ctypes.sizeof(st)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return (round(st.ullTotalPhys / 1024**3, 1),
                    round(st.ullTotalPageFile / 1024**3, 1))
    except Exception:
        pass
    try:
        return (round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
                      / 1024**3, 1), None)
    except Exception:
        return None, None


def dump(rec, outdir, tag):
    """每测完一个深度就落盘 —— 这一轮一个点最长要 13 分钟，
    撑到最后才写会让中途失败等于白跑。"""
    out = Path(outdir) / ("%s_%s.json" % (rec["date"], tag))
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--quant", default="")
    ap.add_argument("--gpu", default="")
    ap.add_argument("--driver", default="")
    ap.add_argument("--ecc", default="off")
    ap.add_argument("--device-selector", default="opencl:0")
    ap.add_argument("--sycl-path", default="")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--ctx", type=int, required=True)
    ap.add_argument("--ncmoe", type=int, default=0)
    ap.add_argument("--n-predict", type=int, default=128)
    ap.add_argument("--depths", default="512,8192,32768,65536,131072")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--load-timeout", type=int, default=600)
    ap.add_argument("--server-args", default="-fa on -ctk q8_0 -ctv q8_0",
                    help="放在 -c 之后的 server 参数")
    ap.add_argument("--tag", default="longctx")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--logdir", required=True)
    a = ap.parse_args()

    srv = Path(a.bin) / "llama-server.exe"
    if not srv.exists():
        srv = Path(a.bin) / "llama-server"
    if not srv.exists():
        sys.exit("[ERR] 找不到 llama-server")

    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    logdir = Path(a.logdir); logdir.mkdir(parents=True, exist_ok=True)
    _RAM = host_mem()
    print("[ENV] 物理内存 %s GiB · 页面文件上限 %s GiB" % _RAM, flush=True)

    env = dict(os.environ)
    if a.device_selector:
        env["ONEAPI_DEVICE_SELECTOR"] = a.device_selector
    if a.sycl_path:
        env["PATH"] = a.sycl_path + os.pathsep + env.get("PATH", "")

    log = logdir / ("%s_%s.log" % (dt.date.today().isoformat(), a.tag))
    cmd = ([str(srv), "-m", a.model, "-ngl", "999", "-ncmoe", str(a.ncmoe),
            "-c", str(a.ctx), "--host", "127.0.0.1", "--port", str(a.port)]
           + a.server_args.split())
    print("[CMD] " + " ".join(cmd), flush=True)

    depths = [int(x) for x in str(a.depths).split(",") if x.strip()]

    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT,
                               env=env, cwd=str(Path(a.bin)))
        t0 = time.time()
        rec = {
            "schema": SCHEMA, "tag": a.tag,
            "date": dt.date.today().isoformat(), "source": "local",
            "env": {"gpu": a.gpu, "driver": a.driver, "ecc": a.ecc,
                    "backend": "SYCL", "tool": "llama-server",
                    "device_selector": a.device_selector,
                    "sycl_path": a.sycl_path,
                    "ram_gb": _RAM[0], "commit_limit_gb": _RAM[1]},
            "model": {"name": Path(a.model).stem, "quant": a.quant,
                      "size_gib": round(Path(a.model).stat().st_size / 1024**3, 2)},
            "ctx_size": a.ctx, "ncmoe": a.ncmoe,
            "server_args": a.server_args, "log": str(log),
            "points": [],
        }
        if not wait_ready(a.port, a.load_timeout, proc):
            rec["status"] = "load_failed"
            rec["exit_code"] = proc.poll()
            print("[FAIL] 加载失败/超时 %.1fs" % (time.time() - t0), flush=True)
        else:
            rec["load_s"] = round(time.time() - t0, 1)
            rec["status"] = "active"
            print("[OK] 加载完成 %.1fs" % rec["load_s"], flush=True)
            url = "http://127.0.0.1:%d/completion" % a.port
            for d in depths:
                prompt = build_prompt(d)
                payload = {"prompt": prompt, "n_predict": a.n_predict,
                           "stream": False, "cache_prompt": False}
                print("  -> 目标深度 %d（prompt %d 字符）…"
                      % (d, len(prompt)), flush=True)
                try:
                    body, wall = post(url, payload, a.timeout)
                except Exception as e:
                    print("     [ERR] %s" % str(e)[:200], flush=True)
                    rec["points"].append({"target": d, "error": str(e)[:200]})
                    continue
                tim = body.get("timings") or {}
                pt = {
                    "target_tokens": d,
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
                }
                # 样本太少时 decode 不可信（首 token 偏慢摊不薄）。
                # 不要把这种点当稳态值引用。
                if (pt["predicted_n"] or 0) < 64:
                    pt["decode_unreliable"] = True
                    pt["decode_note"] = "predicted_n=%s < 64，首 token 开销未摊薄" \
                        % pt["predicted_n"]
                rec["points"].append(pt)
                dump(rec, outdir, a.tag)
                print("     prompt_n=%s  prefill=%s tok/s (%.1fs)  decode@depth=%s tok/s%s"
                      % (pt["prompt_n"], pt["prompt_tok_s"], pt["prefill_s"] or 0,
                         pt["decode_tok_s"],
                         "  ⚠样本不足" if pt.get("decode_unreliable") else ""),
                      flush=True)
        kill_tree(proc)

    rec["log_scan"] = parse_log(log)
    out = dump(rec, outdir, a.tag)
    print("\n-> %s" % out)
    print("\n%-10s %10s %12s %10s %12s" %
          ("target", "prompt_n", "prefill_tok_s", "gen", "decode_tok_s"))
    for p in rec["points"]:
        if "error" in p:
            print("%-10s ERR %s" % (p["target"], p["error"][:60]))
            continue
        print("%-10d %10s %12s %10s %12s"
              % (p["target_tokens"], p["prompt_n"], p["prompt_tok_s"],
                 p["predicted_n"], p["decode_tok_s"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
