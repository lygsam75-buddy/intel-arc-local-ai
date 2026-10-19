# 坑清单

每个坑记三件事：**现象 → 根因 → 修法**。持续追加。

> 收录标准：踩过一次、复现过、修好了。没修好的标 `[未解]`。

---

## 一、环境与工具链

### 1.1 oneMKL 版本必须和 SYCL 运行时对齐

**现象**：编译通过，运行时报符号缺失或直接崩溃。

**根因**：oneMKL 与 SYCL 运行时的 ABI 是绑定的。例如 oneMKL **2026.1 需要 sycl9**，而本机 DPC++ 运行时是 **sycl8**，混用就炸。

**修法**：先确认本机 SYCL 运行时版本，再选对应的 oneMKL：

```powershell
# 本机实测可用组合
$mkl   = '<oneMKL 目录>'
$dpcpp = '<SYCL 运行时目录>'
$env:PATH = "$dpcpp;$mkl\bin;$env:PATH"
```

**别做的事**：看到新版本就升。先查 ABI 对应关系。

---

### 1.2 Arc 上 SYCL 首次 JIT 编译要几十秒

**现象**：第一次启动卡很久，看起来像「挂了」。

**根因**：SYCL 内核在首次运行时 JIT 编译。AOT 需要 `ocloc`，本机不一定有。

**修法**：

```
SYCL_CACHE_PERSISTENT=1
```

开着持久化缓存，后续启动直接命中。**首次慢是正常的，不是故障**，别急着判断失败。

---

### 1.3 两套运行时的 PATH 要求互相冲突（llama.cpp 要，torch 不要）

同一台机器上，**llama.cpp（SYCL）和 torch（XPU）对 `<SYCL 运行时目录>`
的要求完全相反**：

| 运行时 | 要求 | 不满足的后果 |
|---|---|---|
| llama.cpp SYCL | **必须在 PATH 里** | 退出码 `0xC0000005`（访问冲突），1 秒内崩，stderr 全空 |
| torch XPU | **不能在 PATH 最前** | `torch.xpu.is_available()=False`、`device_count=0` |

**根因**：该目录里带 `OpenCL.dll` + `cl.cfg` + `common_clang64.dll`。
- 对 torch：这个 `OpenCL.dll` 会覆盖系统 OpenCL ICD，Intel 的 GPU 实现被顶掉，只剩 CPU 设备。
- 对 llama.cpp：`ggml-sycl.dll`（65.7 MB）并非完全自足，缺这个目录的 DLL 就直接访问冲突。

**实测对照（2026-10-15）**：

```bash
# torch：加了就挂
export PATH="<oneAPI 安装目录>/Library/bin:$PATH"
python -c "import torch; print(torch.xpu.device_count())"   # → 0

# llama-bench：不加就挂（0xC0000005，无任何输出）
"<llama.cpp>/build/bin/llama-bench.exe" --version
```

**修法**：**不要共用一个 shell 环境**，两套东西分开跑。
- 跑 llama.cpp：`PATH=<SYCL 运行时目录>;<oneMKL 目录>;<其余>`
- 跑 torch / ComfyUI：**别加这个目录**

采集脚本 `xpu_bench.py` 已把这条固化：`--sycl-path` 默认只对 llama-bench
子进程生效，不污染外层环境。

**教训**：排查「GPU 认不到」或「程序秒崩」时，**先把自己加的环境变量撤掉再测一遍**。
否则很容易把环境自己造成的故障当成硬件/驱动问题，白查半天。

---

### 1.4 双 Intel 卡共存会让 llama.cpp 崩在 P2P 上

**现象**：装机第二张 Intel 卡后，llama-bench / llama-cli 直接终止：

```
ur_die: Experimental P2P feature is not implemented for OpenCL adapter.
```

**根因**：SYCL 枚举到多张 GPU 后，llama.cpp 尝试在卡间建立 P2P 访问，
而当前驱动走的是 **OpenCL adapter**（非 Level Zero），不支持这个实验特性。
注意：这跟卡本身没关系，是**后端选错了**连带触发的。

**修法**：限定只用一张卡。

```bash
ONEAPI_DEVICE_SELECTOR=opencl:0    # 0 = 第一张，索引以 sycl-ls 枚举为准
```

**别用 `level_zero:0`**——本机 SYCL 工具链虽然编译时
`GGML_SYCL_SUPPORT_LEVEL_ZERO_API: yes`，运行时却明确打印：

```
SYCL GPU device 0 does not use Level Zero backend, disabling Level Zero memory API
```

指定不存在的 `level_zero:0` 只会得到一个访问冲突。

---

### 1.4b Windows 的 PCIe 链路宽度读数在 Arc 上是**假的**

**现象**：想用系统接口确认「这张卡现在到底跑在 x4 还是 x8」，
`Get-PnpDeviceProperty` 读 `DEVPKEY_PciDevice_CurrentLinkWidth` 返回 **1**。

```powershell
Get-PnpDeviceProperty -InstanceId $id |
  Where-Object KeyName -match 'LinkWidth|LinkSpeed'
# Intel(R) Arc(TM) Pro B50 Graphics
#   CurrentLinkWidth = 1     MaxLinkWidth = 1
#   CurrentLinkSpeed = 1     MaxLinkSpeed = 1     # 1 = 2.5 GT/s，明显是空闲态
```

**根因**：Intel Arc 驱动没有填这几个 DEVPKEY，Windows 只能给出设备空闲时的默认值。
同一台机器上 AMD 那张卡读数完全正常（`16 / 4` = Gen4 x16），说明不是接口本身坏了，
是 **Arc 驱动不报**。带载运行时再读一次仍是 1。

**修法**：
- **不要**拿这组 DEVPKEY 当「槽位是 x4 还是 x8」的证据，也不要写进对客材料。
- 可用的替代证据只有两条：① 主板规格（PCIE2 是芯片组挂 x4）；
  ② `DEVPKEY_Device_LocationInfo` 的**总线号**（能区分主槽与副槽，但读不出宽度）。
- 真要量链路带宽，只能自己跑 host↔device 拷贝基准（如 `bandwidthTest`），
  目前**未做**，见待解问题 #8。

---

### 1.5 SYCL 冷 JIT 会让 llama-bench 数字低近 8 倍

**现象**：同一张卡、同一套参数，两次采集差了近 8 倍。

**实测（B70 · Qwen3.6-35B-A3B Q4_0，2026-10-15）**：

| 采集 | 预填充 | 解码 |
|---|---:|---:|
| `-r 1`（冷 JIT） | 43.59 | 9.58 |
| `-r 3`（内核缓存命中） | 1341.36 | **75.92** |

