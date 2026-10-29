"""汇总 bench/data 全部 JSON，产出备案台账用的覆盖矩阵（只读，不写任何文件）。"""
import json, glob, os, collections

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
data_dir = os.path.join(root, "bench", "data")
files = sorted(glob.glob(os.path.join(data_dir, "*.json")))
print(f"total files: {len(files)}\n")

schemas = collections.Counter()
statuses = collections.Counter()
gpus = collections.Counter()
models = collections.Counter()
quants = collections.Counter()
domains = collections.Counter()
tools = collections.Counter()
sources = collections.Counter()
rows = []

for f in files:
    with open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    name = os.path.basename(f)
    sc = d.get("schema", "?")
    schemas[sc] += 1
    st = d.get("status", "active")
    statuses[st] += 1
    sources[d.get("source", "?")] += 1
    env = d.get("env", {}) or {}
    gpu = env.get("gpu") or d.get("gpu") or "(comfyui/compat)"
    gpus[gpu] += 1
    model = d.get("model", {}) or {}
    mname = model.get("name") or d.get("domain") or "?"
    mquant = model.get("quant") or "-"
    models[mname] += 1
    quants[mquant] += 1
    domains[d.get("domain", "-")] += 1
    tools[d.get("tool", env.get("tool", "-"))] += 1
    tag = d.get("tag", name)
    date = d.get("date", name.split("_")[0])
    n = len(d.get("samples", []) or [])
    rows.append((date, gpu, mname, mquant, sc, st, n, tag, name))

print("== schema ==");      [print(f"  {k}: {v}") for k, v in schemas.most_common()]
print("== status ==");      [print(f"  {k}: {v}") for k, v in statuses.most_common()]
print("== source ==");      [print(f"  {k}: {v}") for k, v in sources.most_common()]
print("== gpu ==");         [print(f"  {k}: {v}") for k, v in gpus.most_common()]
print("== model ==");       [print(f"  {k}: {v}") for k, v in models.most_common()]
print("== quant ==");       [print(f"  {k}: {v}") for k, v in quants.most_common()]
print("== domain ==");      [print(f"  {k}: {v}") for k, v in domains.most_common()]
print("== tool ==");        [print(f"  {k}: {v}") for k, v in tools.most_common()]

