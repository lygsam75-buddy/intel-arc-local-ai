# 外部 B70 评测归档：kyuz0 视频与实测数据集（2026-10-24）

> 来源：B 站视频 BV1WfVV67ENt（UP「枫叶边城」中字转发，原作者 kyuz0）+
> 他的 GitHub 仓库与实时基准站。**过程性工程笔记，不是客户文档。**
> 外部数字全部带条件；**与我们不同卡型 / 不同量化 / 不同引擎口径的数字不并排**，只并列。

---

## 0. 结论先行

1. **「SYCL 快还是 Vulkan 快」没有单一答案，按「模型 + 量化 + 测试段」三分**（他 88 条有效实测）：
   - **BF16 稠密**：SYCL 预填充快 1.2 至 1.4 倍，**解码只剩 Vulkan 的 0.17 至 0.29 倍**
     （Ministral-14B-BF16 tg128：SYCL 3.37 vs Vulkan 19.32 tok/s，差 5.7 倍）；
   - **MoE Q4（我们同族的 Qwen3.6-35B-A3B）**：SYCL 解码快 1.85 倍（KV 深 16384 时 2.23 倍），
     **Vulkan 预填充快 2.1 倍**（1275.23 vs 610.44）；
   - **Q8_K_XL**：SYCL 两头都赢（1.49 倍 / 1.81 倍）。
   - gemma-4 在深 KV 下 Vulkan 崩塌（预填充只剩 SYCL 的 1/10.9），SYCL 反而碾压。
2. **他的条件与我们差三处**：单张 B70（32 核）vs 我们 2xB65（20 核）；
   llama.cpp build 9039（2026-05）vs 我们 11431（2026-10）；Linux/Fedora vs Windows。**数字不并排。**
3. 🔴->✅ **「同卡同模型族差 3 倍」已定位是 build 代际**（2026-10-24 当天复现）：
   他 B70 / build 9039：tg128 = 38.97；我们 build 11753 在**更弱的 B65** 上 llama-bench 同口径
   tg128 = **91.27**（pp512 = 2030.12），B70 同 build 是 115.56（核数比 32/20 方向一致）。
   **不是我们的口径问题，是他那一代 build 的 Vulkan MoE 内核慢**。日志：`bench/logs/vk_recheck_2026-10-24_b65_q4_0.log`。
4. **视频三条定性发现**：① 他读代码认为 llama.cpp SYCL 后端**没用上 XMX 矩阵单元**；
   ② MTP（多 token 预测）在 SYCL 上**比不开还慢**；③ SYCL 后端显存利用有 issue，**上下文过 16K 出问题**。
5. **他的负结果**：Q8_K_XL 的 30B / 31B 两个模型加载即失败（32 GiB 文件进 32 GB 卡）——与我们「装得下」结论同向。

---

## 1. 来源

| 来源 | 内容 |
| --- | --- |
| B 站 BV1WfVV67ENt | 26:37，2026-05-30 发布，UP「枫叶边城」中字转发原作者视频；播放 311、0 评论、5 赞 |
| kyuz0/intel-b70-ai-toolboxes | 4 个容器（SYCL / Vulkan / OpenVINO / vLLM）+ 96 条 llama-bench 原始日志 + 实时基准站 |
| kyuz0/llama-toolboxes-cockpit | TUI 管理器；基准模式方法论：**depth = KV 里已有的 token 数**，不是层深 |
| kyuz0.github.io/intel-b70-ai-toolboxes/ | 交互式基准站，数据在 results.json（88 有效 / 8 失败） |

原作者同时做 AMD Strix Halo / Radeon AI Pro R9700 / Intel B70 三个平台，视频里大量对比 R9700
（32 GB、约 600 GB/s、同价位段），**不是我们的 B65**。卡是 Intel 送测（作者原话 "Intel was kind enough to send me this"）。

## 2. 他的实测条件（照抄，用于判断能不能并排）

- 卡：**单张** Intel Arc Pro B70（32 Xe 核）；Fedora 43 Workstation，内核 6.19.14，linux-firmware 20260410
- llama.cpp **build 9039**（hash 74d6248f7），2026-05-06 采集；ngl 99、fa 1、mmap 0
- 口径：llama-bench `pp512` / `tg128`；长上下文是 `pp2048 @ d16384` / `tg32 @ d16384`——
  **先把 KV 填到 16384 深再测**，不是简单把 -c 调大（与我们的 ctx_sweep 是两种问法）
- std 极小（tg128 到 ±0.04），他的机器很稳；我们 llama-server 探针同口径离散度大得多（min–max 差 8%）

