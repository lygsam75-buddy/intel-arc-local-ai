#!/usr/bin/env python
"""由 docs/comfyui-h3.md §一（四卡 × 分辨率矩阵）+ 四张单卡页的时长上限
直出 README 用的「主流分辨率 · 一张表」markdown（中英）。

README 只放主流分辨率（480p / 720p / 1080p）+ 「能出多长」行；
576p / 648p / 864p / 1440p 全档与逐档单步留在 docs/comfyui-h3.md，README 指路。
端到端转分钟（1 位小数）；B50 列是 10-17 批另一栈冷启首条，格内标 *，脚注说明与
480p 拆解表（10-16 批 4 轮均值）不同栈。数字取不到就报错。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
H3 = ROOT / "docs" / "comfyui-h3.md"
CARDS = ROOT / "docs" / "cards"
B60_LADDER = ROOT / "bench" / "data" / "2026-10-26_b60-h3-duration-ladder.json"

RES_MAIN = ["864×480", "1280×720", "1920×1088"]
CARDS4 = ["B50 16G", "B60 24G", "B65 32G", "B70 32G"]
# comfyui-h3.md §一 的列序是 B70 | B65 | B60 | B50
COL_ORDER = ["B70 32G", "B65 32G", "B60 24G", "B50 16G"]


def parse_matrix():
    """comfyui-h3.md §一 → {(res, card): e2e_sec}。"""
    t = H3.read_text(encoding="utf-8").replace("\r\n", "\n")
    sec = t.split("## 一、四张卡 × 六个分辨率")[1].split("## 二、")[0]
    out = {}
    for ln in sec.splitlines():
        if not ln.startswith("|") or "×" not in ln:
            continue
        c = [x.strip() for x in ln.split("|")[1:-1]]
        if c[0] not in RES_MAIN:
            continue
        for card, cell in zip(COL_ORDER, c[2:]):
            if "未测" in cell:
                continue
            m = re.search(r"\*{0,2}([\d,]+\.\d+)\s*s", cell)
            if m:
                out[(c[0], card)] = float(m.group(1).replace(",", ""))
    for res in RES_MAIN:
        for card in CARDS4:
            if card == "B70 32G" and res == "1152×648":
                continue
            assert (res, card) in out, (res, card)
    assert abs(out[("864×480", "B50 16G")] - 283.82) < 0.05, out
    assert abs(out[("1920×1088", "B70 32G")] - 841.55) < 0.05, out
    assert abs(out[("1280×720", "B60 24G")] - 427.31) < 0.05, out
    return out


def parse_ceilings():
    """四张单卡页 / JSON 的时长上限 → {card: cell_str}。"""
    out = {}

    # B65：整页「时长上限」句
    t65 = (CARDS / "B65-README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    m = re.search(r"时长上限：480p ≤ (\d+) 秒 / 720p ≤ (\d+) 秒 / 1080p ≤ (\d+) 秒 / 1440p ≤ (\d+) 秒", t65)
    assert m and tuple(map(int, m.groups())) == (50, 24, 10, 5), m
    out["B65 32G"] = "480p ≤ 50 s / 720p ≤ 24 s / 1080p ≤ 10 s / 1440p ≤ 5 s"

    # B70：整页「上限」句
    t70 = (CARDS / "B70-README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    m = re.search(r"上限：480p ≤ (\d+) 秒 · 720p ≤ (\d+) 秒", t70)
    assert m and tuple(map(int, m.groups())) == (50, 24), m
    out["B70 32G"] = "480p ≤ 50 s / 720p ≤ 24 s"

    # B60：duration-ladder JSON 的通过档最大值 + failure 判死
    d = json.load(open(B60_LADDER, encoding="utf-8"))
    mx = {}
    for row in d.get("ladder") or []:
        res = row["resolution"].replace("x", "×")
        secs = int(re.match(r"(\d+)", row["duration"]).group(1))
        mx[res] = max(mx.get(res, 0), secs)
    assert mx == {"864×480": 20, "1280×720": 15, "1920×1088": 5}, mx
    fail = d.get("failure", {})
    assert "1920×1088 · 10 秒" in fail.get("case", ""), fail
    assert "1080p 上限是 5 秒" in fail.get("reading", ""), fail
    out["B60 24G"] = "480p ≤ 20 s / 720p ≤ 15 s / 1080p ≤ 5 s"

    # B50：时长表最大值 + 「1280×720 只能 5 秒」判死句
    t50 = (CARDS / "B50-README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    sec = t50.split("时长能拉多长")[1].split("**要长片**")[0]
    rows = re.findall(r"^\| (\d+) 秒 \|", sec, re.M)
    assert rows and max(map(int, rows)) == 20, rows
    assert "1280×720 只能 5 秒" in t50, "B50 720p 上限句"
    out["B50 16G"] = "480p ≤ 20 s / 720p ≤ 5 s"
    return out


def render(matrix, ceilings, lang):
    if lang == "zh":
        head = ("| 一条 5 秒片要等多久（端到端 · 6 步 · 124 帧） | "
                + " | ".join(CARDS4) + " |")
        ceil_lab = "**能出多长**（实测）"
        foot = ("\\* B50 为 **10-17 批另一栈冷启首条**，与 480p 拆解表（10-16 批 4 轮均值 6.7 分）不同栈，别相减；"
                "B60 / B65 / B70 为稳态。576p / 648p / 864p 中间档、1440p 全档与逐档单步见 "
                "[`docs/comfyui-h3.md`](docs/comfyui-h3.md)；时长阶梯逐档见各单卡页 §6。")
    else:
        head = ("| Wait per 5 s clip (end to end · 6 steps · 124 frames) | "
                + " | ".join(CARDS4) + " |")
        ceil_lab = "**Longest clip tested**"
        foot = ("\\* B50 figures are cold first clips from the 10-17 batch on a different stack — "
                "not side-by-side with the 480p breakdown table (10-16 batch, 4-run mean, 6.7 min); "
                "B60 / B65 / B70 are steady state. Full six-tier ladder and per-step numbers in "
                "[`docs/comfyui-h3.md`](docs/comfyui-h3.en.md); duration ladders per card sheet §6.")
    lines = [head, "| --- | " + " | ".join("---:" for _ in CARDS4) + " |"]
    for res in RES_MAIN:
        cells = []
        for card in CARDS4:
            sec = matrix.get((res, card))
            if sec is None:
                cells.append("—")
                continue
            mins = round(sec / 60, 1)
            star = "\\*" if card.startswith("B50") else ""
            bold = "**" if card.startswith("B70") else ""
            cells.append(f"{bold}{mins} 分{bold}{star}" if lang == "zh"
                         else f"{bold}{mins} min{bold}{star}")
        lines.append("| " + res + " | " + " | ".join(cells) + " |")
    lines.append("| " + ceil_lab + " | "
                 + " | ".join(ceilings[c] for c in CARDS4) + " |")
    lines.append("")
    lines.append(foot)
    return "\n".join(lines)


def main():
    matrix = parse_matrix()
    ceilings = parse_ceilings()
    for lang in ("zh", "en"):
        print("=" * 24, lang)
        print(render(matrix, ceilings, lang))
        print()


if __name__ == "__main__":
    main()
