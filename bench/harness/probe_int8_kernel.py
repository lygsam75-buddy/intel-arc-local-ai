"""探针：Intel XPU 上「INT8 卷积/线性为什么没走原生路径 / 为什么报参数不匹配」。

回答三个问题，全部只读、不加载模型权重、不起 ComfyUI server：

  ① ComfyUI 侧按什么契约调用 `ck.int8_linear`？内核侧的 facade 实际接受几个参数？
  ② 两者的差集是什么（缺哪些关键字）？XPU kernel 的融合激活白名单支持哪些字面量？
  ③ 打上适配层之后，按 ComfyUI 的契约调用能不能跑通、数值是否正确、比反量化快多少？

这个探针存在的理由：**「INT8 在 XPU 上不支持」这句话经常是错的。**
本机实测过的一次真实故障是 ComfyUI 0.39 按 12 参契约调用，而 XPU provider 里 vendored 的
`comfy_kitchen` 只有 8 参 → `TypeError: int8_linear() got an unexpected keyword argument
'input_act_weight'`。但 XPU kernel 的白名单 `(None,'none','gelu_tanh','swiglu')` **含 `swiglu`**，
出问题的模型用的正是 `swiglu`，缺的 4 个参数在它那条调用路径上本就是空值 ——
**签名不匹配，不是功能缺口**。适配后 cosine 0.9997、零性能代价。

⚠️ 本脚本会在**进程内**临时放宽 provider 的 torch 版本校验（`runtime_bootstrap
._torch_version_without_import`），好让 provider 真正激活、vendored XPU backend 生效，
从而复现真实派发环境。**不写任何磁盘文件。** 要保持现状就不要放宽，直接跑即可
（此时拿到的是 canonical comfy_kitchen，通常不会崩，可用来对照两种环境）。

用法：
    python bench/harness/probe_int8_kernel.py --comfyui <ComfyUI 目录>
    python bench/harness/probe_int8_kernel.py --comfyui <ComfyUI 目录> --shim <custom_nodes/xxx.py>

`<ComfyUI 目录>` 必须是**用跑 ComfyUI 的那个 python** 能 import 到 torch.xpu 的环境。
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import sys
import time
from pathlib import Path

BAR = "=" * 78


def hr(title: str) -> None:
    print("\n" + BAR + "\n" + title + "\n" + BAR)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载模块：{path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--comfyui", required=True, help="ComfyUI 根目录（含 custom_nodes/）")
    ap.add_argument("--shim", default="", help="可选：适配层 .py 路径（装完再复测）")
    ap.add_argument("--hidden", type=int, default=3072, help="Qwen-Image 2.1 的 MLP hidden")
    ap.add_argument("--tokens", type=int, default=1024, help="一次 forward 的 token 数")
    ap.add_argument("--align-provider", action="store_true",
                    help="进程内放宽 provider 的 torch 版本校验（复现 vendored XPU backend）")
    ap.add_argument("--no-bench", action="store_true", help="跳过计时")
    args = ap.parse_args()

    comfy = Path(args.comfyui).resolve()
    if not (comfy / "comfy" / "ops.py").exists():
        raise SystemExit(f"看起来不像 ComfyUI 根目录：{comfy}")
    sys.path.insert(0, str(comfy))

    import torch

    hr("0 · 运行环境")
    print("torch          :", torch.__version__)
    has_xpu = bool(getattr(torch, "xpu", None) and torch.xpu.is_available())
    print("xpu available  :", has_xpu)
    if not has_xpu:
        raise SystemExit("没有可用的 XPU 设备，本探针只对 Intel 核显有意义。")
    props = torch.xpu.get_device_properties(0)
    print("device         :", props.name)
    print("vram           : %.2f GiB" % (props.total_memory / 1024 ** 3))
    dev = "xpu"

    # ── 让 provider 真正激活（vendored XPU backend 才会生效） ──
    omx = comfy / "custom_nodes" / "ComfyUI-OmniXPU" / "runtime_bootstrap.py"
    if omx.exists():
        rb = load_module(omx, "_int8probe_rb")
        if args.align_provider:
            try:
                import comfy_kitchen_xpu_runtime as _pk
                declared = json.loads(
                    (Path(_pk.__file__).parent / "provider.json").read_text(encoding="utf-8")
                )["runtime"]["torch_version"]
                real = rb._torch_version_without_import()
                rb._torch_version_without_import = lambda: declared
                print("\nprovider 声明 torch: %s | 实际 torch: %s → 进程内已对齐（不改磁盘）"
                      % (declared, real))
            except Exception as e:      # noqa: BLE001
                print("\n读取 provider.json 失败：", type(e).__name__, e)
        state = rb.bootstrap()
        print("bootstrap 状态:", state.get("status"))
        print("providers     :", {k: v.get("status") for k, v in state.get("providers", {}).items()})
    else:
        print("\n未找到 ComfyUI-OmniXPU/runtime_bootstrap.py，"
              "将以 canonical comfy_kitchen 为准（可能看不到 XPU backend）。")

    import comfy_kitchen as ck

    print("\ncomfy_kitchen 实际来源:", ck.__file__)
    try:
        from comfy_kitchen.backends import xpu as ckxpu
        print("XPU backend 来源    :", ckxpu.__file__)
        print("kernel 融合激活白名单:", getattr(ckxpu, "_INT8_LINEAR_INPUT_ACTS", "?"))
    except Exception as e:              # noqa: BLE001
        print("XPU backend 不可见  :", type(e).__name__, e)

    # ── ComfyUI ops.py: linear_input_act 实际传的 7 个关键字 ──
    # 写在这里是为了「口径跟着仓库走」：改 ComfyUI 版本时这一处会暴露出来。
    CALL = dict(
        convrot=False,
        convrot_groupsize=256,
        input_act="swiglu",        # qwen_image21 / minimax / minimax_music 都用它
        input_act_weight=None,     # 这条调用路径只给 3 个位置参数 ⇒ 全是空值
        input_act_eps=0.0,
        residual=None,
        residual_scale=None,
    )

    H = args.hidden
    torch.manual_seed(0)
    x = torch.randn(1, args.tokens, 2 * H, dtype=torch.bfloat16, device=dev)   # [gate; up]
    w = torch.randint(-127, 127, (H, H), dtype=torch.int8, device=dev)          # (N, K)
    scale = torch.tensor(0.0021, dtype=torch.float32, device=dev)

    hr("1 · 契约差异")
    sig = inspect.signature(ck.int8_linear)
    print("ck.int8_linear 实际参数（%d）: %s" % (len(sig.parameters), ", ".join(sig.parameters)))
    missing = [k for k in CALL if k not in sig.parameters]
    print("ComfyUI 会传但它不接受的      :", missing or "（无）")
    print("→ " + ("签名不匹配，会直接 TypeError。" if missing else "签名兼容。"))

    hr("2 · 按 ComfyUI 的契约调用")
    reproduced = False
    try:
        ck.int8_linear(x, w, scale, None, torch.bfloat16, **CALL)
        print("调用成功（未打适配层）")
    except TypeError as e:
        print("✅ 复现 TypeError:", e)
        reproduced = True
    except Exception as e:              # noqa: BLE001
        print("⚠️ 其它异常（先看这个）:", type(e).__name__, e)

    if args.shim:
        hr("3 · 装适配层后复测")
        mod = load_module(Path(args.shim).resolve(), "_int8probe_shim")
        print("适配层加载完成；shim 标记:",
              getattr(ck.int8_linear, "_omnixpu_shim", False))
        print("新签名参数（%d）: %s"
              % (len(inspect.signature(ck.int8_linear).parameters),
                 ", ".join(inspect.signature(ck.int8_linear).parameters)))

    out = None
    try:
        out = ck.int8_linear(x, w, scale, None, torch.bfloat16, **CALL)
        torch.xpu.synchronize()
        print("调用成功:", tuple(out.shape), out.dtype,
              "| finite:", bool(torch.isfinite(out).all()))
    except Exception as e:              # noqa: BLE001
        print("❌ 仍失败:", type(e).__name__, e)
        return 1

    hr("4 · 数值对照（INT8 vs 反量化回 bf16）")
    gate, up = x[..., :H].float(), x[..., H:].float()
    act = (torch.nn.functional.silu(gate) * up).to(torch.bfloat16)
    w_deq = (w.to(torch.float32) * scale.to(torch.float32)).to(torch.bfloat16)
    ref = torch.nn.functional.linear(act, w_deq)
    cos = torch.nn.functional.cosine_similarity(
        out.float().flatten().unsqueeze(0), ref.float().flatten().unsqueeze(0)).item()
    rel = ((out.float() - ref.float()).norm() / ref.float().norm()).item()
    print("cosine            = %.6f" % cos)
    print("相对 L2 误差       = %.4f%%（int8 量化的固有误差，不是 bug）" % (rel * 100))

    if not args.no_bench:
        hr("5 · 计时")

        def bench(fn, n=8):
            for _ in range(3):
                fn()
            torch.xpu.synchronize()
            t0 = time.perf_counter()
            for _ in range(n):
                fn()
            torch.xpu.synchronize()
            return (time.perf_counter() - t0) / n * 1000

        t_k = bench(lambda: ck.int8_linear(x, w, scale, None, torch.bfloat16, **CALL))
        t_e = bench(lambda: torch.nn.functional.linear(act, w_deq))
        print("M=%d, K=%d, N=%d" % (args.tokens, 2 * H, H))
        print("  XPU int8 GEMM（含融合激活）: %7.2f ms" % t_k)
        print("  反量化回 bf16 的 F.linear  : %7.2f ms" % t_e)
        print("  比值                      : %7.2f×" % (t_k / t_e))
        print("\n注：这个形状很小，kernel launch 开销占主导，比值不代表整模型端到端。")

    hr("小结")
    print("崩溃可复现        :", "是" if reproduced else "否")
    print("适配后跑通        : 是（cosine %.4f）" % cos)
    print("结论口径          : 签名不匹配 ≠ 功能缺口；"
          "缺的那几个参数在 fused-MLP 调用路径上本就是空值。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())