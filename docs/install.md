# 开始之前：到底要装什么

**一句话**：装什么取决于你走哪条路；三条路**唯一共同的必装项，只有 Intel 显卡驱动**。

这份手册里的数字不分「装得好不好」——同一张卡，装对了就是那样，装错了会慢一个数量级甚至直接崩。
所以先把环境定下来，再看数字。

---

## 1. 三条路，挑一条

| 路 | 适合谁 | 要装 | 不用装 | 代价 |
|---|---|---|---|---|
| **A · 整合包** | 想当天就出图，不想碰命令行 | 驱动 + 解压一个包 | torch、XPU 运行库、补丁、Python——**包里全自带** | 包 6.0 GB；启动器里那些「环境修复 / 更新」入口不能碰（见 §3） |
| **B · 官方 ComfyUI + XPU 轮子** | 想自己控版本、跟着上游走 | 驱动 + Python 3.13 + 3 个 `+xpu` 轮子 + 锁页内存补丁 | — | ComfyUI 每次升级，补丁要重打一遍 |
| **C · 只跑 llama.cpp** | 只用大模型聊天 / 写代码，不画图出视频 | 驱动 + 一个 zip | **Python 完全不用装** | 没有图形界面，只有命令行和 API |

> 机器是 Linux 的话还有第四条：**Docker 镜像**（§5.1）。它只对 Linux 成立，**Windows 用户用不了**。

项目里的 ComfyUI 数字来自 **0.39.0 栈**（路 B 的形态）。路 A 是 **0.34.0 栈**，
两者在「int8 能不能原生算」这一条上有实质差别——见
[`comfyui-capability.md`](comfyui-capability.md) §3.2，**别把两栈的数字混着引用**。

---

## 2. 三条路都要装：显卡驱动

| 项 | 值 |
|---|---|
| 实测驱动版本 | **32.0.101.9150**（B70 32G）· **32.0.101.8976**（B50 16G） |
| 来源 | Intel 官网的 **Arc Pro** 驱动包（不是消费级 Arc 的那一页） |
| 装完确认 | Intel Graphics Software（IGS）里能看到 `Arc(TM) Pro B70 / B60 / B50 Graphics` |
| 重启 | 按安装程序提示走；驱动版本一变，**历史数字全部作废，要重测**（见 §7） |

**ECC 默认是关的**（Intel 驱动出厂默认关闭，需要人工到 IGS 打开）。

- 关着时 B70 可见 **31.16 GiB**（32 GB 档可用全量）
- 打开后只剩 **27.25 GB**，且**不提升算力**（实测差异在 6% 以内，关着反而略快）

本手册的显存口径一律按**关 ECC**算。开过 ECC 的机器，别拿自己的可用显存去套这里的「装得下 / 装不下」判断。

---

## 3. 路 A：整合包（省事那条）

社区里流通的是 **Intel × 秋叶（绘世）订制版**，包名形如 `ComfyUI-intel-aki-v1.x`。
它的价值就是把 §4 那一整套（Python + `+xpu` 轮子 + 补丁）**预装在包里**，解压即可用。

### 3.1 下载

**Intel + ComfyUI 0.34 · 秋叶专改版**

| 渠道 | 链接 | 提取码 |
|---|---|---|
| 百度网盘（国内） | <https://pan.baidu.com/s/1iqa_jrPrLM6DjvhrP8wMoQ?pwd=aaki> | **`aaki`** |
| 夸克网盘（国内） | <https://pan.quark.cn/s/0ef85e3bb6d6> | 无 |

⚠️ **这是第三方作品，不是本项目发布的**。本手册只负责实测它、写清「怎么用 / 别碰什么」，
**不转存、不重新打包**；版本以发布方为准。

