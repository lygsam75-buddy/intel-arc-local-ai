#!/usr/bin/env python3
r"""多模态（视觉）探针：视觉塔与主权重能不能同时驻留，并真的跑一次图像理解。

回答的对客问题：**B50 16G 能不能跑多模态？**

三条判据，缺一条结论就不成立：

1. **装得下** —— 视觉塔（mmproj）默认 offload 到 GPU。所以「能不能跑多模态」
   = 16 GB 上「主权重 + KV + 视觉塔」是否还装得下。用 `xpu_vram.py` 读进程真实显存，
   **对比挂/不挂 mmproj 的差值**，以及 `vram_shared_mb`（溢出到主机内存的部分）。
2. **真的看见了** —— 光看「服务起来了」不算跑通。视觉塔没加载成功时，
   模型照样会返回一段流畅、自信、但**纯属编造**的描述，tok/s 也照样有值。
   所以必须送一张**答案唯一**的图，核对回答内容。
3. **速度** —— 记 decode/prefill，且要把「图像 token 的 prefill」与「文本 decode」分开看。

本脚本自带的测试图是程序生成的（纯 stdlib 写 PNG，无第三方依赖）：
白底 + 三个同排的形状（红方块 / 绿圆 / 蓝方块）。
正确答案唯一：**3 个形状，从左到右依次是红、绿、蓝**。
答错或含糊（如「五颜六色的图形」）= 视觉塔没真正解码图像。

用法:
  python vision_probe.py --bin <llama.cpp>/build/bin \
      --model <模型目录>/Qwen_Qwen3.6-35B-A3B-Q4_0.gguf \
      --mmproj <模型目录>/mmproj-Qwen3.6-35B-A3B-Q8_0.gguf \
      --port 8098 --ncmoe 8 --ctx 16384 \
      --outdir ../data --logdir ../logs --tag b50-16g-q4_0-vision
"""

import argparse
import base64
import ctypes
import datetime as dt
import json
import os
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

SCHEMA = "arc-xpu-vision-probe/1"

# 正确答案唯一，才谈得上"核对"
TEST_PROMPT = ("List the shapes in this image. For each one give its color. "
               "Answer in one short line, left to right.")


# ---------------------------------------------------------------- 测试图

def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def make_test_png(path, w=640, h=360):
    """白底 + 红方块 / 绿圆 / 蓝方块。纯 stdlib 写 8bit RGB PNG。

    故意做成几何图形而不是自然照片：答案唯一、可机器核对。
    自然照片好看，但"模型说了些像那么回事的话"没法区分
    「真解码了」和「在编」。
    """
    RED, GREEN, BLUE, WHITE = (220, 30, 30), (30, 165, 70), (30, 60, 220), (255, 255, 255)
    px = [[WHITE] * w for _ in range(h)]

    def rect(x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(h, y1)):
            row = px[y]
            for x in range(max(0, x0), min(w, x1)):
                row[x] = c

    def circle(cx, cy, r, c):
        for y in range(max(0, cy - r), min(h, cy + r + 1)):
            dy = y - cy
            row = px[y]
            for x in range(max(0, cx - r), min(w, cx + r + 1)):
                dx = x - cx
                if dx * dx + dy * dy <= r * r:
                    row[x] = c

    def tri(x0, y0, size, c):
        # 顶角朝上的实心等腰三角形
        for i in range(size):
            y = y0 + i
            if y >= h:
                break
            half = int(i * size / (2.0 * size)) + 1
            row = px[y]
            for x in range(max(0, x0 - half), min(w, x0 + half + 1)):
                row[x] = c

    # 从左到右：红方块 -> 绿圆 -> 蓝方块。等距、同尺寸。
    rect(60, 130, 180, 250, RED)          # 左
    circle(320, 190, 60, GREEN)           # 中
    rect(460, 130, 580, 250, BLUE)        # 右

    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in px)
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw, 6))
           + _chunk(b"IEND", b""))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(png)
    return {"path": str(path), "w": w, "h": h, "bytes": len(png),
            "expected": ["red", "green", "blue"]}


# ---------------------------------------------------------------- 平台

def host_mem():
    """(物理 GiB, 提交上限 GiB)。与 ctx_sweep.py 同款，不能用 os.sysconf。"""
    try:
        class MSX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MSX(); st.dwLength = ctypes.sizeof(st)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return (round(st.ullTotalPhys / 1024**3, 1),
                    round(st.ullTotalPageFile / 1024**3, 1))
    except Exception:
        pass
    return None, None


def vram(pid):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import xpu_vram
        rows = xpu_vram.snapshot(pid_filter=pid)
        return rows[0] if rows else None
    except Exception as e:
        return {"error": str(e)[:200]}


# ---------------------------------------------------------------- HTTP

