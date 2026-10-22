# -*- coding: utf-8 -*-
"""
从 README.zh-CN.md 的「表 1」「表 1b」生成「四张卡一眼比」的两份产物：

  1. docs/assets/summary-dashboard.svg / .en.svg —— README 里直接显示：矢量、柱子逐根长出
  2. docs/charts.html                            —— 指标可切的交互版

用法：python bench/harness/gen_summary_chart.py

数字只有一个来源：README.zh-CN.md。不在这里另抄一份。
"""
import html
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
README = REPO / "README.zh-CN.md"
OUT_SVG = REPO / "docs" / "assets" / "summary-dashboard.svg"      # 中文版
OUT_SVG_EN = REPO / "docs" / "assets" / "summary-dashboard.en.svg"  # 英文版
OUT_HTML = REPO / "docs" / "charts.html"

CARDS = ["B50 16G", "B60 24G", "B65 32G", "B70 32G"]
SHORT = ["B50", "B60", "B65", "B70"]
COLOR = {"B50 16G": "#8C9BAA", "B60 24G": "#3B6FE0", "B65 32G": "#12897B", "B70 32G": "#E2622B"}


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def strip_md(t):
    t = t.replace("**", "").replace("<br>", " ")
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t).strip()


def first_num(t):
    """取一个数；范围取中点，'17.3~18.8 s' 取 18.05。"""
    t = strip_md(t)
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t.replace(",", ""))]
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    return round((nums[0] + nums[1]) / 2, 3)


