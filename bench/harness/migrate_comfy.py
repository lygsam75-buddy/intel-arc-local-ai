#!/usr/bin/env python3
r"""把 ComfyUI MiniMax H3 的 A/B 实验数据迁移成 comfyui-xpu-bench/1 格式。

源数据：<ComfyUI 日志目录>\bench_*_fresh.json
采集脚本：同目录 bench_h3.py（口径见其 docstring）

⚠️ 原始数据只记录了 tag / mode / duration / runs，**没有随数据落盘环境信息**。
本脚本按 bench_h3.py 的 BASE_ENV 与启动参数补齐环境字段，并在
`env.confidence` 中逐项标明 `recorded` / `inferred` —— 推断值绝不伪装成实测。

用法:
  python migrate_comfy.py --src <_ab_logs 目录> --outdir <bench/data>
  python migrate_comfy.py --src ... --outdir ... --dry-run
"""

import argparse
import datetime as dt
import glob
import re
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 分辨率/帧数的推导与 backfill_resolution.py 共用一份实现，避免两处公式漂移
from backfill_resolution import wh_for, frames_for, SEL_MP, SEL_MULT, ASPECT, FPS  # noqa: E402

SCHEMA = "comfyui-xpu-bench/1"

# 来源：bench_h3.py 的 BASE_ENV（逐字抄录，未改动）
BASE_ENV = {
    "ZE_ENABLE_PCI_ID_DEVICE_ORDER": "1",
    "SYCL_CACHE_PERSISTENT": "1",
    "OMNIXPU_PROVIDER_BOOTSTRAP": "auto",
    "OMNIXPU_PIN_MEMORY": "1",
    "OMNIXPU_PIN_RATIO": "0.12",
    "OMNI_XPU_DEVICE": "bmg",
}

# 采集机的固定事实（机器级，与插哪张卡无关）
RIG = {
    "cpu": "AMD Ryzen 5 9600X",
    "ram_gb": 32,
    "os": "Windows",
}

# 板卡身份（AIB 口径）——**必须按卡查表，不能硬编码单卡**。
# Intel 走 AIB 模式：同型号不同板厂/批次的板子，SUBSYS 与 VBIOS 不同，
# 性能未必一致。取证方式见 bench/harness/gpu_identity.py，来源 docs/test-rig.md。
CARDS = {
    "b50": {
        "gpu": "Intel Arc Pro B50 LP 16G",
        "chip": "E212",
        "subsys": "25221EF7",
        "device_id": "PCI\\VEN_8086&DEV_E212&SUBSYS_25221EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
        "board_code": "2522",
        "vram_visible_gib": 15.51,
        "ecc": "off",
        "driver": "32.0.101.8976",
    },
    "b70": {
        "gpu": "Intel Arc Pro B70 32G",
        "chip": "E223",
        "subsys": "27421EF7",
        "device_id": "PCI\\VEN_8086&DEV_E223&SUBSYS_27421EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
        "board_code": "2742",
        "vram_visible_gib": 31.16,
        "ecc": "off",
        "driver": "32.0.101.8976",
    },
    # 2026-10-20 B60 到手上机。**以下字段全部来自 gpu_identity.py / gpu_sysman.py 实测**
    # （DEV_E211 · SUBSYS_25421EF7 · 板厂 1EF7 = GUNNIR · VBIOS 2304140000 · 23.33 GiB 可见），
    # 不是照规格表填的。注意 driver 是 9150，与 B50/B70 那两行的 8976 **不同** ——
    # 跨驱动版本的端到端秒数不可直接并排（见 docs/test-registry.md §5.1 第 5 条）。
    "b60": {
        "gpu": "Intel Arc Pro B60 24G",
        "chip": "E211",
        "subsys": "25421EF7",
        "device_id": "PCI\\VEN_8086&DEV_E211&SUBSYS_25421EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
        "board_code": "2542",
        "vram_visible_gib": 23.33,
        "ecc": "off",
        "driver": "32.0.101.9150",
    },
}

# 2026-10-16 之前的历史记录是按单卡（B70）口径迁的，其 env 里缺 device_id/subsys。
# 这些字段不回填——回填属改写历史记录，需要单独说明依据后再做。
HISTORICAL_NOTE = (
    " ⚠️ 本记录迁移于单卡口径时期，env 内无 device_id/subsys；"
    "该卡身份见 docs/test-rig.md 的 AIB 身份表。"
)


