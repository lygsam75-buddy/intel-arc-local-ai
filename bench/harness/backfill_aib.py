"""给历史 ComfyUI 记录补 AIB 身份字段（chip / subsys / device_id / board_vendor）。

背景：2026-10-16 起，项目把「板卡身份」列为必填口径（Intel 走 AIB 模式，
同型号不同板厂的板子性能未必一致，见 docs/test-rig.md 与 bench/README.md）。
2026-10-16 之前迁入的记录没有这四个字段。

**标 inferred，不标 recorded**——这些身份是 2026-10-16 从注册表
`HKLM\\...\\Enum\\PCI` 取证的，不是采集当时逐条落盘的。按仓库纪律，
推断值绝不伪装成实测，并写入 env_backfill 说明依据。

只动 comfyui-xpu-bench/1 的记录；已有该字段的记录跳过。
"""
import json, glob, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "bench", "data")

# 卡名 -> AIB 身份（来源：bench/harness/gpu_identity.py 2026-10-16 实测）
AIB = {
    "Intel Arc Pro B70 32G": {
        "chip": "E223",
        "subsys": "27421EF7",
        "device_id": "PCI\\VEN_8086&DEV_E223&SUBSYS_27421EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
    },
    "Intel Arc Pro B50 LP 16G": {
        "chip": "E212",
        "subsys": "25221EF7",
        "device_id": "PCI\\VEN_8086&DEV_E212&SUBSYS_25221EF7&REV_00",
        "board_vendor": "GUNNIR 蓝戟 (PCI vendor 1EF7)",
    },
}

NOTE = (
    "chip/subsys/device_id/board_vendor 四项为 2026-10-16 backfill 补写，标 inferred："
    "采集当时未落盘，身份由注册表 PCI 枚举取证（bench/harness/gpu_identity.py，"
    "见 docs/test-rig.md 的 AIB 身份表）。同一台机器、同一块物理卡，"
    "故该身份对本机全部历史记录成立。"
)

changed = skipped = 0
for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
    with open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("schema") != "comfyui-xpu-bench/1":
        continue
    env = d.setdefault("env", {})
    if env.get("subsys"):
        skipped += 1
        continue
    gpu = env.get("gpu")
    if gpu not in AIB:
        print("[skip] %s —— env.gpu=%r 不在 AIB 表里" % (os.path.basename(f), gpu))
        continue
    env.update(AIB[gpu])
    conf = env.setdefault("env_confidence", {})
    for k in ("chip", "subsys", "device_id", "board_vendor"):
        conf[k] = "inferred"
    old = d.get("env_backfill")
    d["env_backfill"] = (old + " " + NOTE) if old else NOTE
    with open(f, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    changed += 1
    print("[fix ] %-48s %s/%s" % (os.path.basename(f), AIB[gpu]["chip"], AIB[gpu]["subsys"]))

print("\n[OK] 补写 %d 条，跳过（已有身份）%d 条" % (changed, skipped))
