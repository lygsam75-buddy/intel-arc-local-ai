# Intel 多卡（双卡/四卡串联）技术现状：2026-10-24 扫一轮

> 本文是**外部资料归档 + 判断**，不是客户文档。对外结论另写进 `docs/`。  
> 判据：**每条都标来源**；官方数据与我们实测分开列，**不并排下结论**。

---

## 0. 一句话

**硬件没变，软件在动。** Arc Pro B 系列到今天仍然**只有 PCIe**，没有 Xe-Link / NVLink 那类专用互联；  
但 2026 年下半年 Intel 在多卡这条线上确实推了几样东西：

1. **BIOS 里把 x16 拆成 x8/x8，P2P 带宽从 33 GB/s 提到 >40 GB/s**（Intel 官方 KNOWN_ISSUES，根因还没查清）；
2. **oneCCL 现在能在 P2P 与 USM 之间自动回退**，并且官方给了 P2P 到底值多少的数据：  
   **小 batch 几乎没差别，batch 30 时 P2P 比 USM 高约 15%**；
3. **llama.cpp 的 SYCL 后端新增了 Level Zero 直拷路径**（`GGML_SYCL_DEV2DEV_MEMCPY=1`）  
   与 **graph record/replay**，都是 2026-10 的提交；
4. 🔴🔴 **但上面第 3 条救不了张量并行**——我们当晚实测三档拷贝路径（P2P / L0 直拷 / host 中转），  
   解码速度 29.08 / 29.19 / 29.50，**三档在噪声内**。卡间拷贝不是瓶颈。

第 2 条是关键：**它解释了为什么张量并行在解码上不划算**——解码是典型的小 batch，  
P2P 在这个场景本来就没什么可省的。不是实现烂，是负载不吃这一套。  
第 4 条是它的实验版：我们直接把 P2P 掐掉（强制走主机内存中转），速度也没掉。

---

## 1. 硬件：到今天还是没有专用互联

| 项   | 事实                                                          | 来源                     |
| --- | ----------------------------------------------------------- | ---------------------- |
| B70 | **PCIe 5.0 x16**，32 GB GDDR6，608 GB/s，TBP 230 W（LP 160 至 290） | Intel 官方规格页 SKU 245797 |
| B60 | **PCIe 5.0 x8**，24 GB，456 GB/s，TBP 200 W                    | Intel 官方规格页 SKU 243916 |
| 互联  | 规格表里**只有 PCIe**，没有 Xe-Link / 桥接器一类的项目                       | 同上（反向证据）               |

- **Xe-Link 是 Data Center GPU Max（Ponte Vecchio）的东西**，不在 Arc Pro B 系列的规格里。
- **B60 做成 x8 是刻意的**：两个 x16 槽拆成 x8/x8 就能插 4 张 B60，不用 PCIe switch。  
  这也是 Battlematrix 8 卡方案的物理前提（4 张双芯片板卡，每板两个 B60 芯片）。
- **Battlematrix 的「多卡互联」= PCIe + switch，不是专用互联。**  
  Intel 自己的措辞是「多卡互联方案」，但落地形态是 PCIe 拓扑，不是 NVLink 那种。

**推论**：卡间带宽天花板 = PCIe。这一层没有新解法，2026 年也不会 suddenly 出现一个。

---

## 2. 官方软件栈：llm-scaler / vLLM / oneCCL

> 仓库 `intel/llm-scaler`（576 ★），**2026-10-23 仍在更新**。  
> 三条线：`vllm/`、`sglang/`、`omni/`。**我们 ComfyUI 用的 `omni_xpu_kernel` 就是这个仓库的 omni 线。**

### 2.1 oneCCL 的 P2P 与 USM：官方给数了

原文（`vllm/README.md` §2.1）：

> The image includes OneCCL with **automatic fallback between P2P and USM memory exchange modes**.
>
> ```
> export CCL_TOPO_P2P_ACCESS=1  # P2P mode
> export CCL_TOPO_P2P_ACCESS=0  # USM mode
> ```
>
> - **Small batch sizes show minimal difference.**
> - **Large batch sizes (e.g., batch=30) typically see around 15% higher throughput with P2P mode compared to USM.**

