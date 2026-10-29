#!/usr/bin/env python3
r"""对照同一个 -ncmoe 扫描在不同 PCIe 槽位下的结果，量化槽位损失。

为什么需要这个：客户买第二张卡时，第二槽通常是芯片组挂的 x4（带宽只有主槽的 1/4）。
「插第二槽会损失多少」是要能用数字回答的问题，不是感觉。

用法:
  python compare_slots.py --tag-a b50-16g-ncmoe-scan-pcie4x4 \
                          --tag-b b50-16g-ncmoe-scan-pcie5x8 \
                          --label-a "从槽 x4" --label-b "主槽 x8"

也可以一次喂多组 tag（都按 ncmoe 配对）:
  python compare_slots.py --tag-a A1,A2 --tag-b B1,B2

输出：Markdown 对照表 + 损失百分比。
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"


def load(tags):
    """按 tag 前缀收集 {ncmoe: decode}。后出现的覆盖先出现的（同 ncmoe 取最新）。"""
    out = {}
    for tag in tags:
        pat = str(DATA / ("*%s*.json" % tag))
        for f in sorted(glob.glob(pat)):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            if "ncmoe" not in d:
                continue
            dec = (d.get("summary") or {}).get("decode_tok_s")
            if dec is None:
                continue
            out[int(d["ncmoe"])] = {
                "decode": float(dec),
                "prompt": (d.get("summary") or {}).get("prompt_tok_s"),
                "file": os.path.basename(f),
            }
    return out


def pct(new, old):
    if old in (0, None):
        return None
    return round((new - old) / old * 100, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag-a", required=True, help="基线组 tag（逗号分隔可多组）")
    ap.add_argument("--tag-b", required=True, help="对照组 tag（逗号分隔可多组）")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--out", default="", help="写入 Markdown 文件（可选）")
    a = ap.parse_args()

    A = load([t.strip() for t in a.tag_a.split(",")])
    B = load([t.strip() for t in a.tag_b.split(",")])
    if not A or not B:
        print("[ERR] 没找到数据。A=%d 条 B=%d 条" % (len(A), len(B)))
        return 1

    keys = sorted(set(A) | set(B))
    lines = []
    lines.append("| `-ncmoe` | %s (tok/s) | %s (tok/s) | 差异 |" %
                 (a.label_a, a.label_b))
    lines.append("|---:|---:|---:|---:|")
    for k in keys:
        va = A.get(k)
        vb = B.get(k)
        da = va["decode"] if va else None
        db = vb["decode"] if vb else None
        if da is not None and db is not None:
            p = pct(db, da)
            mark = "**" if abs(p or 0) >= 50 else ""
            lines.append("| %d | %s | %s | %s%+g%%%s |" %
                         (k, da, db, mark, p, mark))
        else:
            lines.append("| %d | %s | %s | — |" % (k, da or "—", db or "—"))

    best_a = max(A.items(), key=lambda kv: kv[1]["decode"])
    best_b = max(B.items(), key=lambda kv: kv[1]["decode"])
    lines.append("")
    lines.append("- 最优切分点：%s = `-ncmoe %d`（%.2f tok/s），"
                 "%s = `-ncmoe %d`（%.2f tok/s）"
                 % (a.label_a, best_a[0], best_a[1]["decode"],
                    a.label_b, best_b[0], best_b[1]["decode"]))
    if best_a[1]["decode"]:
        p = pct(best_b[1]["decode"], best_a[1]["decode"])
        lines.append("- 最优点上的槽位差异：**%+g%%**" % p)

    txt = "\n".join(lines)
    print(txt)
    if a.out:
        Path(a.out).write_text(txt + "\n", encoding="utf-8")
        print("\n[OK] 写入 %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
