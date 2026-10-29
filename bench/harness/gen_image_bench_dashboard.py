#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""总测试项汇总动态图：docs/comfyui-image.md §3.0 主表的交互式表达。

数据与 §3.0 主表逐格对账（display 字符串就是表里那串数字），并回读
bench/data/*.json 做来源校验（文件存在 + resident 轮落在显示区间内），
对不上就 WARN，缺文件就报错。输出 docs/assets/image-bench-dashboard.html
（零依赖纯 HTML/JS，可离线打开；中/英切换）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data"
OUT = ROOT / "docs" / "assets" / "image-bench-dashboard.html"

CARDS = ["B50", "B60", "B65", "B70"]
CARD_COLOR = {"B50": "#B9C6D8", "B60": "#6E97C6", "B65": "#3F7CC0", "B70": "#2F6FBA"}
INK, MUTED, GRID = "#2C2C2A", "#5F5E5A", "#E5E4E0"

# cell = (display_zh, display_en, bar_sec, source_file, note_key)
# bar_sec 用作柱高；display 与 §3.0 主表完全一致。
# note_key 见 NOTES；source_file 为 None 表示未测/失败格。
K = "krea"
IMG_ROWS = [
    dict(zh="Qwen-Image 2.1 · 1280×720 · 25 步 · int8", en="Qwen-Image 2.1 · 1280×720 · 25 steps · int8",
         cells={
             "B50": dict(zh="51.75", en="51.75", bar=51.75, src="2026-10-16_b50-16g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json", note="a"),
             "B60": dict(zh="17.33 至 18.80", en="17.33 to 18.80", bar=18.06, src="2026-10-20_b60-24g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json"),
             "B65": dict(zh="16.13 至 16.19", en="16.13 to 16.19", bar=16.16, src="2026-10-21_b65-32g_qwen-image-2.1-int8_convrot-int8fix-comfyui.json"),
             "B70": dict(zh="10.61 至 10.64", en="10.61 to 10.64", bar=10.62, src="2026-10-17_b70-32g_qwen-image-2.1-int8_convrot-b70same-comfyui.json"),
         }),
    dict(zh="Qwen-Image 2.1 · 1280×720 · 25 步 · bf16", en="Qwen-Image 2.1 · 1280×720 · 25 steps · bf16",
         cells={
             "B50": dict(zh="87.34", en="87.34", bar=87.34, src="2026-10-16_b50-16g_qwen-image-2.1-bf16-comfyui.json"),
             "B60": dict(zh="未测", en="not measured", bar=None, src=None, note="i"),
             "B65": dict(zh="22.91", en="22.91", bar=22.91, src="2026-10-21_b65-32g_qwen-image-2.1-bf16-b65q21b16-comfyui.json"),
             "B70": dict(zh="13.79 至 13.85", en="13.79 to 13.85", bar=13.82, src="2026-10-15_b70-32g_q21-bf16-039t212-comfyui.json"),
         }),
    dict(zh="Qwen-Image 2.1 · 1536×864 · 25 步 · int8", en="Qwen-Image 2.1 · 1536×864 · 25 steps · int8",
         cells={
             "B50": dict(zh="64.56", en="64.56", bar=64.56, src="2026-10-16_b50-16g_qwen-image-2.1-int8_convrot-r1536-comfyui.json"),
             "B60": dict(zh="42.02", en="42.02", bar=42.02, src="2026-10-28_b60-24g_qwen-image-2.1-int8_convrot-b60r1536-comfyui.json"),
         }),
    dict(zh="Qwen-Image 2.1 · 2048×2048 · 25 步 · int8", en="Qwen-Image 2.1 · 2048×2048 · 25 steps · int8",
         cells={
             "B50": dict(zh="246.12", en="246.12", bar=246.12, src="2026-10-17_b50-16g_qwen-image-2.1-int8_convrot-r2048full-comfyui.json"),
             "B60": dict(zh="126.76", en="126.76", bar=126.76, src="2026-10-28_b60-24g_qwen-image-2.1-int8_convrot-b60r2048-comfyui.json"),
             "B65": dict(zh="117.53", en="117.53", bar=117.53, src="2026-10-21_b65-32g_qwen-image-2.1-int8_convrot-b65q21r2k-comfyui.json"),
         }),
    dict(zh="Qwen-Image 2.1 · 3072×3072 · 25 步 · int8", en="Qwen-Image 2.1 · 3072×3072 · 25 steps · int8",
         cells={
             "B50": dict(zh="863.10", en="863.10", bar=863.10, src="2026-10-22_b50-16g_qwen-image-2.1-int8_convrot-b50img3072-comfyui.json"),
             "B60": dict(zh="494.52", en="494.52", bar=494.52, src="2026-10-28_b60-24g_qwen-image-2.1-int8_convrot-b60img3072-comfyui.json"),
             "B65": dict(zh="456.15", en="456.15", bar=456.15, src="2026-10-22_b65-32g_qwen-image-2.1-int8_convrot-b65img3072-comfyui.json"),
         }),
    dict(zh="Qwen-Image 2.1 · 4096×4096 · 25 步 · int8", en="Qwen-Image 2.1 · 4096×4096 · 25 steps · int8",
         cells={
             "B60": dict(zh="1426.55", en="1426.55", bar=1426.55, src="2026-10-28_b60-24g_qwen-image-2.1-int8_convrot-b60img4096-comfyui.json"),
             "B65": dict(zh="1306.66", en="1306.66", bar=1306.66, src="2026-10-22_b65-32g_qwen-image-2.1-int8_convrot-b65img4096-comfyui.json"),
         }),
    dict(zh="Qwen-Image 2.1 · 5120×5120 · 25 步 · int8", en="Qwen-Image 2.1 · 5120×5120 · 25 steps · int8",
         cells={
             "B65": dict(zh="3021.75", en="3021.75", bar=3021.75, src="2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-b65img5120-comfyui.json", note="k"),
         }),
    dict(zh="Krea-2 Turbo · 1024×1024 · 8 步 · int8", en="Krea-2 Turbo · 1024×1024 · 8 steps · int8",
         cells={
             "B50": dict(zh="57.89", en="57.89", bar=57.89, src="2026-10-16_b50-16g_krea-2-turbo-int8_convrot-int8fix-comfyui.json", note="c"),
         }),
    dict(zh="Krea-2 Turbo · 1280×720 · 8 步 · int8", en="Krea-2 Turbo · 1280×720 · 8 steps · int8",
         cells={
             "B60": dict(zh="62.30 至 66.00", en="62.30 to 66.00", bar=64.15, src="2026-10-20_b60-24g_krea-2-turbo-int8_convrot-b60k2-comfyui.json", note="d"),
             "B65": dict(zh="8.73 至 8.74", en="8.73 to 8.74", bar=8.73, src="2026-10-21_b65-32g_krea-2-turbo-int8_convrot-b65k2-comfyui.json"),
             "B70": dict(zh="6.03 至 6.07", en="6.03 to 6.07", bar=6.04, src="2026-10-17_b70-32g_krea-2-turbo-int8_convrot-b70k2int8fix-comfyui.json"),
         }),
    dict(zh="Krea-2 Turbo · 1280×768 · 8 步 · int8", en="Krea-2 Turbo · 1280×768 · 8 steps · int8",
         cells={"B70": dict(zh="6.54", en="6.54", bar=6.54, src="2026-10-17_b70-32g_krea-2-turbo-int8_convrot-b70k2res-comfyui.json")}),
    dict(zh="Krea-2 Turbo · 1536×1024 · 8 步 · int8", en="Krea-2 Turbo · 1536×1024 · 8 steps · int8",
         cells={"B70": dict(zh="11.13", en="11.13", bar=11.13, src="2026-10-17_b70-32g_krea-2-turbo-int8_convrot-b70k2res2-comfyui.json")}),
    dict(zh="Krea-2 Turbo · 1280×720 · bf16", en="Krea-2 Turbo · 1280×720 · bf16",
         cells={
             "B50": dict(zh="❌", en="❌", bar=None, src="2026-10-16_b50-16g_krea-2-turbo-bf16-k2bf16-comfyui.json", note="e"),
             "B60": dict(zh="未测", en="not measured", bar=None, src=None, note="i"),
             "B65": dict(zh="167.37 至 167.56", en="167.37 to 167.56", bar=167.47, src="2026-10-21_b65-32g_krea-2-turbo-bf16-b65k2b16-comfyui.json", note="d"),
             "B70": dict(zh="127.74", en="127.74", bar=127.74, src="2026-10-19_b70-32g_krea-2-turbo-bf16-b70pw-comfyui.json", note="d"),
         }),
]

MUS_ROWS = [
    dict(zh="Music 3 · int8 DiT + int8 TE", en="Music 3 · int8 DiT + int8 TE",
         cells={
             "B50": dict(zh="216.82", en="216.82", bar=216.82, src="2026-10-16_b50-16g_minimax-music-3-int8_convrot-m3i8-comfyui.json"),
             "B60": dict(zh="144.89 至 145.84", en="144.89 to 145.84", bar=145.37, src="2026-10-20_b60-24g_minimax-music-3-int8_convrot-b60m3-comfyui.json"),
             "B65": dict(zh="164.56 / 198.31", en="164.56 / 198.31", bar=164.56, src="2026-10-21_b65-32g_minimax-music-3-int8_convrot-b65m3i8te8-comfyui.json", note="f"),
             "B70": dict(zh="61.35 至 66.69", en="61.35 to 66.69", bar=64.02, src="2026-10-17_b70-32g_minimax-music-3-int8_convrot-b70m3teint8b-comfyui.json"),
         }),
    dict(zh="Music 3 · int8 DiT + bf16 TE", en="Music 3 · int8 DiT + bf16 TE",
         cells={
             "B50": dict(zh="218.21", en="218.21", bar=218.21, src="2026-10-17_b50-16g_minimax-music-3-int8_convrot-tebf16-comfyui.json"),
             "B65": dict(zh="236.51 / 301.14", en="236.51 / 301.14", bar=236.51, src="2026-10-21_b65-32g_minimax-music-3-int8_convrot-b65m3-comfyui.json", note="df"),
             "B70": dict(zh="61.83 至 61.97", en="61.83 to 61.97", bar=61.92, src="2026-10-17_b70-32g_minimax-music-3-int8_convrot-b70m3tebf16b-comfyui.json"),
         }),
    dict(zh="Music 3 · int8 DiT + bf16 TE · reserve 2", en="Music 3 · int8 DiT + bf16 TE · reserve 2",
         cells={"B65": dict(zh="180.21 至 180.85", en="180.21 to 180.85", bar=180.53, src="2026-10-21_b65-32g_minimax-music-3-int8_convrot-b65m3res2-comfyui.json")}),
    dict(zh="Music 3 · fp16 DiT + int8 TE", en="Music 3 · fp16 DiT + int8 TE",
         cells={
             "B50": dict(zh="282.29", en="282.29", bar=282.29, src="2026-10-16_b50-16g_minimax-music-3-fp16-m3f16-comfyui.json"),
             "B70": dict(zh="78.70 至 78.76", en="78.70 to 78.76", bar=78.73, src="2026-10-17_b70-32g_minimax-music-3-fp16-b70m3fp16teint8-comfyui.json"),
         }),
    dict(zh="Music 3 · fp16 DiT + bf16 TE", en="Music 3 · fp16 DiT + bf16 TE",
         cells={
             "B65": dict(zh="223.39 至 227.94", en="223.39 to 227.94", bar=225.66, src="2026-10-21_b65-32g_minimax-music-3-fp16-b65m3f16-comfyui.json"),
             "B70": dict(zh="81.34", en="81.34", bar=81.34, src="2026-10-17_b70-32g_minimax-music-3-fp16-b70m3fp16tebf16-comfyui.json", note="g"),
         }),
]

NOTES = {
    "zh": {
        "a": "B50 每轮重载 TE 3,837.8 MB",
        "b": "旧栈读数（torch213 · 无 int8fix；补丁后同卡 int8 为 10.63 s）",
        "c": "1024×1024（16 GB 交付形态），与其余 Krea-2 行不同分辨率",
        "d": "每轮重装（B60 Krea-2：DiT 12.6 GB；Krea-2 bf16 与 Music reserve 4：loads=3）",
        "df": "每轮重装（loads=3）＋两轮未收敛，取快者",
        "e": "采样后设备失联（UR_RESULT_ERROR_DEVICE_LOST）",
        "f": "两轮未收敛，取快者",
        "g": "临界态：跑得通但不稳",
        "i": "B60 在机那批只排了 int8，已拆卡补不了",
        "k": "5120 只跑 3 轮（first + 2×resident），换提示词未跑",
    },
    "en": {
        "a": "B50 reloads the TE every round (3,837.8 MB)",
        "b": "old-stack reading (torch213 · no int8fix; after the patch int8 is 10.63 s on the same card)",
        "c": "1024×1024 (the 16 GB delivery form), a different resolution from the other Krea-2 rows",
        "d": "reloads every round (B60 Krea-2: the 12.6 GB DiT; Krea-2 bf16 and Music reserve 4: loads=3)",
        "df": "reloads every round (loads=3) + two rounds did not converge; the faster one is taken",
        "e": "device lost after sampling (UR_RESULT_ERROR_DEVICE_LOST)",
        "f": "two rounds did not converge; the faster one is taken",
        "g": "borderline: runs but unstable",
        "i": "the B60 in-machine batch only scheduled int8, and the card has been pulled",
        "k": "5120 has only 3 rounds (first + 2×resident); the new-prompt round was not run",
    },
}

T = {
    "zh": dict(
        title="总测试项 · 四卡稳态对比",
        sub="ComfyUI int8fix 栈 · resident 稳态 · 出图为秒/张、出音乐为秒/首（120 s · 30 步）",
        img="出图（稳态 s/张）", mus="出音乐（稳态 s/首）",
        cards="卡型", notes="表注", value="稳态", source="来源批号",
        foot="柱高 = 稳态读数（区间格取中值/快者，与 §3.0 主表同源）；悬停看批号与条件。空白格 = 未测或失败，见表注。"),
    "en": dict(
        title="Master summary · steady state across four cards",
        sub="ComfyUI int8fix stack · resident steady state · s/image for images, s/song for music (120 s · 30 steps)",
        img="Image generation (s/image)", mus="Music generation (s/song)",
        cards="Card", notes="Notes", value="Steady state", source="Source batch",
        foot="Bar height = the steady-state reading (midpoint/fast round for ranges, same source as the §3.0 master table); hover for batch and conditions. Blank cells = not measured or failed, see notes."),
}


def resident_rounds(src):
    d = json.load(open(DATA / src, encoding="utf-8"))
    runs = [r for r in d.get("timing_breakdown", {}).get("runs", [])
            if r.get("matched_sample", {}).get("role") == "resident"]
    return [r["matched_sample"]["server_sec"] for r in runs if r.get("matched_sample", {}).get("server_sec")]


def cross_check(rows, label):
    for row in rows:
        for card, cell in row["cells"].items():
            src = cell.get("src")
            if src is None:
                continue
            if not (DATA / src).exists():
                print(f"ERROR: missing source JSON for [{label}] {row['zh']} / {card}: {src}", file=sys.stderr)
                sys.exit(1)
            bar = cell["bar"]
            if bar is None:
                continue
            rounds = resident_rounds(src)
            if not rounds:
                continue  # 失败格（如设备失联）本身就没有 resident 轮
            # 允许显示字符串的取整误差 + 派生统计（127.74 = b70pw 去首轮三轮均值）
            lo, hi = min(rounds), max(rounds)
            if not (lo * 0.97 - 0.6 <= bar <= hi * 1.03 + 0.6):
                print(f"WARN: [{label}] {row['zh']} / {card}: bar={bar} outside resident rounds {rounds} ({src})", file=sys.stderr)


def row_json(rows):
    out = []
    for row in rows:
        cells = {}
        for card in CARDS:
            c = row["cells"].get(card)
            if not c:
                continue
            cells[card] = dict(v=c.get("bar"), tz=c["zh"], te=c["en"], n=c.get("note"), s=c.get("src"))
        out.append(dict(zh=row["zh"], en=row["en"], cells=cells))
    return out


def main():
    cross_check(IMG_ROWS, "image")
    cross_check(MUS_ROWS, "music")
    data = {
        "img": row_json(IMG_ROWS),
        "mus": row_json(MUS_ROWS),
        "notes": NOTES, "t": T, "cards": CARDS, "colors": CARD_COLOR,
    }
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    html = html.replace("%INK%", INK).replace("%MUTED%", MUTED).replace("%GRID%", GRID).replace("%C70%", CARD_COLOR["B70"])
    OUT.write_text(html.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    print(f"OK {OUT} ({OUT.stat().st_size} bytes)")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>image-bench-dashboard</title>
<style>
  :root { --ink: %INK%; --muted: %MUTED%; --grid: %GRID%; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 28px 24px 40px; background: #FAFAF8; color: var(--ink);
         font-family: "Microsoft YaHei", "Segoe UI", "Noto Sans SC", sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; }
  h1 { font-size: 21px; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 12.5px; margin: 0 0 18px; }
  .toolbar { display: flex; gap: 8px; margin: 0 0 18px; }
  .toolbar button { border: 1px solid var(--grid); background: #fff; color: var(--ink);
    border-radius: 6px; padding: 5px 13px; font-size: 12.5px; cursor: pointer; }
  .toolbar button.on { background: %C70%; border-color: %C70%; color: #fff; }
  .panel { background: #fff; border: 1px solid var(--grid); border-radius: 10px;
           padding: 16px 18px 10px; margin: 0 0 18px; }
  .panel h2 { font-size: 14px; margin: 0 0 12px; }
  .row { display: grid; grid-template-columns: 300px 1fr; gap: 10px; align-items: center;
         padding: 5px 0; border-top: 1px dashed var(--grid); }
  .row:first-of-type { border-top: 0; }
  .lbl { font-size: 11.5px; line-height: 1.35; color: var(--ink); }
  .bars { position: relative; height: 56px; }
  .bar { position: absolute; height: 9px; border-radius: 2px; min-width: 1px; }
  .val { position: absolute; font-size: 9.5px; color: var(--muted); white-space: nowrap; }
  .na { position: absolute; font-size: 9.5px; color: var(--muted); cursor: default; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; margin: 4px 0 14px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; opacity: 1; }
  .chip.off { opacity: .3; }
  .sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
  .notes { font-size: 11px; color: var(--muted); line-height: 1.7; }
  .foot { font-size: 11px; color: var(--muted); margin: 8px 2px 0; line-height: 1.6; }
  #tip { position: fixed; pointer-events: none; background: %INK%; color: #fff; font-size: 11px;
         padding: 7px 10px; border-radius: 6px; max-width: 340px; line-height: 1.55; display: none; z-index: 9; }
</style>
</head>
<body>
<div class="wrap">
  <h1 id="title"></h1>
  <p class="sub" id="sub"></p>
  <div class="toolbar">
    <button id="b-zh" class="on">中文</button>
    <button id="b-en">English</button>
  </div>
  <div class="legend" id="legend"></div>
  <div class="panel"><h2 id="h-img"></h2><div id="p-img"></div></div>
  <div class="panel"><h2 id="h-mus"></h2><div id="p-mus"></div></div>
  <div class="notes" id="notes"></div>
  <p class="foot" id="foot"></p>
</div>
<div id="tip"></div>
<script>
const DATA = __DATA__;
let lang = "zh";
const off = {};
const tip = document.getElementById("tip");

function fmt(v) { return v == null ? "" : (Math.round(v * 100) / 100).toFixed(2).replace(/\\.00$/, ""); }

function render() {
  const t = DATA.t[lang];
  document.getElementById("title").textContent = t.title;
  document.getElementById("sub").textContent = t.sub;
  document.getElementById("h-img").textContent = t.img;
  document.getElementById("h-mus").textContent = t.mus;
  document.getElementById("foot").textContent = t.foot;
  document.getElementById("b-zh").className = lang === "zh" ? "on" : "";
  document.getElementById("b-en").className = lang === "en" ? "on" : "";

  const leg = document.getElementById("legend");
  leg.innerHTML = "";
  DATA.cards.forEach(c => {
    const el = document.createElement("span");
    el.className = "chip" + (off[c] ? " off" : "");
    el.innerHTML = '<span class="sw" style="background:' + DATA.colors[c] + '"></span>' + c;
    el.onclick = () => { off[c] = !off[c]; render(); };
    leg.appendChild(el);
  });

  const max = {};
  ["img", "mus"].forEach(k => {
    max[k] = 0;
    DATA[k].forEach(r => DATA.cards.forEach(c => {
      const cell = r.cells[c];
      if (cell && cell.v != null && !off[c]) max[k] = Math.max(max[k], cell.v);
    }));
    max[k] = (max[k] || 1) * 1.02;
  });

  ["img", "mus"].forEach(k => {
    const host = document.getElementById("p-" + k);
    host.innerHTML = "";
    DATA[k].forEach(r => {
      const row = document.createElement("div");
      row.className = "row";
      const lbl = document.createElement("div");
      lbl.className = "lbl";
      lbl.textContent = lang === "zh" ? r.zh : r.en;
      const bars = document.createElement("div");
      bars.className = "bars";
      let slot = 0;
      DATA.cards.forEach(c => {
        const cell = r.cells[c];
        if (!cell || off[c]) return;
        const y = 2 + slot * 13;
        if (cell.v == null) {
          const na = document.createElement("div");
          na.className = "na";
          na.style.top = (y - 2) + "px";
          na.style.left = "2px";
          na.textContent = c + " " + (lang === "zh" ? cell.tz : cell.te) + (cell.n ? " " + cell.n : "");
          na.onmousemove = ev => {
            tip.style.display = "block";
            tip.style.left = Math.min(ev.clientX + 14, window.innerWidth - 360) + "px";
            tip.style.top = (ev.clientY + 12) + "px";
            tip.innerHTML = "<b>" + c + " · " + (lang === "zh" ? cell.tz : cell.te) + "</b>" +
              (cell.n ? "<br>" + DATA.notes[lang][cell.n] : "") +
              (cell.s ? "<br>" + t.source + ": " + cell.s.replace("-comfyui.json", "") : "");
          };
          na.onmouseleave = () => tip.style.display = "none";
          bars.appendChild(na);
        } else {
          const w = Math.max(2, (cell.v / max[k]) * 100);
          const b = document.createElement("div");
          b.className = "bar";
          b.style.cssText = "top:" + y + "px;left:0;width:" + w + "%;background:" + DATA.colors[c];
          const v = document.createElement("div");
          v.className = "val";
          v.style.cssText = "top:" + (y - 2) + "px;left:calc(" + w + "% + 5px)";
          v.textContent = c + " " + fmt(cell.v) + (cell.n ? " " + cell.n : "");
          b.onmousemove = ev => {
            tip.style.display = "block";
            tip.style.left = Math.min(ev.clientX + 14, window.innerWidth - 360) + "px";
            tip.style.top = (ev.clientY + 12) + "px";
            tip.innerHTML = "<b>" + c + " · " + fmt(cell.v) + " s</b><br>" + (lang === "zh" ? cell.tz : cell.te) +
              (cell.n ? "<br>" + DATA.notes[lang][cell.n] : "") +
              (cell.s ? "<br>" + t.source + ": " + cell.s.replace("-comfyui.json", "") : "");
          };
          b.onmouseleave = () => tip.style.display = "none";
          bars.appendChild(b); bars.appendChild(v);
        }
        slot++;
      });
      row.appendChild(lbl); row.appendChild(bars);
      host.appendChild(row);
    });
  });

  const n = document.getElementById("notes");
  const keys = [...new Set(["img", "mus"].flatMap(kk => DATA[kk].flatMap(r => Object.values(r.cells).map(c => c.n).filter(Boolean))))];
  n.innerHTML = keys.map(kk => "· " + kk + " = " + DATA.notes[lang][kk]).join("<br>");
}
document.getElementById("b-zh").onclick = () => { lang = "zh"; render(); };
document.getElementById("b-en").onclick = () => { lang = "en"; render(); };
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
