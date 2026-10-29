# 多卡并行：外部资料与解决方案（2026-10-24 调研）

> 本文是**外部资料归档 + 与我们实测的交叉核对**，不是客户文档。对外结论另写。
> 所有外部数字都标注了来源与条件；**不同引擎 / 不同模型代际的数字一律不并排**。

---

## 0. 结论先行

1. **4xB70 在 llama.cpp 上跑得起来，但官方文档明说张量并行只对 2 卡优化过**——
   "Tensor parallelism is currently optimized for 2 GPUs; other device counts fall back to a
   generic all-reduce." >2 卡走的是通用 all-reduce，不是专用路径。
2. **目前唯一「为 Intel Arc 多卡从零写成的引擎」是 `Red-Weasel/machx-inference-engine`**：
   C++/SYCL，作者声明"built and tuned on two Arc Pro B70 cards"，v0.2.27 起才支持 >2 卡，
   且作者自己写明 **"Real four-card speed is not measured"**（四卡速度没实测过）。
3. **我们的双卡结论和外部一致**：拆层不赔速度、固定开销对页缓存敏感。
4. 🔴🔴 **`-sm tensor` 在 2xB65 上跑通了，但是全场最慢**（2026-10-24 实测）：
   decode 28.65 至 29.22 tok/s，低于同口径拆层 35.14 至 37.30，**也低于单卡全驻 31.46**；
   `GGML_SYCL_ENABLE_HOST_PINNED_MEM=0` 救不了（同批单变量 28.65->28.91，+0.9% 在噪声内）。
   **张量并行在 2 卡已不划算**；官方文档明说 >2 卡退化通用 all-reduce -> **4 卡更不该走 tensor，
   拆层（`-sm layer`）是唯一不赔速度的协同模式**。数据见 `bench/data/2026-10-24_b65-32g-q8_0-dual-tensor-scan.json`。
5. **`-sm row` 在我们 build 11431 上加载即失败，但外部 6 卡 Battlematrix 用 `--split-mode row`
   跑通了** -> 那是我们这个 build 的问题，不是模式本身不通。**这是下一步最该复现的一条。**

---

## 1. 关键来源

### 1.1 `Red-Weasel/machx-inference-engine`（与我们的场景最相关）

- <https://github.com/Red-Weasel/machx-inference-engine> · Apache 2.0 · C++20/SYCL ·
  topics: `battlemage` `intel-arc` `sycl` `tensor-parallel` `oneapi`
- 作者原话：**"built and tuned on two Arc Pro B70 cards: XMX kernels, quantized models,
  multi-GPU execution, an OpenAI-compatible server"**。不 fork llama.cpp，语言模型引擎不用 PyTorch。
- 2026-10-23 仍在发版（v0.2.33），迭代极快（一天好几个版本）。

**多卡实现方式**

| 路径 | 开关 | 状态 |
| --- | --- | --- |
| 层切分（layer split） | 默认 | 主力路径，两卡各跑一半层 |
| 张量并行（tensor parallel） | `IE_DS41_TP=1`（DeepSeek）/ `IE_QWEN35_TP` | opt-in |

**两卡 B70（64 GB）实测，作者 2026-10 数据**（注意：模型是 **Qwen3.8** 代际，我们是 Qwen3.6，**不并排**）：

| 模型 | 预填充 tok/s | 解码 tok/s |
| --- | --- | --- |
| Qwen3.8-27B Q8_0 | 2,962（2.4K）/ 3,001（10.7K） | 17.1 plain / 24.3 `--spec` |
| Qwen3.8-35B-A3B Q8_0 | 2,896 / 2,808 | 89.0 @2K / 86.6 @9.8K |

**>2 卡（v0.2.27，2026-10-21）**

- v0.2.26 及以前：超过两张卡**prompt >2,048 token 直接失败、>16K token 的 attention 是错的**，
  必须 `--cards 0,1` 手动限制。
- v0.2.27 修好。作者的验证方式很老实：**把 4 张卡模拟成 2 张 B70 上的 4 个流水段**，
  15/15 条 trace 与两卡逐字节相同（prompt 最长 19,783 token）。
- 作者原话：**"Real four-card speed is not measured"**（模拟共享同一张卡的显存和链路，测不出真四卡）。

**关键工程坑（作者归因到驱动）**

- `intel/compute-runtime#948` + `drm/xe#8390`：**copy engine 对单次 >=512 MiB 的 pageable 拷贝会 fault**，
  持续负载下在 B70 和 B580 上都会出现。表现为一张 B70 卡死、GPU reset 失败。