## 3. SYCL vs Vulkan 全表（B70 · build 9039 · llama-bench）

| 模型 | 量化 | 参数量 | 文件 | 口径 | SYCL t/s | Vulkan t/s | SYCL/Vulkan |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| Ministral-3-14B-Instruct-2512-BF16 | BF16 | 13.5B | 25.16 GiB | 默认 · pp512 |   568.07 |   464.50 | 1.22 |
| Ministral-3-14B-Instruct-2512-BF16 | BF16 | 13.5B | 25.16 GiB | 默认 · tg128 |     3.37 |    19.32 | 0.17 |
| Ministral-3-14B-Instruct-2512-BF16 | BF16 | 13.5B | 25.16 GiB | KV 深 16384 · pp2048 @ d16384 |   201.84 |   159.95 | 1.26 |
| Ministral-3-14B-Instruct-2512-BF16 | BF16 | 13.5B | 25.16 GiB | KV 深 16384 · tg32 @ d16384 |     3.23 |    12.56 | 0.26 |
| Ministral-3-8B-Instruct-2512-BF16 | BF16 | 8.5B | 15.81 GiB | 默认 · pp512 |   900.90 |   698.30 | 1.29 |
| Ministral-3-8B-Instruct-2512-BF16 | BF16 | 8.5B | 15.81 GiB | 默认 · tg128 |     5.43 |    31.04 | 0.17 |
| Ministral-3-8B-Instruct-2512-BF16 | BF16 | 8.5B | 15.81 GiB | KV 深 16384 · pp2048 @ d16384 |   261.52 |   201.68 | 1.30 |
| Ministral-3-8B-Instruct-2512-BF16 | BF16 | 8.5B | 15.81 GiB | KV 深 16384 · tg32 @ d16384 |     5.11 |    17.85 | 0.29 |
| Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL | Q4_K_XL | 31.6B | 21.26 GiB | 默认 · pp512 |   657.26 |  1300.13 | 0.51 |
| Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL | Q4_K_XL | 31.6B | 21.26 GiB | 默认 · tg128 |    30.20 |    40.35 | 0.75 |
| Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL | Q4_K_XL | 31.6B | 21.26 GiB | KV 深 16384 · pp2048 @ d16384 |   575.64 |   744.13 | 0.77 |
| Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL | Q4_K_XL | 31.6B | 21.26 GiB | KV 深 16384 · tg32 @ d16384 |    29.57 |    35.51 | 0.83 |
| Qwen3.5-9B-BF16 | BF16 | 8.9B | 16.68 GiB | 默认 · pp512 |   910.98 |   702.03 | 1.30 |
| Qwen3.5-9B-BF16 | BF16 | 8.9B | 16.68 GiB | 默认 · tg128 |     5.42 |    28.17 | 0.19 |
| Qwen3.5-9B-BF16 | BF16 | 8.9B | 16.68 GiB | KV 深 16384 · pp2048 @ d16384 |   577.51 |   406.13 | 1.42 |
| Qwen3.5-9B-BF16 | BF16 | 8.9B | 16.68 GiB | KV 深 16384 · tg32 @ d16384 |     5.35 |    22.09 | 0.24 |
| Qwen3.5-9B-UD-Q8_K_XL | Q8_K_XL | 8.9B | 12.07 GiB | 默认 · pp512 |  2521.50 |  1697.02 | 1.49 |
| Qwen3.5-9B-UD-Q8_K_XL | Q8_K_XL | 8.9B | 12.07 GiB | 默认 · tg128 |    38.83 |    21.47 | 1.81 |
| Qwen3.5-9B-UD-Q8_K_XL | Q8_K_XL | 8.9B | 12.07 GiB | KV 深 16384 · pp2048 @ d16384 |   938.72 |   613.56 | 1.53 |
| Qwen3.5-9B-UD-Q8_K_XL | Q8_K_XL | 8.9B | 12.07 GiB | KV 深 16384 · tg32 @ d16384 |    35.15 |    18.04 | 1.95 |
| Qwen3.6-27B-UD-Q4_K_XL | Q4_K_XL | 26.9B | 16.39 GiB | 默认 · pp512 |   731.43 |   507.84 | 1.44 |
| Qwen3.6-27B-UD-Q4_K_XL | Q4_K_XL | 26.9B | 16.39 GiB | 默认 · tg128 |    19.79 |    13.21 | 1.50 |
| Qwen3.6-27B-UD-Q4_K_XL | Q4_K_XL | 26.9B | 16.39 GiB | KV 深 16384 · pp2048 @ d16384 |   307.07 |   207.48 | 1.48 |
| Qwen3.6-27B-UD-Q4_K_XL | Q4_K_XL | 26.9B | 16.39 GiB | KV 深 16384 · tg32 @ d16384 |    17.36 |     9.35 | 1.86 |
| Qwen3.6-35B-A3B-UD-Q4_K_XL | Q4_K_XL | 34.7B | 20.81 GiB | 默认 · pp512 |   610.44 |  1275.23 | 0.48 |
| Qwen3.6-35B-A3B-UD-Q4_K_XL | Q4_K_XL | 34.7B | 20.81 GiB | 默认 · tg128 |    72.23 |    38.97 | 1.85 |
| Qwen3.6-35B-A3B-UD-Q4_K_XL | Q4_K_XL | 34.7B | 20.81 GiB | KV 深 16384 · pp2048 @ d16384 |   479.59 |   489.23 | 0.98 |
| Qwen3.6-35B-A3B-UD-Q4_K_XL | Q4_K_XL | 34.7B | 20.81 GiB | KV 深 16384 · tg32 @ d16384 |    64.55 |    28.96 | 2.23 |
| gemma-4-26B-A4B-it-UD-Q4_K_XL | Q4_K_XL | 25.2B | 15.90 GiB | 默认 · pp512 |  1135.26 |  1093.93 | 1.04 |
| gemma-4-26B-A4B-it-UD-Q4_K_XL | Q4_K_XL | 25.2B | 15.90 GiB | 默认 · tg128 |    69.52 |    37.69 | 1.84 |
| gemma-4-26B-A4B-it-UD-Q4_K_XL | Q4_K_XL | 25.2B | 15.90 GiB | KV 深 16384 · pp2048 @ d16384 |   540.62 |    49.54 | 10.91 |
| gemma-4-26B-A4B-it-UD-Q4_K_XL | Q4_K_XL | 25.2B | 15.90 GiB | KV 深 16384 · tg32 @ d16384 |    52.93 |    16.15 | 3.28 |
| gemma-4-31B-it-UD-Q4_K_XL | Q4_K_XL | 30.7B | 17.46 GiB | 默认 · pp512 |   619.04 |   304.80 | 2.03 |
| gemma-4-31B-it-UD-Q4_K_XL | Q4_K_XL | 30.7B | 17.46 GiB | 默认 · tg128 |    18.49 |    13.52 | 1.37 |
| gemma-4-31B-it-UD-Q4_K_XL | Q4_K_XL | 30.7B | 17.46 GiB | KV 深 16384 · pp2048 @ d16384 |   179.87 |    12.20 | 14.74 |
| gemma-4-31B-it-UD-Q4_K_XL | Q4_K_XL | 30.7B | 17.46 GiB | KV 深 16384 · tg32 @ d16384 |    13.92 |     4.65 | 2.99 |
| gpt-oss-20b-mxfp4 | MXFP4 | 20.9B | 11.27 GiB | 默认 · pp512 |  1387.13 |  2102.16 | 0.66 |
| gpt-oss-20b-mxfp4 | MXFP4 | 20.9B | 11.27 GiB | 默认 · tg128 |    52.81 |    44.57 | 1.18 |
| gpt-oss-20b-mxfp4 | MXFP4 | 20.9B | 11.27 GiB | KV 深 16384 · pp2048 @ d16384 |   803.27 |   504.48 | 1.59 |
| gpt-oss-20b-mxfp4 | MXFP4 | 20.9B | 11.27 GiB | KV 深 16384 · tg32 @ d16384 |    48.78 |    28.97 | 1.68 |
| llama-2-7b.Q4_0 | Q4_0 | 6.7B | 3.56 GiB | 默认 · pp512 |  2541.35 |  2414.28 | 1.05 |
| llama-2-7b.Q4_0 | Q4_0 | 6.7B | 3.56 GiB | 默认 · tg128 |   106.27 |    87.36 | 1.22 |
| llama-2-7b.Q4_0 | Q4_0 | 6.7B | 3.56 GiB | KV 深 16384 · pp2048 @ d16384 |   319.24 |   242.04 | 1.32 |
| llama-2-7b.Q4_0 | Q4_0 | 6.7B | 3.56 GiB | KV 深 16384 · tg32 @ d16384 |    41.43 |    24.26 | 1.71 |

