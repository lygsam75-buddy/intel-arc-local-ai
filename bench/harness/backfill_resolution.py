"""给历史 ComfyUI 记录补分辨率维度（`workload.width` / `height` / `frames` / `fps`）。

背景：`comfyui-xpu-bench/1` 原来只记 `duration_sec`，**不记分辨率**。
于是「B70 出片 60 秒」这种说法没法核对是哪个分辨率下的——而分辨率差一倍、
耗时差约 3.9 倍。分辨率是这类记录的**量纲**，不是可选元数据。

**只补能确定性映射的，绝不猜。**

映射依据（三处独立证据，互相印证）：

  1. 采集工作流 `MiniMax_H3_低显存修复.json`（`bench_h3.py` 的 `UI_WF`）：
       节点 115 `ResolutionSelector` = 16:9 / **0.4 MP** / 32 的倍数
       节点 133 `MiniMaxH3ImageToVideo` 的 width/height 连到节点 115
       → 按 `comfy_extras/nodes_resolution.py` 的实现
         （`total_pixels = megapixels * 1024 * 1024`，宽高各自 `round` 到 multiple）
         0.4 MP @ 16:9 @ 32 倍数 → **864×480**
  2. 帧数由节点 134 `ComfyMathExpression` 推导：
       `max(5, round(sec*24)) + (5 - (max(5, round(sec*24)) % 17)) % 17`
       → duration=5.0 时 = 120 + 4 = **124 帧**（即 17k+5 网格，k=7）
  3. `docs/comfyui-h3.md` §1 采集口径表记「**864×480**（实测产物核对）」

三条一致，故 12 条 H3 记录统一按 864×480 / 124 帧 / 24 fps 回填。

为什么标 inferred：原始采集 JSON 里**没有**分辨率字段，本值是**事后按工作流
与产物重建**的，不是采集当时写进记录的。按仓库纪律，重建值不伪装成 recorded，
并写入 env_backfill 说明依据。

⚠️ 与「B70 H3 实战」资料那套的口径差异（**这正是必须有分辨率维度的原因**）：
   本项目采集用 0.4 MP 选择器 → **864×480**；
   资料那套用 0.5 MP 选择器 → **960×544**。
   两边都被口头称作「0.5 MP」，实际不是同一个分辨率，**不能并排引用**。

用法：
    python bench/harness/backfill_resolution.py --dry-run   # 只看计划，不写
    python bench/harness/backfill_resolution.py             # 实际写入
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "bench", "data")

# 采集工作流的事实（见 docstring 证据 1/2）
SEL_MP = 0.4
SEL_MULT = 32
FPS = 24
GRID = 17          # 帧数须落 17k+5 网格
ASPECT = (16, 9)


def frames_for(sec):
    """复刻工作流节点 134 的公式。"""
    n = max(5, round(sec * FPS))
    return n + (5 - (n % GRID)) % GRID


def wh_for(mp, mult, aspect):
    """复刻 `comfy_extras/nodes_resolution.py` 的 ResolutionSelector.execute。

    ⚠️ 分母是 **1024²** 不是 10⁶ —— 这是该节点的实现细节，
    按 10⁶ 算会把 0.4 MP 算成 832×480（错），实际是 864×480。
    """
    w_ratio, h_ratio = aspect
    total_pixels = mp * 1024 * 1024
    scale = (total_pixels / (w_ratio * h_ratio)) ** 0.5
    w = round(w_ratio * scale / mult) * mult
    h = round(h_ratio * scale / mult) * mult
    return w, h


NOTE = (
    "workload 的分辨率维度（width/height/frames/fps）为 2026-10-16 backfill 补写，"
    "标 inferred：原始采集记录只落了 duration_sec，分辨率事后重建。"
    "重建依据三条独立证据：① 采集工作流 MiniMax_H3_低显存修复.json 的节点 115 "
    "ResolutionSelector = 16:9 / 0.4 MP / 32 的倍数，按 comfy_extras/nodes_resolution.py "
    "的实现（total_pixels = megapixels × 1024²，宽高各自 round 到 multiple）得 864×480；"
    "② 节点 134 ComfyMathExpression 的帧数公式在 duration=5.0 时得 124 帧；"
    "③ docs/comfyui-h3.md §1 采集口径表记「864×480（实测产物核对）」。"
    "⚠️ 口径提醒：本项目采集用 0.4 MP 选择器（864×480），"
    "「B70 H3 实战」资料那套用 0.5 MP 选择器（960×544）——"
    "两边都被口头称作「0.5 MP」，实为不同分辨率，不可并排引用。"
)

FIELDS = ("width", "height", "frames", "fps")


def main():
    dry = "--dry-run" in sys.argv
    changed = skipped = nodur = 0
    w, h = wh_for(SEL_MP, SEL_MULT, ASPECT)

    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        name = os.path.basename(f)
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("schema") != "comfyui-xpu-bench/1":
            continue
        wl = d.setdefault("workload", {})
        if all(k in wl for k in FIELDS):
            skipped += 1
            continue

        sec = wl.get("duration_sec")
        if not sec:
            nodur += 1
            print("[skip] %-56s 无 duration_sec，不猜" % name)
            continue

        fr = frames_for(sec)
        wl["width"] = w
        wl["height"] = h
        wl["frames"] = fr
        wl["fps"] = FPS
        wl["resolution"] = "%dx%d" % (w, h)
        wl["selector_megapixels"] = SEL_MP
        wl["duration_sec_exact"] = round(fr / FPS, 3)

        conf = d.setdefault("env", {}).setdefault("env_confidence", {})
        for k in ("resolution", "width", "height", "frames", "fps"):
            conf[k] = "inferred"
        d["env_backfill"] = (d["env_backfill"] + " " + NOTE
                             if d.get("env_backfill") else NOTE)

        if not dry:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        changed += 1
        print("[fix ] %-56s %sx%s · %d 帧 · %.2f s"
              % (name, w, h, fr, fr / FPS))

    print("\n%s：补写 %d 条 | 已有字段跳过 %d 条 | 不可判定 %d 条"
          % ("[dry-run 未落盘]" if dry else "[已落盘]", changed, skipped, nodur))


if __name__ == "__main__":
    main()