- 作者解法：**所有 host<->device 拷贝走 pinned memory，单次 <=64 MiB**；小尺寸 D2H 读改写成计算队列上的 kernel。
- 另一个：**>=64 MiB 的设备分配要做 page-alias 自检**（两个 2 MiB page 可能由同一个物理 page 背书，
  写一个会静默改另一个），v0.2.13 起每次分配都检，约 0.5 s / 49 GiB。

**诚实的「还慢在哪」章节（这个写法本身值得学）**
—— 每版都单列一节，例如 v0.2.31：单请求下两卡仍是轮流干活（4.3 + 5.2 ms/token），
router 两个 kernel 占 1.3 ms/token，attention 部分 scan 约 0.16 ms/层@8K。

### 1.2 llama.cpp SYCL 后端（官方文档）

- 多设备选择：`ONEAPI_DEVICE_SELECTOR="level_zero:0;level_zero:1"`，或 llama 侧 `--device SYCL0,SYCL1`。
- 切分模式四种：`--split-mode none|layer|tensor|row`。
- **`--split-mode tensor`（张量并行）把每一层切片铺到多卡**，需要 flash attention
  （`--flash-attn` 默认 `auto` 会自动开，所以开箱即用）；**`--flash-attn off` 配 `--split-mode tensor`
  在建 context 时直接被拒**。推荐默认 f16 KV cache。
- **官方原句：Tensor parallelism is currently optimized for 2 GPUs; other device counts
  fall back to a generic all-reduce.**（**这条直接回答了「4 片联机」的预期**）
- 单设备模式用 `--split-mode none --main-gpu DEVICE_ID`。

### 1.3 llama.cpp issue #27888 —— 一份现成的「混合架构双卡稳定配置」

<https://github.com/ggml-org/llama.cpp/issues/27888>（B50 + A770，BMG + DG2 混搭）

稳定配置（作者结论）：

```
GGML_SYCL_ENABLE_VMM=1
GGML_SYCL_USE_LEVEL_ZERO_API=1
GGML_SYCL_ENABLE_FUSION=1
GGML_SYCL_ENABLE_ESIMD=1
GGML_SYCL_ENABLE_HOST_PINNED_MEM=0     <- 关键：关掉 host pinned memory 才稳
```

```
--device SYCL0,SYCL1 --split-mode layer --n-gpu-layers 66 \
  --ctx-size 2048 --batch-size 32 --ubatch-size 32 \
  --flash-attn off --fit off --no-warmup
```

- 结果：66/66 层全卸载，B50 7.65 GiB / A770 8.07 GiB，**CPU-mapped 只剩 682 MiB**
  （之前 Chrome 等桌面程序被内存回收杀掉）。
- 附带坑：`--batch-size 1` 会触发 `GGML_ASSERT(n_tokens_all <= cparams.n_batch)`，
  要 `--batch-size 32 --ubatch-size 32`。
- **llama.cpp SYCL 维护者 tv1wnd 在这个 issue 下问：
  "what OS are you on and is there anything special you did to get tensor split mode working
  on your 2x B70 setup?"** -> **存在一个能跑通的 2xB70 张量切分配置，值得去翻这个 issue 的完整回复。**

### 1.4 6 卡 192 GB Battlematrix（craftrigs.com，Linux + IPEX-LLM）

- <https://craftrigs.com/guides/intel-battlematrix-192gb-vram-workstation-under-10k>
- 6x B70 = 192 GB，双路 CPU，每路 3 卡（否则 CPU1 内存饿死，GPU0 67% / GPU5 34%）。
- 启动串：

```
ZE_AFFINITY_MASK=0,1,2,3,4,5
ONEAPI_DEVICE_SELECTOR=level_zero:gpu
./llama-server -m model.gguf -c 32768 -ngl 99 \
  --split-mode row --tensor-split 0.17,0.17,0.17,0.17,0.17,0.15
```

- 数字：70B Q4_K_M（38.5 GB）4.2 tok/s @4K、3.8 tok/s @32K；122B Q5_K_M（76.8 GB）2.1 tok/s @4K。
- **`ZE_ENABLE_PCI_ID_DEVICE_ORDER=1` 会改变枚举顺序**：oneAPI 2025.0 有 3 个已知多卡 SYCL event
  问题，这个 workaround 开了之后，**已经调好的 tensor-split 权重会错配到错的卡上，输出直接变垃圾**。
  要么在调权重之前设，要么别设。
