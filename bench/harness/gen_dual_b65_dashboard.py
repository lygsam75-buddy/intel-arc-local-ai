# -*- coding: utf-8 -*-
"""从 bench/data 直出 docs/assets/dual-b65-dashboard.html 与 dual-b65-dashboard.en.html。

双语一次生成，数字同源（bench/data/*.json），行尾 CRLF、无尾换行，与仓库其他生成件一致。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA_DIR = os.path.join(REPO, "bench", "data")
OUT = {
    "zh": os.path.join(REPO, "docs", "assets", "dual-b65-dashboard.html"),
    "en": os.path.join(REPO, "docs", "assets", "dual-b65-dashboard.en.html"),
}

CARDS = {"zh": ["单卡 B65", "双卡 2×B65", "一片 B70"],
         "en": ["Single B65", "Dual 2×B65", "One B70"]}
COLORS = {"zh": ["#6E97C6", "#2F6FBA", "#B9C6D8"],
          "en": ["#6E97C6", "#2F6FBA", "#B9C6D8"]}


def load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def sample(rec, mode, idx=0):
    xs = [s for s in rec["samples"] if s.get("mode") == mode and s.get("ok")]
    return xs[idx]


b65_720 = load("2026-10-21_b65-32g_minimax-h3-int8_convrot-b65h3-1280x720-comfyui.json")
b65_1080 = load("2026-10-21_b65-32g_minimax-h3-int8_convrot-b65h3-1920x1088-comfyui.json")
b70_720 = load("2026-10-19_h3_1280x720_b70scan.json")
b70_1080 = load("2026-10-19_h3_1920x1088_b70scan.json")
b70_pw = load("2026-10-19_h3_1280x720_b70pw.json")
dual_d6 = load("2026-10-23_h3_1280x720_duald6.json")

img_solo = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2solo-comfyui.json")
img_c0 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2c0-comfyui.json")
img_c1 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2c1-comfyui.json")
pw_s0 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3s0-comfyui.json")
pw_b0 = load("2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3b0-comfyui.json")

q_solo = load("2026-10-23_b65-32g-q4_0-dual-c1.json")["summary"]
q_conc = load("2026-10-23_b65-32g-q4_0-dual-c1-concurrent.json")["summary"]
b70_q4 = load("2026-10-20_b70-q4-0-sycl-l0.json")["summary"]
q8 = {x["tag"]: x for x in load("2026-10-23_b65-32g-q8_0-dual-split-scan.json")["samples"]}
q8t = {x["tag"]: x for x in load("2026-10-24_b65-32g-q8_0-dual-tensor-scan.json")["samples"]}
scan2 = {x["tag"]: x for x in load("2026-10-24_b65-32g-dual-ts-scan2.json")["samples"]}
q4_solo = load("2026-10-24_b65-32g-q4_0-solo.json")["samples"][0]
q8_37b = load("2026-10-24_b65-32g-q8_0-solo37-recheck.json")["samples"][0]
ctx = load("2026-10-23_b65-32g_q4_0-ctxcap-dual.json")["summary"]

b65f = sample(b65_720, "fresh")
d6f = sample(dual_d6, "fresh")
b70f = sample(b70_720, "fresh")

thr_dual = 2 * 3600.0 / b65f["server_sec"]
thr_b70 = 3600.0 / b70f["server_sec"]

solo_ss = [x["server_sec"] for x in img_solo["samples"] if x.get("ok")][1:]
conc_ss = [x["server_sec"] for x in img_c0["samples"] if x.get("ok")][1:] + \
          [x["server_sec"] for x in img_c1["samples"] if x.get("ok")][1:]


def r2(x):
    return None if x is None else round(x, 2)


def build_groups(lang):
    t = lambda zh, en: zh if lang == "zh" else en
    return [
        {"t": t("H3 视频 · 端到端（s，越低越好）",
                "H3 video · end-to-end (s, lower is better)"), "rows": [
            {"lbl": t("720p · 5 s · 6 步（稳态）", "720p · 5 s · 6 steps (steady)"),
             "v": [r2(b65f["server_sec"]), r2(d6f["server_sec"]), r2(b70f["server_sec"])],
             "u": "s",
             "n": t("双卡对单条零提速；B70 快 1.42×",
                    "No speedup on a single job with dual; B70 is 1.42× faster")},
            {"lbl": t("1080p · 5 s · 6 步（稳态）", "1080p · 5 s · 6 steps (steady)"),
             "v": [r2(sample(b65_1080, "fresh")["server_sec"]), None,
                   r2(sample(b70_1080, "fresh")["server_sec"])],
             "u": "s",
             "n": t("B70 快 1.58×；双卡未测", "B70 is 1.58× faster; dual not tested")},
        ]},
        {"t": t("H3 视频 · 单步（s/it，越低越好）",
                "H3 video · per-step (s/it, lower is better)"), "rows": [
            {"lbl": t("720p · 5 s · 6 步（稳态）", "720p · 5 s · 6 steps (steady)"),
             "v": [r2(b65f["sampling_sec_per_step"]), r2(d6f["sampling_sec_per_step"]),
                   r2(b70f["sampling_sec_per_step"])],
             "u": "s/it",
             "n": t("第二张卡对单条片子贡献 0", "The second card contributes 0 to a single clip")},
        ]},
        {"t": t("LLM 解码（tok/s，越高越好）", "LLM decode (tok/s, higher is better)"), "rows": [
            {"lbl": "Qwen Q4_0 · 19/128",
             "v": [r2(q_solo["decode_tok_s"]), r2(q_conc["decode_tok_s"]), r2(b70_q4["decode_tok_s"])],
             "u": "tok/s",
             "n": t("双卡并发 −0.2%，不掉速", "Dual concurrent −0.2%, no slowdown")},
            {"lbl": t("Q8_0 34.37 GiB · 拆层", "Q8_0 34.37 GiB · layer-split"),
             "v": [r2(q8_37b["decode_tok_s"]), r2(scan2["ts6040"]["decode_tok_s"]), None],
             "u": "tok/s",
             "n": t("单卡装不下；拆层买容量不赔速度",
                    "Won't fit on one card; layer-split buys capacity without losing speed")},
            {"lbl": t("Q4_0 19.41 GiB · 全驻", "Q4_0 19.41 GiB · fully resident"),
             "v": [r2(q4_solo["decode_tok_s"]), r2(scan2["ts5050_q4"]["decode_tok_s"]), None],
             "u": "tok/s",
             "n": t("单卡装得下就别拆（慢 7%）", "If it fits on one card, don't split (7% slower)")},
            {"lbl": t("Q8_0 · 张量并行", "Q8_0 · tensor parallel"),
             "v": [None, r2(q8t["tensor5050"]["decode_tok_s"]), None],
             "u": "tok/s",
             "n": t("比单卡全驻还慢，别走张量",
                    "Slower than single-card full-resident; don't use tensor parallel")},
        ]},
        {"t": t("容量", "Capacity"), "rows": [
            {"lbl": t("可驻留显存", "Resident VRAM"),
             "v": [31.16, 62.32, 31.16], "u": "GiB",
             "n": t("双卡买到的是 2× 显存，不是速度", "Dual buys 2× VRAM, not speed")},
            {"lbl": t("上下文（真装下）", "Context (actually fits)"),
             "v": [round(ctx["single_max_allocated_ctx"] / 1048576.0, 2),
                   round(ctx["dual_max_allocated_ctx_unified"] / 1048576.0, 2),
                   round(ctx["single_max_allocated_ctx"] / 1048576.0, 2)],
             "u": "M token",
             "n": t("3M 只是分配上限，对外说 1.75M",
                    "3M is only the allocation cap; quote 1.75M externally")},
        ]},
        {"t": t("出图 · 稳态（s/张，越低越好）",
                "Image gen · steady (s/image, lower is better)"), "rows": [
            {"lbl": t("Qwen-Image int8 · 720p · 25 步", "Qwen-Image int8 · 720p · 25 steps"),
             "v": [r2(sum(solo_ss) / len(solo_ss)), r2(sum(conc_ss) / len(conc_ss)), None],
             "u": "s/张",
             "n": t("双实例并发持平，零损失", "Dual-instance concurrent holds parity, zero loss")},
        ]},
        {"t": t("产能与功耗", "Throughput & power"), "rows": [
            {"lbl": t("两条 5 秒片", "Two 5-second clips"),
             "v": [None, round(thr_dual, 1), round(thr_b70, 1)],
             "u": "条/时",
             "n": t("同价产能双卡赢 1.40×", "At same cost dual wins 1.40× throughput")},
            {"lbl": t("满载功耗 P90", "Load power P90"),
             "v": [r2(pw_s0["summary"]["power"]["p90_w_busy"]),
                   r2(pw_b0["summary"]["power"]["pair_sum_p90_w"]),
                   r2(b70_pw["summary"]["power"]["p90_w_max"])],
             "u": "W",
             "n": t("双卡叠加不互压，按 400 W 级配电源",
                    "Two cards don't throttle each other; size the PSU at 400 W class")},
        ]},
    ]


META = {
    "zh": {
        "lang": "zh",
        "file": "dual-b65-dashboard",
        "title": "双卡 B65 · 总测试项汇总动态图",
        "sub": "2× GUNNIR B65 32G · ECC 关 · 32 GB 内存 · B850M；柱长 = 同行内相对值，悬停看一个结果",
        "foot": "数据与 <code>dual-b65-report.md</code> 总表同源（bench/data/*.json 直出）。空白 = 未测。",
        "tip": "一个结果：",
    },
    "en": {
        "lang": "en",
        "file": "dual-b65-dashboard.en",
        "title": "Dual B65 · All-Test Summary Dashboard",
        "sub": "2× GUNNIR B65 32G · ECC off · 32 GB RAM · B850M; bar length = relative within row, hover for one result",
        "foot": "Data shares source with the <code>dual-b65-report.md</code> summary table (straight from bench/data/*.json). Blank = not tested.",
        "tip": "One result: ",
    },
}

TEMPLATE = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__FILE__</title>
<style>
  :root { --ink: #2C2C2A; --muted: #5F5E5A; --grid: #E5E4E0; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 28px 24px 40px; background: #FAFAF8; color: var(--ink);
         font-family: "Microsoft YaHei", "Segoe UI", "Noto Sans SC", sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; }
  h1 { font-size: 21px; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 12.5px; margin: 0 0 16px; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; margin: 0 0 14px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
  .chip.off { opacity: .3; }
  .sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
  .panel { background: #fff; border: 1px solid var(--grid); border-radius: 10px;
           padding: 16px 18px 10px; margin: 0 0 18px; }
  .panel h2 { font-size: 14px; margin: 0 0 12px; }
  .row { display: grid; grid-template-columns: 280px 1fr; gap: 10px; align-items: center;
         padding: 6px 0; border-top: 1px dashed var(--grid); }
  .row:first-of-type { border-top: 0; }
  .lbl { font-size: 11.5px; line-height: 1.35; }
  .bars { position: relative; height: 58px; }
  .bar { position: absolute; height: 10px; border-radius: 2px; min-width: 1px; }
  .val { position: absolute; font-size: 9.5px; color: var(--muted); white-space: nowrap; }
  .foot { font-size: 11px; color: var(--muted); margin: 8px 2px 0; line-height: 1.6; }
  #tip { position: fixed; pointer-events: none; background: #2C2C2A; color: #fff; font-size: 11px;
         padding: 7px 10px; border-radius: 6px; max-width: 340px; line-height: 1.55; display: none; z-index: 9; }
</style>
</head>
<body>
<div class="wrap">
  <h1></h1>
  <p class="sub"></p>
  <div class="legend" id="legend"></div>
  <div id="panels"></div>
  <p class="foot">__FOOT__</p>
</div>
<div id="tip"></div>
<script>
const DATA = __DATA__;
const tip = document.getElementById("tip");
const off = {};
function fmt(v, u) { return v == null ? "—" : (Math.round(v * 100) / 100) + " " + u; }
function render() {
  document.querySelector("h1").textContent = DATA.title;
  document.querySelector(".sub").textContent = DATA.sub;
  const lg = document.getElementById("legend");
  lg.innerHTML = DATA.cards.map(c =>
    `<span class="chip${off[c] ? " off" : ""}" data-c="${c}"><span class="sw" style="background:${DATA.colors[c]}"></span>${c}</span>`).join("");
  lg.querySelectorAll(".chip").forEach(el => el.onclick = () => { off[el.dataset.c] = !off[el.dataset.c]; render(); });
  const root = document.getElementById("panels");
  root.innerHTML = DATA.groups.map(g => {
    const rows = g.rows.map(r => {
      const mx = Math.max(...r.v.map(v => v == null ? 0 : v), 1e-9);
      const bars = DATA.cards.map((c, i) => {
        const v = r.v[i];
        if (v == null) return "";
        const w = v / mx * 82;
        const top = i * 17;
        return `<div class="bar" style="width:${w}%;top:${top}px;background:${DATA.colors[c]}" data-t="${r.lbl}" data-c="${c}" data-v="${fmt(v, r.u)}" data-n="${r.n}"></div>` +
               `<div class="val" style="top:${top - 1}px;left:calc(${w}% + 6px)">${fmt(v, r.u)}</div>`;
      }).join("");
      return `<div class="row"><div class="lbl">${r.lbl}</div><div class="bars">${bars}</div></div>`;
    }).join("");
    return `<div class="panel"><h2>${g.t}</h2>${rows}</div>`;
  }).join("");
  root.querySelectorAll(".bar").forEach(b => {
    b.onmousemove = e => {
      tip.style.display = "block";
      tip.innerHTML = `<b>${b.dataset.t}</b><br>${b.dataset.c} = ${b.dataset.v}<br>${DATA.tip}${b.dataset.n}`;
      tip.style.left = Math.min(e.clientX + 14, innerWidth - 360) + "px";
      tip.style.top = (e.clientY + 14) + "px";
    };
    b.onmouseleave = () => { tip.style.display = "none"; };
  });
}
render();
</script>
</body>
</html>"""


def build(lang):
    m = META[lang]
    payload = {
        "title": m["title"],
        "sub": m["sub"],
        "tip": m["tip"],
        "cards": CARDS[lang],
        "colors": dict(zip(CARDS[lang], COLORS[lang])),
        "groups": build_groups(lang),
    }
    text = TEMPLATE
    text = text.replace("__LANG__", m["lang"])
    text = text.replace("__FILE__", m["file"])
    text = text.replace("__FOOT__", m["foot"])
    text = text.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    if text.endswith("\r\n"):
        text = text[:-2]
    return text


for lang in ("zh", "en"):
    text = build(lang)
    with open(OUT[lang], "wb") as f:
        f.write(text.encode("utf-8"))
    print("written:", OUT[lang], len(text), "bytes")