**这条要贴在墙上。** 它把「张量并行值不值」这件事量化了：

- 解码（batch 小）→ P2P 省不出东西 → **all-reduce 的固定开销就是纯赔**；
- 预填充（batch 大）→ P2P 值 ≈15% → 但前提是 all-reduce 本身的开销小于这 15%。

我们 2026-10-24 实测的 `-sm tensor`：decode 28.65、prefill 45.44，两项都低于拆层  
（35.14 / 59.40）——**与这条官方数据同向：连 prefill 的 15% 都补不回 all-reduce 的代价。**

### 2.2 oneCCL 的架构弱点（第三方权威）

ACM Computing Surveys《The Landscape of GPU-Centric Communication》对 oneCCL 的定性：

- **oneCCL 不在 GPU kernel 里跑集合通信**，它是 **CPU worker 线程驱动**的中间件，构建在 MPI / libfabric 上；
- 原文：*"oneCCL's GPU participation remains dependent and host-driven"*；
- 原文：*"direct Level Zero and IPC-based approaches can outperform oneCCL for GPU–GPU collectives  
  when host intervention becomes a limiting factor"*。

**翻译**：NCCL 的集合通信是 GPU 自己在算；oneCCL 是 CPU 在指挥。卡少、消息小的时候看不出来，  
卡一多、host 一旦成为瓶颈，oneCCL 就拖后腿——**而且论文直接说，绕过 oneCCL 用 Level Zero + IPC 可以更快**。

这正好对上 llama.cpp 走的路：它不走 oneCCL，自己用 Level Zero IPC 做卡间拷贝。

### 2.3 官方的多卡能力矩阵（`intel/vllm` 0.21.0 镜像）

| 并行方式     | 后端              | 状态              |
| -------- | --------------- | --------------- |
| TP（张量并行） | oneCCL（xccl）    | 支持              |
| PP（流水并行） | 单节点 `mp` 后端     | 支持              |
| DP（数据并行） | 权重复制，各跑各的 batch | 支持              |
| EP（专家并行） | —               | 实验性，支持 TP+DP+EP |

- 官方验证过的例子：**Qwen2.5-VL-32B 跑在 4 张 B60 上**（多模态）。
- 多节点 PP/TP 走 **Docker Swarm / SSH / MPI / Ray**。
- BKC（0.21.0）：Ubuntu 24.04、Python 3.12、PyTorch 2.11、oneCCL 2021.15.9.14、KMD 7.0、UMD 26.14。
- **全部是 Linux + Docker。Windows 不在官方验证范围内。**

### 2.4 官方自己的多卡性能曲线（这条最有说服力）

Intel 公布的 Llama-3.1-8B-Instruct FP16 推理数据（1 / 2 / 4 卡 B60）：

| 并发  | 单卡        | 4 卡         | 倍数           |
| --- | --------- | ----------- | ------------ |
| 低并发 | —         | —           | **与单卡几乎无差别** |
| 100 | 396 tok/s | 1,595 tok/s | **约 4×**     |

- 来源：Intel 官方多卡方案新闻稿 / 媒体转述的官方测试图。
- **读法**：Intel 卖的也是**吞吐**，不是单请求速度。低并发时 4 卡和 1 卡一样快——  
  **跟我们实测的「单步 42.30 → 42.41」是同一件事**，只是他们在 B60 上用 vLLM、我们在 B65 上用 ComfyUI。

---

## 3. 那条免费的红利：BIOS x8/x8

`intel/llm-scaler` 的 `vllm/KNOWN_ISSUES.md` 第 02 条原文：

> **Limited 33 GB/s Bi-Directional P2P Bandwidth with 1x GPU Card**  
> When using a single GPU card over a x16 PCIe connection without a PCIe switch, the observed  
> bi-directional P2P bandwidth is limited to **33 GB/s**.  
> Workaround: Change the PCIe slot configuration in BIOS from Auto/x16 to **x8/x8**.  
> With this change, **over 40 GB/s** bi-directional P2P bandwidth can be achieved.  
> **Root cause analysis is still in progress.**

