#!/usr/bin/env python3
r"""扫 llama-server 的上下文天花板（-c），并做变量隔离。

为什么必须用 server 而不是 llama-bench：
  llama-bench 不接受 -c（docs/pitfalls.md 1.6），所以"能开多长上下文"
  这个指标只能由 llama-server 承载。

为什么必须显式固定 -fa / -ctk / -ctv：
  之前一轮 server 读数在 -c 16384 掉到 12.5 tok/s，而 llama-cli 同参数下
  仍有 45.4 —— 参数没记录，无法归因。SYCL 后端在 FA 开/关、KV 量化档不同时
  走的是**不同注意力内核**，所以这一轮把这三个量从"默认值"改成"显式值"，
  并在 -c 16384 上做对照，把变量一个一个摘掉。

每个配置都留全量日志（--logdir），因为"为什么慢"的答案在日志里的
compute buffer / KV buffer / FA 状态那几行，而不在 tok/s 本身。

用法:
  python ctx_sweep.py --bin <llama.cpp>/build/bin --model <gguf> \
      --port 8099 --n-predict 128 --reps 3 \
      --outdir bench/data --logdir bench/logs
"""

import argparse
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCHEMA = "arc-xpu-ctx-sweep/1"

# 与 scan_ncmoe.py 完全一致的基础参数，保证两组数据可直接对比
KV_ARGS_Q8 = ["-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0"]
KV_ARGS_DEFAULT = []          # 交给 llama.cpp 默认（f16 KV，-fa auto）

# 日志里要摘的行：决定"慢"的机制证据都在这几类里
PATTERNS = {
    "flash_attn":   re.compile(r"flash_attn\s*[:=]\s*(\S+)", re.I),
    "n_ctx":        re.compile(r"n_ctx\s*[:=]\s*(\d+)"),
    "n_ctx_per_seq": re.compile(r"n_ctx_per_seq\s*[:=]\s*(\d+)"),
    "n_parallel":   re.compile(r"n_parallel\s*[:=]\s*(\d+)"),
    "n_batch":      re.compile(r"n_batch\s*[:=]\s*(\d+)"),
    "n_ubatch":     re.compile(r"n_ubatch\s*[:=]\s*(\d+)"),
    "kv_buf":       re.compile(r"KV buffer size\s*=\s*([\d.]+)\s*MiB"),
    "compute_buf":  re.compile(r"compute buffer size\s*=\s*([\d.]+)\s*MiB"),
    "recr_buf":     re.compile(r"([\d.]+)\s*MiB.*recurrent", re.I),
    "model_buf":    re.compile(r"model buffer size\s*=\s*([\d.]+)\s*MiB"),
    "offloaded":    re.compile(r"offloaded\s+(\d+)/(\d+)\s+layers"),
    "swa":          re.compile(r"swa\s*[:=]\s*(\S+)", re.I),
}

# 分配行的**设备维度**。上面的 PATTERNS 是「同类行取最后一条」，而 `-v` 日志里
# 每个 buffer 会打两行：SYCL0（真显存里那部分）与 SYCL_Host（主机侧那部分），
# 最后一条**永远**是 SYCL_Host —— 于是 ncmoe=0 的配置会把 18,731.34 MiB 的
# 模型记成 272.81 MiB（B60 实测，差 68 倍），记录读起来像「模型根本没上卡」。
#
# 两个数回答的是不同问题，不能只留一个：
#   `*_buf`      = 真显存里那部分 → 决定「装不装得下」
#   `*_buf_host` = 主机内存里那部分 → `ncmoe>0` 时被卸下专家的落点，
#                  经 WDDM 共享显存回读，所以它同时在 xpu_vram 的 shared 里出现
# → 键名直说归属，不留「一个数两个含义」。本字典在 PATTERNS 之后跑，覆盖同名键；
#   SYCL 行不存在时（换后端）自动退回 PATTERNS 的通用匹配。
DEV_BUF = {
    "model_buf":        re.compile(r"SYCL0\s+model buffer size\s*=\s*([\d.]+)\s*MiB"),
    "model_buf_host":   re.compile(r"SYCL_Host\s+model buffer size\s*=\s*([\d.]+)\s*MiB"),
    "compute_buf":      re.compile(r"SYCL0\s+compute buffer size\s*=\s*([\d.]+)\s*MiB"),
    "compute_buf_host": re.compile(r"SYCL_Host\s+compute buffer size\s*=\s*([\d.]+)\s*MiB"),
}


def host_mem():
    """返回 (物理内存 GiB, 提交上限 GiB)。
    提交上限 = 物理内存 + 页面文件（Windows 的 ullTotalPageFile 定义如此），
    不是页面文件本身的大小 —— 命名成 pagefile_gb 会误导。

    注意：**不能用 os.sysconf** —— Windows 上没有这个函数，
    之前用它写会静默记成 None，而 ram_gb 是硬性必填项
    （见 bench/README.md：测试环境的内存必须随数据登记）。
    """
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