**读表三条**：

- BF16 那几行是重灾区：SYCL 解码 3 至 5 tok/s，基本不可用；这与他「XMX 没用上」的读代码结论吻合
  （BF16 解码是带宽活，SYCL 却比 Vulkan 慢 4 至 6 倍，说明内核本身效率有问题，不是带宽问题）。
- MoE 两行（Nemotron-30B-A3B / Qwen3.6-35B-A3B）方向一致：**Vulkan 预填充快约 2 倍，SYCL 解码快 1.75 至 2.2 倍**。
- gemma-4 深 KV 下 Vulkan 崩塌（tg32 @ d16384 只剩 4.65）——**同一个后端在不同模型上能差 3 至 15 倍，不能拿一个数代表一个后端**。

## 4. 视频定性发现（作者口述，我们未验证）

1. **XMX 矩阵单元**：作者翻 llama.cpp SYCL 实现，认为矩阵单元「currently not used」，是个 to-do；
   BF16 解码极慢与此自洽。**这是我们之外第一个独立指出 SYCL 内核完成度问题的人。**
2. **MTP（多 token 预测）**：作者在 B70 上实测 MTP **比不开还慢**，猜测 SYCL 后端没为 MTP 优化。我们没测过 MTP。
3. **上下文天花板**：作者在 B70 上 SYCL 后端过 16K「start having some issues」，同模型在 R9700 上可以用更大上下文；
   他归因为 SYCL 后端「还没把显存用到最理想」。**与我们长上下文结论（分配 vs 填满是两件事）不同卡不同 build，不并排。**