def post(url, payload, timeout, api_key=""):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
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
            if e.code != 503:      # 503 = 还在加载，预期中间态
                return False
        except Exception:
            pass
        time.sleep(2)
    return False


def probe_image(port, image_path, prompt, n_predict, timeout, api_key="",
                no_think=False):
    """走 /v1/chat/completions，图片以 data URI (base64) 内联。

    2026-10-16 踩到的坑：第一次跑 n_predict=96，返回 `completion_tokens: 96`
    但 `content` 是**空字符串** —— 96 个 token 全被推理模型的思考阶段吃掉，
    还没轮到正文就撞上 max_tokens。所以这里把整个 message 都记下来
    （含 `reasoning_content`）与 `finish_reason`，否则「答为空」
    会被误读成「多模态跑不起来」。
    """
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    payload = {
        "model": "local",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + b64}},
        ]}],
        "max_tokens": n_predict,
        "temperature": 0,
        "stream": False,
    }
    if no_think:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    body, wall = post("http://127.0.0.1:%d/v1/chat/completions" % port,
                      payload, timeout, api_key)
    choice = (body.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = body.get("usage") or {}
    return {"wall_s": round(wall, 2), "answer": (msg.get("content") or "").strip(),
            "reasoning": (msg.get("reasoning_content") or "").strip(),
            "message_keys": sorted(msg.keys()),
            "finish_reason": choice.get("finish_reason"),
            "timings": body.get("timings") or {}, "usage": usage}


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


def scan_log(path):
    """摘「视觉塔到底加载了没有、放在哪」的证据行。"""
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    out = {"lines": txt.count("\n")}
    # 版本横幅：跨后端对照靠这一条判断「是不是同一个 build」
    _b = re.search(r"build (\d+) \(([0-9a-f]{7,})\) with (.+?) for Windows", txt)
    if _b:
        out["engine_build"] = [_b.group(1), _b.group(2), _b.group(3).strip()]
    pats = {
        "clip_loaded": re.compile(r"(loaded.*mmproj[^\n]*)", re.I),
        "clip_offload": re.compile(r"(clip[^\n]*(offload|device|SYCL)[^\n]*)", re.I),
        "mmproj_note": re.compile(r"(mmproj[^\n]*)", re.I),
        "projector": re.compile(r"(projector[^\n]*)", re.I),
        "n_embd_vision": re.compile(r"(vision[^\n]*n_embd[^\n]*)", re.I),
        "non_causal": re.compile(r"(non[- ]causal[^\n]*)", re.I),
        "image_tokens": re.compile(r"(\d+)\s*image token", re.I),
    }
    for k, p in pats.items():
        hits = [h if isinstance(h, str) else " ".join(h) for h in p.findall(txt)]
        if hits:
            out[k] = hits[-3:]
    out["key_lines"] = [ln.strip() for ln in txt.splitlines()
                        if re.search(r"clip|mmproj|projector|vision|image|MTMD|"
                                     r"load_tensors|offloaded|buffer size|failed|error",
                                     ln, re.I)][-40:]
    return out


def probe_version(srv, env=None):
    """问二进制要版本串：`0.7.0-dev (build 11753, commit d8d92973c)`。
    格式与 xpu_bench.py 的 get_version() 逐字一致。cwd 必须是 bin 目录。"""
    try:
        out = subprocess.run([str(srv), "--version"], capture_output=True, text=True,
                             timeout=60, encoding="utf-8", errors="replace",
                             env=env, cwd=str(Path(srv).parent))
        blob = (out.stdout or "") + (out.stderr or "")
        m = re.search(r"version:\s*(\S+.*)", blob)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--mmproj", required=True)
    ap.add_argument("--quant", default="")
    ap.add_argument("--gpu", default="")
    ap.add_argument("--driver", default="")
    ap.add_argument("--ecc", default="off")
    ap.add_argument("--slot", default="")
    ap.add_argument("--chip", default="")
    ap.add_argument("--subsys", default="")
    ap.add_argument("--vbios", default="")
    ap.add_argument("--vram-gib", type=float, default=0.0)
    ap.add_argument("--device-selector", default="opencl:0")
    ap.add_argument("--backend", default="SYCL",
                    help="写进记录 env.backend 的后端名。原先硬编码 SYCL，"
                         "跑 Vulkan 会把记录标成 SYCL")
    ap.add_argument("--device", default="",
                    help="llama.cpp 的 -dev 设备名（Vulkan 只认这个，如 Vulkan1）")
    ap.add_argument("--sycl-path", default="")
    ap.add_argument("--port", type=int, default=8098)
    ap.add_argument("--ncmoe", type=int, default=8)
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--n-predict", type=int, default=96)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--image", default="")
    ap.add_argument("--image-min-tokens", type=int, default=1024)
    ap.add_argument("--api-key", default="")
    ap.add_argument("--no-think", action="store_true",
                    help="给 chat template 传 enable_thinking=false（推理模型把 token "
                         "预算全花在思考阶段时，content 会是空的）")
    ap.add_argument("--prompt", default=TEST_PROMPT)
    ap.add_argument("--extra-args", default="")
    ap.add_argument("--server-verbose", action="store_true",
                    help="给 llama-server 加 -v（逐 token 日志；会影响速度读数）")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--load-timeout", type=int, default=900)
    ap.add_argument("--tag", default="vision-probe")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--logdir", required=True)
    a = ap.parse_args()

    srv = Path(a.bin) / "llama-server.exe"
    if not srv.exists():
        srv = Path(a.bin) / "llama-server"
    if not srv.exists():
        sys.exit("[ERR] 找不到 llama-server: %s" % a.bin)

    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    logdir = Path(a.logdir); logdir.mkdir(parents=True, exist_ok=True)

    image = a.image or str(outdir / "assets" / "vision_test.png")
    img_info = make_test_png(image)
    print("[IMG] %s  (%dx%d, %d B)  期望答案: %s"
          % (img_info["path"], img_info["w"], img_info["h"],
             img_info["bytes"], "/".join(img_info["expected"])), flush=True)

    _RAM = host_mem()
    print("[ENV] 物理内存 %s GiB · 提交上限 %s GiB" % _RAM, flush=True)

    env = dict(os.environ)
    # 同 ctx_sweep：ONEAPI_DEVICE_SELECTOR 只对 SYCL 有意义
    if a.device_selector and a.backend.upper().startswith("SYCL"):
        env["ONEAPI_DEVICE_SELECTOR"] = a.device_selector
    if a.sycl_path:
        env["PATH"] = a.sycl_path + os.pathsep + env.get("PATH", "")

    cmd = [str(srv), "-m", a.model, "-ngl", "999", "-ncmoe", str(a.ncmoe),
           "--host", "127.0.0.1", "--port", str(a.port),
           "-c", str(a.ctx), "--parallel", "1",
           "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
           "--fit", "off", "-lm", "dio", "--jinja",
           "--mmproj", a.mmproj, "--image-min-tokens", str(a.image_min_tokens)]
    if a.device:
        cmd += ["-dev", a.device]
    # -v 默认不开：本轮实测发现 verbose 的「每 token 一行」日志会让 decode
    # 偏低的嫌疑（同配置 -v 35.55 / 无 -v 37.5）。视觉塔证据行是 info 级，
    # 不开 -v 也在，所以默认关掉，保证速度读数与其它配置同口径。
    if a.server_verbose:
        cmd.append("-v")
    if a.api_key:
        cmd += ["--api-key", a.api_key]
    if a.extra_args.strip():
        cmd += a.extra_args.split()

    log = logdir / ("%s_%s.log" % (dt.date.today().isoformat(), a.tag))
    rec = {
        "schema": SCHEMA, "tag": a.tag, "date": dt.date.today().isoformat(),
        "source": "local",
        "env": {"gpu": a.gpu, "driver": a.driver, "ecc": a.ecc, "backend": a.backend,
                "tool": "llama-server /v1/chat/completions",
                "device_selector": (a.device_selector
                                    if a.backend.upper().startswith("SYCL") else ""),
                "sycl_path": a.sycl_path,
                "ram_gb": _RAM[0], "commit_limit_gb": _RAM[1]},
        "model": {"name": Path(a.model).stem, "quant": a.quant,
                  "size_gib": round(Path(a.model).stat().st_size / 1024**3, 2)},
        "mmproj": {"file": Path(a.mmproj).name,
                   "size_gib": round(Path(a.mmproj).stat().st_size / 1024**3, 2)},
        "ncmoe": a.ncmoe, "ctx": a.ctx,
        "image_min_tokens": a.image_min_tokens,
        "server_args": cmd[1:], "log": str(log),
        "test_image": img_info, "prompt": a.prompt,
    }
    for k, v in (("slot", a.slot), ("chip", a.chip), ("subsys", a.subsys),
                 ("vbios", a.vbios)):
        if v:
            rec["env"][k] = v
    if a.vram_gib:
        rec["env"]["vram_visible_gib"] = a.vram_gib

    print("\n" + "=" * 70)
    print("  起 server（带 --mmproj）")
    print("=" * 70, flush=True)
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                env=env, cwd=str(Path(a.bin)))
        t0 = time.time()
        ok = wait_ready(a.port, a.load_timeout, proc)
        rec["load_s"] = round(time.time() - t0, 1)
        if not ok:
            rec["status"] = "load_failed"
            rec["exit_code"] = proc.poll()
            print("[FAIL] 加载失败/超时 (exit=%s, %.1fs)"
                  % (rec["exit_code"], rec["load_s"]))
        else:
            print("[OK] 加载 %.1fs —— 视觉塔与主权重同时驻留中" % rec["load_s"])
            rec["vram_after_load"] = vram(proc.pid)
            v = rec["vram_after_load"] or {}
            print("     显存 %.1f MB · 共享(溢出) %.1f MB · 工作集 %.1f MB · 提交 %.1f MB"
                  % (v.get("vram_dedicated_mb") or -1, v.get("vram_shared_mb") or -1,
                     v.get("ram_working_set_mb") or -1, v.get("ram_commit_mb") or -1))

            runs = []
            for i in range(a.reps):
                try:
                    r = probe_image(a.port, image, a.prompt, a.n_predict,
                                    a.timeout, a.api_key, a.no_think)
                except urllib.error.HTTPError as e:
                    runs.append({"rep": i,
                                 "error": "HTTP %d: %s" % (e.code,
                                           e.read().decode("utf-8", "replace")[:300])})
                    continue
                except Exception as e:
                    runs.append({"rep": i, "error": str(e)[:300]})
                    continue
                tim = r["timings"]
                runs.append({
                    "rep": i, "wall_s": r["wall_s"], "answer": r["answer"],
                    "reasoning_head": (r.get("reasoning") or "")[:300],
                    "message_keys": r.get("message_keys"),
                    "finish_reason": r.get("finish_reason"),
                    "decode_tok_s": tim.get("predicted_per_second"),
                    "prompt_tok_s": tim.get("prompt_per_second"),
                    "prompt_n": tim.get("prompt_n"),
                    "predicted_n": tim.get("predicted_n"),
                    "usage": r["usage"],
                })
                print("     rep%d  wall=%.1fs  decode=%s  prompt=%s  prompt_n=%s  finish=%s"
                      % (i, r["wall_s"], tim.get("predicted_per_second"),
                         tim.get("prompt_per_second"), tim.get("prompt_n"),
                         r.get("finish_reason")))
                print("       答: %s" % (r["answer"][:200].replace("\n", " ") or "(空)"))
                if r.get("reasoning"):
                    print("       思考(前120字): %s"
                          % r["reasoning"][:120].replace("\n", " "))
            rec["runs"] = runs
            rec["vram_after_probe"] = vram(proc.pid)

            good = [r for r in runs if r.get("decode_tok_s")]
            if good:
                ds = [r["decode_tok_s"] for r in good]
                rec["decode_tok_s"] = round(sum(ds) / len(ds), 2)
                ps = [r["prompt_tok_s"] for r in good if r.get("prompt_tok_s")]
                if ps:
                    rec["prompt_tok_s"] = round(sum(ps) / len(ps), 2)
                rec["image_prompt_n"] = good[0].get("prompt_n")
            # 内容核对：答案里必须同时出现三种颜色才算"真的看见了"。
            # 思考文本也算数——重点是「模型有没有从图里读出这三个颜色」，
            # 而不是它把结论放在 content 还是 reasoning_content。
            joined = " ".join(((r.get("answer") or "") + " " +
                               (r.get("reasoning_head") or "")).lower()
                              for r in good)
            hit = [c for c in img_info["expected"] if c in joined]
            rec["content_check"] = {
                "expected_colors": img_info["expected"], "found": hit,
                "pass": len(hit) == len(img_info["expected"]),
                "answers": [r.get("answer") for r in good],
                "reasoning_heads": [r.get("reasoning_head") for r in good],
            }
            print("\n[核对] 期望 %s / 命中 %s  -> %s"
                  % (img_info["expected"], hit,
                     "PASS" if rec["content_check"]["pass"] else "FAIL"))
            rec["status"] = "active" if good else "probe_failed"
        kill_tree(proc)

    rec["log_scan"] = scan_log(log)
    # 版本取证：格式与 xpu_bench.py 的 get_version() 对齐。
    # ⚠️ 本脚本默认不开 -v，而**不开 -v 时服务端不打印版本横幅**（实测 verbosity 3 下
    # `common_params_print_info` 那行不出现）→ 日志里取不到，只能直接问二进制。
    _ver = probe_version(srv, env)
    if _ver:
        rec["env"]["engine_version"] = _ver
        rec["env"]["engine_version_source"] = "llama-server --version"
    _b = rec["log_scan"].get("engine_build")
    if _b:
        rec["env"]["engine_build"] = _b[0]
        rec["env"]["engine_commit"] = _b[1]
        rec["env"]["compiler"] = _b[2]
        rec["env"]["build_evidence"] = "server log banner"
    out = outdir / ("%s_%s.json" % (rec["date"], a.tag))
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n-> %s" % out)
    for ln in rec["log_scan"].get("key_lines", [])[-15:]:
        print("   | " + ln[:150])
    return 0


if __name__ == "__main__":
    sys.exit(main())
