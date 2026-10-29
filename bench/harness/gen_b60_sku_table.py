#!/usr/bin/env python
"""由 bench/data/2026-10-27_b60-tf-vs-bs.json 直接打印 Markdown 对照表（中文/英文）。

只读数据件、只打印到 stdout，不写任何文件——贴进 B60 单卡页时用。
表格禁止手抄，改数据后重跑本脚本即可。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data" / "2026-10-27_b60-tf-vs-bs.json"

HEAD = {
    "zh": "| 档位 | 端到端 TF → BS | 单步 TF → BS | 每片电耗 TF → BS |",
    "en": "| Tier | End-to-end TF → BS | Per-step TF → BS | Energy per clip TF → BS |",
}
ALIGN = "|---|---:|---:|---:|"


def fmt_s(sec):
    m, s = divmod(int(round(sec)), 60)
    return f"{m} 分 {s:02d} 秒" if m else f"{s} 秒"


def fmt_s_en(sec):
    m, s = divmod(int(round(sec)), 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def main():
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    rows = doc["tiers"]
    pend = doc["pending"]
    for lang in ("zh", "en"):
        print(f"\n===== {lang.upper()} =====")
        print(HEAD[lang])
        print(ALIGN)
        for r in rows:
            a, b = r["TF"], r["BS"]
            fs = fmt_s if lang == "zh" else fmt_s_en
            lab = r["label_zh"] if lang == "zh" else r["label_en"]
            d = r["delta_pct"]
            sd = r["sit_delta_pct"]
            wd = r["wh_delta_pct"]
            dstr = f"**+{d:.1f}%**" if d >= 8 else f"+{d:.1f}%"
            sdstr = f"**+{sd:.1f}%**" if sd >= 20 else f"+{sd:.1f}%"
            lo, hi = ("（", "）") if lang == "zh" else (" (", ")")
            if wd is None:
                energy = "—"
            else:
                energy = f"{a['wh']:.1f} → **{b['wh']:.1f}** Wh{lo}{wd:+.1f}%{hi}"
            e2e = f"{a['server_s']:.0f} → **{b['server_s']:.0f}** s{lo}{dstr}{hi}"
            step = f"{a['sit_s']:.1f} → **{b['sit_s']:.1f}** s{lo}{sdstr}{hi}"
            print(f"| {lab} | {e2e} | {step} | {energy} |")
        for p in pend:
            lab = p["label_zh"] if lang == "zh" else p["label_en"]
            print(f"| {lab} | — | — | — | — | — | — | — |")
        print(f"\n（{len(rows)} 档 / 待补 {len(pend)} 档）")


if __name__ == "__main__":
    main()