4. **vLLM 侧**：走 llm-scaler（Intel 官方 vLLM fork），2026-05 为 B70 专门更过一次；
   坑：不是最新版、Gemma 4 不支持、**AWQ 量化跑不了**（GPTQ 可以）、**必须 eager 模式**（图编译不稳）。
5. **他的 vLLM 数**：Llama 3.1 8B 2054 tok/s（B70）约等于 R9700；Qwen 3.5 9B 2236 tok/s，R9700「差得远」。
   小模型预填充，与我们 35B-A3B / H3 的赛道不同，**不并排**。
6. **只有一张卡**：作者明说做不了 tensor parallelism——**外部多卡数据依然只有 machx 一家**。

## 5. 与我们实测的交叉核对

| 他的（B70 / build 9039 / Linux / llama-bench） | 我们的（B65x2 或 B70 / build 11431 / Windows） | 判断 |
| --- | --- | --- |
| 35B-A3B Q4_K_XL SYCL tg128 = 72.23 | 35B-A3B Q8_0 SYCL 单卡 31.46 | 量化与卡都不同，不并排；但同向（MoE 解码跟每 token 字节数走） |
| 35B-A3B Q4_K_XL Vulkan tg128 = 38.97（B70 / build 9039） | 35B-A3B Q4_0 Vulkan：B65 91.27 / B70 115.56（build 11753 / llama-bench 同口径） | ✅ **差在他那一代 build**：更弱的卡反而快 2.3 倍。我们的 115.56 成立 |
| SYCL 上下文过 16K 出问题 | 我们 -c 拉到 262144 三卡只掉 ≤2.2% | 问的问题不同（他的「用起来出问题」vs 我们的「分配得到吗」），不并排 |
| Q8_K_XL 30B/31B 加载失败 | 我们「装得下」判据一致 | 同向：32 GiB 文件进 32 GB 卡不行 |
| 单卡，无多卡数据 | 我们 2xB65 双卡六工况 | 互补：外部多卡依旧只有 machx |

## 6. 待办

1. ✅ **已复现（2026-10-24）**：`llama-bench -m Q4_0 35B-A3B -dev Vulkan1 -fa on -ncmoe 0 -p 512 -n 128 -r 3`
   （b11753-vulkan / B65）：pp512 = 2030.12 ± 4.92，tg128 = 91.27 ± 0.13。
   **结论：3 倍差在 build 代际（9039 vs 11753），不在我们的口径。**
2. **待办**：把「Vulkan 倍数跟核数走 + build 代际差 3 倍」写进 docs 的 Vulkan 小节
   （`docs/` 里 Vulkan 数字都要标 build 11753；引用外部老 build 数字必须标 9039）。
3. MTP 在 SYCL 上慢——我们没测过，**记着有这么个负结果**，不主动测（非对客线）。
4. 视频说辞手法已并进 B70 README 改写（见 docs/cards/B70-README.md 修订记录）。

---

*归档：2026-10-24。外部链接与数字归原作者 kyuz0，条件随文标注。视频完整机转文字见同目录 raw-kyuz0-b70-transcript.txt。*
