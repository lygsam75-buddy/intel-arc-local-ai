# 在 Ubuntu 上复现 B50 的 Strata：准备清单

> 目标：在本机（Arc Pro B50 16G + Ryzen 5 9600X + 32 GB RAM）复现社区报告的
> **Coder IQ1_M ~23 tok/s / IQ2_XS ~25-27 tok/s**。
> 结论先给：**有一个硬卡点（磁盘）必须先解决，另一个（内存）会让复现结果天生低于社区数字。**

---

## 0. 先看结论：三个前提，一红一黄一绿

| # | 前提 | 现状 | 判定 |
|---|---|---|---|
| 1 | **磁盘 ≥ 150 GB 给 Linux 侧，且必须在机内 NVMe 上**（官方最低 80 GB） | Ubuntu 分区 **53.57 GB（USB 外置盘更不可用，见 §2.1）** | 🔴 **硬卡点，必须扩** |
| 2 | **内存 32 GB 是官方下限，官方同时说 64 GB 才是实际推荐值** | 31.1 GB | 🟡 **会跑通，但不是干净复现** |
| 3 | CPU 有 AVX-512（专家由 CPU 算） | Ryzen 5 9600X 有 | 🟢 达标 |
| 4 | **内核 ≥ 6.14**（B50 完整支持线） | 待确认 | ⚪ **先查 `uname -r`，见 §4.1** |
| 5 | **B50 插在主槽**（Strata 是 PCIe 敏感负载） | 现在在副槽 | 🟡 **见 §3，测前换回主槽** |

---

## 1. 🔴 磁盘：当前 Ubuntu 分区只有 53.57 GB，差 3 倍

### 为什么这么吃盘

Strata 官方口径：**「磁盘约 80 GB 起，大档位超过 150 GB」**。拆开算：

| 项 | 体积 | 说明 |
|---|---:|---|
| 模型（Strata 的 `--model` 档） | **~70 GB** | 官方安装器提示 "about 70 GB" |
| Docker 镜像 `strata-sycl-dev` | **13 GB** | `sycl/setup_intel.py` 就是跑在这个镜像里 |
| Intel oneAPI（DPC++ + oneMKL） | ~5 GB | 官方说 "About 5 GB"（走 Docker 时不需要装，但镜像里已含） |
| 构建产物 + JIT 缓存 | 3–5 GB | |
| Ubuntu 系统本体 | 15–25 GB | |
| **swap（本机 32 GB 内存的必需项）** | **64 GB+** | 工作集 35–55 GB 装不下 31 GB 内存，靠 swap 兜 |

→ **总计 ~170–180 GB**。官方最低 80 GB 只适用于 64 GB 内存、且不做 swap 的机器。
本机是 32 GB 内存，**swap 必须给足**，所以门槛落在 **150–200 GB**。

### 现状

```
disk 0（WD 500GB，NVMe）
  ├─ 分区1  System      0.29 GB
  ├─ 分区2  Reserved    0.02 GB
  ├─ 分区3  <数据盘> NTFS   411.88 GB   （已用 89.4 GB，空 322.5 GB）
  └─ 分区4  ext4       53.57 GB  ← Ubuntu 在这里（UEFI 条目存在，可启动）
```

**关键约束：ext4 是 disk 0 的最后一个分区，<数据盘> 在它前面。**
缩 <数据盘> 空出来的是「F 尾部到 ext4 头部之间」的空隙 → **ext4 不能直接向右扩**。

### 2.1 磁盘实测：不要用 USB 外置盘跑这个复现

用 `bench/harness/disk_probe.py` 量的（原始扇区只读读取，同一方法）：

| 盘 | 接口 | 顺序读 | **随机 4K 延迟** | 随机 4K IOPS |
|---|---|---:|---:|---:|
| **ORICO CN300 500G** | **USB 3.0（UASP）** | 414.6 MB/s | **215.1 µs** | 4,642 |
| WDS500G3XHC（现 Ubuntu 所在） | 机内 NVMe | 998.4 MB/s | **32.1 µs** | **30,940** |
| WD_BLACK SN750 SE 1TB | 机内 NVMe | 1703.8 MB/s | 165.6 µs ⚠️ | 6,027 |

> ⚠️ SN750 SE 的随机数字**被污染**：采集时 `llama-server` 正在运行（占 14.3 GB，
> 系统空闲内存仅 1 GB），模型文件就在该盘上持续被读。其真实值应接近左列那块蓝盘。

**为什么随机延迟是这题的胜负手：**