def range_of(t):
    """'17.3~18.8 s' -> '17.3~18.8'；没跨多轮就返回 None。柱子位置用中点，标签写原区间。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*[~～–]\s*(\d+(?:\.\d+)?)", strip_md(t).replace(",", ""))
    return f"{m.group(1)}~{m.group(2)}" if m else None


def rows_of_region(lines, start_marker, end_marker):
    """只取两个二级标题之间的表行：首列 -> 后四格。列数 5/6 都收（表 1 多一列结论）。"""
    i = next(k for k, l in enumerate(lines) if l.startswith(start_marker))
    j = next(k for k, l in enumerate(lines) if k > i and l.startswith(end_marker))
    rows = {}
    for ln in lines[i:j]:
        if not ln.startswith("|"):
            continue
        c = cells(ln)
        if len(c) < 5:
            continue
        if set("".join(c)) <= set("-: "):
            continue
        rows[strip_md(c[0])] = c[1:5]
    return rows


def load():
    text = README.read_bytes().decode("utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    rows = rows_of_region(lines, "## 表 1 ·", "## 表 2 ·")
    ranges = {}

    def pick(key):
        for k, v in rows.items():
            if k.startswith(key):
                got = [first_num(x) for x in v]
                assert all(x is not None for x in got), f"{key} 有一格没取到数：{v}"
                rng = [range_of(x) for x in v]
                if any(rng):
                    ranges[key] = rng
                return got
        raise KeyError(key)

    spec = {
        "price": pick("参考价（2026-10-21"),
        "vram": pick("显存"),
        "usable": pick("应用可见显存"),
        "bw": pick("带宽"),
        "core": pick("Xe2 核心"),
        "tops": pick("INT8 TOPS"),
        "tbp": pick("整卡功耗 TBP"),
    }
    chat = pick("聊天解码 · 35B-A3B Q4_0")
    d = {
        "cards": CARDS,
        "short": SHORT,
        "color": COLOR,
        "spec": spec,
        "ranges": ranges,
        "chat_tok_s": chat,
        "image_sec": pick("出图 · Qwen-Image 2.1 INT8"),
        "v480_min": pick("出视频 · 5 秒 · 480p"),
        "v1080_min": pick("出视频 · 5 秒 · 1080p"),
        "music_min": pick("生成一首 2 分钟的曲子"),
    }
    d["price_per_tok_s"] = [round(p / t, 1) for p, t in zip(spec["price"], chat)]
    # ranges 是按 README 行名收的，这里换成数据键，图表直接用
    d["ranges"] = {
        "chat_tok_s": ranges.get("聊天解码 · 35B-A3B Q4_0"),
        "image_sec": ranges.get("出图 · Qwen-Image 2.1 INT8"),
        "v480_min": ranges.get("出视频 · 5 秒 · 480p"),
        "v1080_min": ranges.get("出视频 · 5 秒 · 1080p"),
        "music_min": ranges.get("生成一首 2 分钟的曲子"),
    }
    d["ranges"] = {k: v for k, v in d["ranges"].items() if v}
    return d


def show(fmt, v):
    """52.0 -> 52，18.05 -> 18.1：跟正文写法一致。"""
    t = fmt.format(v)
    return t[:-2] if t.endswith(".0") else t


# (中文标题, 英文标题, 中文单位, 英文单位, 数据键, 越大/越小, 格式化)
PANELS = [
    ("聊天解码 · 35B", "Chat decode · 35B", "tok/s", "tok/s", "chat_tok_s", 1, "{:.1f}"),
    ("出一张 720p 图", "One 720p image", "秒", "s", "image_sec", -1, "{:.1f}"),
    ("5 秒 480p 视频", "5 s 480p video", "分钟", "min", "v480_min", -1, "{:.1f}"),
    ("5 秒 1080p 视频", "5 s 1080p video", "分钟", "min", "v1080_min", -1, "{:.1f}"),
    ("一首 2 分钟的曲子", "One 2-minute track", "分钟", "min", "music_min", -1, "{:.1f}"),
    ("每 tok/s 的买价", "Price per tok/s", "元", "¥", "price_per_tok_s", -1, "{:.0f}"),
]

HEAD = {
    "zh": ("四张卡，一眼比", "同一台机器、只换显卡 · 全部本机实测 · 每格数字可追到 bench/data/",
           "越大越好", "越小越好"),
    "en": ("Four cards, one glance", "Same machine, only the GPU swapped · all measured here · "
           "every number traces to bench/data/", "higher is better", "lower is better"),
}


def gen_svg(d, lang="zh"):
    i18n = 0 if lang == "zh" else 1
    title, sub, hi, lo = HEAD[lang]
    COLS, PW, PH, GAP = 2, 430, 246, 22
    LEFT, TOP = 24, 96
    ROWS = (len(PANELS) + COLS - 1) // COLS
    W = LEFT * 2 + COLS * PW + (COLS - 1) * GAP
    H = TOP + ROWS * PH + (ROWS - 1) * GAP + 24

    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif">')
    a('''<defs><style>
  .pt{font-size:16px;font-weight:700;fill:#1a202c}
  .pu{font-size:11.5px;fill:#8b95a5}
  .cl{font-size:13px;fill:#4a5568}
  .vl{font-size:14.5px;font-weight:700;fill:#1a202c}
  .bar{transform-box:fill-box;transform-origin:bottom;animation:g .85s cubic-bezier(.2,.8,.25,1) both}
  @keyframes g{from{transform:scaleY(.001)}to{transform:scaleY(1)}}
</style></defs>''')
    a(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    a(f'<text x="{LEFT}" y="42" font-size="22" font-weight="800" fill="#1a202c">{html.escape(title)}</text>')
    a(f'<text x="{LEFT}" y="66" font-size="13" fill="#8b95a5">{html.escape(sub)}</text>')

    lx = W - LEFT - 4 * 104
    for i, c in enumerate(d["cards"]):
        x = lx + i * 104
        a(f'<rect x="{x}" y="28" width="12" height="12" rx="3" fill="{d["color"][c]}"/>')
        a(f'<text x="{x + 18}" y="39" font-size="12.5" fill="#4a5568">{html.escape(c)}</text>')

    for idx, pn in enumerate(PANELS):
        ptitle, punit, key, better, fmt = pn[i18n], pn[i18n + 2], pn[4], pn[5], pn[6]
        r, c = divmod(idx, COLS)
        X = LEFT + c * (PW + GAP)
        Y = TOP + r * (PH + GAP)
        vals = d[key]
        rng = d["ranges"].get(key) or [None] * 4
        vmax = max(vals)
        best = max(vals) if better == 1 else min(vals)

        a(f'<rect x="{X}" y="{Y}" width="{PW}" height="{PH}" rx="12" fill="#f8fafc" stroke="#e6ebf1"/>')
        a(f'<text x="{X + 18}" y="{Y + 30}" class="pt">{html.escape(ptitle)}</text>')
        a(f'<text x="{X + PW - 18}" y="{Y + 30}" class="pu" text-anchor="end">{html.escape(punit)} · '
          f'{hi if better == 1 else lo}</text>')

        base, top = Y + PH - 36, Y + 58
        bw, bgap = 58, 44
        x0 = X + (PW - (4 * bw + 3 * bgap)) / 2

        for i, (card, v) in enumerate(zip(d["cards"], vals)):
            hgt = max((base - top) * (v / vmax) * 0.92, 1.0)
            bx, by = x0 + i * (bw + bgap), base - hgt
            lab = rng[i] or show(fmt, v)
            win = "★ " if v == best else ""
            a(f'<g><title>{html.escape(card)}: {lab} {html.escape(punit)}</title>')
            a(f'<rect class="bar" x="{bx:.1f}" y="{by:.1f}" width="{bw}" height="{hgt:.1f}" rx="5" '
              f'fill="{d["color"][card]}" style="animation-delay:{(0.045 * i + 0.04 * (idx % 2)):.2f}s"/>')
            a(f'<text class="vl" x="{bx + bw / 2:.1f}" y="{by - 9:.1f}" text-anchor="middle">'
              f'{win}{lab}</text>')
            a(f'<text class="cl" x="{bx + bw / 2:.1f}" y="{base + 18:.1f}" text-anchor="middle">'
              f'{html.escape(d["short"][i])}</text>')
            a('</g>')
        a(f'<line x1="{X + 16}" y1="{base}" x2="{X + PW - 16}" y2="{base}" stroke="#d7dee8"/>')

    a('</svg>')
    out = OUT_SVG if lang == "zh" else OUT_SVG_EN
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(o), encoding="utf-8", newline="\n")
    return W, H


HTML_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>四张卡，一眼比 · Intel Arc Pro B 系列</title>
<style>
  :root{--bg:#f5f7fa;--panel:#fff;--ink:#1a202c;--ink2:#4a5568;--ink3:#8b95a5;--line:#e4e9f0;--accent:#c05621}
  @media (prefers-color-scheme:dark){:root{--bg:#12161c;--panel:#1a1f27;--ink:#eef2f7;--ink2:#aab4c2;
    --ink3:#7c8797;--line:#28303b;--accent:#f6ad55}}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);padding:28px 20px 60px;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
  .wrap{max-width:1000px;margin:0 auto}
  h1{font-size:24px;margin:0 0 6px}
  .sub{color:var(--ink3);font-size:13px;margin-bottom:22px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 22px 12px}
  .bar-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
  button{border:1px solid var(--line);background:transparent;color:var(--ink2);padding:7px 13px;
    border-radius:999px;font-size:13px;cursor:pointer;transition:.16s}
  button:hover{color:var(--ink)}
  button[aria-pressed=true]{background:var(--ink);color:var(--panel);border-color:var(--ink)}
  .meta{display:flex;justify-content:space-between;align-items:baseline;font-size:13px;
    color:var(--ink3);margin:6px 0 14px;gap:16px}
  .meta b{color:var(--ink2);font-weight:600}
  table{width:100%;border-collapse:collapse;font-size:14px}
  th,td{padding:11px 8px;border-bottom:1px solid var(--line);text-align:right}
  th:first-child,td:first-child{text-align:left}
  th{font-size:12px;color:var(--ink3);font-weight:600}
  tr:last-child td{border-bottom:none}
  .track{height:22px;border-radius:6px;background:transparent}
  .fill{height:22px;border-radius:6px;transition:width .5s cubic-bezier(.2,.8,.25,1),background .2s}
  tr:hover .fill{background:var(--accent)!important}
  tr:hover td{color:var(--ink)}
  .v{font-variant-numeric:tabular-nums;font-weight:700}
  .best:after{content:" ★";color:var(--accent);font-size:12px}
  .foot{margin-top:16px;font-size:12px;color:var(--ink3);line-height:1.7}
</style>
</head>
<body>
<div class="wrap">
  <h1>四张卡，一眼比</h1>
  <div class="sub">同一台机器、只换显卡 · 全部本机实测 · 与 README 表 1 / 表 1b 同源</div>
  <div class="card">
    <div class="bar-row" id="metrics"></div>
    <div class="meta"><span id="hint"></span><span style="flex:none">长度按本列最大值归一</span></div>
    <table>
      <thead><tr><th>型号</th><th id="unitHead"></th><th style="width:50%">占比</th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
    <div class="foot" id="foot"></div>
  </div>
</div>
<script>
const DATA = __DATA__;
const tf = v => { const s = v.toFixed(1); return s.endsWith('.0') ? s.slice(0,-2) : s; };
const METRICS = [
  {k:'chat_tok_s', label:'聊天解码', unit:'tok/s', better:1, fmt:v=>tf(v), src:'llama-bench -p 512 -n 128 -r 3 · Qwen3.6-35B-A3B Q4_0'},
  {k:'image_sec', label:'出图 720p', unit:'秒', better:-1, fmt:v=>tf(v), src:'Qwen-Image 2.1 INT8 · 25 步 · 稳态'},
  {k:'v480_min', label:'5 秒 480p', unit:'分钟', better:-1, fmt:v=>tf(v), src:'MiniMax H3 · 6 步 · 端到端含装载'},
  {k:'v1080_min', label:'5 秒 1080p', unit:'分钟', better:-1, fmt:v=>tf(v), src:'MiniMax H3 · 6 步 · 端到端含装载'},
  {k:'music_min', label:'2 分钟音乐', unit:'分钟', better:-1, fmt:v=>tf(v), src:'MiniMax Music 3 · 30 步 · int8 DiT + int8 TE · reserve 4'},
  {k:'price_per_tok_s', label:'每 tok/s 买价', unit:'元', better:-1, fmt:v=>v.toFixed(0), src:'售价 ÷ 聊天解码 · 2026-10-21 价格'}
];
const SPEC = [
  {k:'price', label:'参考价', unit:'元', better:-1, fmt:v=>v.toLocaleString(), src:'2026-10-21 官方/京东价'},
  {k:'vram', label:'显存', unit:'GB', better:1, fmt:v=>v.toFixed(0), src:'厂商规格'},
  {k:'usable', label:'可用显存（关 ECC）', unit:'GiB', better:1, fmt:v=>v.toFixed(2), src:'实测 torch.xpu 读到'},
  {k:'bw', label:'带宽', unit:'GB/s', better:1, fmt:v=>v.toFixed(0), src:'厂商规格'},
  {k:'core', label:'Xe2 核心', unit:'个', better:1, fmt:v=>v.toFixed(0), src:'厂商规格'},
  {k:'tops', label:'INT8 算力', unit:'TOPS', better:1, fmt:v=>v.toFixed(0), src:'厂商规格'},
  {k:'tbp', label:'整卡功耗 TBP', unit:'W', better:-1, fmt:v=>v.toFixed(0), src:'厂商规格（非实测）'}
];
const ALL = METRICS.concat(SPEC);
let cur = 'chat_tok_s';
function vals(k){ return k in DATA.spec ? DATA.spec[k] : DATA[k]; }
function render(){
  const m = ALL.find(x=>x.k===cur), v = vals(cur);
  const max = Math.max(...v), best = m.better===1 ? max : Math.min(...v);
  document.getElementById('unitHead').textContent = m.unit + (m.better===1?' · 越大越好':' · 越小越好');
  document.getElementById('hint').innerHTML = '当前：<b>' + m.label + '</b> · ' + m.src;
  document.getElementById('foot').textContent =
    (cur==='price_per_tok_s' ? '这一列不是性能，是「花多少钱买一 tok/s」，越低越划算。' : '') +
    (SPEC.some(x=>x.k===cur) ? '这一列是厂商规格，不是本机实测。' : '');
  const tb = document.getElementById('rows'); tb.innerHTML = '';
  const rng = (DATA.ranges && DATA.ranges[m.k]) || [];
  DATA.cards.forEach((c,i)=>{
    const tr = document.createElement('tr');
    tr.innerHTML = '<td><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:'+
      DATA.color[c]+';margin-right:8px"></span>'+c+'</td><td class="v'+(v[i]===best?' best':'')+'">'+
      (rng[i]||m.fmt(v[i]))+' <span style="font-weight:400;color:var(--ink3)">'+m.unit+'</span></td>'+
      '<td><div class="track"><div class="fill" style="width:0;background:'+DATA.color[c]+'"></div></div></td>';
    tb.appendChild(tr);
    requestAnimationFrame(()=>{ tr.querySelector('.fill').style.width = (v[i]/max*100).toFixed(1)+'%'; });
  });
  document.querySelectorAll('#metrics button').forEach(b=>b.setAttribute('aria-pressed', b.dataset.k===cur));
}
const box = document.getElementById('metrics');
ALL.forEach(m=>{
  const b = document.createElement('button');
  b.textContent = m.label; b.dataset.k = m.k;
  b.onclick = ()=>{ cur = m.k; render(); };
  box.appendChild(b);
});
render();
</script>
</body>
</html>
"""


def main():
    d = load()
    w, h = gen_svg(d, "zh")
    gen_svg(d, "en")
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(HTML_TMPL.replace("__DATA__", json.dumps(d, ensure_ascii=False)),
                        encoding="utf-8", newline="\n")
    print(f"SVG {w}x{h} -> {OUT_SVG.relative_to(REPO)}")
    print(f"SVG {w}x{h} -> {OUT_SVG_EN.relative_to(REPO)}")
    print(f"HTML -> {OUT_HTML.relative_to(REPO)}")
    for k in ("chat_tok_s", "image_sec", "v480_min", "v1080_min", "music_min", "price_per_tok_s"):
        print(" ", k, d[k])
    print("  spec.price", d["spec"]["price"])


if __name__ == "__main__":
    main()
