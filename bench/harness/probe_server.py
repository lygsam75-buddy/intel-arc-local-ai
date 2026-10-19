#!/usr/bin/env python3
r"""量一个正在运行的 llama-server 的真实吞吐（口径 B：/completion 单次请求）。

为什么需要这个：仓库里的口径 B 数据是 2026-10-06 用临时参数手工打的，
而客户实际面对的是「某个具体 server 进程」。这个脚本量的是**那套配置本身**。

鉴权（2026-10-16 实测，四种方式逐一试过，别猜）：
  server 端 `--api-key local` 时，客户端**能过**的是这两种：

      Authorization: Bearer local      -> 200
      X-Api-Key: local                 -> 200

  **过不了**的三种，全都是 401 Invalid API Key：

      （不带任何凭据）
      Authorization: bearer local      <- 注意 scheme 必须大写 B，小写不行
      body 里放 {"api_key": "local"}    <- 头部才是唯一被读的位置

  这是本轮踩得最贵的一个坑：`--api-key local` 被写进了 server 侧的
  启动参数（--extra-args），却没同步给探针，于是 4 组配置全部 401、
  速度字段全空，而加载日志与显存读数一切正常 —— **看起来像跑通了**。

用法:
  python probe_server.py --port 8080 --api-key local --n-predict 256
  python probe_server.py --port 8080 --chat   # 走 /v1/chat/completions
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def post(url, payload, timeout, api_key=""):
    headers = {"Content-Type": "application/json"}
    if api_key:
        # llama-server 只认 Authorization 头，放在 body 里会被判 Invalid API Key
        headers["Authorization"] = "Bearer %s" % api_key
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8", "replace"))
    return body, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--api-key", default="")
    ap.add_argument("--n-predict", type=int, default=256)
    ap.add_argument("--prompt", default=
                    "用三句话解释 PCIe 带宽对大模型推理的影响。")
    ap.add_argument("--chat", action="store_true", help="走 /v1/chat/completions")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()

    base = "http://%s:%d" % (a.host, a.port)
    if a.chat:
        url = base + "/v1/chat/completions"
        payload = {
            "model": "local",
            "messages": [{"role": "user", "content": a.prompt}],
            "max_tokens": a.n_predict,
            "stream": False,
        }
    else:
        url = base + "/completion"
        payload = {"prompt": a.prompt, "n_predict": a.n_predict, "stream": False}
    if a.api_key:
        payload["api_key"] = a.api_key

    print("[GET ] %s" % url)
    print("[BODY] n_predict=%d chat=%s" % (a.n_predict, a.chat))
    try:
        body, wall = post(url, payload, a.timeout, a.api_key)
    except urllib.error.HTTPError as e:
        print("[ERR] HTTP %d: %s" % (e.code, e.read().decode("utf-8", "replace")[:400]))
        return 1
    except Exception as e:
        print("[ERR] %s" % e)
        return 1

    tim = body.get("timings") or {}
    rec = {
        "schema": "llama-server-probe/1",
        "url": url,
        "n_predict_req": a.n_predict,
        "wall_s": round(wall, 2),
        "timings": tim,
        "tokens_per_second": tim.get("predicted_per_second"),
        "prompt_per_second": tim.get("prompt_per_second"),
        "prompt_n": tim.get("prompt_n"),
        "predicted_n": tim.get("predicted_n"),
        "context_shift": body.get("context_shift"),
        "truncated": body.get("truncated"),
    }
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())