- `intel_gpu_top` 验证：6 张卡都该在 95 至 100% 利用率。

### 1.5 eRacks 双 B70 实测（外部，Linux，2026-08-26）

<https://blog.eracks.com/?p=3946/>

- 栈：llama.cpp 官方 Intel build（SYCL）+ rootless Podman，OpenAI 兼容 API。
- 数字：**Qwen3-14B 54 tok/s；Qwen3.6-27B 26 tok/s（单卡）**，GGUF 4-bit，16K 上下文。
- 作者用法：**一张卡服务模型，第二张卡自由地跑第二个模型 / embedding 模型 / 给更多用户留余量**。
- **三个「没人写」的坑**：
  1. Linux 电源管理在三个层级（runtime PM、PCIe 端口电源、display engine）把无头 Arc 卡睡死，
     多卡系统上第二张卡会锁死到下一次完全断电。要 udev 规则 + 开机服务 + 两个内核启动参数三层配置。
     **暖重启救不回来，只有冷断电能救。**
  2. rootless 端口转发每次请求都重置连接——现象和应用崩溃一模一样，能吃掉几小时到几天的调试时间。
     现在这类栈一律绑 host 网络。
  3. 容器镜像格式会静默丢构建指令；上游配置文件里的行内注释会变成字面参数，启动即崩。
- 价格参照：单卡 AIDAN 起 $13,895；双卡 AINSLEY（Threadripper）起 $21,395；8 卡 HIGHLANDER 起 $154,995。

### 1.6 快科技：4 卡 B70 评测（2026-07-06）

<https://news.mydrivers.com/1/1134/1134459_4.htm>

- 单卡 Qwen3-4B：B70 32GB 比 RTX Pro 4000 Blackwell 24GB **快 15%**（预处理与生成两段都是）。
- **并发爬升后反转**：并发 40 时 B70 领先 **83%**，之后稳定保持 **70%**（KV 缓存吃掉 24 GB 卡的空间）。
- **双卡高并发下几乎是单卡的 2 倍。**
- **4 张 B70 硬件采购成本约为同规格 NVIDIA 专业卡的 30%**，配 OpenClaw 零授权费、零边际调用费。
- 128 GB 显存可跑 8bit 70B 并留足 KV 缓存。

### 1.8 两条 B 站实测视频（2026-10-24 转录归档）

- **kyuz0「【中字】老外实测评 Intel Arc B70 本地AI算力」**（BV1WfVV67ENt，26:37，2026-05-30 发布）：
  单卡评测，附 **88 条 SYCL/Vulkan 对照实测**（build 9039 / Fedora 43 / llama-bench pp512+tg128+深 KV 剖面）。
  核心：BF16 稠密 SYCL 解码只剩 Vulkan 的 0.17 至 0.29 倍；MoE Q4 反过来（SYCL 解码快 1.85 至 2.23 倍）。
  详见同目录 `external-kyuz0-b70-bench.md`（原始机转文字 `raw-kyuz0-b70-transcript.txt`）。
- **讲广普的YEX「两万元内拿下64G大显存新卡？但intel B70能好用吗？双卡搭建实测分享」**
  （BV1vCV66GEAv，10:28，2026-06-02，2.9 万播放 / 192 评论）：**双卡评测**。
  他没跑通双卡协同（只做到两卡各一个独立进程），但原话结论和我们逐字同向：
  「双 B70 的核心价值**不是让单请求跑得更快**，而是提高并发容量」。
  详见同目录 `external-dual-b70-yex.md`（原始机转文字 `raw-yex-dual-b70-transcript.txt`）。

### 1.7 反面意见（必须记，否则调研是偏的）

<https://specpicks.com/reviews/intel-arc-pro-b70-llm-scaler-vllm-14-budget-inference-2026>

- Intel 的 vLLM fork（llm-scaler-vllm）张量并行：**PCIe 4.0 x8 + x8 板上只有 1.5 至 1.7x 扩展，
  不是 CUDA 双卡的 1.85 至 1.95x**。原因：这个 fork 比上游更激进地跨总线搬 attention 激活；
  Arc 产品线没有 NVLink 等价物，**纯总线受限**。