三点要注意：

1. **反常识**：把 x16 拆成 x8/x8，带宽反而涨。原因官方没查清（"still in progress"），  
   现象是双向 P2P 流量在单卡独占 x16 时吃了非对称的亏。
2. **是 workaround，不是设计**：说明后面还有优化空间，不是终局。
3. **前提是主板支持 x8/x8 拆分**，而且**两张卡都得在 CPU 直连槽上**。

### 3.1 我们这台机器：拿不到这条红利

| 项    | 值                                    |
| ---- | ------------------------------------ |
| 主板   | 技嘉 **B850M FORCE WIFI6E**（mATX）      |
| CPU  | Ryzen 5 9600X（PCIe 5.0，16 lanes 给显卡） |
| 当前拓扑 | 卡 0 在 CPU 直连 **x16**，卡 1 在芯片组 **x4** |

- mATX 板只有**一条** CPU 直连全长槽，第二条是芯片组 x4 → **物理上做不了 x8/x8 双卡**。
- 🔴 **本机不打算换板**（2026-10-24 定）：能拆 x8/x8 要 X870 那一级芯片组，那是工作站，  
  已经背离「一台主流电脑跑本地大模型」这个前提。**这条红利只当背景记录，不落地、不对外推荐。**
- 换板 + 进 BIOS 改设置本来也要他本人动手（拆机 + 重启），不划算。

**这条对外怎么讲**：x8/x8 只影响**卡间拷贝带宽**，而卡间拷贝**不是我们这条路径的瓶颈**。

- 实测（2026-10-24，2× B65）：把两卡之间的 P2P 完全掐掉（`GGML_SYCL_DEV2DEV_MEMCPY=2`，  
  强制走主机内存中转），层切分解码 **37.38** vs 默认 P2P 的 **37.29**——**在噪声内**。
- 另一头也有实测：同一张 B65 单独跑 H3，插芯片组 **x4** 槽是 **42.31 s/it**、  
  插 CPU 直连 **x16** 槽是 **42.41 s/it**。

→ **层切分不吃链路宽度，主板拓扑对这条路不是变量。** 真正吃带宽的是拿卡间通道做高频同步  
（张量并行），而那条路本身是赔本的（§4.1）。

---

## 4. llama.cpp 这边 2026-10 的增量

### 4.1 新增 Level Zero 直拷

`ggml/src/ggml-sycl/ggml-sycl.cpp`，`dev2dev_memcpy()` 现在三档（`GGML_SYCL_DEV2DEV_MEMCPY`）：

| 值         | 名字             | 实现                                                                                           |
| --------- | -------------- | -------------------------------------------------------------------------------------------- |
| **0**（默认） | SYCL API       | `ext_oneapi_can_access_peer()` 判定 → `enable_peer_access()` → 直接 memcpy；**不支持则静默回落到 host 中转** |
| **1**     | Level Zero API | `zeCommandListAppendMemoryCopy`，只对两张都是 dGPU 生效                                               |
| **2**     | Host Forward   | 显式走主机内存中转（`memcpy_host_forward`）                                                             |

- 前提：`GGML_SYCL_SUPPORT_LEVEL_ZERO_API` 编译开关 + `GGML_SYCL_USE_LEVEL_ZERO_API=1`。  
  **我们的 build 两个都满足**（运行日志里打印 `GGML_SYCL_SUPPORT_LEVEL_ZERO_API: yes`、  
  `GGML_SYCL_USE_LEVEL_ZERO_API: 1`、`GGML_SYCL_DEV2DEV_MEMCPY: 0 (SYCL API)`）。
- **判据**：拿 0 / 1 / 2 三档同配置对照。  
  若 0 与 2 一致 → **P2P 从来没生效，一直在走 host**；若 1 单独更高 → L0 直拷是真解法。

**实测结果（2026-10-24，2× B65，Q8_0 34.37 GiB，`-ts 50,50`，各 3 次取中位数）**

