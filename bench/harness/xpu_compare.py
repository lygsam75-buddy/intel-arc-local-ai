#!/usr/bin/env python3
"""把多份 arc-xpu-bench/1 JSON 并排成 Markdown 对照表。

用法:
  python xpu_compare.py ../data/*.json
  python xpu_compare.py ../data/*.json --group backend     # 按后端分组
  python xpu_compare.py ../data/*.json --out 对照表.md

规则:
  - source 不同的记录不会混在一张表里（本机实测 / 官方 / 社区分开列）
  - 同一 tag 多条记录会取最新日期的
  - 缺字段显示 '-'，绝不猜
"""

import argparse
import glob
import json
import sys
from collections import OrderedDict


def load(paths):
    recs = []
    for pat in paths:
        for p in sorted(glob.glob(pat)):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    r = json.load(f)
            except Exception as e:
                print("[WARN] 跳过 %s: %s" % (p, e), file=sys.stderr)
                continue
            if r.get("schema") != "arc-xpu-bench/1":
                print("[WARN] %s 不是 arc-xpu-bench/1，跳过" % p, file=sys.stderr)
                continue
            r["_path"] = p
            recs.append(r)
    # 同 tag 取最新日期
    by_tag = OrderedDict()
    for r in recs:
        tag = r.get("tag") or r["_path"]
        prev = by_tag.get(tag)
        if prev is None or (r.get("date", "") > prev.get("date", "")):
            by_tag[tag] = r
    return list(by_tag.values())


def cell(v, dash="-"):
    if v is None or v == "":
        return dash
    return str(v)


def table(rows, cols):
    out = []
    out.append("| " + " | ".join(c[0] for c in cols) + " |")
    out.append("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        out.append("| " + " | ".join(cell(c[1](r)) for c in cols) + " |")
    return "\n".join(out)


COLS = [
    ("日期", lambda r: r.get("date")),
    ("显卡", lambda r: (r.get("env") or {}).get("gpu")),
    ("显存GiB", lambda r: (r.get("env") or {}).get("vram_visible_gib")),
    ("后端", lambda r: (r.get("env") or {}).get("backend")),
    ("模型", lambda r: (r.get("model") or {}).get("name")),
    ("量化", lambda r: (r.get("model") or {}).get("quant")),
    ("体积GiB", lambda r: (r.get("model") or {}).get("size_gib")),
    ("预填充 tok/s", lambda r: (r.get("summary") or {}).get("prompt_tok_s")),
    ("解码 tok/s", lambda r: (r.get("summary") or {}).get("decode_tok_s")),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="JSON 路径或 glob")
    ap.add_argument("--out", default="", help="输出 Markdown 文件")
    ap.add_argument("--group", default="", choices=["", "backend", "gpu", "model"],
                    help="按某字段分组出多张表")
    a = ap.parse_args()

    recs = load(a.paths)
    if not recs:
        print("没有可用的记录。")
        return

    parts = []
    for src, title in (("local", "本机实测"), ("official", "官方数据"), ("community", "社区报告")):
        sub = [r for r in recs if r.get("source", "local") == src]
        if not sub:
            continue
        parts.append("### %s\n" % title)
        if a.group:
            keys = sorted({(r.get("env") or {}).get(a.group)
                           or (r.get("model") or {}).get(a.group) or "-" for r in sub})
            for k in keys:
                g = [r for r in sub
                     if ((r.get("env") or {}).get(a.group)
                         or (r.get("model") or {}).get(a.group) or "-") == k]
                parts.append("**%s**\n" % k)
                parts.append(table(g, COLS))
                parts.append("")
        else:
            parts.append(table(sub, COLS))
            parts.append("")

    md = "\n".join(parts).rstrip() + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
        print("[OK] 写入 %s（%d 条记录）" % (a.out, len(recs)))
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