def pw_resets(p):
    """整卡域的能耗计数器归零次数。

    顶层缺（早期采集器只写在 `domains` 子项里）就回落到同一下标的域。
    ⚠️ **取不到返回 None，不是 0** —— `or 0` 会把「没记录」伪装成「零次归零」，
    读者会以为这段数据完整可信。实测：顶层 None 的 15 s 档，域 1 里明确写着 1 次。
    """
    v = p.get("counter_resets")
    if v is not None:
        return v
    dom = (p.get("domains") or {}).get(str(p.get("card_domain")))
    return (dom or {}).get("counter_resets")


def detect_card(tag, override=None):
    """从 tag 名判断测的是哪张卡。判不出来就报错——**不静默用默认卡**。"""
    if override:
        if override not in CARDS:
            raise SystemExit("未知 --card: %s（可选 %s）" % (override, sorted(CARDS)))
        return override
    low = tag.lower()
    for key in ("b50", "b60", "b65", "b70"):
        if key in low:
            return key
    raise SystemExit(
        "[ERR] 从 tag %r 判断不出板卡型号，拒绝迁移——"
        "用 --card 显式指定（可选 %s）。静默套用默认卡会把型号写错。" % (tag, sorted(CARDS))
    )


def infer_reserve(tag):
    """从 tag 名推断 --reserve-vram。bench_h3.py 默认 5，rsv9 组显式传 9。"""
    import re
    m = re.search(r"rsv(\d+)", tag)
    return int(m.group(1)) if m else 5


def summarize(runs):
    ok = [r["server_sec"] for r in runs if r.get("ok") and r.get("server_sec")]
    bad = [r for r in runs if not r.get("ok")]
    s = {"n_total": len(runs), "n_ok": len(ok), "n_fail": len(bad)}
    if ok:
        s["server_sec_mean"] = round(sum(ok) / len(ok), 2)
        s["server_sec_min"] = round(min(ok), 2)
        s["server_sec_max"] = round(max(ok), 2)
    return s


def _resolution_fields(duration):
    """分辨率维度——**必须随数据落盘，否则数字没有量纲**。

    来源是采集工作流的两个节点（`MiniMax_H3_低显存修复.json`）：
      节点 115 `ResolutionSelector` = 16:9 / 0.4 MP / 32 的倍数 → 864×480
      节点 134 `ComfyMathExpression` 由 duration 推帧数（17k+5 网格）
    两个推导与 backfill_resolution.py 共用实现，避免公式在两处漂移。

    标 `inferred`：分辨率不在原始采集 JSON 里，是按工作流重建的。
    """
    if not duration:
        return {}
    w, h = wh_for(SEL_MP, SEL_MULT, ASPECT)
    fr = frames_for(duration)
    return {
        "width": w,
        "height": h,
        "frames": fr,
        "fps": FPS,
        "resolution": "%dx%d" % (w, h),
        "selector_megapixels": SEL_MP,
        "duration_sec_exact": round(fr / FPS, 3),
    }