官方文档写明，内存不够的机器上「**专家会从盘上读**，走系统文件缓存」。
本机 **32 GB 内存 < 模型体积（约 70 GB）→ 必然走这条路**。
即每 token 都可能要付一次磁盘随机读的延迟：

- 机内 NVMe：**32.1 µs**
- USB 外置：**215.1 µs** → **差 6.7 倍**

这是**持续性**开销，不是一次性装载开销。**USB 盘的根本问题不是慢，是让结论失真。**

**顺序带宽反而是次要的**：415 MB/s 装 70 GB 模型约 169 秒（一次性），可以接受。
所以 USB 盘可以当**模型仓库/备份**，不能当**运行盘**。

**另外两个 USB 特有风险：**
- 把 Ubuntu 装在它上面 → **系统 I/O、swap、模型读取三份流量挤同一条 USB 3.0 链路**
  （415 MB/s 已是天花板：UASP 协议、直连 USB 3.0 根集线器，换口不会更快）；
- 长时间满负载下 USB 存储掉线是已知风险，中途掉线会让整轮测试作废。

### 2.2 方案：不用移动任何分区

三条路，推荐 **B+**：

| 方案 | 做法 | 代价 | 风险 |
|---|---|---|---|
| A. 扩现有 Ubuntu | 缩 <数据盘> → 用 GParted 把 ext4 **左移**贴紧 <数据盘> → 向右扩到 ~330 GB | 移动 53.57 GB 分区，20–40 分钟 | 中。移动分区是常规操作，但动的是唯一的 Linux 分区 |
| **B+（推荐）** | 缩 <数据盘> 到 ~120 GB（腾出 ~292 GB）→ **删掉旧 ext4** → 在「腾出的 292 GB + 旧的 53.57 GB」上新建一个 **~345 GB ext4** → 装 Ubuntu 24.04.3 | 重装 + 重配环境 | **低。不需要移动任何分区**（缩 F 腾出的空隙正好紧贴 ext4 前面），旧数据不动 |
| C. USB 外置盘 | Ubuntu 装到 CN300 | 省事 | **高。随机延迟差 6.7 倍、三份 I/O 挤一条 USB、掉线风险** |

**B+ 的全部理由**（对照实测数字）：

1. Ubuntu、模型、swap **全落在机内 NVMe（随机 32.1 µs）**，而不是 USB（215.1 µs）；
2. **不需要移动分区** —— 因为 ext4 紧跟在 F 后面，缩 F 腾出的空间位置天生正确；
3. 顺带把内核带上 6.14（B50 的完整支持线，见 §4.1）。

**执行前必须确认：旧 Ubuntu（53.57 GB）里没有要保留的东西。**
它看起来是刚装好、还没配环境的（否则不会只有 53.57 GB），但要他自己确认。
<数据盘> 里的 89.4 GB 也要先备份。

> **CN300 唯一合适的用途**：零风险地先验证一次「链路能不能通」，
> 或者当模型文件的搬运/备份盘。**但它的速度数字不能写进对客材料**——
> 盘会把结论拖偏，导致误判 B50 的真实水平。

---

## 2.3 B+ 执行步骤

### 版本选择：本机已有的 ISO 是 26.04，直接用它

本机 `<Ubuntu ISO 文件>`（6.07 GB）**校验通过**：

| | SHA256 |
|---|---|
| 本机文件 | `487f87faaf547ea30e0aba4d5b53346292571256b25333a978db1692bcee9dd2` |
| Canonical 官方 | `487f87faaf547ea30e0aba4d5b53346292571256b25333a978db1692bcee9dd2` ✅ |

**为什么用 26.04 而不是 24.04.3：**

| | Ubuntu 24.04.3 | **Ubuntu 26.04 LTS** |
|---|---|---|
| 内核 | 6.14 (HWE) | **Linux 7.0** |
| B50（要求 ≥6.14） | ✅ | ✅ |
| **B70（要求 ≥6.17）** | ❌ **不够** | ✅ |
| 支持周期 | 2029 / 2039 | **2031 / 2041** |

→ **26.04 一块盘同时满足 B50 和 B70。** 用 24.04.3 的话，以后测 B70 的 Strata 还要再装一次系统。
（ISO 库里有 `26.04.1` 的更新镜像，用哪个都行，内核同为 7.0.x。）

