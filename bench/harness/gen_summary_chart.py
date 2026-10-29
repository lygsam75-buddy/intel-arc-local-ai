# -*- coding: utf-8 -*-
"""
从 README.zh-CN.md 的「表 1」「表 1b」生成「四张卡一眼比」的两份产物：

  1. docs/assets/summary-dashboard.svg      —— 中文版，README.zh-CN.md 用
  2. docs/assets/summary-dashboard.en.svg   —— 英文版，README.md 用

用法：python bench/harness/gen_summary_chart.py

数字只有一个来源：README.zh-CN.md。不在这里另抄一份。
"""
import html
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
README = REPO / "README.zh-CN.md"
OUT_SVG = REPO / "docs" / "assets" / "summary-dashboard.svg"      # 中文版
OUT_SVG_EN = REPO / "docs" / "assets" / "summary-dashboard.en.svg"  # 英文版

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


def main():
    d = load()
    w, h = gen_svg(d, "zh")
    gen_svg(d, "en")
    print(f"SVG {w}x{h} -> {OUT_SVG.relative_to(REPO)}")
    print(f"SVG {w}x{h} -> {OUT_SVG_EN.relative_to(REPO)}")
    for k in ("chat_tok_s", "image_sec", "v480_min", "v1080_min", "music_min", "price_per_tok_s"):
        print(" ", k, d[k])
    print("  spec.price", d["spec"]["price"])


if __name__ == "__main__":
    main()