| `GGML_SYCL_DEV2DEV_MEMCPY` | `-sm tensor` decode | `-sm tensor` prefill | `-sm layer` decode | `-sm layer` prefill |
| -------------------------- | ------------------- | -------------------- | ------------------ | ------------------- |
| **0** SYCL peer（默认）        | 29.08               | 47.34                | 37.29              | 61.77               |
| **1** Level Zero 直拷        | 29.19               | 44.80                | 36.81              | 60.15               |
| **2** host 中转（P2P 掐掉）      | 29.50               | 42.17                | 37.38              | 59.90               |

**读法**：

1. 🔴🔴 **三档拷贝路径在解码上没有差别**（极差 1.5%），而**同一档内 3 次跑动的极差本身就有 2.25 tok/s**。→ **卡间拷贝路径不是 decode 的瓶颈**。即使把 P2P 完全掐掉走主机内存，速度也不掉。
2. 🔴 **张量并行与层切分的差距跨批次复现**：本批 29.19 vs 37.16（差 27%），早批 28.65 vs 35.14~~37.30（差 22~~30%）。**两批同向**。  
   ⚠️ 但「层切分 35.14 → 37.30」那段**不是趋势，是场次波动**：同一天 16:10 场次的 `50,50`  
   就量到 37.29，与 17:37 场次的 60/40 / 80/20 / 90/10 完全重合。**同一配置跨场次能差 6%。**
3. ⚠️ prefill 那一列有个单调趋势（tensor 47.34 → 44.80 → 42.17），但 layer 列刚好反过来且幅度小，且 prompt 只有 19 token。**只记现象，不给因果。**
4. **结论**：「换一条更底层的卡间拷贝路径来救张量并行」这条路，实测堵死。省下的力气应该花在「减少同步次数」上（层切分就是这么做的），而不是「让每次同步更快」。

### 4.2 其他相关提交（2026-10-21 至 10-23）

| PR     | 内容                                                                        | 对多卡的意义                                           |
| ------ | ------------------------------------------------------------------------- | ------------------------------------------------ |
| #28725 | sycl: **Add graph record and replay**                                     | 降 CPU 端每层提交开销；层切分的固定开销有望下降                       |
| #27168 | SYCL/OpenCL P2P 在 OpenCL 适配器上 `ur_die`（**已关闭**）                           | 顺带暴露了上面那套 P2P 代码路径；Level Zero 适配器上可用             |
| #25423 | SYCL 张量并行加载 20+ 分钟（**已关闭**）                                               | 用户环境 2×B70 + 驱动 8804；说明 TP 的加载路径曾经很烂             |
| #26581 | **B70 上 decode attention 是访存延迟受限**，每 KV 位置每层恒定 ≈21 至 25 ns，Vulkan 与 SYCL 一样 | **架构性**的，不是后端问题；解释了长上下文为什么线性变慢                   |
| #28967 | **NCCL 只给 CUDA 实现**（多节点 TP）                                               | **Intel 没有对应的跨节点集合通信实现**，多机 Intel 卡走不通 llama.cpp |

### 4.3 `-sm row`：已复现两次，确认是 build 问题

**实测（2026-10-24，2× B65，Q8_0，`-ts 50,50` 与 `70,30` 各起一次）**

```
<本机工作目录>\llama.cpp\ggml\src\ggml-backend.cpp:1081: pre-allocated tensor
(blk.0.attn_norm.weight) in a buffer (SYCL_Split) that cannot run the operation (NONE)
```

- **两次报错逐字一致**，与 2026-10-23 那次也完全一样；都停在**装载权重**阶段，没进推理。
- 日志里**没有** OOM / `OUT_OF_RESOURCES` / `DEVICE_LOST` → **不是显存不够**，  
  是 `SYCL_Split` 这个 buffer 的能力声明（`NONE`）与 row 切分要做的操作对不上。
- 外部 6 卡 Battlematrix 用 `--split-mode row` 跑得通 → **是这份 build 的问题，不是 row 在 SYCL 上不可用**。
- 🔴 **对外口径：双卡只推 `-sm layer`。** row 不做承诺，也不当备选方案写。
- 记录：`bench/data/2026-10-24_b65-32g-q8_0-dual-row-recheck.json`。