**唯一风险**：Strata 的社区验证路径是 **24.04 + oneAPI 2026.1.1 + NEO 26.09**。
26.04 是更新的发行版，Mesa / NEO / Level Zero 版本更新——大概率更好，但不是那个「已验证组合」。
走 Docker 路径可以规避 oneAPI 宿主版本问题（镜像自带 oneAPI）。

### 步骤

#### 阶段一：制作启动盘与 BIOS 设置

1. **把 ISO 拷到 Ventoy 盘（<U 盘>）** —— 无需制作启动盘。<U 盘> 是那块 CN300，
   已装 Ventoy（卷标 `Ventoy`，exFAT，当前 456.8 GB 空闲）。
2. **进 BIOS 关掉 Secure Boot。** ⚠️ Ventoy 在 Secure Boot 开启时无法直接启动
   （需要注册 MOK 密钥）。装 Linux 前关掉最省事。
3. **关闭 Windows 快速启动**，然后**完全关机**（不是重启）：
   ```powershell
   powercfg /h off
   ```
   > 必须完全关机。若 NTFS 处于休眠态，任何缩容操作都可能损坏文件系统。

4. **确认 <数据盘> 里没有不可丢失的东西。** <数据盘> 现有内容（已用 89.4 GB）：
   `ARC PRO系列图`、`BaiduNetdiskDownload`、`ComfyUI-Intel`、`LLM`、`MyDrivers`、`oneMKL_pkg`
   → 缩容**不会丢数据**（只腾尾部空间），但缩容过程要搬运数据，
   **重要文件仍应另备一份**后再动手。
5. **确认旧 Ubuntu（53.57 GB ext4）里没有要留的东西。** 它看起来是刚装好未配环境的。

#### 阶段二：分区 —— 全部在 Live 的 GParted 里做

> **为什么不用 Windows 的「压缩卷」**：本机 <数据盘> 有 322.5 GB 空闲，
> 但 Windows 只肯缩 **10.76 GB**（`Get-PartitionSupportedSize` 实测）。
> 已排除卷影副本（<数据盘> 用量 0 字节）与页面文件（只在 <非系统盘>）。
> 真因是**碎片**：<数据盘> 文件碎片 **15,445 个**、可用空间碎成 **3,665 段**
> （最大连续仅 184.09 GB），有文件落在 ~401 GB 处 ——
> **Windows 不移动文件，所以只能缩到最后那个文件之前。**
> GParted 的 `ntfsresize` 会搬文件，一步到位，且反正删/建分区都要在 Live 里做。

6. 从 Ventoy 启动 → 选 **Try Ubuntu**（先进 Live 桌面，不直接装）
7. 打开 **GParted**，按顺序操作（每步都要点 ✓ 应用）：

   | 步 | 操作 | 结果 |
   |---|---|---|
   | a | 缩 `<数据盘>` (ntfs) **到 200 GB** | `[<数据盘> 200][空闲 212][ext4 53.57]` |
   | b | 删除旧的 `ext4` 分区 | `[<数据盘> 200][空闲 ~265]` 连成一片 |
   | c | 在空闲区建 **ext4**（将来挂 `/`），约 **200 GB** | — |
   | d | 建 **linux-swap**，**64 GB** | 32 GB 内存装不下 35–55 GB 工作集，swap 是硬需求 |
   | e | 应用 | — |

   > **为什么 200 GB 就够**：模型 70 + Docker 镜像 13 + oneAPI 5 + 构建/缓存 5 +
   > 系统 20 + swap 64 ≈ **177 GB**。缩得越少，要搬的数据越少、耗时越短。

   > ⚠️ **跳过 a 步的代价**：a 会搬运数据，在 412 GB 的空盘上预计 10–40 分钟。
   > 中途**绝不能断电**。这也是为什么先备份。

8. 关掉 GParted，运行安装器 → 安装类型选 **「手动分区 / Something else」**
   - 把刚建的 ext4 设为 **`/`**，**不要勾选格式化**（已经是 ext4 了）
   - 把 swap 分区设为 swap
   - **ESP（EFI 系统分区）复用已有的 0.29 GB 那个**，⚠️ **不要格式化它**
   - 「安装启动引导器的设备」选 **disk 0**（那块 WD 500G）

   > **绝对不要选「清除整个磁盘」**——那会连 Windows 一起抹掉。

#### 阶段三：装完立刻验证

```bash
uname -r                                          # 期望 7.0.x
lspci -nn | grep -i 8086                          # 期望看到 [8086:e212] Arc Pro B50
ls /sys/class/drm/                                # 卡能被 setup_intel.py 找到
free -h && swapon --show                          # 确认 swap 生效
lscpu | grep -o 'avx512[a-z_]*' | sort -u         # 确认 AVX-512 在
```