- 1.3 版多卡路径的内存泄漏是该 fork 最高频的 bug report；1.4 号称修了。
- 其他：B70 TGP 225 W + 瞬态，550 W 电源纸面够但持续负载会不稳，建议 650 W；
  别配 PCIe 通道少的 CPU（Ryzen 5 5500 + PCIe 3.0 x16 会掉 15 至 25% 预填充）。

---

## 2. 与我们已测结论的交叉核对

| 我们的结论 | 外部是否一致 |
| --- | --- |
| 双卡拆层不赔速度（35.14 vs 单卡全驻 31.46，比 spill 快 2.55x） | 一致：快科技「双卡高并发几乎是单卡 2 倍」；eRacks「一卡跑模型、二卡跑第二个模型」 |
| `-ts` 比例几乎不影响速度 -> 瓶颈不在跨卡次数 | 一致：machx 也说单请求下两卡轮流干活（4.3+5.2 ms/token）是主要开销 |
| **`-sm row` 在我们 build 11431 上加载即断言失败** | **不一致**：craftrigs 6 卡 Battlematrix 用 `--split-mode row` 跑通了。**说明是我们的 build/环境问题，要去复现** |
| 固定开销对页缓存高度敏感（冷 543.31 s / 热 406.29 s） | 一致（外部没人量化，但「服务别重启」是同一条建议） |
| 多卡容量是 3 倍不是 2 倍（要显式 `--parallel = ctx/262144`） | 一致：eRacks「第二张卡跑第二个模型」是同一件事的另一种说法 |
| **`-sm tensor` 双卡 28.65 至 29.22，比单卡全驻 31.46 还慢**（2026-10-24 实测） | 同向：machx 说单请求下两卡轮流干活是主要开销；specpicks 说 vLLM fork 张量并行只 1.5 至 1.7x；YEX 视频评论区「没跑满还是因为 PCIe 撑不住卡间通信」——**张量并行的跨卡开销 > 收益** |
| 双卡拆层 +12 至 19%、不赔速度 | 一致：YEX 视频「核心价值不是让单请求跑得更快」；快科技「双卡高并发几乎 2 倍」 |

**一条必须守住的边界**：machx 的 35B-A3B 是 **Qwen3.8** 代际，我们测的是 **Qwen3.6-35B-A3B**；
eRacks 的 27B 26 tok/s 是**单卡 Linux 4-bit**，我们的 75.9/113 tok/s 是**单卡 Windows Q4_0 全驻**。
**这些数字之间不能互相印证，只能并列呈现。**

---

## 3. 待办（按优先级）

1. ✅ **已测（2026-10-24）**：`--split-mode tensor` 在 2xB65 上**跑通**（`-fa on` 是硬前提，脚本所有跑法都已开），
   但是全场最慢——decode 28.65 至 29.22 < 单卡全驻 31.46 < 拆层 35.14 至 37.30；`-ts` 比例几乎不影响（+2%）。
   数据：`bench/data/2026-10-24_b65-32g-q8_0-dual-tensor-scan.json`。
   **结论：4 卡不走 tensor；拆层是唯一不赔速度的协同模式。**
2. ✅ **已测（2026-10-24）**：`GGML_SYCL_ENABLE_HOST_PINNED_MEM=0`。tensor 上无效（同批单变量 28.65->28.91）；
   layer 上本批 36.67 vs 10-23 批 35.14（+4.3% 但跨日期、非单变量，**不归因给开关本身**）。
3. **翻 issue #27888 完整回复**，找 tv1wnd 问的那个「2xB70 tensor split」到底怎么配的。
4. **读 `intel/compute-runtime#948`**——单次 >=512 MiB pageable 拷贝 fault copy engine，
   在 B70/B580 上复现。**这可能就是我们「进程静默消失 / DEVICE_LOST」的另一条独立成因**，
   和已知的 TDR 线是两回事。
5. **>=64 MiB 分配做 page-alias 自检**（machx 的做法）——两个 2 MiB page 可能由同一物理 page 背书。
6. 四卡：先解决「起得来」，再谈速度。**没有任何外部来源实测过 4xB70 的张量并行速度。**

---

## 4. 一句话给客

> 双卡买**吞吐与容量**，不买单任务速度——张量并行我们实测比单卡还慢，
> **拆层是唯一不赔速度的协同模式**；四卡目前没有任何人实测过张量并行速度，官方文档也只说优化到 2 卡。
> 真要上四卡：走拆层，别走张量并行。

---

*归档：外部链接均为 2026-10-24 可访问内容。引用的第三方数字归原作者，条件已随文标注。*
