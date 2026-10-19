"""迁移 2026-10-14/15 的 ComfyUI 0.39 升级 A/B 数据（**内核配对实验**）。

为什么需要单独的迁移器：这批数据的 tag 后缀编码的是
`（内核/注意力后端）`，而不是 `migrate_comfy_media.py` 认识的
`b50` / `b70` + `int8fix` / `sigfix` 组合：

    q21_int8_convrot_039t212   → 0.39 新栈 + torch212 内核
    q21_int8_convrot_039cute   → 同上 + CUTE 注意力
    krea2_int8_convrot_039cute4
    q21_bf16_c3C / c3S         → clean3 A/B 的 CUTE / SDPA 两组

**这批数据回答的是本项目最关键的一个问题**：
「同一张卡、同一套 ComfyUI，int8 到底快不快」。
答案是**取决于内核变体**——torch213.bmg 的 int8 GEMM 慢近一倍，
换 torch212.bmg 后 Qwen-Image 2.1 的 int8 快 1.78×，而 bf16 分毫未动。

⚠️ 三条落盘纪律：
  1. **内核变体与注意力后端必须逐字段落盘**（`env.kernel_variant` /
     `env.attention_backend`）——它们就是本批数据的唯一变量，
     丢了就还原不了这批实验。
  2. **拿不到日志的批一律标 `log_evidence.status = "missing"`**，
     不假装取证做过（这批的 boot 日志在 `_upgrade/boot_*.log`，
     与 sweep 日志不同源，且多数已被覆盖）。
  3. **Music 3 的 `new_song` 全组失败按规范标 `discarded` 记录的原因**，
     不当采集失误删掉——那是 0.39 栈的已知容量墙。
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

SCHEMA = "comfyui-xpu-bench/1"

# ── 模型与体积（字节数取自模型文件实际大小，与 migrate_comfy_media.py 同源）──
MODELS = {
    "q21": {
        "name": "Qwen-Image 2.1", "domain": "comfyui-image", "task": "text-to-image",
        "res": (1280, 720), "steps": 25, "cfg": 1.0,
        "dit": {"bf16": ("qwen_image_2.1_bf16.safetensors", 14230280616),
                "int8_convrot": ("qwen_image_2.1_int8_convrot.safetensors", 7256783064)},
        "text_encoder": ("qwen3vl_8b_int8_convrot.safetensors", 9350798360),
        "vae": ("qwen_image_2.1_vae_bf16.safetensors", 675509688),
        "seeds": {"first": 701, "resident": [702, 703], "newprompt": 704},
    },
    "krea2": {
        "name": "Krea-2 Turbo", "domain": "comfyui-image", "task": "text-to-image",
        "res": (1024, 1024), "steps": 8, "cfg": 1.0,
        "dit": {"bf16": ("krea2_turbo_bf16.safetensors", 26283332608),
                "int8_convrot": ("krea2_turbo_int8_convrot.safetensors", 13492686496)},
        "text_encoder": ("qwen3vl_4b_bf16.safetensors", 8875719384),
        "vae": ("qwen_image_vae.safetensors", 253806246),
        "seeds": {"first": 401, "resident": [402, 403], "newprompt": 404},
    },
    "music3": {
        "name": "MiniMax Music 3", "domain": "comfyui-audio", "task": "text-to-music",
        "res": None, "steps": 30, "cfg": 1.7, "seconds": 120.0,
        "dit": {"fp16": ("minimax_music3_dit_fp16.safetensors", 4914078208),
                "int8_convrot": ("minimax_music3_dit_int8_convrot.safetensors", 2501707264)},
        "text_encoder": ("minimax_music3_text_encoder_pruned_bf16.safetensors", 16704231168),
        "vae": ("minimax_music3_dav.safetensors", 216615936),
        "seeds": {"first": 601, "resident": [602], "new_song": 3001},
    },
    "h3": {
        "name": "MiniMax H3", "domain": "comfyui-video", "task": "image-to-video",
        "res": (864, 480), "steps": 6, "cfg": None,
        "dit": {"int8_convrot": ("minimax_h3_fl2va_pruned_int8_convrot.safetensors", 20961138560)},
        "text_encoder": ("qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", 14960219904),
        "vae": ("minimax_h3_video_vae_fp16.safetensors", 4966189056),
        "seeds": {},
    },
}

GIB = 1024 ** 3

# ── 采集机的固定事实 ──
RIG = {"cpu": "AMD Ryzen 5 9600X", "ram_gb": 32, "os": "Windows"}
CARD_B70 = {
    "gpu": "Intel Arc Pro B70 32G", "chip": "E223", "subsys": "27421EF7",
    "device_id": "PCI\\VEN_8086&DEV_E223&SUBSYS_27421EF7&REV_00",
    "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)", "board_code": "2742",
    "vram_visible_gib": 31.16, "ecc": "off", "driver": "32.0.101.8976",
}

# ── tag 后缀 → (内核变体, 注意力后端) ──
# 依据：各批的 `boot_*.log` 里的 `omni_xpu_kernel` 与 `OMNI_ATTN_BACKEND`。
# 推断值一律 inferred 并写明依据；取不到就不填，绝不猜。
VARIANTS = {
    "039t212": {"kernel_variant": "omni_xpu_kernel 0.2.0b2+torch212.bmg",
                "attention_backend": "inferred: 未留 boot 日志，按同批其它文件推定为默认 SDPA"},
    "039cute": {"kernel_variant": "omni_xpu_kernel 0.2.0b2+torch212.bmg",
                "attention_backend": "cute (OMNI_ATTN_BACKEND=cute)",
                "note": "日志自带 last_sit / n_load，取值完整"},
    "039cute4": {"kernel_variant": "omni_xpu_kernel 0.2.0b2+torch212.bmg",
                 "attention_backend": "cute (OMNI_ATTN_BACKEND=cute)",
                 "note": "第三轮 cute，取值完整"},
    "c3C": {"kernel_variant": "omni_xpu_kernel 0.2.0b2+torch212.bmg",
            "attention_backend": "cute", "note": "clean3 A/B 的 CUTE 组"},
    "c3S": {"kernel_variant": "omni_xpu_kernel 0.2.0b2+torch212.bmg",
            "attention_backend": "sdpa", "note": "clean3 A/B 的 SDPA 组"},
    "039": {"kernel_variant": "omni_xpu_kernel 0.2.0b2+torch212.bmg",
            "attention_backend": "inferred: 未留 boot 日志"},
    "": {"kernel_variant": "omni_xpu_kernel 0.2.0b2+torch212.bmg",
         "attention_backend": "inferred: 未留 boot 日志"},
}

STACK = {
    "app": "ComfyUI", "app_version": "0.39.0",
    "comfy_kitchen": "0.2.37", "comfy_kitchen_xpu_runtime": "0.2.33",
    "backend": "XPU (SYCL)",
    # 这批全部是 0.39 栈 + omni_int8fix.py 已装（能力声明 + 签名适配）
    "stack_variant": "int8fix",
    "int8fix_env": {"OMNIXPU_INT8_COMPUTE": "1", "OMNIXPU_INT8_SIGFIX": "1"},
    "comfyui_patch": "OMNIXPU_INT8_COMPUTE=1（能力声明）+ 签名适配",
    "comfyui_patch_note": (
        "0.39 的 supports_int8_compute() 对 is_intel_xpu() 硬编码 return False，"
        "且 ComfyUI-OmniXPU 把 comfy_kitchen 路由到 vendored 0.2.33 快照（8 参），"
        "而 0.39 按 12 参契约调用 —— 两处都要补，缺一不可。"
        "**与 2026-10-14 那批（torch213 内核 / 无 int8fix）不是同一栈。**"
    ),
    "stack_note": (
        "本批来自 2026-10-14/15 的 0.39 升级 A/B（`_upgrade/`），"
        "全部带 omni_int8fix 且用 **torch212.bmg 内核**；"
        "仓库里 2026-10-14 那批 B70 出图数据是 **torch213.bmg 内核**，"
        "**两者不可并排引用**——内核变体就是本实验的唯一变量。"
    ),
}

# 每个 jsonl 对应哪批（tag 前缀在文件里混着不同模型，按 tag 里的模型段分组）
FILES = {
    "sweep_039_fid.jsonl": ("b70", "2026-10-15", "torch212 内核首轮，全模型"),
    "smoke_039_q21fid.jsonl": ("b70", "2026-10-14", "torch212 内核 Qwen-Image 复测（比 sweep_039_fid 早一天）"),
    "sweep_039_cute.jsonl": ("b70", "2026-10-15", "CUTE 注意力"),
    "sweep_039_cute4.jsonl": ("b70", "2026-10-15", "CUTE 注意力第三轮（含 Krea-2 / Music 3）"),
    "sweep_clean3_cute.jsonl": ("b70", "2026-10-15", "clean3 A/B · CUTE"),
    "sweep_clean3_sdpa.jsonl": ("b70", "2026-10-15", "clean3 A/B · SDPA"),
    "smoke_039.jsonl": ("b70", "2026-10-15", "H3 冒烟（含 fresh/warm 口径）"),
    "smoke_039_qwen.jsonl": ("b70", "2026-10-14", "Qwen-Image 2.1 变体冒烟"),
}


def gib(n):
    return round(n / GIB, 3)


def split_tag(tag):
    """`q21_int8_convrot_039t212` → ('q21', 'int8_convrot', '039t212')

    H3 那批的 tag 是口径而不是量化档（`h3_480x864` / `h3_480x864_warm` /
    `h3_480x864_fresh` / `clean2_sdpa` / `clean3_sdpa`），
    统一归到 `('h3', 'int8_convrot', '039')`，**原始口径记进 `variant_tag`**。
    """
    parts = tag.split("_")
    if not parts:
        return None, None, "", ""
    if parts[0] == "h3" or tag.startswith("clean"):
        # H3 只有 int8 一个档（采集时就是 int8_convrot）
        return "h3", "int8_convrot", "039", tag
    key = parts[0]
    if key not in MODELS:
        return None, None, "", tag
    # 从右往左找变体段
    for i in range(len(parts) - 1, 0, -1):
        cand = "_".join(parts[i:])
        if cand in VARIANTS and cand:
            return key, "_".join(parts[1:i]), cand, tag
    return key, "_".join(parts[1:]), "", tag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="`_upgrade` 目录")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    outdir = Path(a.outdir)
    if not a.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)

    n = 0
    for fn, (card, date, desc) in FILES.items():
        p = os.path.join(a.src, fn)
        if not os.path.exists(p):
            print("[skip] 没有 %s" % fn)
            continue
        rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

        groups = {}
        for r in rows:
            key, quant, variant, raw = split_tag(r.get("tag", ""))
            if key is None or quant is None:
                print("[skip] 认不出 tag: %s (%s)" % (r.get("tag"), fn))
                continue
            r = dict(r, _raw_tag=raw)
            groups.setdefault((key, quant, variant), []).append(r)

        for (key, quant, variant), rs in sorted(groups.items()):
            m = MODELS[key]
            if quant not in m["dit"]:
                print("[skip] %s 没有 %s 档 (%s)" % (key, quant, fn))
                continue
            dit_file, dit_bytes = m["dit"][quant]
            te_file, te_bytes = m["text_encoder"]
            vae_file, vae_bytes = m["vae"]

            samples = []
            for r in rs:
                role = r.get("role")
                if role is None:
                    # H3 那批只有 tag，按其口径后缀补 role
                    raw = r.get("_raw_tag", "")
                    role = ("cold" if "warm" not in raw and "fresh" not in raw
                            else "warm" if "warm" in raw else "fresh")
                s = {"role": role, "ok": r.get("ok"),
                     "server_sec": r.get("server_sec"), "wall_sec": r.get("wall_sec"),
                     "tag_raw": r.get("_raw_tag")}
                if r.get("prompt_executed_s") is not None:
                    s["log_prompt_executed_s"] = r["prompt_executed_s"]
                for k in ("last_sit", "n_load", "n_offload", "oom", "device_lost"):
                    if r.get(k) is not None:
                        s[k] = r[k]
                seed = m["seeds"].get(r.get("role", ""))
                s["seed"] = seed[0] if isinstance(seed, list) else seed
                samples.append(s)

            ok = [s["server_sec"] for s in samples if s["ok"] and s["server_sec"]]
            summary = {"n_ok": len(ok), "n_fail": len(samples) - len(ok), "n_total": len(samples)}
            if ok:
                summary.update({"server_sec_mean": round(sum(ok) / len(ok), 2),
                                "server_sec_min": round(min(ok), 2),
                                "server_sec_max": round(max(ok), 2)})
            for role in ("first", "resident", "newprompt", "new_song",
                         "cold", "warm", "fresh"):
                v = [s["server_sec"] for s in samples
                     if s["role"] == role and s["ok"] and s["server_sec"]]
                if v:
                    summary["%s_sec_mean" % role] = round(sum(v) / len(v), 2)

            wl = {"model": m["name"], "task": m["task"], "steps": m["steps"],
                  "dit_file": dit_file, "dit_size_gib": gib(dit_bytes),
                  "text_encoder_file": te_file, "text_encoder_size_gib": gib(te_bytes),
                  "vae_file": vae_file, "vae_size_gib": gib(vae_bytes),
                  "sampler": "euler", "scheduler": "simple"}
            if m["res"]:
                wl["width"], wl["height"] = m["res"]
                wl["resolution"] = "%dx%d" % m["res"]
            if m.get("cfg") is not None:
                wl["cfg"] = m["cfg"]
            if m.get("seconds"):
                wl["seconds"] = m["seconds"]
            if key == "h3":
                # 0.39 栈的 H3：480×864 / 6 步 / 124 帧（工作流自带 17k+5 帧数网格）
                wl["frames"], wl["fps"] = 124, 24
                wl["duration_sec_exact"] = 5.167
                wl["selector_megapixels"] = 0.4
                env_hint = "recorded"   # 与仓库既有 H3 记录同口径

            env = dict(RIG, **CARD_B70)
            env.update(STACK)
            env.update(VARIANTS.get(variant, VARIANTS[""]))
            env["env_confidence"] = {
                "gpu": "recorded", "chip": "inferred", "subsys": "inferred",
                "device_id": "inferred", "board_vendor": "inferred",
                "board_code": "inferred", "driver": "inferred",
                "vram_visible_gib": "recorded", "ecc": "recorded",
                "ram_gb": "recorded", "cpu": "recorded", "os": "recorded",
                "app": "recorded", "app_version": "recorded",
                "comfy_kitchen": "recorded",
                "omni_xpu_kernel": "recorded",
                "comfy_kitchen_xpu_runtime": "inferred",
                "kernel_variant": "inferred",
                "attention_backend": "inferred",
                "reserve_vram_gb": "inferred",
                "steps": "recorded", "cfg": "recorded", "seed": "inferred",
            }
            if m["res"]:
                for k in ("width", "height", "resolution"):
                    env["env_confidence"][k] = "recorded"

            status = "active"
            discard = None
            if summary["n_ok"] == 0:
                status, discard = "discarded", "该组全部失败，无有效样本"
            elif any((s.get("role") == "new_song" and not s["ok"]) for s in samples):
                discard = ("`new_song`（换整首新歌）失败：0.39 栈的已知容量墙，"
                           "见升级说明 §6.5。其它角色有效，保留为 active")

            name = "%s_b70-32g_%s-%s-%s-comfyui.json" % (
                date, key, quant, variant or "039")
            rec = {
                "schema": SCHEMA, "domain": m["domain"], "status": status,
                "source": "local",
                "tool": "sweep_039*.py / smoke_039*.py + ComfyUI /prompt + /history",
                "batch": desc,
                "tag": "%s-%s" % (key, quant),
                "samples": samples, "summary": summary, "workload": wl, "env": env,
                # 这批的 boot/sweep 日志与 _upgrade/ 里的其它实验混在一起、
                # 且多数已被覆盖 —— 取证链不完整，如实登记，不假装做过。
                "log_evidence": {
                    "status": "missing",
                    "note": "原始日志在 `_upgrade/boot_*.log`，与本批 tag 不一一对应"
                            "且多份已被后续实验覆盖；未做逐条取证回填。"
                            "**因此本批的时间分解（采样段 / 固定开销）不可用。**",
                },
                "note": ("本批的唯一实验变量是**内核变体与注意力后端**；"
                         "与仓库里 2026-10-14 的 B70 出图记录（torch213.bmg、无 int8fix）"
                         "**不可并排引用**。"),
            }
            if discard:
                rec["discard_reason"] = discard

            print("%-28s -> %-52s %s | ok=%d/%d%s"
                  % (fn, name, status, summary["n_ok"], summary["n_total"],
                     " mean=%s" % summary.get("server_sec_mean") if ok else ""))
            if not a.dry_run:
                tgt = outdir / name
                if tgt.exists():
                    print("   [!] 已存在，未覆盖：%s" % name)
                else:
                    tgt.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            n += 1

    print("\n[%s] 生成 %d 条记录" % ("dry-run 未落盘" if a.dry_run else "OK", n))
    return 0


if __name__ == "__main__":
    sys.exit(main())