### 4.4 `-ts` 细扫与 Q4_0 档：拆层不是「第二张卡来帮忙算」

**2026-10-24 17:37 至 17:47 同一时段连跑**（`bench/data/2026-10-24_b65-32g-dual-ts-scan2.json`、  
`2026-10-24_b65-32g-q4_0-solo.json`、`2026-10-24_b65-32g-q8_0-solo37-recheck.json`）：

| 配置                   | 模型                  | 解码 tok/s  | 相对单卡       |
| -------------------- | ------------------- | --------- | ---------- |
| 单卡 `-ngl 99`         | Q4_0 19.41 GiB 全驻   | **53.63** | 基准         |
| 双卡 `-sm layer 50,50` | Q4_0                | 49.80     | **−7.1%**  |
| 双卡 `-sm layer 90,10` | Q4_0                | 50.95     | −5.0%      |
| 单卡 `-ngl 37`         | Q8_0，约 4 GiB 层落 CPU | **31.86** | 基准         |
| 双卡 `-sm layer 60,40` | Q8_0 全驻显存           | 37.35     | **+17.2%** |
| 双卡 `-sm layer 80,20` | Q8_0                | 37.32     | +17.1%     |
| 双卡 `-sm layer 90,10` | Q8_0                | 37.41     | +17.4%     |

三条读法：

1. 🔴🔴 **单卡本来就装得下时，拆层是负收益**（Q4_0 −5–−7%）。切点同步是纯开销，第二张卡在解码上一点忙都没帮上。**双卡的准确价值是「把单卡装不下的模型变成全驻显存」。**
2. 🔴 **`-ts` 比例对解码没有可测影响**：Q8_0 同场次四档 37.29 / 37.35 / 37.32 / 37.41，极差 0.3%；Q4_0 两档 49.80 / 50.95。早批那个「单调上升」已确认是场次波动（见 §4.1 读法 2）。
3. ⚠️ Q8_0 的 +17% **不是「两个卡一起算」**，是原来约 4 GiB 层被挤到 CPU 上、现在全回显存。所以这条数字**不能**拿来证明「双卡能加速单条任务」——Q4_0 那一组才是干净的对照。

### 4.5 3M 上下文：分配成功 ≠ 跑得动（把整机跑挂过一次）

**完整取证 `bench/notes/ctx3m-hang-2026-10-24.md`，数据件 `2026-10-24_b65-32g-q4_0-ctx3m-probe.json`。**

- 3M 档（`-c 3145728 --parallel 12`）装载成功、短请求正常（decode 31.86 tok/s），  
  但一条 35,401 token 的长 prompt 让 prefill 卡在 8192 token，**14 分钟后整机静默卡死**。
- **不是 GPU 超时**：无 WATCHDOG dump、无 minidump、无 WER 报告，只有 Kernel-Power 41。
- **是主机提交内存顶穿**：进程私有 73.11 GB、整机提交 91.79 / 95.11 GiB（96.6%）。
- **对照**：同 prompt 单卡 `-c 262144`，prefill 937.39 tok/s / 38.64 s，提交仅 43.7%。
- **页面文件 64 GB 是帮凶**：让系统敢承诺 95.11 GiB，本该「进程报 OOM 自己退」变成「整机卡死」。  
  ✅ **已定案：初始 = 最大 = 32768 MB（32 GB 固定）**，3M 档失败形态实测变成「进程报 OOM 自己退」。  
  数据 `2026-10-24_b65-32g-q4_0-ctx3m-loadonly-pf3232.json`。
- ⛔ **3M 这条线不再测。** 对外只作「分配上限」，可用上限报单卡 1M / 双卡默认 1.75M。

---

## 5. 结论：双卡/四卡串联今天有什么、没什么