def post(url, payload, timeout, api_key=""):
    headers = {"Content-Type": "application/json"}
    if api_key:
        # llama-server 只认 Authorization 头；放进 body 会被判 Invalid API Key。
        # 交付配置带 --api-key，所以要能照原样量（见 probe_server.py 的同款注释）。
        headers["Authorization"] = "Bearer %s" % api_key
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
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
            # 503 = 还在加载，是预期的中间态
            if e.code == 503:
                pass
            else:
                return False
        except Exception:
            pass
        time.sleep(2)
    return False


def parse_log(path):
    txt = ""
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"ok": False, "lines": 0}
    out = {"ok": True, "lines": txt.count("\n")}
    for key, pat in PATTERNS.items():
        hits = pat.findall(txt)
        if hits:
            out[key] = hits[-1] if isinstance(hits[-1], str) else list(hits[-1])
    # 设备维度的分配行覆盖上面的通用匹配（见 DEV_BUF 的注释：通用匹配取到的是
    # SYCL_Host 那条，会把模型显存占用记小一两个数量级）
    for key, pat in DEV_BUF.items():
        hits = pat.findall(txt)
        if hits:
            out[key] = hits[-1]
    # 整段摘出来给人工复核，不做二次推断
    keep = [ln for ln in txt.splitlines()
            if re.search(r"KV buffer|compute buffer|model buffer|flash_attn|"
                         r"n_ctx|offloaded|recurrent|pipeline|no_alloc|"
                         r"failed to|OOM|out of memory|abort", ln, re.I)]
    out["key_lines"] = keep[-60:]
    return out