def convert(src, card_override=None, dry_run=False):
    d = json.load(open(src, encoding="utf-8"))
    tag = d.get("tag") or Path(src).stem
    runs = d.get("runs", [])
    if not runs:
        return None

    mtime = dt.date.fromtimestamp(os.path.getmtime(src)).isoformat()
    reserve = infer_reserve(tag)
    steps = sorted({r.get("steps") for r in runs if r.get("steps")})
    card_key = detect_card(tag, card_override)
    card = CARDS[card_key]

    record = {
        "schema": SCHEMA,
        "tag": "comfyui-h3-%s" % tag,
        "date": mtime,
        "source": "local",
        "domain": "comfyui-video",
        "tool": "bench_h3.py + ComfyUI /prompt + /history",
        "status": "active",
        # env_confidence 放在 env 内——与本仓库其它 schema（arc-xpu-bench/1 等）
        # 以及 registry_audit.py 的读法一致。曾误放在记录级，导致同一份记录里
        # 出现两份 env_confidence（2026-10-16 修正）。
        "env": dict(RIG, **card, env_confidence={
            "gpu": "recorded",
            "chip": "recorded",
            "subsys": "recorded",
            "device_id": "recorded",
            "board_vendor": "recorded",
            "driver": "recorded",
            "vram_visible_gib": "recorded",
            "ecc": "recorded",
            "cpu": "recorded",
            "ram_gb": "recorded",
            "envvars": "recorded",
            "reserve_vram_gb": "inferred",
            "steps": "recorded",
            "duration_sec": "recorded",
            "resolution": "inferred",
            "width": "inferred",
            "height": "inferred",
            "frames": "inferred",
            "fps": "inferred",
        }),
        "envvars": dict(BASE_ENV),
        "workload": {
            "model": "MiniMax H3 (DiT + Qwen3VL 32B nvfp4 文本编码器)",
            "task": "image-to-video",
            "steps": steps,
            "duration_sec": d.get("duration"),
            "text_encoder_quant": "qwen3vl_32b_minimax_h3_nvfp4_awq",
            **_resolution_fields(d.get("duration")),
        },
        "mode": d.get("mode"),
        "reserve_vram_gb": reserve,
        "samples": [
            {
                "steps": r.get("steps"),
                "round": r.get("round"),
                "seed": r.get("seed"),
                "ok": bool(r.get("ok")),
                "server_sec": r.get("server_sec"),
                "loads_delta": r.get("loads_delta"),
                "prompt_len": len(r.get("prompt") or ""),
            }
            for r in runs
        ],
        "summary": summarize(runs),
        "notes": (
            "口径：服务端 execution_start → execution_success，不含排队；"
            "fresh 模式每条换提示词以强制重载文本编码。"
            "板卡身份按 tag 判定并查 CARDS 表（AIB 口径，不硬编码单卡）；"
            "环境字段中 reserve_vram_gb 由 tag 名推断（默认 5，rsv9 为 9），"
            "原始数据未逐组记录 env，其余按 bench_h3.py BASE_ENV 补齐。"
        ),
    }

    if d.get("mode") == "fresh":
        record["notes"] += (
            " fresh 口径的固有风险：换提示词触发卸载/重装，同一服务器会话第 2~3 条"
            "易 DEVICE_LOST（bench_h3.py 注释已实锤），故多数组只有第 1 条成功——"
            "失败样本保留不删，按口径视为该组的有效约束而非成绩。"
        )

    return record