# --- 取证覆盖率（2026-10-16 起）------------------------------------------
# 门禁作用：只看总时长的记录无法归因（卡慢 / 装不下 / 栈变了混成一个数），
# ComfyUI 口径的日志还在就应该回填出 timing_breakdown。缺的要能一眼看见。
# ⚠️ 这里曾写 `"comfyui" in os.path.basename(f)` —— H3 那批文件名是
# `2026-10-19_h3_1280x720_b70pw.json`，**不含 "comfyui" 这个词**，于是 27 条
# comfyui-video 记录从来没被审计到（功耗覆盖率也一起漏）。与 annotate 同一个教训：
# **判范围要按内容（schema），不要按文件名。**
def _is_comfy(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("schema") == "comfyui-xpu-bench/1"
    except (OSError, ValueError):
        return False


comfy = [f for f in files if _is_comfy(f)]
n_tb = n_ev = 0
missing = []
allfail = []          # 样本全失败 → 日志里没有执行记录，取证**不可能有**，不是漏填
inferred_total = collections.Counter()
ev_status = collections.Counter()
LOST = []             # 有跑成功的轮次，但日志已找不到 → 时间分解永久缺失（不可事后补）
for f in comfy:
    with open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("timing_breakdown"):
        n_tb += 1
    elif any((s.get("ok") and s.get("server_sec")) for s in (d.get("samples") or [])):
        missing.append(os.path.basename(f))
    else:
        # 没有任何一轮成功跑完 → 不报告警。硬报成「该回填却没回填」会让真缺口淹没在噪声里。
        allfail.append(os.path.basename(f))
    env = d.get("env", {}) or {}
    if env.get("env_evidence") or d.get("log_evidence"):
        n_ev += 1
    # ⚠️ `log_evidence` 历史上出现过裸字符串（annotate 早期版本写的），
    # 按 `le.get("status")` 读会 AttributeError。两种形态都要吃得下。
    le = d.get("log_evidence")
    st = (le.get("status") if isinstance(le, dict)
          else ("annotated" if isinstance(le, str) else None))
    ev_status[st or "None"] += 1
    if st in ("missing", "no_log"):
        LOST.append(os.path.basename(f))
    for k, v in (env.get("env_confidence") or {}).items():
        if v == "inferred":
            inferred_total[k] += 1

# 日志已找不到的记录，别在「该回填却没回填」里再报一次 —— 它补不了，
# 重复报会让读者以为跑一次 annotate 就能消掉告警。
_lost = set(LOST)
missing = [m for m in missing if m not in _lost]

print("\n== 取证覆盖率（comfyui 记录）==")
print(f"  timing_breakdown: {n_tb}/{len(comfy)}    log/env_evidence: {n_ev}/{len(comfy)}")
print("  log_evidence.status: " + "  ".join(
    f"{k}={v}" for k, v in ev_status.most_common()))
if LOST:
    print(f"  · {len(LOST)} 条日志已找不到（status=missing）→ 时间分解**永久缺失**，"
          "别指望补跑一次就有：")
    for m in LOST:
        print(f"      {m}")
if missing:
    print(f"  ⚠ 缺 timing_breakdown 的 {len(missing)} 条（有日志就应回填，用 annotate_comfy_evidence.py）：")
    for m in missing:
        print(f"      {m}")
if allfail:
    print(f"  · {len(allfail)} 条样本全轮失败，日志里没有执行记录 → 取证为空是正确状态：")
    for m in allfail:
        print(f"      {m}")
if inferred_total:
    print("  仍标 inferred 的 env 字段（推断值没伪装成实测，属正常；但可选升为 recorded）：")
    for k, v in inferred_total.most_common():
        print(f"      {k}: {v}")

# --- 功耗覆盖率（2026-10-19 起）------------------------------------------
# 功耗**只能在该配置实际运行时采到**，事后无法补。所以历史批次必然是 None。
# 这里不把它当「回归」告警，只如实列出边界：哪些是实测、哪些是未采集。
# ⚠️ `power is None` 与 `avg_w == 0` 是两件不同的事，别混（后者说明采样器起了但读不到）。
n_pw = 0
pw_missing = []
for f in comfy:
    with open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    s = d.get("summary", {}) or {}
    if isinstance(s.get("power"), dict):
        n_pw += 1
    else:
        pw_missing.append(os.path.basename(f))

print("\n== 功耗覆盖率（comfyui 记录）==")
print(f"  有 power 汇总: {n_pw}/{len(comfy)}")
if pw_missing:
    print(f"  未采集 {len(pw_missing)} 条（最早 {pw_missing[0][:10]} / 最晚 "
          f"{pw_missing[-1][:10]}）。采集能力 2026-10-19 才上线，"
          f"功耗无法事后补 → 历史批次留 None 是对的，不是漏跑")
    # 采集能力上线之后还缺的，才是真该看的。
    # 门槛用 **> 2026-10-19**（能力当天上线，当天早于上线时刻的批次必然是 None）。
    late = [m for m in pw_missing if m[:10] > "2026-10-19"]
    if late:
        print(f"  ⚠ 其中 {len(late)} 条日期晚于 2026-10-19 却仍无 power"
              f"（应确认这批是不是关了 --no-power）：")
        for m in late:
            print(f"      {m}")

# --- env.slot 覆盖率（2026-10-16 起）--------------------------------------
# 门禁作用：槽位是环境必填口径之一（同卡不同槽性能有差，见 docs/slot-comparison.md）。
# 文件名带 pcie token 的记录，槽位是**确定可判**的——若这类记录缺 env.slot，
# 说明有记录绕过了 backfill_slot.py，属回归，必须报警。
# 文件名不带 token 的（B70 / ComfyUI / 2026-10-15 那批 ctx 扫描）：事后无法判定，
# 属已知未知，只报数不报警（见 docs/test-registry.md §6 第 8 条）。
have_slot = 0
slot_backfillable_missing = []
known_unknown = []
for f in files:
    with open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    env = d.get("env", {}) or {}
    name = os.path.basename(f)
    if env.get("slot"):
        have_slot += 1
    elif "pcie5x8" in name or "pcie4x4" in name:
        slot_backfillable_missing.append(name)
    else:
        known_unknown.append(name)

print("\n== env.slot 覆盖率 ==")
print(f"  有 slot: {have_slot}/{len(files)} | 缺 slot 但文件名可判: {len(slot_backfillable_missing)}"
      f" | 缺 slot 且不可判（已知未知）: {len(known_unknown)}")
if slot_backfillable_missing:
    print(f"  ⚠ 回归！以下 {len(slot_backfillable_missing)} 条文件名带 pcie token 却没 env.slot"
          f"（应跑 backfill_slot.py）：")
    for m in slot_backfillable_missing:
        print(f"      {m}")
if known_unknown:
    print(f"  已知未知 {len(known_unknown)} 条（文件名无槽位 token，不猜、见 §6 第 8 条）：")
    for m in known_unknown:
        print(f"      {m}")

print("\n== 全部记录（date | gpu | model | quant | schema | status | n_samples | tag）==")
for r in sorted(rows):
    print(f"  {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | n={r[6]} | {r[7]}")