**根因**：SYCL 内核首次运行时 JIT 编译。`-r 1` 的唯一次采样把编译开销算进去了。
`SYCL_CACHE_PERSISTENT=1` 的持久缓存对 llama-cli 与 llama-bench 的
内核组合并不通用，换工具等于重新编译一遍。

**修法**：
- 采集一律 `-r 3` 以上，取平均；
- **任何单次采样（`-r 1`）的数字不许进基准表**；
- 换工具、换参数、换驱动后，第一次采集视为预热，作废重跑。

#### 反向陷阱：`-r 1` 也可能**偏高**，不是只会偏低

冷 JIT 只解释了「r=1 偏低」。但 2026-10-15 在 B50 上撞到了相反的方向：

| 配置 | `-ncmoe 8` r=1 | r=3 | 差 |
|---|---:|---:|---:|
| B50 主槽 x8 | 37.13 | 37.43 / 37.74 | +0.8%（正常） |
| **B50 第二槽 x4** | **36.66** | **25.67** | **−30%** |

r=1 反而比 r=3 **快 30%**，且掉速发生在同一轮测试**过程中**。
（当时怀疑散热/供电：B50 LP 70 W 挨着 290 W 的 B70。
**后续复测证明这个 25.67 是环境脏导致的，真因见 1.7**——推断本身也错了。）

→ 所以规则要写全：**`-r 1` 既不许当基准（可能偏低），也不许当峰值（可能偏高）。
持续吞吐只能取 `-r 3`。** 若 r=1 明显高于 r=3，那本身就是要记的故障信号，不是好消息。

---

### 1.7 刚杀完大内存进程就跑 benchmark，数字会烂掉

**现象**：同一张卡、同一个槽、同一套参数，`-ncmoe 12` 跑出 **6.00** 和 **35.22**
（差 5.9 倍）；`-ncmoe 8` 一次 **OOM 崩溃**、一次 **35.89**。
差点被写成「第二槽比主槽慢 32%」的硬件结论。

**根因**：那一轮（轮1）开跑于**杀掉一个占 22.6 GB 的 `llama-server` 之后约 1 分钟**
（系统空闲内存刚从 **0.8 GB** 回到 **24.2 GB**）。
页面文件回写、modified page list 都还没落定，19.41 GiB 权重必须重新从磁盘拉入，
于是权重**没有驻留在显存**，而是被逐层从页面文件换进换出。

**决定性判据是 prefill，不是 decode**：

| 配置 | `-ncmoe` | prefill | decode |
|---|---:|---:|---:|
| 主槽 x8 | 4 | 439.81 | 15.03 |
| 副槽（脏） | 4 | **28.55** | 2.77 |
| 副槽（干净） | 8 | 371.41 | 35.89 |

prefill 是纯 GPU 计算、几乎不走 PCIe。它掉 15.4 倍，**不可能是带宽问题**，
只能是权重供不上 → 内存/页面文件压力。

**修法**：
- **杀大内存进程后，至少等页面文件回写完再采集**（经验值：等到空闲内存稳定、
  且 `Win32_PageFileUsage.PeakUsage` 不再增长为止，不要只看"进程已退出"）。
- **看到 prefill 与 decode 同时异常下滑，先查宿主内存，别先赖 PCIe。**
  decode 掉但 prefill 正常 → 才可能是带宽/卸载问题；
  **两个一起掉 → 是内存没供上。**
- 任何「某槽位/某配置突然慢 N 倍」的结论，**必须先复现至少 3 次**才准写进文档。
  一句「单次测量」的免责声明就能把污染数据送出去——别这么干。
- 反向排查技巧：把慢读数与**同一配置的历史快读数对比**。
  差 5 倍以上、且无硬件改动，优先假设测量污染，而不是硬件退化。

---

### 1.6 `llama-bench` 没有 `-c` / `--ctx-size` 参数

**现象**：`error: invalid parameter for argument: -c`

**根因**：`-c` / `--ctx-size` 是 `llama-cli` / `llama-server` 的参数，
`llama-bench` 用的是 `-b/--batch-size`、`-ub/--ubatch-size`、
`-fitc/--fit-ctx`。从 cli 的参数习惯错搬过来就报错。

**修法**：跑 `llama-bench --help` 核对，别凭 llama-cli 的印象写。

---

### 1.8 「复现 3 次」挡不住**持续存在**的污染源（`-c 16384` 断崖撤回）

**现象**：`-c 4096` 解码 **45.2**，`-c 16384` 掉到 **12.5**（−72%），
而且 prefill 也同步从 42 掉到 11。三次连续复测极稳：

```
-c 4096:  44.72 / 44.21 / 44.93   （极差 1.6%）
-c 16384: 12.47 / 12.55 / 12.51   （极差 0.6%）
```

按 1.7 的判据，prefill 与 decode **同时**下滑 → 「内存没供上权重」。
差点被写成一条硬件结论：「16 GB 卡在 16K 上下文撞上 SYCL 慢路径」。

**为什么 `1.7` 的纪律没拦住它**：1.7 要求「至少复现 3 次」。
但这条规则的前提假设是**污染是瞬态的**。这次污染源是一个**常驻的**第二个
`llama-server`（看门狗拉起的，见 3.4），它会在每一次测量里稳定地分走算力 ——
**复现 3 次只会给你 3 个一致的假数。**

**真正的判据——换一条独立代码路径交叉验证**：

| 路径 | `-c 4096` | `-c 16384` | 是否跟随断崖 |
|---|---:|---:|---|
| `llama-server`（口径 B） | 45.20 | **12.5** | “有” |
| `llama-cli -v`（同一模型同一参数） | 45.25 | **45.40** | **不跟随** |
| `llama-bench -p 512`（只支持默认 ctx） | 45.99 | — | — |

同一个模型、同一套 `-fa/-ctk/-ctv`，`llama-cli` 在 `-c 16384` 上**根本没有断崖**。
两条路径给出相反结论 → 必然是其中一条被环境影响了，而不是模型的属性。

**干净环境重测结论（B50 16G 主槽 · IQ2_M · `-ncmoe 0`）**：

| `-c` | 4096 | 16384 | 32768 | 65536 | 131072 | 262144 |
|---|---:|---:|---:|---:|---:|---:|
| decode tok/s | 45.21 | 45.07 | 45.07 | 44.47 | 44.75 | **44.93** |
| prompt tok/s | 43.24 | 44.63 | 42.88 | 41.91 | 42.51 | 43.78 |

**跨 64 倍上下文只掉 1.6%，`-c 262144`（模型原生满上下文）能加载、能跑。**
断崖不存在，**数字撤回**。