def probe(port, prompt, n_predict, reps, timeout, api_key=""):
    url = "http://127.0.0.1:%d/completion" % port
    payload = {"prompt": prompt, "n_predict": n_predict, "stream": False}
    # 注意：api_key **不能**放进 body —— llama-server 只认 Authorization 头，
    # body 里带 key 会被判 401 Unauthorized（probe_server.py 记过这个坑，
    # 这里 2026-10-16 又踩了一次：4 组配置全部 401，速度全空）。
    rows = []
    for i in range(reps):
        try:
            body, wall = post(url, payload, timeout, api_key)
        except Exception as e:
            rows.append({"rep": i, "error": str(e)[:200]})
            continue
        tim = body.get("timings") or {}
        rows.append({
            "rep": i,
            "wall_s": round(wall, 2),
            "decode_tok_s": tim.get("predicted_per_second"),
            "prompt_tok_s": tim.get("prompt_per_second"),
            "prompt_n": tim.get("prompt_n"),
            "predicted_n": tim.get("predicted_n"),
        })
    # 早停（predicted_n < n_predict，模型自己吐了 EOS）不影响速率有效性，
    # 只要求生成够长以免被首 token 开销污染。太短的丢弃并记录原因。
    good = [r for r in rows
            if r.get("decode_tok_s") and r.get("predicted_n", 0) >= 32]
    out = {"probes": rows}
    dropped = [r for r in rows if r not in good]
    if dropped:
        out["dropped_probes"] = len(dropped)
        out["drop_reason"] = "predicted_n<32 或出错"
    if good:
        ds = [r["decode_tok_s"] for r in good]
        ps = [r["prompt_tok_s"] for r in good if r.get("prompt_tok_s")]
        out["decode_tok_s"] = round(sum(ds) / len(ds), 2)
        out["decode_min"] = round(min(ds), 2)
        out["decode_max"] = round(max(ds), 2)
        out["decode_n"] = len(ds)
        # 早停计数：模型自己吐 EOS 的次数（有 prompt cache 时 prompt_n 会很小，
        # 这是预期的，不是错误）
        out["early_stop"] = sum(1 for r in good if r.get("predicted_n", 0) < n_predict)
        if ps:
            out["prompt_tok_s"] = round(sum(ps) / len(ps), 2)
        # 重复性：极差/均值。>10% 说明这轮读数不可用（见 pitfalls 1.7）
        if len(ds) > 1:
            out["spread_pct"] = round(
                (max(ds) - min(ds)) / (sum(ds) / len(ds)) * 100, 1)
    return out


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
    ap.add_argument("--api-key", default="", help="与 server 的 --api-key 一致；空则不发 Authorization 头")
    ap.add_argument("--ncmoe", type=int, default=0)
    # —— 平台身份（T-20 / bench/README.md 第 1 节，必填项）——
    ap.add_argument("--slot", default="", help="CPU 直连槽 / 芯片组槽（gpu_identity.py 判定）")
    ap.add_argument("--chip", default="", help="芯片 DEV，如 E212")
    ap.add_argument("--subsys", default="", help="SUBSYS，如 25221EF7（AIB 口径）")
    ap.add_argument("--vbios", default="", help="OptionROM 版本（gpu_sysman.py 读）")
    ap.add_argument("--vram-gib", type=float, default=0.0,
                    help="应用可见显存 GiB（随 ECC 变）")
    ap.add_argument("--n-predict", type=int, default=128)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--load-timeout", type=int, default=600)
    ap.add_argument("--prompt", default="用三句话解释 PCIe 带宽对大模型推理的影响。")
    ap.add_argument("--tag", default="ctx-sweep")
    ap.add_argument("--server-verbose", action="store_true",
                    help="给 llama-server 加 -v。默认 verbosity 下日志只有 38 行，"
                         "不含 KV/compute buffer 分配行 —— 追"
                         "「为什么慢」必须开。")
    ap.add_argument("--extra-args", default="",
                    help="追加到每组配置末尾的参数（如 '-lm dio --jinja'）")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--logdir", required=True)
    ap.add_argument("--sample-vram", action="store_true",
                    help="每个配置加载后用 Windows 性能计数器读**真实**显存占用。"
                         "必须开：llama-server 日志在 SYCL 上报的 buffer size 是 0.00 MiB，"
                         "不可用（见 docs/pitfalls.md 4.5）")
    # 配置矩阵：名字|附加参数（空格分隔）
    ap.add_argument("--configs", default="")
    a = ap.parse_args()

    srv = Path(a.bin) / "llama-server.exe"
    if not srv.exists():
        srv = Path(a.bin) / "llama-server"
    if not srv.exists():
        sys.exit("[ERR] 找不到 llama-server: %s" % a.bin)

    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    logdir = Path(a.logdir); logdir.mkdir(parents=True, exist_ok=True)
    _RAM = host_mem()
    print("[ENV] 物理内存 %s GiB · 页面文件上限 %s GiB" % _RAM, flush=True)

    env = dict(os.environ)
    if a.device_selector:
        env["ONEAPI_DEVICE_SELECTOR"] = a.device_selector
    if a.sycl_path:
        env["PATH"] = a.sycl_path + os.pathsep + env.get("PATH", "")

    if a.configs.strip():
        configs = []
        for chunk in a.configs.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            name, _, rest = chunk.partition("|")
            configs.append((name.strip(), rest.split()))
    else:
        # 默认矩阵：先摘 FA/KV 变量，再扫 -c
        configs = [
            ("c4096-faON-q8",   ["-c", "4096"]   + KV_ARGS_Q8),
            ("c16384-faON-q8",  ["-c", "16384"]  + KV_ARGS_Q8),
            ("c16384-default",  ["-c", "16384"]  + KV_ARGS_DEFAULT),
            ("c4096-default",   ["-c", "4096"]   + KV_ARGS_DEFAULT),
        ]

    base = ["-m", a.model, "-ngl", "999", "-ncmoe", str(a.ncmoe),
            "--host", "127.0.0.1", "--port", str(a.port)]
    if a.server_verbose:
        base.append("-v")
    if a.extra_args.strip():
        base += a.extra_args.split()

    results = []
    for name, extra in configs:
        log = logdir / ("%s_%s.log" % (dt.date.today().isoformat(), name))
        cmd = [str(srv)] + base + extra
        print("\n" + "=" * 70)
        print("  [%s]  %s" % (name, " ".join(extra)))
        print("=" * 70, flush=True)

        # 注意：变量名不能叫 env —— 上面的进程环境 env 在同名作用域里，
        # 会被覆盖成这个记录字段字典，导致 Popen(env=...) 拿到 float 报
        # "environment can only contain strings"。
        env_info = {"gpu": a.gpu, "driver": a.driver, "ecc": a.ecc,
                    "backend": "SYCL", "tool": "llama-server",
                    "device_selector": a.device_selector,
                    "sycl_path": a.sycl_path,
                    "ram_gb": _RAM[0], "commit_limit_gb": _RAM[1]}
        # T-20 平台身份：给了才写，避免造出「看起来有、其实空」的字段
        if a.slot:
            env_info["slot"] = a.slot
        if a.chip:
            env_info["chip"] = a.chip
        if a.subsys:
            env_info["subsys"] = a.subsys
        if a.vbios:
            env_info["vbios"] = a.vbios
        if a.vram_gib:
            env_info["vram_visible_gib"] = a.vram_gib

        rec = {
            "schema": SCHEMA, "tag": "%s::%s" % (a.tag, name),
            "date": dt.date.today().isoformat(), "source": "local",
            "env": env_info,
            "model": {"name": Path(a.model).stem, "quant": a.quant,
                      "size_gib": round(Path(a.model).stat().st_size / 1024**3, 2)},
            "config_name": name,
            "ncmoe": a.ncmoe,
            "server_args": extra,
            "log": str(log),
        }

        with open(log, "w", encoding="utf-8", errors="replace") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                    env=env, cwd=str(Path(a.bin)))
            t0 = time.time()
            ok = wait_ready(a.port, a.load_timeout, proc)
            rec["load_s"] = round(time.time() - t0, 1)
            if not ok:
                rcode = proc.poll()
                print("[FAIL] %s 加载失败/超时 (exit=%s, %.1fs)"
                      % (name, rcode, rec["load_s"]))
                rec["status"] = "load_failed"
                rec["exit_code"] = rcode
            else:
                # 真实显存：日志报不出来，只能从性能计数器读
                if a.sample_vram:
                    try:
                        sys.path.insert(0, str(Path(__file__).resolve().parent))
                        import xpu_vram
                        rows = xpu_vram.snapshot(pid_filter=proc.pid)
                        rec["vram"] = rows[0] if rows else None
                        if rec.get("vram"):
                            print("     显存 %.1f MB (共享 %.1f) 工作集 %.1f MB 提交 %.1f MB"
                                  % (rec["vram"].get("vram_dedicated_mb") or -1,
                                     rec["vram"].get("vram_shared_mb") or -1,
                                     rec["vram"].get("ram_working_set_mb") or -1,
                                     rec["vram"].get("ram_commit_mb") or -1))
                    except Exception as e:
                        rec["vram_error"] = str(e)[:200]
                        print("     [WARN] 显存采样失败: %s" % str(e)[:120])
                # 首次请求含 warmup/JIT，单独记一条不进均值
                warm = probe(a.port, a.prompt, a.n_predict, 1, a.timeout, a.api_key)
                rec["warmup"] = warm.get("probes", [{}])[0]
                meas = probe(a.port, a.prompt, a.n_predict, a.reps, a.timeout, a.api_key)
                if a.sample_vram:
                    try:
                        rows = xpu_vram.snapshot(pid_filter=proc.pid)
                        rec["vram_after_probe"] = rows[0] if rows else None
                        # 「是否换页」的硬证据：两次快照之间的硬缺页增量。
                        # vram_shared_mb 只说明显存溢出到主机内存，
                        # 溢出之后有没有继续换到页面文件上，只有缺页计数说得清。
                        # 深度扫描时这段区间恰好就是"跑满上下文"的那段，所以很贴题。
                        v0 = rec.get("vram") or {}
                        v1 = rec.get("vram_after_probe") or {}
                        f0, f1 = v0.get("ram_page_faults"), v1.get("ram_page_faults")
                        if f0 is not None and f1 is not None:
                            rec["page_faults_delta"] = int(f1 - f0)
                            gen = sum((p.get("predicted_n") or 0)
                                      for p in meas.get("probes", []))
                            rec["probe_tokens_total"] = gen
                            if gen:
                                rec["page_faults_per_token"] = round(
                                    (f1 - f0) / gen, 1)
                    except Exception:
                        pass
                rec.update(meas)
                rec["status"] = "active" if meas.get("decode_tok_s") else "probe_failed"
                print("[OK] %s  load=%.1fs  decode=%s (min %s / max %s, n=%s)"
                      % (name, rec["load_s"], meas.get("decode_tok_s"),
                         meas.get("decode_min"), meas.get("decode_max"),
                         meas.get("decode_n")))
                if meas.get("prompt_tok_s"):
                    print("     prompt=%s  warmup_decode=%s"
                          % (meas["prompt_tok_s"],
                             rec["warmup"].get("decode_tok_s")))
                if rec.get("vram_after_probe"):
                    v = rec["vram_after_probe"]
                    shared = v.get("vram_shared_mb") or 0
                    print("     显存 %.1f MB · 共享溢出 %.1f MB%s · 硬缺页增量 %s"
                          % (v.get("vram_dedicated_mb") or -1, shared,
                             "  <== 溢出" if shared > 512 else "",
                             rec.get("page_faults_delta", "-")))
            kill_tree(proc)

        rec["log_scan"] = parse_log(log)
        out = outdir / ("%s_%s_%s.json" % (rec["date"], a.tag, name))
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print("     -> %s" % out.name)
        # 关键行直接打到屏幕，省得回头翻日志
        for ln in rec["log_scan"].get("key_lines", [])[-12:]:
            print("     | " + ln.strip()[:150])
        results.append(rec)

    print("\n=== 汇总 ===")
    print("%-20s %8s %8s %8s %8s" % ("config", "load_s", "decode", "prompt", "spread"))
    for r in results:
        print("%-20s %8s %8s %8s %8s"
              % (r["config_name"], r.get("load_s", "-"),
                 r.get("decode_tok_s", "-"), r.get("prompt_tok_s", "-"),
                 r.get("spread_pct", "-")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
