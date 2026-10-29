"""补录 5 条缺失 env.tool 的记录（备案审计发现，见 docs/test-registry.md 数据卫生节）。

背景：bench/README.md 要求「测量工具必填，不同工具不可混比」，
但 xpu_bench.py 早期版本不写 env.tool，scan_ncmoe.py 写（llama-bench）、
ctx_sweep/longctx_probe 写（llama-server），导致 5 条 xpu_bench 系记录缺字段。

判定依据（逐条写进 env_backfill，绝不静默补）：
  - 2026-10-06_b70-32g_...：notes 明写「通过 llama-server /completion 接口采集（非 llama-bench）」
  - 其余 4 条：args 为 llama-bench CLI 形制（-p/-n/-r），且 xpu_bench.py 只跑 llama-bench
    （其 docstring：「只跑 llama-bench，不自己实现计时」）。
    注意 tag 里的 "probe" 不是 probe_server.py——那个脚本产出 llama-server-probe/1
    schema，而这 5 条都是 arc-xpu-bench/1。

按仓库惯例标 inferred（采集时未落盘，现在凭记录内证据重建），并追加 env_backfill 说明。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "bench", "data")

# 文件名 -> (tool, 证据)
FIX = {
    "2026-10-06_b70-32g_qwen3.6-35b-a3b-q4_0-sycl.json": (
        "llama-server",
        "记录 notes 采集时即注明「通过 llama-server /completion 接口采集（非 llama-bench）」",
    ),
    "2026-10-15_b50-16g_ncmoe0-r3-pcie4x4.json": (
        "llama-bench",
        "args 为 llama-bench CLI 形制（-p 512 -n 128 -r 3）；xpu_bench.py 只跑 llama-bench",
    ),
    "2026-10-15_b50-16g_probe-ncmoe0-pcie4x4.json": (
        "llama-bench",
        "args 为 llama-bench CLI 形制（-p 512 -n 128 -r 1）；tag 里的 probe 不是 probe_server.py"
        "（该脚本产出 llama-server-probe/1 schema，本条为 arc-xpu-bench/1）",
    ),
    "2026-10-15_b70-32g_qwen3.6-35b-a3b-q4_0-sycl-r3.json": (
        "llama-bench",
        "args 为 llama-bench CLI 形制（-p 512 -n 128 -r 3）；xpu_bench.py 只跑 llama-bench",
    ),
    "2026-10-15_warmup-discard-single-card.json": (
        "llama-bench",
        "args 为 llama-bench CLI 形制（-p 512 -n 128 -r 1）；xpu_bench.py 只跑 llama-bench",
    ),
}

changed = 0
for name, (tool, why) in FIX.items():
    path = os.path.join(DATA, name)
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    env = d.setdefault("env", {})
    if env.get("tool") == tool:
        print(f"[skip] {name} 已有 tool={tool}")
        continue
    env["tool"] = tool
    conf = env.setdefault("env_confidence", {})
    conf["tool"] = "inferred"
    note = (
        f"tool 字段为 2026-10-15 备案审计时补录，标 inferred（采集时未落盘，"
        f"凭记录内证据重建）。证据：{why}。"
    )
    old = d.get("env_backfill")
    d["env_backfill"] = (old + " " + note) if old else note
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    changed += 1
    print(f"[fix ] {name} -> tool={tool}")

print(f"\nchanged: {changed}/{len(FIX)}")