> 一个容易误导的巧合：如果上下文**真的塞到 19 万 token**，解码确实会掉到 ~12 tok/s
> （见 [`vram-16gb.md` D 节](vram-16gb.md) 的深度-速度曲线）。
> 但那一轮 probe 的 prompt 只有约 50 token —— **深度根本没上去**，
> 所以 12.5 只可能是环境问题，不是"深上下文的正常表现"。

**修法（纪律升级）**：

- **「复现 N 次」证明的是稳定性，不是有效性。** 常驻污染源会让假数同样稳定。
- **必须有第二条独立路径交叉验证**，而且两条路径要**各自成理**。
  本仓库现有三条：`llama-bench`（口径 A）、`llama-cli -v`（取分配证据）、
  `llama-server + probe`（口径 B）。**任何一条出异常值，先拿另外两条对一下。**
- 每条路径**换一台干净的进程环境**再跑一次，成本远低于写下一条错误结论。

### 1.9 Windows 的 TDR 会在 2 秒内杀掉长计算任务（AI 推理的头号「玄学崩溃」）

**症状**：跑大模型时**进程毫无征兆地消失**。没有 OOM、没有 `UR_RESULT_ERROR_DEVICE_LOST`、
没有 Python traceback —— 日志停在某一行装载/计算中途，然后就没了。

**根因**：Windows 的 **TDR**（Timeout Detection and Recovery）默认只给 GPU **2 秒**。
超过就判定「引擎挂死」，抓一个 live dump 并把进程连坐杀掉。
大模型的一次内核调度、一次权重装载本来就可能远超 2 秒 —— **这不是 bug，是默认值不适合这类负载。**

**取证（三步，按顺序）**：

```powershell
# ① 看有没有 GPU 看门狗 dump，以及最后一次是什么时候
#    ⚠️ 判据是【文件名里的时间戳】，不是事件日志的 TimeCreated ——
#    WER 会把历史积压报告在某一天集中冲刷出来，TimeCreated 全是冲刷时刻
Get-ChildItem "$env:WINDIR\LiveKernelReports\WATCHDOG" -Filter *.dmp |
    Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime

# ② 事件日志里的签名（LiveKernelEvent，P1 = 141 = 视频引擎超时）
Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=(Get-Date).AddDays(-7)} |
    Where-Object { $_.Message -match 'LiveKernelEvent' } | Select-Object -First 3 TimeCreated, Message

# ③ 确认 stderr 是被捕获的 —— 有 traceback 就说明是 Python 层问题，不是 TDR
#    （本仓库的采集器把 stdout/stderr 写同一个日志，所以「没有 traceback」本身就是证据）
```