> 如果 `lspci` 有卡但 `/sys/class/drm` 是空的，按 §4.1 加内核参数 `xe.force_probe=e212`。

#### 备选：不改分区的快速验证路径

若想先零风险确认「链路能不能通」，可以**先不碰分区**：
把 Ubuntu 装到 CN300（USB）上跑一次，只求「能启动、能认卡、能装 Strata、能出 token」。
**但它的速度数字一律作废**（见 §2.1：随机延迟差 6.7 倍）。

---

## 2. 🟡 内存：32 GB 是官方下限，不是推荐值

官方原文（`docs/INTEL_ARC.md` + 项目文档）：

> VRAM: the port keeps the experts on the card (`--stream-experts`).
> **A 32 GB card holds the Coder IQ1_M or IQ2_XS. Smaller cards mirror part of the experts in RAM and are slower.**

> RAM: **32 GB 是最低要求，64 GB 才是每种模型档位都跑得动的实际推荐值。**
> Strata **会往 RAM 里装 35–55 GB** 并锁住一部分给显卡。

**B50 是 16 GB 卡 → 必然走「部分专家镜像到 RAM」这条路 → RAM 是瓶颈，不是显存。**

对照最接近的社区数据（JR-Strata / Arc Pro B60 24 GB，IQ3_XXS，128K 上下文）：

| 层级 | 专家数 | 占用 |
|---|---:|---:|
| B60 显存 | 10,617 | ~17.22 GiB |
| **系统 RAM（pinned）** | 13,959 | **~22.75 GiB** |

→ 24 GB 卡都要 **22.75 GiB 内存**装专家，B50 只有 16 GB 显存，
**需要镜像到 RAM 的专家只会更多**。31.1 GB 总内存扣掉系统 3–4 GB、KV、
再加上 n-gram 表的文件缓存，余量非常紧。

**这对复现意味着什么（必须写进结论）**：社区报的 B50 16 GB ~23–27 tok/s，
大概率出自 **64 GB 内存**的机器。本机 32 GB 跑出来的数字**天然低于它**，
而且差距不是因为卡，是因为内存。**这就是为什么这次复现的价值在于「32 GB 能不能跑通」，
不在于「能不能追平 23 tok/s」——前者才是对客答案。**

---

## 3. 🟢 必须装回主槽：Strata 是 PCIe 敏感负载

**这一条和 llama.cpp 在「参数调对」时的结论正好相反，别搞混——但两者互洽。**

| 引擎 | 每 token 过 PCIe 的东西 | 槽位重要吗 |
|---|---|---|
| llama.cpp + `-ncmoe 8` | 只有 activation（几十 KB） | **不重要**（实测差 2.9%，小于副槽自身噪声 13.9%） |
| llama.cpp + `-ncmoe 4~7` | **整层/专家权重来回搬** | **重要**（副槽实测慢 41%~145%） |
| **Strata（Intel SYCL 端口）** | **专家权重**（`--stream-experts`，从 RAM/pinned 内存流到 GPU） | **非常重要** |

JR-Strata 把「H2D 带宽 ~6.8 GB/s（PCIe 4.0 x4 via OCuLink）」当作关键指标列出，
就是因为专家要从主机侧流进 GPU。

→ 规律是同一条：**只要权重持续过 PCIe，槽位就是瓶颈；只有 activation 过 PCIe，槽位就无所谓。**
llama.cpp 的 `-ncmoe 4~7`（权重搬）与 Strata（权重流）落在同一侧，
`-ncmoe ≥ 8`（不搬）落在另一侧。

→ **测 Strata 前，把 B50 插回主槽 PCIE1（x8）。** 副槽 x4 会在这个负载上吃大亏，
而且会让「23 tok/s 追不追得上」这个问题失去意义。

---

## 4. 软件准备清单

### 4.1 系统：内核版本是本项目最容易白干的一步

Intel 官方支持表（按 PCI ID 查，**同一代卡的支持状态不一样**；下表**只列本系产品**）：

| PCI ID | 型号 | 架构 | 初始支持（实验性） | **完整支持（默认启用）** |
|---|---|---|---|---|
| **E212** | **Arc Pro B50** | Xe2 Battlemage | **内核 6.11** | **Ubuntu 24.04+（内核 6.14）** |
| E211 | Arc Pro B60 | Xe2 | 不可用 | Ubuntu 24.04+（内核 6.15） |
| E223 | Arc Pro B70 | Xe2 | 不可用 | Ubuntu 25.10+（内核 6.17） |

