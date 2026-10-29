"""给历史记录补 env.slot（槽位）字段。

背景：`env.slot` 是「环境必填口径」之一（见 docs/test-registry.md §3 命名规范与
bench/README.md 第 1 节），但 2026-10-16 之前几乎没落盘——槽位信息只留在**文件名**
（`...-pcie4x4-ncmoe8.json` / `...-pcie5x8-...`）。

**只补能确定性映射的，绝不猜。** 映射依据（docs/slot-comparison.md §1「测试条件」表 +
docs/test-rig.md 拓扑取证）：

    pcie5x8 -> PCIE1  CPU 直连，物理 PCIe 5.0 x16，B50 实际协商 x8
    pcie4x4 -> PCIE2  芯片组挂，物理 PCIe 4.0 x4，B50 协商 x4

为什么标 inferred：槽位是**靠文件名 token 重建**的，不是采集当时写进记录的。
按仓库纪律，重建值不伪装成 recorded，并写入 env_backfill 说明依据。

**不补的两类（登记为「不可判定」，见 docs/test-registry.md §6 第 8 条）**：
  1. 文件名里没有 pcie token 的 B50 记录（`iq2m-ctx_*` / `q3ks-ctx_*` 等 21 条）
     —— 2026-10-15 那天在主槽/副槽都跑过，事后无法从记录内区分。
  2. 无 token 的 B70 / ComfyUI 记录 —— 「哪张卡在哪个槽」已被用户定为
     **不作为结论依据**（见 docs/test-registry.md §6 第 16 条），不做推断。

反例检查过、**不可用**的旁证：`env.device_selector`（opencl:0 / opencl:1）。
它看似与槽位相关（pcie5x8 全部 opencl:0、副槽多数 opencl:1），但
`-alone-` 系列 8 条（B70 拔掉、B50 单独在机）在**副槽**也报 opencl:0 ——
枚举号随「在机卡数」翻转，**不是槽位的函数**，故不采用。

用法：
    python bench/harness/backfill_slot.py --dry-run   # 只看计划，不写
    python bench/harness/backfill_slot.py             # 实际写入
"""
import json
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "bench", "data")

# 文件名 token -> (env.slot 值, 口径依据)
# 卡名用 B50 是因为带 token 的记录全部是 B50（脚本仍会按 env.gpu 复核）
SLOT = {
    "pcie5x8": "PCIE1 (CPU-attached x16, B50 negotiates x8)",
    "pcie4x4": "PCIE2 (chipset-attached x4, B50 negotiates x4)",
}

# 采集当时就写了 slot、但分隔符是中文逗号的 1 条（2026-10-15 vl4b 基线），
# 与另外 12 条英文逗号不一致 -> 只归一标点，不改语义。
CANON = {
    "PCIE1 (CPU-attached x16，B50 协商 x8)": "PCIE1 (CPU-attached x16, B50 negotiates x8)",
}

NOTE = (
    "env.slot 为 2026-10-16 backfill 补写，标 inferred：槽位在采集当时未落盘，"
    "由**文件名 token** 重建（pcie5x8 -> PCIE1 CPU 直连 x8；pcie4x4 -> PCIE2 芯片组 x4）。"
    "口径依据：docs/slot-comparison.md §1「测试条件」表 + docs/test-rig.md 的 PCIe 拓扑取证。"
    "注：env.device_selector 不可作槽位旁证——B50 单独在机时副槽也报 opencl:0。"
)


def main():
    dry = "--dry-run" in sys.argv
    changed = skipped = undet = canon = 0
    undet_list = []

    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        name = os.path.basename(f)
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        env = d.setdefault("env", {})
        old = env.get("slot")

        # 已有 slot：只做标点归一（若命中 CANON），否则跳过
        if old:
            if old in CANON:
                env["slot"] = CANON[old]
                note = ("env.slot 的值与另外 12 条不一致（中文逗号 + 「协商」），"
                        "2026-10-16 归一为英文逗号写法，仅标点、不改语义。")
                d["env_backfill"] = (d["env_backfill"] + " " + note
                                     if d.get("env_backfill") else note)
                if not dry:
                    _write(f, d)
                canon += 1
                print("[canon] %-56s -> %s" % (name, env["slot"]))
            else:
                skipped += 1
            continue

        # 判定 token
        tok = "pcie5x8" if "pcie5x8" in name else ("pcie4x4" if "pcie4x4" in name else None)
        if tok is None:
            undet += 1
            undet_list.append(name)
            continue

        env["slot"] = SLOT[tok]
        conf = env.setdefault("env_confidence", {})
        conf["slot"] = "inferred"
        d["env_backfill"] = (d["env_backfill"] + " " + NOTE
                             if d.get("env_backfill") else NOTE)
        if not dry:
            _write(f, d)
        changed += 1
        print("[fix ] %-56s %-7s -> %s" % (name, tok, env["slot"]))

    print("\n%s：补写 %d 条 | 归一标点 %d 条 | 已有 slot 跳过 %d 条 | 不可判定 %d 条"
          % ("[dry-run 未落盘]" if dry else "[已落盘]", changed, canon, skipped, undet))
    if undet_list:
        print("\n不可判定（文件名无 pcie token，不猜）：")
        for u in undet_list:
            print("   ", u)


def _write(path, d):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