**修法**：把 TDR 等待时间从 2 秒提高到 60 秒（[Intel oneAPI 安装指南](https://www.intel.com/content/www/us/en/docs/oneapi-toolkit/installation-guide-windows/latest/gpu-adjust-timeout-detection-and-recovery-setting.html)
对 GPU compute 给出的官方建议是「20 秒或更高」）：

```powershell
$k = 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers'
New-ItemProperty -Path $k -Name 'TdrDelay'    -Value 60 -PropertyType DWord -Force
New-ItemProperty -Path $k -Name 'TdrDdiDelay' -Value 60 -PropertyType DWord -Force
# 需要重启生效；回滚 = 删掉这两个值再重启（默认就是 2 秒）
```

**实测效果**（Arc Pro B70 32G，同一份 ComfyUI、同一个模型、同一批启动参数）：

| 状态 | 864×480 · 6 步 · 5 s 的 H3 |
|---|---|
| `TdrDelay` = 默认 2 s | **每次都在文本编码器装载中途进程消失**，日志无任何报错 |
| `TdrDelay` = 60 s | **连续 3 轮全部跑完**（188.81 / 152.54 / 159.62 s），0 个新增 dump |

⚠️ **TDR 延时是缓解，不是根治**：真死锁只会把 2 秒拖成 60 秒。
如果改完还崩，就转驱动（清装 WHQL）/ 供电 / 重插卡方向查，别继续加数值。

⚠️ **别把它和「显存不够」混为一谈**：OOM 会打印 `UR_RESULT_ERROR_OUT_OF_RESOURCES`，
TDR 死法**什么都不打印**。判据是「有没有 dump + 有没有 traceback」，不是猜。

---

## 二、显存与内存口径

### 2.1 ECC 开启会划走约 4 GB（32 GB 卡只认 27.25 GB）

**现象**：卡是 32 GB，但程序只认 27.25 GB。

**根因**：这张卡上 **ECC 处于开启态**。

> ★ **ECC 在 Intel 驱动里默认是关闭的，要人工到 IGS 打开。**
> 所以看到 27.25 GB 不是「默认就这样」，而是**这台机器的 ECC 被打开过**。
> 反过来说：新装机的卡读出来就应该是「关闭」；若读到 27.25 GB，先去 IGS 看 ECC 是不是被开了。

**修法**：关掉 ECC（IGS → Graphics → ECC → 关闭 → **重启**）→ 可用 31 GB。

**自检**：

```python
import torch
print(torch.xpu.get_device_properties(0).total_memory)
# 关 ECC 应报 ~31.16 GiB（实测 31,920.4 MB）
```

**注意**：ECC 只影响容量，**不影响算力**（实测差异都在 6% 内，关 ECC 反而略快）。
但**做性能记录前必须先登记显存口径**，否则跨记录无法比较。

---

### 2.2 32 GB 内存环境下，「加大内存」不是解法

**根因**：目标用户大量是「8 GB 显存 + 32 GB 内存」的配置，**很多机器只有两条内存槽**，想加也加不了多少。内存降价空间也不大。

**修法**：不要提「加内存」这类方案。在 32 GB 下，**模型档位选择才是能不能跑的门槛**，
而**页面文件是唯一可扩展的「内存」**——它是硬性交付项，必须写进配置。

---

### 2.3 Arc Pro B50 标称 16 GB，实测可用 15.51 GiB

**现象**：拿「16 GB」直接算模型能不能装下，会算错。

**实测（2026-10-15，torch 2.12.0+xpu，驱动 32.0.101.8976）**：

```
xpu:1  Intel(R) Arc(TM) Pro B50 Graphics   15.51 GiB
```

**口径**：B50 与 B70 同比例——B70 标称 32 GB 实测 31.16 GiB（关 ECC），
B50 标称 16 GB 实测 15.51 GiB。**可用容量约为标称的 97% —— ECC 关闭态已确证**（2026-10-16）。
（对照：B70 开 ECC 时可见容量掉 12.5%；若 B50 开着 ECC，读数应落在约 13.3 GiB。）

**修法 / 纪律**：
- 16 GB 档的模型选型一律按 **15.51 GiB** 计算，不按 16。
- **装机后第一件事就是登记显存实数**，别拿标称值做后续推算。
- ECC 状态**不用开 IGS 截图**，一条命令取：`python bench/harness/gpu_sysman.py`（读 Level Zero Sysman）。
  注意 `zes_device_ecc_state_t` 两代枚举编号相反，**定论看物理容量不看枚举值**（见 2.3）。

**直接推论**：Qwen3.6-35B-A3B Q4_0 = **19.4 GiB > 15.51 GiB**
→ B50 上**必须走专家卸载**（`-ncmoe`），这就是 16 GB 档专项存在的理由。

---

### 2.4 `llama-bench` 与 `llama-server` 的数字不可混比

**现象**：同一张 B70、同一个模型，一边报 75.92 tok/s，一边报 39.82 tok/s，差近一倍。

**根因**：两套计时口径根本不同——
- `llama-bench`：批量预填充、有 warmup、`-r` 多次取平均、不含采样开销；
- `llama-server /completion`：单次真实请求，prompt 长度取决于用户输入，含采样与流式开销。

预填充侧差距更大（1341 vs 118 tok/s），因为 bench 用 `-p 512` 一次性 batch，
而 server 侧那次 prompt 只有 48 token。

**修法**：
1. **基准表必须带口径标签**（`tool` 字段：`llama-bench` / `llama-server` / `llama-cli`）；
2. 对外只引用 `llama-bench` 口径，server 口径单独列；
3. 引用别人的数字前先问一句「哪个工具测的」。

---

### 2.5 `vram_shared_mb` **不等于**溢出量（`-ncmoe > 0` 时）

**现象**：B50 16G（可用 15.51 GiB）跑 Q4_0 + `-ncmoe 8` + `-c 16384`，
`xpu_vram.py` 报「共享 3848 MB，**显存溢出到主机内存**」——
按仓库原来的读法，这意味着"已经溢出 3.8 GB 了"。**但同一配置的速度是满速的。**

**根因**：`-ncmoe 8` 会把前 8 层的专家权重**刻意**搬进 `SYCL_Host`。
这部分是**设计如此**，不是被挤出去的，但它**同样计入 `vram_shared_mb`**。
日志里写得明明白白：

```
-ncmoe 0：SYCL0 model buffer size = 18731.34 MiB   SYCL_Host model buffer size =   272.81 MiB
-ncmoe 8：SYCL0 model buffer size = 15195.34 MiB   SYCL_Host model buffer size =  3808.81 MiB
```

`-ncmoe 8` 的 3848 MB 共享 ≈ 3808.81 MiB 的 `SYCL_Host` buffer + 39 MB 真溢出。
**直接把 shared 当溢出读，会把"完全不溢出"误判成"溢出 3.8 GB"。**

**修法（口径）**：

> **报溢出必须写出三样：`vram_shared_mb` 原值、`SYCL_Host model buffer size` 减数、以及两者之差。**
> 只有 `-ncmoe 0`（`SYCL_Host` 只剩 ~273 MiB）时，shared 才近似等于溢出。

**扣完之后的真溢出**（2026-10-16 实测，Q4_0 + `-ncmoe 8`）：

| `-c` | shared | 减 SYCL_Host 3808.81 | decode |
| ---: | ---: | ---: | ---: |
| 16384 | 3,848 MB | **~39 MB** | 37.5（满速） |
| 32768 | 3,864 MB | **~55 MB** | 37.57（满速） |
| 65536 | 4,206 MB | **~397 MB** | 26.62（**−29%**） |
| 262144 | 7,160 MB | **~3,351 MB** | 10.35（**−72%**） |

**算不平的部分登记为 `[待解]`**：扣完之后与「计算出的超出卡容量部分」仍差 0.8~1.4 GB
（本机 15881.88 MB 可用 vs `-ncmoe 0` 时 `SYCL0 model buffer` 18731.34 MiB）。
差在哪未查清，**不解释**；但"扣减后剩余量与掉速同步增长"这件事本身已经够用。

**`-v` 的副作用（同轮发现）**：`llama-server -v` 会为每个 token 写一行日志。
同配置带 `-v` 35.55 tok/s / 不带 37.45~37.55 tok/s。
**速度读数一律不要带 `-v`**，需要机制证据时另开一轮。

---

## 三、进程与后台任务

### 3.1 长任务必须交给同一条后台命令

**现象**：单独 detach 启动服务（`DETACHED_PROCESS`），外层命令一返回，进程就被清掉。
日志停在某一行后无声死亡。

**根因**：父进程结束时子进程被连带回收。

**修法**：用「**启动 + 跑 + 收尾**」一条龙脚本，别拆成两条命令。

```bash
python run_suite.py --tag b70-6step --shots 4   # 内部完成 起服务/等就绪/跑片/收尾
```

---

### 3.2 前台命令超过约 120 秒会被 SIGTERM

**现象**：长测试跑到一半被强杀，没有结果。

**修法**：**所有长测试一律后台运行**（后台任务有 task_id、有输出捕获、有完成通知）。
别用 `nohup` / 尾随 `&` 自己脱离，那样进程游离在任务协议之外。

---

### 3.3 外层 Python 不加 `-u`，后台看不到任何进度

**现象**：后台跑的脚本像卡死，日志一片空白。

**根因**：stdout 被缓冲。

**修法**：外层也要 `-u`。

```bash
python -u run_suite.py ...
```

---

### 3.4 部署用的「看门狗」会在 15 秒内把你刚清空的 GPU 重新占满

**现象**：`Stop-Process` 杀掉 `llama-server`，进程确实消失了，内存也回来了，
但十几秒后 `Get-Process llama-server` 又有一个**新 PID**，而且正在加载模型。
你以为在跑一个"独占 GPU"的 benchmark，实际全程有一个 20 GB 的服务在抢显存和内存。

**根因**：交付部署里装了一个保活脚本（本机是
`<部署目录>\watchdog.bat`，由 `cmd.exe` / `watchdog_silent.vbs` 拉起）。
它的循环逻辑是：

```
每 15 秒：探测 127.0.0.1:8080
  端口在服务 → 什么都不做，继续等
  端口不在服务 → 立刻启动 llama-server，再等 45 秒
```

它**只认端口，不认你是谁**。所以顺手的 `Stop-Process` 在它眼里等于"服务挂了"，
必然被拉回来。本机实测：杀掉 PID 24048，新进程 PID 24704 在 15 秒内出现。

**修法**：不要硬杀 `llama-server`，要走部署自带的停机路径——
本机是 `<部署目录>\stop_model.ps1`（等价于双击「停止本地模型.bat」）。
它一次处理三样，缺一不可：

| 目标 | 为什么不能漏 |
|---|---|
| `llama-server.exe` | 它占着 ~20 GB 显存与内存 |
| 跑 watchdog 的 `cmd.exe` | 漏了它，server 15 秒后复活 |
| `wscript.exe`（`watchdog_silent.vbs`） | 隐藏的自启宿主，重启机器后还会再来 |

并且它会写一个 **`model_off.flag`**，把这次停机标记为"用户有意为之"，
让每 2 小时的健康检查自动化不要去修。**该 flag 有 6 小时 TTL** ——
超过 6 小时会被判定为"忘了切回来"（曾经因此把一个真实故障掩盖了 13.7 小时），
届时健康检查会重新拉起服务。所以长时间跑 benchmark 要留意这个时间窗。

**给 benchmark 的纪律**：
- 采集前先确认**没有** `llama-server`、**没有**带 `watchdog` 的 `cmd.exe`、
  **没有** `wscript` 宿主，三样都清干净再动手；
- 跑完想恢复服务，用部署自带的切换脚本（本机 `switch_to_qwen.ps1` /
  「切到千问.bat」），它会清掉 `model_off.flag`；
- 这一条和 1.7 是一对：**1.7 是"清场了但没等干净"，3.4 是"根本没清干净"。**
  两者的表现都是"什么都没改却突然慢很多"，排查顺序都应该是**先查宿主进程和内存，再怀疑硬件。**

> 严谨起见说明证据边界：本次实测确证的是「watchdog 会在 15 秒内重启被杀的 server」。
> 历史上几轮异常读数里**确实出现过来路不明的 `llama-server` 占卡**，
> 但是否由这个 watchdog 引起**没有留下进程树证据**，不作结论。

---

## 四、日志与计时

### 4.1 进度条会污染 `s/it` 采样

**现象**：解析到的 `s/it` 数字明显不对。

**根因**：日志里同时有**采样**和 **VAE** 两条进度条，格式一样。

**修法**：只认总量等于目标步数的那条。

```
正则：(\d+)/(\d+) \[.*\] (\d+\.\d+) s/it
过滤：分割后的总数 == 目标步数
```

---

### 4.2 失败也会返回一个「耗时」

**现象**：跑分很好看，但产物没落盘。

**根因**：出片失败 / 空返回同样会返回时间戳。

**修法**：**每次采集必须核对异常次数 + 确认产物真的存在**。
不核对就是拿失败当成绩。

---

### 4.3 服务端计时与客户端计时要对得上

**现象**：报告里的 `Prompt executed in X seconds` 和客户端秒表差很多。

**根因**：两套计时来源。

**修法**：两侧都采，**对得上才算真出片**。

#### 4.3b ⚠️ `Prompt executed in …` 有两种格式，**超过 10 分钟就换写法**

**现象**：取证脚本对 1920×1088、10 s / 15 s 视频这几条报「无匹配日志」，
而日志文件明明在目录里、`Prompt executed` 那行也在。

**根因**：ComfyUI 对**超过 10 分钟**的任务改印 `HH:MM:SS`，不是秒数：

```
Prompt executed in 301.75 seconds     ← 5 分钟，秒数
Prompt executed in 00:11:59           ← 12 分钟，时分秒
```

只写 `([\d.]+) seconds` 的正则会把后者**整行跳过**，于是所有 ≥10 分钟的跑测取证全部落空，
而且失败形态是「无匹配日志」——**看起来像日志丢了，实际是解析器吃不下**。

**修法**：正则同时吃两种格式，转成秒再比：

```python
RE_EXEC = re.compile(r"Prompt executed in (?:(\d+):(\d+):(\d+)|([\d.]+) seconds)")
```

**判据**：日志里 grep 到 `Prompt executed in 00` 就是踩上了。

---

### 4.4 `vram_total` 单位是字节

**现象**：显存数字大得离谱。

**根因**：ComfyUI `/system_stats` 返回的 `vram_total` 单位是**字节**，不是 MB。

**修法**：自己除。别直接当 MB 打印。

---

### 4.5 `llama-server` 默认日志没有分配信息；加 `-v` 后要**翻到第二遍**才有真数字

**现象（第一层）**：想查「为什么慢」，去翻 `llama-server` 的日志，
结果整份日志只有 **38 行**，`offloaded N/N layers`、`KV buffer size`、
`compute buffer size` 一行都没有 —— **推理相关的证据一条也拿不到**。

**根因**：`llama-server` 默认 verbosity 只打到 3
（日志里自称 `verbosity = 3 (adjust with the '-lv N' CLI arg)`），
后端的张量分配细节不外露。

**修法**：显式加 `-v`。加上以后才有：

```
load_tensors: offloaded 41/41 layers to GPU
llama_context: flash_attn            = enabled
llama_kv_cache: layer   0/1/2: filtered             ← 线性注意力层，无 KV
llama_kv_cache: layer   3/7/11/.../39: dev = SYCL0  ← 40 层里只有 10 层带 KV
llama_memory_recurrent: layer 1/2/4/5/6/...: dev = SYCL0
llama_memory_recurrent: layer 3/7/11/.../39: skipped
srv llama_server: n_parallel is set to auto, using n_parallel = 4 and kv_unified = true
```

**现象（第二层）**：加了 `-v` 之后，`buffer size` 行**会**出现，
但**同一个日志里会打印两遍**，第一遍全是 `0.00 MiB`：

```
load_tensors:        SYCL0 model buffer size =     0.00 MiB     ← 第一遍（试算），假的
load_tensors:    SYCL_Host model buffer size =     0.00 MiB
llama_kv_cache:      SYCL0 KV buffer size =     0.00 MiB        ← -c 262144 也是 0
...
load_tensors:   CPU_Mapped model buffer size =   333.44 MiB     ← 第二遍（真加载），真值
load_tensors:        SYCL0 model buffer size = 10644.99 MiB
llama_kv_cache:      SYCL0 KV buffer size =  2720.00 MiB        ← -c 262144 = 2720 MiB
```

**真正的根因**：`--fit`（自动内存适配）默认**开着**。fit 会先做一次
**试算/dry-run 加载**，此时权重与 KV 还没真正分配，所以 `model` / `KV` 这两类
**依赖实际分配体积**的 buffer 报 `0.00 MiB`；而 `output` / `RS` / `compute`
这几类**由配置算出**的 buffer 在第一遍就是真值（3.79 / 251.25 / 824.29 MiB）。
试算之后才是**真加载**，第二遍把两类都打成真值。

**判据（三条，实测验证）**：

1. **同一个日志里出现两遍 `llm_load_tensors`** —— 数一下
   `load_tensors: offloaded N/N layers to GPU` 出现了几次。**2 次 = fit 开**，
   第二处才是真值。
2. 日志里会有 `common_fit_params: successfully fit params to free device memory`
   / `fitting params to free memory took X seconds`。
3. **`-v` 日志里认缓冲数字，认「后一遍」的**。拿 10-15 那批（fit 开）：
   `SYCL0 model buffer size = 10644.99 MiB`（IQ2_M）+ `KV 2720.00 MiB`（`-c 262144`）
   —— 与 `xpu_vram.py` 的读数对得上。

**对照（`--fit off`）**：2026-10-16 全部配置显式带 `--fit off`，
日志里 `llm_load_tensors` **只出现 1 次**、没有 `common_fit_params` 行，
直接打印真值 `SYCL0 model buffer size = 15195.34 MiB` /
`SYCL_Host = 3808.81 MiB` / `KV = 170.00 MiB`（`-c 16384`）。
**没有第一遍的 0.00**，因为 `--fit off` 跳过了试算。

**修法**：

- **`--fit off` 时**：日志里的 `buffer size` 直接可用，是唯一一遍、是真值。
- **fit 开（默认）时**：往下翻到**第二处** `llm_load_tensors`，
  认后一遍的数字；第一遍的 `0.00 MiB` 是试算，不是「没实现」。
- 层数、`flash_attn`、`layer N: dev/filtered` 这几类**两遍都可信**。
- 不放心就用 `torch.xpu.get_device_properties(0).total_memory` 或 `xpu_vram.py`
  交叉验证（本仓库的口径就是「日志数字 + 独立读数对得上才算数」）。
- **`--fit` 默认是开**（直接证据：不加即触发试算遍）。
  `--help` 里读不到默认值，别靠 `--help` 判断。

---

### 4.6 `failed to fit params ... abort` 不等于进程退出

**现象**：日志里看到

```
W common_fit_params: failed to fit params to free device memory:
  n_gpu_layers already set by user to 999, abort
```

容易读成「启动失败」，然后去改参数。

**真相**：这句 `abort` 的宾语是**自动适配**（auto-fit），不是进程。
紧接着的日志是 `model loaded` + `listening on http://127.0.0.1:8080`，**服务是起来的**。

**含义**：**用户显式指定了 `-ngl 999`，llama.cpp 就不再做自动分层适配**。
权重装不进显存时它不会帮你改，而是照你说的全放上去，靠驱动侧溢出
（WDDM 把显存页换到主机内存）来"跑通"—— 这正是
[`vram-16gb.md` B 节](vram-16gb.md) 里 `-ncmoe 0` 崩到 4.14 tok/s 的成因。

> **与 4.5 的关系**：`abort` 这句本身就说明 **`--fit` 默认是开的** ——
> 不开就不会有「自动适配」可 abort。`--fit off` 时连这句都不会出现
> （2026-10-16 实测：10-16 那批日志里 `common_fit_params` 一行都没有）。

**判据**：看到 `abort` 先往下读几行，**只认 `model loaded` / `listening`**。
本项目部署目录（`<部署目录>\watchdog.bat`）用的就是
裸 `-ngl 999`，所以它的 `server.log` 里这句反复出现，而服务一直是正常的。

---

### 4.7 `--api-key` 只配了 server 一边 → 速度全空，但**其它一切正常**

**现象（2026-10-16，白跑一轮）**：4 组配置依次起 server、加载成功、显存读数合理、
日志无错。**结果 `decode` 字段全是 `None`。**
拉开记录才发现每个 probe 都是 `HTTP Error 401: Unauthorized`。

**根因**：`--api-key local` 进了 server 的启动参数，但**没同步给探针脚本**。
server 要求鉴权、client 没带凭据。**加载和显存采样完全不经过 HTTP，所以全部正常**——
这让失败看起来像成功。

**llama-server 到底认什么**（逐种试过，别猜）：

| 客户端做法 | 结果 |
| --- | --- |
| `Authorization: Bearer local` | ✅ 200 |
| `X-Api-Key: local` | ✅ 200 |
| `Authorization: bearer local`（scheme 小写） | ❌ 401 |
| body 里放 `{"api_key": "local"}` | ❌ 401 |
| 不带任何凭据 | ❌ 401 |

**修法**：
1. 扫配置时 `--api-key` **同时给 server 和 client 两边**；
2. **探针失败要让它显眼**：`decode: None` 不是"还没测"，是"这轮数据作废"，不能当 0 或忽略。

---

### 4.8 推理模型会把 token 预算全花在思考上 → `content` 是**空字符串**

**现象**：多模态探针送图提问，返回 `completion_tokens: 96`、速度正常、
`finish_reason` 正常，**但 `content` 是 `""`**。
看起来完全像「多模态跑不起来」——服务是好的，图像明明也编码进去了。

**根因**：`max_tokens: 96` 全被**思考阶段**吃掉，还没轮到正文就撞上限。
（本轮模型 Qwen3.6-35B-A3B 带思考；`message` 里只有 `content` 和 `role`，
所以思考内容也没落到 `reasoning_content` 里，看上去就是"什么都没答"。）

**修法**：
1. `max_tokens` 给够（实测 512 足够；关掉思考后**只用 9 个 token** 就答对了）；
2. 或传 `chat_template_kwargs: {"enable_thinking": false}`；
3. **报速度时核对 `predicted_n` 与回答是否为空**——"有 tok/s"不代表"答出来了"。

---

### 4.9 同配置跨会话波动约 ±5%，别引用小数位

**现象**：同一卡、同模型、同参数（Q4_0 + `-ncmoe 8` + `-c 16384` + 纯文本），
三个会话分别给出 **35.55 / 37.45 / 37.55 tok/s**。会话内极差只有 0.7~3.5%。

**含义**：

- **对外报「约 37 tok/s」，不要报小数点后一位**——精度是假象；
- **倍数只能在会话内比**。跨会话算出来的"差 5%"可能是噪声，也可能是真的，
  分不清。要下结论就把两组配置放进同一轮扫描；
- 采样次数只能压缩**会话内**的方差，压不掉会话间的那 5%。

---

## 五、脚本小坑

### 5.1 Python 百分号格式化里写 `-51.2%` 会 `ValueError`

**修法**：要写成 `%%`。

---

### 5.2 Windows 控制台输出中文

**修法**：

```bash
PYTHONIOENCODING=utf-8 python -u script.py
```

---

### 5.3 PowerShell 工具在部分环境无 stdout 回显

**修法**：`Out-File` 写文件再读，别指望直接看到输出。

---

### 5.4 Git Bash 的 coreutils 可能残缺

**现象**：`dirname` / `head` / `ls` 在 Git Bash 里报 command not found。

**修法**：扫文件、跑命令直接用 Python 写脚本，别依赖 shell 工具。

### 5.5 用文件名过滤记录会**静默漏掉一整批**

**现象**：审计脚本报「功耗汇总 6/102」，而实际应该有 13 条。
取证覆盖率也长期少算 —— 但没有任何报错。

**根因**：过滤条件写成了文件名包含某个词：

```python
comfy = [f for f in files if "comfyui" in os.path.basename(f)]   # ❌
```

视频域的记录文件名是 `<日期>_h3_<WxH>_<标记>.json`，**不含 "comfyui"** ——
27 条记录从来没被审计脚本遍历到，`timing_breakdown` 缺了也看不见。

**修法**：**按内容判，不按文件名判**：

```python
if json.load(open(f, encoding="utf-8")).get("schema") == "comfyui-xpu-bench/1":
```

**判据**：「某个脚本的统计数比预期小」时，先数一遍 `glob` 的命中数，
再数一遍「按内容筛」的命中数，两者不等就是踩上了。
同一类错误还在别处出现过两回（取证脚本、迁移器），**记住「文件名只是线索」**。

### 5.6 迁移器「dry-run 过」≠「迁过了」；源文件名以下划线开头会被 glob 跳过

**现象**：三批明明跑完的数据（B70 五档分辨率、B70 的 TDR 验证三桶、B50 的 864×480）
在仓库里一条都没有，但印象里「迁过了」。

**两个独立成因，都会静默通过**：

1. **只在 dry-run 里看过，没真跑**。dry-run 打印的逐条对照表长得和真跑一样，
   只是**不写文件**。几天后回看终端历史，会误判成已入库。
2. **源文件名以 `_` 开头**（`_h3_864x480_ok_cold.jsonl`，人为标记「这档另放」），
   而迁移器的 glob 是 `*.jsonl` —— 匹配不上，**不报错，直接少处理一个文件**。

**修法/纪律**：

- 迁移器必须打印 **「源 N 条 → 落盘 M 条」**，两个数不相等就要停下查；
- 有 dry-run 的脚本，**dry-run 完必须立刻真跑一次**，别把它当终点；
- 迁移后做一次**可追溯核对**：把源 jsonl 每一行的耗时（如 `server_sec`）
  与仓库 `samples[].server_sec` 做**集合比对**，差集里的每一条都要能解释
  （是冒烟测试？是作废批次？还是真漏了？）。

```python
# 判据：源里有、库里没有的耗时，逐条列出来
src = {round(float(r["server_sec"]), 2) for r in map(json.loads, open(src_jsonl))}
dst = {round(float(s["server_sec"]), 2) for f in glob("bench/data/*.json")
       for s in json.load(open(f))["samples"] if s.get("ok")}
print(sorted(src - dst))
```

### 5.7 同一个字段写成两种形态，比字段缺失更难查

**现象**：统计脚本抛 `AttributeError: 'str' object has no attribute 'get'`。

**根因**：`log_evidence` 这个字段，一个脚本写**裸字符串**（一段取证说明），
另外三个脚本写 **`{status, note}` 对象**。按 `obj.get("status")` 读就炸。

它比「字段缺失」更难查，因为数据「**看着有**」：非空校验全过、
覆盖率报 100%，只有真正去读子键的时候才炸。

**修法**：同一字段在全库只能有一种形态。统一为 `{status, note}`，
`status` 用封闭取值（`annotated` / `missing` / `pending`），
原文说明挪进 `note`。转换时**只搬形态、不动内容**，并逐条核对
「除该字段外零差异」。

**判据**：写任何跨记录统计脚本之前，先跑一遍**形态普查**：

```python
c = collections.Counter(type(json.load(open(f)).get("log_evidence")).__name__
                        for f in glob("bench/data/*.json"))
```

`Counter` 里出现两种以上类型名，就是有坑。

### 5.8 「待回填」状态必须能自己变成「补不了」

**现象**：一条记录的状态永远停在 `pending`（「待跑取证脚本」），
而它的日志其实早被后续批次覆盖了 —— 读者会一直以为「补跑一次就有」。

**根因**：取证脚本找不到日志时**直接 return、不落盘**，于是迁移器写下的
初始状态永远没人改。

**修法**：取证脚本在「**确实有跑成功的轮次、但在给定日志目录里找不到日志**」时，
把状态写成 `missing` 并在说明里讲清「时间分解不可用、不假装取证做过」；
一轮都没跑成功的记录不动（那种记录取证为空本来就对）。

下游审计相应地**不再把 `missing` 报成「该回填却没回填」** ——
它补不了，重复报会让人以为消掉告警只是再跑一次的事。

---

## 六、后端专项

### 6.1 不同后端的数字不能混比

SYCL / Vulkan / HIP / IPEX 的解码速度差异很大，**同一套参数换后端算新记录**，
不能覆盖旧记录——两者要能并排看。

### 6.2 Intel 的到达速度

上游（llama.cpp / vLLM / ComfyUI / 各类新推理引擎）对 Intel 的官方支持普遍滞后。
遇到「新模型/新引擎没提 Intel」，先确认是不是有社区 fork，或者自己构建。
**这是常态，不是异常。**

---

## 待解问题

| # | 问题 | 状态 |
|---|---|---|
| 1 | llama.cpp Vulkan 后端在 Arc Pro B70 / B50 上的实际表现（vs SYCL） | `[未解]` 待实测 |
| 2 | 16 GB 档 MoE 专家卸载的最优切分点（`-ncmoe`） | **`-ncmoe 8`**（Q4_0 19.41 GiB，两槽位一致）。**其他量化档的拐点见 `docs/vram-16gb.md` B 节**（IQ2_M / Q3_K_S 已实测，拐点会随权重体积移动） |
| 3 | 32 GB 内存 + B50 16G 下，页面文件的推荐大小 | `[未解]` 待实测 |
| 7 | B50 第二槽 r=3 与同配置 r=1 差 30% | **测量污染**，真因是页面文件换入（见 1.7）。结论：**槽位差 −2.9% 小于副槽自身复现极差 13.9%** → x4 与 x8 **统计上无法区分**（见 `slot-comparison.md` §3.3） |
| 4 | Strata 在 Arc 上的 Windows 路径（官方无，WSL2 也认不出卡） | `[未解]` |
| 5 | `sycl-ls` 干净环境仍只列 `opencl:*`、无 Level Zero，而 `torch.xpu` 能看到 2 卡 → 本机 SYCL 工具链疑缺 PI Level Zero plugin；**llama.cpp SYCL 可能一直在跑 OpenCL 后端而非 Level Zero**，若是则 B70 的 42.45 tok/s 存在未挖掘提速空间 | `[未解]` 待实测 |
| 6 | B50 的 ECC 当前状态 | **ECC 关闭**。Level Zero Sysman 取证（`gpu_sysman.py`）得 `EccAvailable=true` / `EccConfigurable=true` / `currentState=2`，`pendingAction=NONE`；枚举值两代编号相反故不用它定论，**定论看物理容量**（可见 15881.88 MB / 标称 16 GB = 关闭态一侧；开启应在 ~13.3 GiB）。与「驱动默认关闭、需人工开启」口径一致 |
| 8 | 主槽与副槽的 **host↔device 实际带宽**没有直接测量过（Windows 的 PCIe DEVPKEY 在 Arc 上不可用，见 1.4b）。目前「副槽 = x4」只有主板规格作依据，缺一条自量数据 | `[未解]` 待实测。**Level Zero `zesDevicePciGetState` 在本机同样无值**（返回全 0 / `status=UNKNOWN`），只有 `zesDevicePciGetProperties` 的能力值（Gen5 x8）可用 → 协商宽度确实读不到，只能实测带宽 |
| 9 | `-ncmoe 8` 在副槽出现过一次 OOM 崩溃（未复现）。是否在内存吃紧的机器上副槽更容易分配失败 | `[未解]` 待复测 |
| 10 | 部署自带的看门狗（`watchdog.bat`）会在 benchmark 期间自动拉起 `llama-server` 抢 GPU（机制见 3.4，已确证 15 秒内复活）。历史若干轮异常读数是否受其影响，**因未留进程树证据，不作追溯结论** | `[机制已定位]` 停机须走 `stop_model.ps1`；该 flag 6 小时过期 |
| 11 | 16 GB 档的上下文天花板（`-c` 能开多大、深上下文解码掉多少） | 见 [`vram-16gb.md` D 节](vram-16gb.md)：`-c 262144` 可加载可跑，且 **`-c` 从 4096 到 262144 只掉 1.6%**（上下文**分配**不花钱）。真正的代价在**实际深度**上：解码随深度近似线性下降。**边界条件**：这个「不花钱」只对**权重装得下**的档位成立；Q4_0（靠 `-ncmoe` 卸载）上 `-c` 从 16384 开到 262144 会让 decode 掉 **72%**（见 `vram-16gb.md` D.5） |
| 12 | `-c 16384` 的「掉 72% 断崖」 | **不是 `-c` 的效应**：干净环境不复现，是常驻进程污染（见 1.8）；同配置在 `llama-cli` 路径上从来没有断崖 |
| 13 | q8_0 的 KV 实测 **1.35 B/值**，比教科书的 1.0625 B/值高 **24%**（f16 实测 2.08 B/值，与理论吻合） | `[未解]` 机制未查清。**预算显存用实测值 13.5 KiB/token，别用理论值** |
| 14 | `-c 262144` 的实测总占用比「权重 + KV 公式」多出约 **1 GiB**，且其中一块**随上下文增长**（大上下文的斜率高于小上下文的 13.5 KiB/token） | `[未解]` 疑似计算缓冲/循环状态，未定位 |
| 15 | Windows 允许**显存超额订阅**：超了不 OOM，驱动换页、速度下降（溢出 2,332 MB → 掉 58%）。`docs/test-rig.md` 里的「可用量 15.51 GiB」因此是**软上限**不是硬上限 | `[已确证]` 见 [`vram-16gb.md` C/D 节](vram-16gb.md)。**判据：prefill 与 decode 同时掉 = 溢出** |
| 16 | `docs/test-rig.md` 记录的装机状态（哪张卡在哪个槽） | `[不作结论依据]` 「哪张卡放在哪个槽」不作为本项目的结论依据。槽位结论只来自「同一张 B50 分别插主槽 / 插副槽」的对照 |
| 17 | `vram_shared_mb` 不能直接当溢出量（`-ncmoe > 0` 时含刻意放到 `SYCL_Host` 的专家权重） | `[口径已定 / 差值未解]` 扣减规则见 2.5：**报溢出必须写出 shared 原值 + `SYCL_Host model buffer size` + 两者之差**。但扣完仍与「超出卡容量」对不上 0.8~1.4 GB，`[未解]`，不解释 |
| 18 | `-ncmoe 0` 在两套口径下差 **2.6×**：`llama-bench`（`docs/vram-16gb.md` B 节，`load_mode=auto`）= **4.14**；`llama-server`（带 `-lm dio`）= **10.71** | `[未解]` 疑似与 `-lm dio` 有关（整层 offload 下 mmap 页被换出会持续读盘），**未验证**。引用「`-ncmoe 0` 有多惨」时两个数都要写 |
| 19 | `-c 32768`（37.57）比 `-c 16384`（35.55）快 5.7%，大于各自会话内极差（1.9% / 3.5%） | `[按会话波动处理]` 重复实验里 16384 也能跑到 37.45 / 37.55 → 更像会话间波动（4.9），**未找到 `-c` 层面的机制** |
| 20 | 挂上 `--mmproj` 后，**纯文本请求**的 prefill 也从 42.93 掉到 27.94（**−35%**），显存只多了 +204 MB | `[未解]` 推测是计算图里多了视觉塔节点，机制未查清。"挂了就掉"是实测的 |
| 21 | 同一套交付配置在两种机器状态下差 2.3×（副槽 x4 + 空闲内存 5.2 GB → 2.47 tok/s；主槽 x8 + 空闲 20.9 GB → 5.76 tok/s） | `[未解]` 槽位与空闲内存**两个变量同时变**，无法归因。引用倍数时一律取主槽/内存充足那一档（见 `server-config.md` §1） |
| 22 | 本机构建上 `--fit` 的**默认值** | **默认 `--fit on`**。证据：不加 `--fit` 时日志里 `llm_load_tensors` **跑两遍**并出现 `common_fit_params: successfully fit params to free device memory`（见 4.5）；显式 `--fit off` 后只跑一遍、无该行。**`--help` 里读不到默认值，别靠它判断。** 4.6 的 `abort` 与 `watchdog.bat` 注释（fit 把 `-c` 夹回 16384）是否同版本仍 `[未解]` |