| 层面        | 有没有新解法             | 说明                                                                           |
| --------- | ------------------ | ---------------------------------------------------------------------------- |
| 硬件互联      | ❌ **没有**           | 只有 PCIe。没有 Xe-Link。天花板没动                                                     |
| BIOS 拓扑   | ✅ **有，且免费**        | x8/x8 拆分：33 → >40 GB/s 双向 P2P。我们这块 mATX 板做不到                                 |
| 卡间通信      | ⚠️ **有增量，但对解码无用**  | oneCCL 支持 P2P/USM 自动回退；llama.cpp 新增 L0 直拷——**实测三档在 decode 上无差别**             |
| 张量并行      | ⚠️ **仍是赔本**        | 官方自己说小 batch 下 P2P 收益 minimal；实测 decode 29.19 vs 拆层 37.16（差 27%），两批同向        |
| 层切分       | ⚠️ **买容量，不买单任务速度** | 单卡装不下的 Q8_0：+17.2%（37.35 vs 31.86，同场次）；单卡装得下的 Q4_0：**−7.1%**（49.80 vs 53.63） |
| `-sm row` | ❌ **本机跑不起来**       | build 11431 装载即退（§4.3），不对外承诺                                                 |
| `-ts` 比例  | ➖ **无可测影响**        | Q8_0 同场次四档极差 0.3%，Q4_0 两档差 2.3%；都在噪声内                                        |
| 跨节点       | ❌ **Intel 没有实现**   | llama.cpp 的 NCCL 只做了 CUDA                                                    |
| Windows   | ❌ **无官方多卡栈**       | llm-scaler / vLLM 全是 Linux + Docker                                          |

**一句话给客户**：多卡买的是显存和并发，不是单条速度——这一点 2026 年没有变，Intel 自己的性能图（低并发 4 卡 = 单卡，并发 100 时 4×）就是同一个结论。

🔴 **别把「换主板 / 上四卡」当建议给出去。** 本机定位就是一台主流电脑：B850M 这一级 mATX 板 + 一颗主流 CPU + 两张卡。实测支撑（§3.1）：拆层模式下  
卡间 P2P 掐掉速度不掉、芯片组 x4 槽与 CPU x16 槽单跑一个水平 →**x8/x8 那条红利只对高频同步（张量并行）有意义，而张量并行本身就是赔本的。**

🔴🔴 **也别把「上下文写到 3M」当卖点。** 3M 只是分配上限：一条 35k token 的长 prompt就把整机跑成静默卡死（§4.5）。**可用上限单卡 1M / 双卡默认 1.75M。**

---

## 6. 待验证 / 待办

1. ✅ **dev2dev 三档实测已完成**（2026-10-24）——`bench/data/2026-10-24_b65-32g-q8_0-dual-dev2dev-scan.json`，结论见 §4.1：三档无差别。
2. ✅ **`-sm row` 已复现两次**（2026-10-24）——`bench/data/2026-10-24_b65-32g-q8_0-dual-row-recheck.json`，结论见 §4.3：build 问题，不对外承诺。
3. **`SYCL graph record and replay` 对层切分固定开销的影响**——build 11753 之后才有，需要确认我们的 build 是否已包含。
4. ⛔ **换 ATX 板验证 x8/x8**——**不做**：要 X870 那一级芯片组，等于换掉「主流电脑」这个前提。
5. ⛔ **B60 x8 卡在 x8/x8 主板上的 P2P 实测**——既没有第二张 B60，也不换板，做不了。
6. ✅ **`-ts` 细扫 + Q4_0 档双卡/单卡同场次对照**（2026-10-24）——§4.4：  
   单卡装得下时拆层 −7.1%，`-ts` 无可测影响。
7. ✅ **3M 上下文跑不跑得动**（2026-10-24）——§4.5：短请求正常，长 prompt 把整机跑死。护栏已写进 `dual_ctx_probe.py`（`--max-commit-frac 0.90`）。
8. ✅ **页面文件已定案（2026-10-24 晚实测闭环）**：初始 = 最大 = 32768 MB（32 GB 固定）。「初始小 + 最大大」锁不住（Windows 扩回 86.97 GiB / 提交 98.9%）；32/32 锁死 commit limit，63.11 GiB 后，3M 装载 20.4 s 报 SYCL alloc FAILED 自己退、提交峰值只到 55.4%、limit 全程不扩。终局结论见 `ctx3m-hang-2026-10-24.md` §5.1。