🌍 **国外或打不开这两个网盘** → 走 [§4 自己装](#4-路-b官方-comfyui--xpu-轮子)。
那一节存在的意义就是这个：不依赖任何网盘。

实测这一版的环境（包内自带，无需另装）：

| 项 | 值 |
|---|---|
| Python | 3.13.14（包内 `python_embeded`） |
| torch | **2.13.0+xpu**（不是 `+cuXXX`） |
| ComfyUI | 0.34.0 + 本地 XPU 补丁 |
| 体积 | **6.0 GB**（其中 `python_embeded` 占 4.4 GB） |
| 启动 | 双击包根目录的 `run_intel_gpu.bat` |

启动脚本里有 7 个环境变量，**缺一个就会静默降级**（不报错，只是变慢）：

```
OMNIXPU_ENABLE=1
OMNIXPU_PROVIDER_BOOTSTRAP=required
OMNI_IMAGE_XPU_TARGET=bmg
OMNI_ATTN_BACKEND=cute
SOL_ATTN_XPU_EXPERIMENTAL=1
OMNIXPU_INTERPOLATE_FIX=0
OMNI_COMFYUI_RESERVE_VRAM_GB=4
```

走 `run_intel_gpu.bat` 就会自动设好；**绕过它、自己拼命令行启动，这串变量会全部丢失**。

🔴 **整合包里那两个入口绝对不能点**：

| 入口 | 会发生什么 |
|---|---|
| 「修复环境 / 安装 torch」 | 它认识的是 CUDA / ROCm 逻辑，**不认识 `+xpu`** → 直接把你换成 `+cu130` 的轮子，XPU 环境报废，得从头重建 |
| 「更新 ComfyUI」 | 走 `git pull` → 包里的本地 XPU 补丁被上游覆盖 |

同理，包里的 `install_torch_cu130.sh`、`升级_pytorch_cu130.bat`、`wheels\`、
`.launcher\*.extpack`（ROCm 内核包 / ZLUDA）全是 CUDA/AMD 时代的残留，**别执行**。

**为什么本项目不转存这个包**
它是第三方作品（含闭源启动器 + ComfyUI 本体 + 各自许可证的模型），而且 **6.0 GB 的体积
GitHub 装不下**（普通仓库单文件上限 100 MiB，Releases 单文件 2 GB）。
所以这里的做法是：**给官方分享链接（§3.1）+ 写清怎么用、别碰什么**，而不是自己再传一份。

---

## 4. 路 B：官方 ComfyUI + XPU 轮子

### 4.1 实测验过的轮子组合

Windows · CPython 3.13 · `win_amd64`，装成一套才能用（版本要配套，别东拼西凑）：

| 包 | 版本 |
|---|---|
| `torch` | **2.12.0+xpu** 或 **2.13.0+xpu** |
| `torchvision` | 0.27.0+xpu |
| `torchaudio` | 2.11.0+xpu |

两个 torch 版本都在 B70 上跑通过（2.12 与 2.13 各一套环境）。
🔴 **判断装没装对，只看版本号里的后缀**：`+xpu` 才是对的，`+cpu` 会安静地只跑 CPU，
`+cuXXX` 是给 NVIDIA 的——后两种都不会报错，只是慢，很容易被当成「Intel 卡不行」。

### 4.2 锁页内存补丁：改哪三处

ComfyUI 的 `comfy/model_management.py` 里，锁页内存上限 `MAX_PINNED_MEMORY` 的门控是
`is_nvidia() or is_amd()` —— **Intel XPU 永远进不去**，于是模型每次上下显卡都走可分页内存。
补丁就三件事：

1. **门控**加上 `is_intel_xpu()`，上限按 ComfyUI 自己的公式算（Windows：`RAM × 0.40`）
2. **`pin_memory()`** 增加 XPU 分支——torch 的 XPU 后端没有 `cudaHostRegister`
   那种原地注册接口，只能「申请锁页内存 + 把张量的存储换过去」
3. **`unpin_memory()`** 加对称分支，把存储换回普通内存、归还物理页

⚠️ **收益看场景，别照抄「提速 19%」这个数**：那个数字来自**权重需要反复换进换出**的情形。
本机实测（2 步 · 5 s · B70）：

| 组 | 端到端 | 相对基准 |
|---|---:|---:|
| 默认（pin 开） | 240.66 s | 基准 |
| `nopin`（pin 关） | 241.02 s | **+0.1%** |

**DiT 整驻显存、不发生 offload 时，这个开关收益为零。** 而 32 GB 机上锁页内存不可换出、
硬占物理内存，反而增加风险。所以：

- **32 GB 档（B70/B65）、模型整驻** → 开关都行，**不必特意开**
- **16 GB 档（B50）、需要卸权重** → 才值得打开

**外部佐证（同向）**：做 B70 XPU 镜像的那个第三方项目自己写了两条 ——
「固定内存最多占用 **90%** 内存」「内存不到 64 GB 就加 `OMNIXPU_PIN_MEMORY=0`，单跑一个 H3 就要固定约 **52 GB**」。
也就是说 pin 是**拿物理内存换搬运**：不搬运的时候，它只留下占用。
32 GB 机器上一个 H3 就要 52 GB 锁页 —— 这就是为什么这条在桌面档位不划算。

完整实测见 [`comfyui-h3.md`](comfyui-h3.md) 的「开关组」一节。

---

## 5. 路 C：llama.cpp（最轻的一条）

llama.cpp 的官方预编译包**自带运行时**，不装 Python、不装 oneAPI：

| 后端 | 包 | 怎么钉设备 |
|---|---|---|
| **SYCL** | `llama-b11753-bin-win-sycl-x64.zip` | `opencl:0`（另可选 `level_zero:0`） |
| **Vulkan** | `llama-b11753-bin-win-vulkan-x64.zip` | 🔴 **`Vulkan1`** |

🔴 **Vulkan 下第 0 张设备是核显**。直接跑会挑到 `AMD Radeon(TM) Graphics`，慢得离谱还不报错。
先跑一次 `llama-bench.exe --list-devices` 看清顺序再钉：

```
Vulkan0 = AMD Radeon(TM) Graphics   (uma: 1, matrix cores: none)
Vulkan1 = Intel(R) Arc(TM) Pro B70  (matrix cores: KHR_coopmat)
SYCL0   = Intel(R) Arc(TM) Pro B70
```

两边该选哪个，以及 1.5~1.65× 的差距怎么来的，见
[`server-config.md`](server-config.md) §8。

---

## 5.1 Linux 上还有第四条路：Docker 镜像（Windows 用不了）

如果机器是 Linux（或 LXC 容器），整个环境可以装进镜像里，一条 `docker run` 起服务。
这是 Intel 给**生产环境**的路，不是给个人桌面的。

| 镜像 | 里面是什么 | 体积 |
|---|---|---|
| `intel/llm-scaler-omni:0.2.0-b1`（[官方](https://github.com/intel/llm-scaler)） | ComfyUI **0.31** + torch **2.11** + `omni_xpu_kernel` | — |
| `gerrywang/comfyui-b70-xpu:0.1.0-b1`（[第三方增强](https://github.com/igerry/comfyui-b70-xpu)） | 在官方镜像上升级到 ComfyUI **0.39** + torch **2.13** | **10.8 GB / 17 层，实际下载 4.05 GB** |

**「10.8 GB」不等于要下 10.8 GB。** Docker 按层共享，17 层里有相当一部分来自 Intel 官方基础镜像；
换版本时通常只拉差异层。这也说明**大环境该怎么分发**：不是塞进 Git 仓库（单文件上限 100 MiB），
而是放镜像仓库 —— 一个 10 GB 的镜像，用户可能只多下几百 MB。

🔴 **Windows 用户用不上**：它要 `--device=/dev/dri`（Linux 的 DRM 设备节点）和
`--memory=<物理内存>`，仓库明确写 `Requirements: Linux, an Intel Arc B-series GPU with working drivers, Docker`。
本手册的目标用户是 Windows + 32 GB 内存，所以这条路只对服务器 / Linux 工作站成立。

⚠️ **这两个镜像本项目没有在本机跑过**（本机是 Windows、没有 Docker 环境），此处只作为
「上游怎么配的」引用，**里面的性能数字一个都没进本手册的表格**。

### 本项目那套 0.39 栈是什么

本手册的出图 / 出视频数字里，标注「0.39 栈」的那批，组件构成是（本机实取）：

| 组件 | 版本 |
|---|---|
| ComfyUI | **0.39.0** |
| torch | **2.12.0+xpu** |
| `omni_xpu_kernel` | 已装（Intel omni 生态的 XPU 算子） |
| `comfy_kitchen` | 已装（含 XPU 后端） |

⚠️ **注意它和上面那个镜像不是同一套**：镜像里是 torch **2.13**，本项目这批是 torch **2.12**。
三个栈（Intel 官方 0.31/2.11 → 第三方镜像 0.39/2.13 → 本项目 0.39/2.12）的数字**不能并排引用**。

---

## 6. 任何一条路都躲不掉：内存与页面文件

**目标用户的机器是 32 GB 内存起步**，很多只有两条内存槽，加不了。
所以「内存不够就加内存」不是解法，**页面文件是唯一可扩展的那部分**。

| 项 | 实测值 | 说明 |
|---|---|---|
| 物理内存 | 31.1 GiB 可用 | 32 GB 机器扣掉核显与系统占用 |
| 页面文件 | **初始 64 GB / 最大 128 GB** | 本项目所有 ComfyUI 实测都在这个设置下 |
| 为什么这么大 | 16 GB 档要卸权重、32 GB 档高档分辨率会进换页区 | 页面文件太小 → 加载阶段直接失败 |

跑测前先确认，别在半路才发现是内存问题：
`Get-CimInstance Win32_PageFileUsage` 看 `AllocatedBaseSize`（单位 MB）。

---

## 7. 装完先自检这三条

**① 卡认没认到、显存多少**

```
python_embeded\python.exe -c "import torch; print(torch.__version__, torch.xpu.is_available(), torch.xpu.get_device_name(0), round(torch.xpu.get_device_properties(0).total_memory/2**30, 2))"
```

期望输出（B70 · ECC 关）：

```
2.13.0+xpu True Intel(R) Arc(TM) Pro B70 Graphics 31.16
```

看到 `False`、或者显存报 27.2 左右，先回 §2 查驱动和 ECC。

**② llama.cpp 枚举对不对**

`llama-bench.exe --list-devices` —— 必须有 `Vulkan1` 或 `SYCL0` 那一行是你的卡。
（`llama-bench.exe` 要在它自己的目录里跑，否则 `*-impl.dll` 加载失败，rc=127。）

**③ 页面文件够不够** —— 见 §6。

---

## 8. 装不上的时候，先看这张表

| 现象 | 最可能的原因 | 去看 |
|---|---|---|
| `torch.xpu.is_available()` 是 `False` | 装成了 `+cpu` 或 `+cuXXX` 轮子 | §4.1 |
| 显存只报 27.2 GB | ECC 处于打开状态 | §2 |
| 能跑但慢一个数量级 | Vulkan 挑到了核显（`Vulkan0`） | §5 |
| 变慢、但不报错，且刚点过启动器的「修复环境」 | `+xpu` 被换成 CUDA 轮子 | §3 |
| 更新 ComfyUI 后行为变了 | 本地 XPU 补丁被 `git pull` 冲掉 | §3 / §4.2 |
| 加载阶段直接失败 / OOM | 页面文件不够 | §6 |
| 跑着跑着进程「静默消失」，没有 traceback | 不是 Python 崩，是 GPU 引擎超时（TDR）把进程连坐杀了 | [`pitfalls.md`](pitfalls.md) |

---

## 相关

- 一页纸汇总：[`at-a-glance.md`](at-a-glance.md)
- 坑清单：[`pitfalls.md`](pitfalls.md)
- 测试平台规格与卡身份取证：[`test-rig.md`](test-rig.md)