**本机要的结论：**

1. **Ubuntu 24.04.3（HWE 内核 6.14）是本机 B50 的达标线**，`uname -r` 要看到 `6.14.x`。
2. **Ubuntu 24.04.1 的默认内核是 6.8 —— 对 B50 完全不可用，不是「慢」而是「认不出卡」。**
   如果他的 Ubuntu 是 24.04.1，第一件事是升级 HWE 内核，或直接重装 24.04.3。
3. **在 6.11–6.13 上（即 24.04.2 的 6.11）卡是「实验性可用、默认不启用」**，
   可能需要在内核命令行加 `xe.force_probe=e212` 才会被检测到。
   → 如果 `lspci` 看得到卡但 `sycl-ls` / `/sys/class/drm` 看不到，**先试这一条**。
4. 顺带记住：**B70 的完整支持要 Ubuntu 25.10（6.17）**。
   所以以后要测 B70 的 Strata，别用 24.04——这是两个不同的系统要求。

进系统后先跑这三条确认：

```bash
uname -r                                          # 期望 >= 6.14（B50 完整支持线）
lspci -nn | grep -i vga                           # 应看到 Arc Pro B50 [8086:e212]
ls /sys/class/drm/                                # setup_intel.py 靠这个找卡
```

> 若 `lspci` 有卡但后两条空 → 内核偏旧或没启用，试加内核参数：
> ```bash
> sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 xe.force_probe=e212"/' /etc/default/grub
> sudo update-grub && sudo reboot
> ```

### 4.2 GPU 驱动与运行时

```bash
sudo apt update
sudo apt install -y intel-opencl-icd libze1 libze-intel-gpu1
```

> 若 Ubuntu 自带版本太旧（`xe` + Level Zero V2 需要较新的 NEO），
> 用 Intel 的客户端 GPU 仓库：<https://dgpu-docs.intel.com/driver/client/overview.html>

**最容易踩的一步——权限组**：

```bash
sudo usermod -aG render $USER     # 不加，sycl-ls 只显示 CPU，看不到 Arc
sudo usermod -aG docker $USER
# 然后必须重新登录（注销/重登，不是只开新终端）
```

验证：`sycl-ls` 应当列出 Arc。**如果只列出 CPU 设备，就是没进 `render` 组。**

### 4.3 构建依赖

两条路，推荐先走 Docker（就是 `./setup.sh --backend sycl` 用的那条）：

```bash
sudo apt install -y docker.io git
git clone https://github.com/Niko1221/Strata
cd Strata
docker build -t strata-sycl-dev sycl/tools           # 约 6 分钟，产出 13 GB 镜像
```

原生构建（不走 Docker）才需要 oneAPI：

```bash
sudo apt install -y intel-oneapi-compiler-dpcpp-cpp intel-oneapi-mkl-devel ninja-build cmake git
```

> 官方要求 **DPC++ 2025.3 或更新**（测试用的是 2026.1）。

### 4.4 AOT 目标 —— **B50 不在官方列表里，要现场确认**

官方给的 AOT 目标（下表**只列本系产品**）：

| 目标 | 对应卡 |
|---|---|
| `bmg-g31` | Arc Pro B70 32G |
| `bmg-g21` | **Arc Pro B60** |

**B50（`e212`）没有出现在这张表里。** 进系统后必须先用：

```bash
sycl-ls
ocloc ids bmg-g21     # 看输出的 device id 是否与 B50 匹配
```

确认后再决定 `-DSTRATA_SYCL_AOT=bmg-g21` 还是干脆不开 AOT（走 JIT）。
**不开 AOT 的代价：首次启动每个 kernel 现场 JIT，官方说约 47 秒。** 只是慢，不是不能跑。

### 4.5 环境变量（`xe` 卡专用，不加会踩坑）

| 变量 | 值 | 原因 |
|---|---|---|
| `SYCL_CACHE_PERSISTENT` | **`0`** | 持久 JIT 缓存**在 Xe2 上首次编译会崩** |
| `ZES_ENABLE_SYSMAN` | `1` | 原生运行时需要 |
| `STRATA_VERIFY_DEVICE_PLAN` | `1` | 原生运行时需要 |
| `STRATA_VERIFY_NO_HOST` | **`1`** | **`xe` 卡上只要有专家不在显存里就必需**，否则输出 NaN logits。B50 必然命中这个条件 |

