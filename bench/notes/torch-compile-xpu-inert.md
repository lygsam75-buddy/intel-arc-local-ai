# torch.compile / Comfy model compiler 在 XPU 上惰性（2026-10-22 · B65 实测）

## 问题

Triton 的 XPU 后端（triton-xpu 3.7.1）已经装在采集环境里，而且**已经在干活**：
H3 的 VSA / SLA 注意力内核（`ComfyUI-H3-VSA-XPU/vsa_kernel.py`、`ComfyUI-SLA-XPU/sla_xpu.py`）
本身就是 triton-xpu 内核。问题是再上一层——`torch.compile` / inductor / Comfy fork 自带的
「Comfy model compiler」（含 CUDA graphs 子功能）——在 XPU 上有没有可吃的收益。

## 实验

B65 · H3 720p · 5 秒 · steps 6 · seed 20261014 · reserve 4 · cold 单条，三组对照：

| 组 | server 参数 | cold 端到端 | 单步 | 峰值功耗 | 能量 |
| --- | --- | ---: | ---: | ---: | ---: |
| tc1 | `--torch-compile` | ❌ **参数不存在**，server usage 报错退出 | — | — | — |
| tc0 | 默认（编译器开） | 433.24 s | **42.44 s/it** | 222.6 W | 67.7 kJ |
| tc2 | `--disable-comfy-compiler` | 424.58 s | **42.45 s/it** | 215.5 W | 67.2 kJ |

（tc0 基线与 2026-10-21 批同协议数字对上：437.11 s / 42.30 s/it。）

## 结论

1. **`--torch-compile` 在这套 fork 上不存在**——它自带的是 `--disable-comfy-compiler` 体系
   （`comfy/cli_args.py`，绑定 CUDA graphs，走 `is_device_cuda` 判定）。
2. **开关对采样性能零影响**：单步 42.44 vs 42.45 s/it 逐位一致；端到端差 2% 在 cold 装载噪声内。
   → 编译器（inductor / CUDA graphs）在 XPU 上**没有挂进执行路径**，也没有可吃的收益空间。
3. Triton 的收益已经全部体现在手写内核里（VSA / SLA / int8 convrot），
   「要不要打开 torch.compile 加速」这个问题在 XPU 上**不成立**，数据到此关闭。

## 过程备注

- `--extra-arg` 的值以 `--` 开头时 argparse 必须用等号（`--extra-arg=--torch-compile`），
  空格分隔会报 expected one argument。
- `bench_f_h3.py` cold-only 轮不落 jsonl，只落 report/power——采集端后续可补。
- 看门狗阈值 `BENCH_STALL_SEC` 环境变量可调（编译类实验放宽到 2400 s 防误判）。
