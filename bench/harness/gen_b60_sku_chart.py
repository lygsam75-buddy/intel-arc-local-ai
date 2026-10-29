#!/usr/bin/env python
"""由 bench/data/2026-10-27_b60-tf-vs-bs.json 生成 B60 两个 SKU 的对照图。

输出 docs/cards/assets/b60-tf-vs-bs.svg 与 b60-tf-vs-bs.en.svg（纯 LF）。
不读任何本机绝对路径；数据不在时直接报错而不是画空图。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data" / "2026-10-27_b60-tf-vs-bs.json"
OUT_ZH = ROOT / "docs" / "cards" / "assets" / "b60-tf-vs-bs.svg"
OUT_EN = ROOT / "docs" / "cards" / "assets" / "b60-tf-vs-bs.en.svg"

INK = "#2C2C2A"
MUTED = "#5F5E5A"
GRID = "#E5E4E0"
TF_C = "#2F6FBA"
BS_C = "#E8873B"
WORSE = "#C2410C"
BETTER = "#0F766E"
FONT = "'Microsoft YaHei','PingFang SC','Noto Sans SC',sans-serif"

W = 680
L, R = 78, 640          # 绘图区左右
PA_T, PA_B = 100, 250   # 面板 A 上下
PB_T, PB_B = 296, 400   # 面板 B 上下
LBL_Y = 420             # 档位名
FOOT_Y = 454            # 脚注起始

TXT = {
    "zh": dict(
        title="同一个型号，两个 SKU：TF（200 W）对 BS（120 W）",
        sub="MiniMax H3 · 6 步 · 同提示词同 seed · 端到端含装载（秒）与整轮电耗（Wh）",
        leg_tf="TF · 双槽 · 200 W 墙",
        leg_bs="BS · 单槽 · 120 W 墙",
        pa="端到端耗时（秒）",
        pb="每片电耗（Wh，整轮含装载）",
        foot=[
            "单步差 **+{sit_lo}–+{sit_hi}%**、端到端 **+{e2e_lo}–+{e2e_hi}%**；档位间不成比例，按档取数，别按比例外推。",
            "电只省 {wh_lo}–{wh_hi}%：功率降 {pw_drop}%，时间多花 {e2e_lo}–{e2e_hi}%，电耗基本抵消 —— **BS 换来的是单槽与更低发热，不是电费**。",
            "480p·10 与 720p·15 的 TF 电耗没采到，下面电耗面板这两档只有 BS 一根柱。",
        ],
        cap="端到端取 fresh 轮，与产品页同口径",
    ),
    "en": dict(
        title="One card, two SKUs: TF (200 W) vs BS (120 W)",
        sub="MiniMax H3 · 6 steps · same prompt & seed · end-to-end incl. loading (s), plus energy per clip (Wh)",
        leg_tf="TF · dual-slot · 200 W cap",
        leg_bs="BS · single-slot · 120 W cap",
        pa="End-to-end time (s)",
        pb="Energy per clip (Wh, whole run)",
        foot=[
            "Per-step gap **+{sit_lo}–+{sit_hi}%**, end-to-end **+{e2e_lo}–+{e2e_hi}%**; not proportional",
            "across tiers — read each tier, do not scale one from another.",
            "Energy drops just {wh_lo}–{wh_hi}%: {pw_drop}% less power against {e2e_lo}–{e2e_hi}% more",
            "time — a wash. **What BS buys is the single slot and lower heat, not the power bill.**",
            "TF energy was not captured for 480p·10 and 720p·15; those two groups show a BS bar only.",
        ],
        cap="End-to-end uses the fresh round, same basis as the product page",
    ),
}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rich(s):
    """**加粗** -> tspan，其余转义。"""
    out, bold = [], False
    for part in s.split("**"):
        if part:
            out.append(
                f'<tspan font-weight="700" fill="{INK}">{esc(part)}</tspan>' if bold else esc(part)
            )
        bold = not bold
    return "".join(out)


def nice_scale(v):
    """返回 (上限, 刻度步长)：上限紧贴数据（不超过 1.22 倍），刻度落在 3~6 格。"""
    import math
    best = None
    for exp in range(-1, 7):
        for m in (1, 2, 2.5, 4, 5):
            step = m * (10 ** exp)
            top = step * math.ceil(v / step)
            if top < v:
                continue
            n = top / step
            if not (3 <= n <= 6):
                continue
            if top / v > 1.22:
                continue
            best = (top, step) if best is None or top < best[0] - 1e-9 else best
            break
    if best is None:                      # 兜底：最粗一档
        step = 10 ** math.floor(math.log10(v))
        best = (step * math.ceil(v / step), step)
    return best


def panel(rows, top, bot, field, gmax, step, tick_fmt, delta_key, dcolor):
    """一组分组柱状图，返回 (svg 片段, 每档中心 x)。"""
    s = []
    n = len(rows)
    slot = min((R - L) / n, 118.0)
    x0 = L + ((R - L) - slot * n) / 2.0
    bw = min(26.0, slot * 0.30)
    gap = 3.0
    h = bot - top

    k = 0
    while k * step <= gmax + 1e-9:
        v = k * step
        y = bot - h * v / gmax
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{L - 10}" y="{y + 4:.1f}" font-size="10.5" fill="{MUTED}" '
                 f'text-anchor="end">{tick_fmt(v)}</text>')
        k += 1

    centers = []
    for i, r in enumerate(rows):
        cx = x0 + slot * (i + 0.5)
        centers.append(cx)
        for j, (val, col) in enumerate(((r["TF"][field], TF_C), (r["BS"][field], BS_C))):
            x = cx + (j - 0.5) * (bw + gap) - bw / 2.0
            if not val:                       # 没采到这个数：留空位，标 n/a
                s.append(f'<text x="{x + bw / 2:.1f}" y="{bot - 4:.1f}" font-size="9" '
                         f'fill="#8A8880" text-anchor="middle">n/a</text>')
                continue
            bh = h * val / gmax
            s.append(f'<rect x="{x:.1f}" y="{bot - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                     f'rx="2" fill="{col}"/>')
        # 差值只标在两根柱顶之上；有一根缺数就不标
        d = r.get(delta_key)
        if d is not None and r["TF"][field] and r["BS"][field]:
            top_bars = max(r["TF"][field], r["BS"][field])
            y = bot - h * top_bars / gmax - 6
            s.append(f'<text x="{cx:.1f}" y="{y:.1f}" font-size="10.5" font-weight="700" '
                     f'fill="{dcolor}" text-anchor="middle">{d:+.1f}%</text>')
    return s, centers


def stats(rows):
    """把脚注要用的数字全从数据里算出来，改档位不用手改文案。"""
    def mm(vals):
        return f"{min(vals):.1f}", f"{max(vals):.1f}"

    s_lo, s_hi = mm([r["sit_delta_pct"] for r in rows])
    e_lo, e_hi = mm([r["delta_pct"] for r in rows])
    whs = [abs(r["wh_delta_pct"]) for r in rows if r.get("wh_delta_pct") is not None]
    w_lo, w_hi = mm(whs)
    ok = [r for r in rows if r["TF"]["avg_w"] > 0 and r["BS"]["avg_w"] > 0]
    pw = (1 - sum(r["BS"]["avg_w"] for r in ok) / sum(r["TF"]["avg_w"] for r in ok)) * 100
    return dict(sit_lo=s_lo, sit_hi=s_hi, e2e_lo=e_lo, e2e_hi=e_hi,
                wh_lo=w_lo, wh_hi=w_hi, pw_drop=f"{pw:.0f}")


def build(lang):
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    t = TXT[lang]
    rows = doc["tiers"]
    st = stats(rows)
    key_zh, key_en = "label_zh", "label_en"
    lab = key_zh if lang == "zh" else key_en
    lbl_fs = 10.5 if len(rows) <= 5 else 9.2

    h = FOOT_Y + 17 * len(t["foot"]) + 30
    s = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" '
        f'font-family="{FONT}">',
        f'<text x="28" y="30" font-size="15" font-weight="700" fill="{INK}">{esc(t["title"])}</text>',
        f'<text x="28" y="52" font-size="11.5" fill="{MUTED}">{esc(t["sub"])}</text>',
        f'<rect x="28" y="63" width="9" height="9" rx="2" fill="{TF_C}"/>',
        f'<text x="42" y="71.5" font-size="11.5" fill="{MUTED}">{esc(t["leg_tf"])}</text>',
        f'<rect x="210" y="63" width="9" height="9" rx="2" fill="{BS_C}"/>',
        f'<text x="224" y="71.5" font-size="11.5" fill="{MUTED}">{esc(t["leg_bs"])}</text>',
    ]

    # 面板 A：端到端耗时
    s.append(f'<text x="28" y="{PA_T - 10}" font-size="11.5" font-weight="600" fill="{INK}">{esc(t["pa"])}</text>')
    max_s = max(max(r["TF"]["server_s"], r["BS"]["server_s"]) for r in rows)
    gs, ss = nice_scale(max_s * 1.12)
    frag, centers = panel(rows, PA_T, PA_B, "server_s", gs, ss,
                          lambda v: f"{v:,.0f}", "delta_pct", WORSE)
    s += frag

    # 面板 B：每片电耗
    s.append(f'<text x="28" y="{PB_T - 10}" font-size="11.5" font-weight="600" fill="{INK}">{esc(t["pb"])}</text>')
    max_e = max(max(r["TF"]["wh"], r["BS"]["wh"]) for r in rows)
    ge, se = nice_scale(max_e * 1.12)
    frag, _ = panel(rows, PB_T, PB_B, "wh", ge, se,
                    lambda v: f"{v:,.0f}", "wh_delta_pct", BETTER)
    s += frag

    # 档位名
    for cx, r in zip(centers, rows):
        s.append(f'<text x="{cx:.1f}" y="{LBL_Y}" font-size="{lbl_fs}" fill="{MUTED}" '
                 f'text-anchor="middle">{esc(r[lab])}</text>')

    # 脚注
    y = FOOT_Y
    for line in t["foot"]:
        s.append(f'<text x="28" y="{y}" font-size="11" fill="{MUTED}">{rich(line.format(**st))}</text>')
        y += 18
    s.append(f'<text x="28" y="{y + 4}" font-size="10.5" fill="#8A8880">{esc(t["cap"])}</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def main():
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    if not doc["tiers"]:
        raise SystemExit("数据件没有可画的档位")
    for lang, out in (("zh", OUT_ZH), ("en", OUT_EN)):
        svg = build(lang)
        out.write_bytes(svg.encode("utf-8"))
        print(f"wrote {out.relative_to(ROOT)} ({len(svg.encode('utf-8'))} B)  "
              f"{len(doc['tiers'])} 档 / pending {len(doc['pending'])}")


if __name__ == "__main__":
    main()