def convert_jsonl(path, card_override=None, dry_run=False):
    """把 `bench_f_h3_<tag>.jsonl`（2026-10-17 分辨率扫描）转成 schema 记录。

    与旧 `bench_*_fresh.json` 的两处差异必须处理：
      · 逐条增量（一个 tag 一个文件，多条记录）
      · **字段是 `mode`（cold/fresh）不是 `role`**
    """
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    if not rows:
        return None
    tag = rows[0].get("tag") or "h3"
    # tag 形如 h3_1280x720_b50scan → 分辨率从 tag 里取
    m = re.search(r"(\d+)x(\d+)", tag)
    w, h = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    # ⚠️ 这里曾写死 `"b50" if "b50" in tag else None` —— B70 的 H3 数据因此全部报
    # 「无法判定卡型」。判得出卡型却只认一张卡，比判不出更坏。统一走 detect_card。
    card = detect_card(tag, card_override)
    cinfo = CARDS[card]
    ok = [r for r in rows if r.get("ok") and r.get("server_sec")]
    summary = {"n_total": len(rows), "n_ok": len(ok),
               "n_fail": len(rows) - len(ok),
               "server_sec_mean": round(sum(r["server_sec"] for r in ok) / len(ok), 2)
               if ok else None}
    # 功耗汇总：只统计**真的采到了**的轮次；一条都没采到就留 None（不是 0）
    _pw = [r["power"] for r in ok
           if isinstance(r.get("power"), dict) and r["power"].get("avg_w") is not None]
    if _pw:
        summary["power"] = {
            "basis": "整卡电源域 · 能耗计数器求差 · 均值覆盖整轮（含装载）",
            "card_domain": _pw[0].get("card_domain"),
            "card_limit_mw": _pw[0].get("card_limit_mw"),
            "n_rounds": len(_pw),
            "avg_w_min": min(p["avg_w"] for p in _pw),
            "avg_w_max": max(p["avg_w"] for p in _pw),
            # P90 = 90% 的 1 s 窗口都不超过的功率。**判断「这档有没有把卡压满」看它**，
            # 不要看 avg_w：装载主导的档位 avg 会被磁盘段拉低一半以上。
            "p90_w_min": min(p.get("p90_w") or 0 for p in _pw),
            "p90_w_max": max(p.get("p90_w") or 0 for p in _pw),
            "peak_w_max": max(p.get("peak_w", 0) for p in _pw),
            "peak_basis": "1s",
            "energy_j_max": max(p.get("energy_j", 0) for p in _pw),
            # 能耗计数器归零次数（整卡域）。>0 说明该窗口经历过重置 ——
            # 我们的积分法不受影响，但读者要能看见它，才知道这段可不可信。
            "counter_resets_max": (max(_r) if (_r := [x for x in (pw_resets(p) for p in _pw)
                                                     if x is not None]) else None),
            # 占空比 = 整轮里 1 s 窗口 ≥ 80% 功率上限的比例（无需推断相位）
            "busy_share_mean": round(
                sum(p.get("busy_share") or 0 for p in _pw) / len(_pw), 3),
        }
    else:
        summary["power"] = None
    #⚠️ `sampling_sec` 必须单独抽成**数值**字段（2026-10-17 补）：
    # 采集器只给了 `last_sit`（'179.82 s/it' 字符串），而取证脚本要靠
    # **采样段耗时**跟日志里的轮次配对——H3 这套的 `Prompt executed`
    # 与 `server_sec` 不同口径（前者只算节点执行，差 1200 s 以上），
    # 只有采样段耗时是同源的。没有这个字段 → 取证必然匹配不上。
    def _sit(r):
        """把 '179.82 s/it' 解析成 (总秒, 每步秒)。解析不了就留 None，不猜。"""
        v = r.get("last_sit")
        if not v:
            return (None, None)
        m = re.search(r"([\d.]+)\s*s/it", str(v))
        if not m:
            return (None, None)
        per = float(m.group(1))
        n = r.get("steps") or 6
        return (round(per * n, 2), per)

    samples = []
    for r in rows:
        samp, per = _sit(r)
        samples.append({"mode": r.get("mode"), "ok": r.get("ok"),
                        "server_sec": r.get("server_sec"),
                        "last_sit": r.get("last_sit"),
                        # 采样段耗时（数值）——取证配对用；`steps` 缺时按 6 步算
                        "sampling_sec": samp,
                        "sampling_sec_per_step": per,
                        "n_load": r.get("n_load"),
                        "vram_post_gib": r.get("vram_post"),
                        # 整卡功耗（2026-10-19 起采集器默认采）：None = 未采集，
                        # 不是 0。跨批次比较前先确认这一项不是 None。
                        "power": r.get("power")})
    date = dt.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    # ⚠️ steps / duration / frames **必须从记录里读**，不能写死 6 步 5 秒。
    # 2026-10-17 那批扫描全是 6 步 5 s，写死看不出问题；一旦接入时长维度
    # （10 s / 15 s 档）就会把 705 s 的数据标成 5 s —— 结论直接错。
    r0 = rows[0]
    steps = r0.get("steps") or 6
    dur = r0.get("duration") or 5.0
    nfr = r0.get("frames") or frames_for(dur)
    # `selector_megapixels` 记的是**工作流里 ResolutionSelector 的标称值**（0.4 MP），
    # 不是 w×h/1024²：864×480 折算只有 0.3956（宽高被 round 到 32 的倍数）。
    # 只有分辨率正好是从标称值推导出来的那一组才填，其余（按 tag 手填的分辨率）
    # 无法反推标称值 → 留 None，别拿折算值冒充。
    _w0, _h0 = wh_for(SEL_MP, SEL_MULT, ASPECT)
    sel_mp = SEL_MP if (w, h) == (_w0, _h0) else None
    wl = {"model": "MiniMax H3", "task": "image-to-video",
          "steps": steps, "duration_sec": dur, "frames": nfr, "fps": FPS,
          "duration_sec_exact": round(nfr / FPS, 3),
          "selector_megapixels": sel_mp,
          "width": w, "height": h,
          "resolution": ("%dx%d" % (w, h)) if w else None,
          "dit_file": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
          "text_encoder_file": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
          "sampler": "euler", "scheduler": "simple"}
    env = {"gpu": cinfo["gpu"], "chip": cinfo["chip"], "subsys": cinfo["subsys"],
           "device_id": cinfo["device_id"], "board_vendor": cinfo["board_vendor"],
           "board_code": cinfo["board_code"],
           "vram_visible_gib": cinfo["vram_visible_gib"], "ecc": "off",
           "driver": cinfo["driver"], "cpu": "AMD Ryzen 5 9600X",
           "ram_gb": 32, "os": "Windows",
           # ⚠️ **这一批与仓库里其它 H3 记录不同栈**：attention backend 强制 SDPA
           # （CUTE 开着跑 H3 音频封装必崩，`avcodec_send_frame() returned 22`），
           # torch 2.12 / kernel torch212。**不可与 10-14 那批（torch213 / CUTE）并排引用。**
           "attention_backend": "sdpa (CUTE 关闭；CUTE 开着跑 H3 音频封装必崩)",
           "stack_variant": "int8fix",
           "int8fix_env": {"OMNIXPU_INT8_COMPUTE": "1", "OMNIXPU_INT8_SIGFIX": "1"},
           "env_confidence": {"gpu": "recorded", "vram_visible_gib": "recorded",
                              "ecc": "recorded", "cpu": "recorded",
                              "ram_gb": "recorded", "os": "recorded",
                              "width": "recorded", "height": "recorded",
                              "resolution": "recorded", "steps": "recorded",
                              "attention_backend": "recorded",
                              "chip": "inferred", "subsys": "inferred",
                              "device_id": "inferred", "board_vendor": "inferred",
                              "board_code": "inferred", "driver": "inferred",
                              "reserve_vram_gb": "inferred"}}
    return {"schema": "comfyui-xpu-bench/1", "domain": "comfyui-video",
            "date": date, "tag": tag,
            "status": "active" if ok else "discarded",
            "source": "local",
            "tool": "bench_f_h3.py + ComfyUI /prompt + /history",
            "batch": "B50 出视频分辨率天花板扫描（cold 单轮）",
            "samples": samples, "summary": summary, "workload": wl, "env": env,
            "log_evidence": {"status": "pending",
                             "note": "日志在 `_bench_f/server_<tag>.log`，"
                                     "取证回填待跑 annotate_comfy_evidence.py"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="_ab_logs 目录")
    ap.add_argument("--outdir", required=True, help="输出目录（bench/data）")
    ap.add_argument("--card", default=None,
                    help="强制指定板卡（b50/b70）。默认从 tag 判定；判不出就报错")
    ap.add_argument("--only", default=None,
                    help="只处理文件名含该子串的源文件（增量迁移用，避免重写历史记录）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # 两种源格式：
    #   ① bench_*_fresh.json —— 10-14 那批（合并的 JSON，一个文件含多组）
    #   ② bench_f_h3_<tag>.jsonl —— 2026-10-17 的分辨率扫描（逐条增量，
    #      **字段名是 `mode` 不是 `role`**，且带 width/height）
    files = sorted(glob.glob(os.path.join(a.src, "bench_*_fresh.json")))
    jsonl_files = sorted(glob.glob(os.path.join(a.src, "bench_f_h3_*.jsonl")))
    if a.only:
        files = [f for f in files if a.only in os.path.basename(f)]
        jsonl_files = [f for f in jsonl_files if a.only in os.path.basename(f)]
    if not files and not jsonl_files:
        print("[ERR] %s 下没找到 bench_*_fresh.json 或 bench_f_h3_*.jsonl" % a.src)
        return 1

    outdir = Path(a.outdir)
    if not a.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)

    n = 0
    for jf in jsonl_files:
        rec = convert_jsonl(jf, card_override=a.card, dry_run=a.dry_run)
        if rec is None:
            print("[skip] %s（无 cold 记录）" % os.path.basename(jf))
            continue
        out = outdir / ("%s_%s.json" % (rec["date"], rec["tag"]))
        print("%-52s -> %s" % (os.path.basename(jf), out.name))
        print("      card=%s %s×%s steps=%s | ok=%d fail=%d mean=%s" % (
            rec["env"]["gpu"], rec["workload"].get("width"),
            rec["workload"].get("height"), rec["workload"]["steps"],
            rec["summary"]["n_ok"], rec["summary"]["n_fail"],
            rec["summary"].get("server_sec_mean")))
        if not a.dry_run:
            out.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        n += 1
    for f in files:
        rec = convert(f, card_override=a.card, dry_run=a.dry_run)
        if rec is None:
            print("[skip] %s（无 runs）" % os.path.basename(f))
            continue
        out = outdir / ("%s_%s.json" % (rec["date"], rec["tag"]))
        print("%-52s -> %s" % (os.path.basename(f), out.name))
        print("      card=%s chip=%s subsys=%s | steps=%s mode=%s rsv=%s | ok=%d fail=%d mean=%s" % (
            rec["env"]["gpu"], rec["env"]["chip"], rec["env"]["subsys"],
            rec["workload"]["steps"], rec["mode"], rec["reserve_vram_gb"],
            rec["summary"]["n_ok"], rec["summary"]["n_fail"],
            rec["summary"].get("server_sec_mean")))
        if not a.dry_run:
            out.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        n += 1

    print("\n[OK] 处理 %d 组%s" % (n, "（dry-run，未写盘）" if a.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