> `strata-sycl.sh` 会自动带上 `STRATA_VERIFY_NO_HOST=1`；用原生运行时就得自己设。
> 另：`source /opt/intel/oneapi/setvars.sh` 在开了 `set -u` 的 shell 里会因
> `OCL_ICD_FILENAMES: unbound variable` 中断（oneAPI 2026.1.1 已知），先 `set +u`。

---

## 5. 模型选择

Strata 支持的档位：`Q2_0` / `IQ2_XS` / `IQ3_XXS` / `IQ3_S` / `Coder (IQ1_M)`，
安装器默认下载 **约 70 GB**。

**本机（16 GB 显存 + 32 GB 内存）只能选最小的档。** 参考体积：

| 档位 | 必须常驻部分 | 体积 |
|---|---:|---:|
| Q2_0 / IQ2_XS | 权重分片 | 35–40 GB |
| 其中 n-gram 表（可 mmap 在 SSD 上） | — | 28.8 GB |
| IQ3_XXS 及以上 | — | 更大，本机不要考虑 |

> **注意一个反直觉点**：`Q2_0` 体积比 `IQ2_XS` 略小，但**提示吞吐高 3.4 倍**。
> 原因是它避开了依赖大查找表的量化格式，而在这个模型上解码查找表的开销会主导推理。
> **要速度选 Q2_0，要质量选 IQ2_XS。** 首次复现建议从 **Q2_0** 起——先证明链路通、速度可看，
> 再换 IQ2_XS 对比。

**下载前先确认盘够**：70 GB 模型 + 13 GB 镜像 + swap，见第 1 节。

---

## 6. 安全红线（官方明确警告，别踩）

> **Do not ask for more VRAM than the card has.** On the `xe` driver, an allocation past
> VRAM can push buffers into RAM until the machine runs out of memory and stalls.
> **Leave about 1.5 GB free.**

翻译成人话：在 `xe` 驱动上，**配置里索要的显存超过卡的实际容量时，驱动不会报错，
而是把 buffer 推去系统内存，直到整机内存耗尽、系统卡死**。

本机是 **16 GB 卡 + 32 GB 内存**，是最容易撞这条的组合。所以：

- B50 可用显存按 **15.51 GiB** 算，配置里**只敢要 ~14 GB**；
- 跑之前关掉所有吃内存的东西（**包括 Windows 侧不留后台**，双系统不会同时跑，但重启前确认）；
- 出问题先看 `dmesg`，不要反复重试。

---

## 7. 执行顺序（建议）

1. **决定磁盘方案**（推荐 §2.3 的 Live+GParted 路径：缩 <数据盘> 到 200 GB → 删旧 ext4 →
   建 ext4 200 GB + swap 64 GB → 装 26.04，**全部在一处完成，不用移动已建分区**）
   → 这一步不做完，后面全白干
2. 准备 Ubuntu 24.04.3，确认内核 ≥ 6.12、`lspci` 看到 `e212`
3. 装 GPU 驱动 + `render`/`docker` 组，**重新登录**，`sycl-ls` 看到 Arc
4. **把 B50 插回主槽 PCIE1**（第 3 节）
5. 分出 ≥64 GB swap
6. `git clone` Strata → `docker build` 出 13 GB 镜像
7. `./setup.sh --backend sycl --model Q2_0 --context 32768`
8. 跑通后记录：**能否启动 / 是否触发 SSD 回退 / decode / prefill / 峰值内存与 swap 占用**
9. 再试 IQ2_XS 做对照

---

## 8. 这次复现对客户意味着什么（先想清楚再动手）

社区那张 B50 16 GB 表**没有标注测试机的内存**。本机 32 GB 是官方下限，
社区大概率是 64 GB。所以两种结果的解读完全不同：

| 结果 | 解读 | 对客说法 |
|---|---|---|
| 32 GB 上跑通，速度明显低于 23 tok/s | **很可能**。差距来自内存，不是卡 | 「B50 能跑 125B，但 32 GB 内存是它的下限，要用最小的量化档，且会触发 SSD 回退」 |
| 32 GB 上跑不通 | 也是有价值的负结果 | 「跑 125B 这类模型，32 GB 内存不够，别对客户承诺」 |

**两种都是可交付的结论**，但**只有标清楚 `ram_gb: 32` 才有意义**。
如果先把内存加到 64 GB 再测，得到的数字对 90% 的客户无效——
这和之前记的那条纪律是同一条：**测试环境的 `ram_gb` 必须随数据一起登记。**
