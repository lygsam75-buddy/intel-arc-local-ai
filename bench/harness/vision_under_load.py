# -*- coding: utf-8 -*-
"""vision_under_load.py — 多模态问答能不能和别的重负载**同时**跑。

回答的对客问题：一张卡在出视频，另一张卡能不能同时「看图问答」？
本脚本**只发请求、不负责起服务**：server 由调用方起好（通常在另一张卡），
本脚本在指定时机打 N 轮，把每轮墙钟、prefill / decode 速率、回答内容落盘。

两个必须守住的点：

1. **关掉 prompt 缓存**（`cache_prompt: false`）。llama.cpp 默认会复用上一次的
   prompt 前缀；同一张图连打三次，第 2、3 次会直接命中缓存，墙钟 0.1 s、
   `predicted_per_second` 飙到 100+ —— 那是**缓存**，不是这张卡解得动。
2. **核对回答内容**。视觉塔没加载成功时，模型照样返回流畅、自信、**纯属编造**的描述。
   测试图沿用 `vision_probe.py` 的程序生成图（白底 + 红方块 / 绿圆 / 蓝方块），
   正确答案唯一：**3 个形状，从左到右依次是红、绿、蓝**。

用法：
    python vision_under_load.py --port 8099 --rounds 3 --tag a4_solo \
        --out ../_out/a4_solo.jsonl
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vision_probe import make_test_png, post  # noqa: E402

PROMPT = "这张图里有几个形状？从左到右依次是什么颜色？只答数量与颜色，不要解释。"


def ask(port, image_path, n_predict, timeout, api_key="", no_think=False):
    """自己发请求（不走 vision_probe.probe_image），因为要多一个 cache_prompt=false。"""
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    payload = {
        "model": "local",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        ]}],
        "max_tokens": n_predict,
        "temperature": 0,
        "stream": False,
        "cache_prompt": False,          # ← 关键：同一张图每轮都真跑一遍
    }
    if no_think:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    body, wall = post("http://127.0.0.1:%d/v1/chat/completions" % port,
                      payload, timeout, api_key)
    choice = (body.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    timings = body.get("timings") or {}
    return {"wall_s": round(wall, 2),
            "answer": (msg.get("content") or "").strip(),
            "reasoning_len": len((msg.get("reasoning_content") or "").strip()),
            "finish_reason": choice.get("finish_reason"),
            "prompt_n": timings.get("prompt_n"),
            "predicted_n": timings.get("predicted_n"),
            "prefill_tps": timings.get("prompt_per_second"),
            "decode_tps": timings.get("predicted_per_second"),
            "cache_n": timings.get("cache_n")}


def answer_ok(text):
    """答案唯一：数量 3，且红 / 绿 / 蓝都在。答错或含糊 = 视觉塔没真解码。"""
    t = (text or "").replace(" ", "")
    return ("3" in t or "三" in t) and "红" in t and "绿" in t and "蓝" in t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--n-predict", type=int, default=96)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", required=True, help="jsonl 落盘路径")
    ap.add_argument("--image", default="", help="自定义测试图；不给就用程序生成的")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--no-think", action="store_true")
    a = ap.parse_args()

    img = a.image
    if not img:
        img = os.path.join(os.path.dirname(os.path.abspath(a.out)) or ".",
                           "_vision_test.png")
        if not os.path.exists(img):
            make_test_png(img)
    print("[vision] 测试图 %s" % img, flush=True)

    rows = []
    for i in range(a.rounds):
        t0 = time.time()
        try:
            r = ask(a.port, img, a.n_predict, a.timeout,
                    api_key=a.api_key, no_think=a.no_think)
        except Exception as e:                                   # 服务被打挂也要留痕
            rows.append({"tag": a.tag, "i": i, "ok": False,
                         "error": "%s: %s" % (type(e).__name__, e),
                         "wall_s": round(time.time() - t0, 2)})
            print("[vision] 第 %d 轮失败：%s" % (i, e), flush=True)
            continue
        r.update({"tag": a.tag, "i": i, "ok": bool(answer_ok(r["answer"]))})
        rows.append(r)
        print("[vision] 第 %d 轮 %6.2f s · prefill %7s · decode %7s tok/s · cache_n=%-4s · 答案%s"
              % (i, r["wall_s"], _fmt(r.get("prefill_tps")), _fmt(r.get("decode_tps")),
                 r.get("cache_n"), "✅" if r["ok"] else "❌ %s" % r["answer"][:60]), flush=True)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ok = [r for r in rows if r.get("ok")]
    dec = [r["decode_tps"] for r in ok if r.get("decode_tps")]
    pre = [r["prefill_tps"] for r in ok if r.get("prefill_tps")]
    wall = [r["wall_s"] for r in ok]
    print("[vision] %s：%d/%d 轮答对 · 墙钟均值 %s s · prefill %s tok/s · decode %s tok/s"
          % (a.tag, len(ok), len(rows), _mean(wall), _mean(pre), _mean(dec)), flush=True)
    return 0 if ok else 1


def _mean(xs):
    return "%.2f" % (sum(xs) / len(xs)) if xs else "—"


def _fmt(x):
    return "%.1f" % x if isinstance(x, (int, float)) else "—"


if __name__ == "__main__":
    sys.exit(main())
