# 同一份代码差 3 倍：XPU 运行时的 SYCL 配套铁律（实测）

> **结论**：给 ComfyUI 自编 Intel XPU 运行时（comfy-aimdo），**编译器链接的 SYCL 运行时版本必须和 torch 自带的 sycl DLL 对上**。同一份源码、同一台 B70、同一套参数，只换 SYCL 运行时版本（sycl8 vs sycl9），Pika H3 Flex 六步 480p 出片墙钟 **377 s vs 104 s——3.6 倍差距**。版本号高低是伪命题，配套才是真命题。

- 测试机：Arc Pro B70 32G（ECC 关）+ Ryzen 5 9600X + 32 GB 内存 + Windows
- 软件：ComfyUI 0.43.2 · torch 2.13.0+xpu（自带 **sycl9.dll**）· 2026-11-02 实测
- 可直接安装的配套包：**[Release: xpu-runtime-sycl9-20261102](https://github.com/lygsam75-buddy/intel-arc-local-ai/releases/tag/xpu-runtime-sycl9-20261102)**

## 1. 问题是怎么暴露的

给 Pika H3 Flex 出性能报告时发现怪事：上午在整合包运行时上测出 5 秒 480p 片 **111.8 s**，下午换成自编的正式运行时（AIMDO 0.6.0），同一条工作流变成 **350~380 s**。中间只做过一件事：装 oneAPI 工具链、自己编译了 XPU 运行时。

于是做了完整排除（全部单变量实测）：

| 假设 | 排除方式 | 结果 |
|---|---|---|
| 0.6.0 代码比旧版慢 | 同一工具链重编旧 commit（`4972231d`）与 0.6.0 HEAD 对跑 | 376.7 s vs 377.4 s，**同速 → 排除** |
| 初始化参数不对（allocator 模式 / 4 GiB headroom） | 逐项补齐复测 | 无变化 → **排除** |
| init 时机（prestartup vs 节点加载） | 专门做早初始化对照 | 377.4 s，无变化 → **排除** |
| 冷热缓存口径 | 每条清缓存、冷热配对 | 无法解释 3 倍 → **排除** |
| **编译时链接的 SYCL 运行时** | 同源码换 oneAPI 2026.1（sycl9）重编 | **112.1 s / 104.1 s → 定案** |

## 2. 机制

`aimdo_xpu.dll` 编译时会链接一个 SYCL 运行时（`syclN.dll`）。两个来源：

- **torch 2.13/2.14+xpu 自带 `sycl9.dll`**（`python_embeded\Library\bin`）——和 XPU 驱动、UR 适配器成套调优；
- oneAPI 2025.x 编译器默认链接 **`sycl8.dll`** + 通用 UR 适配器——版本代差，调度路径不同。

用 2025.x 编译器编出的 dll 链上 sycl8，即使运行时把 torch 的 UR 栈塞在旁边，**内核派发仍然走 sycl8 路径**，实测慢 3 倍以上。用 oneAPI **2026.x** 编译（链 sycl9）与 torch 配套后，性能完整恢复。

**判断方法一句话**：看 `comfy_aimdo` 目录里 `aimdo_xpu.dll` 旁边的 `sycl*.dll` 是几号——和 `Library\bin` 里 torch 的一致就对了。

## 3. 实测数据（B70，同 seed 20261220，墙钟 = Queue → MP4 落盘）

| 工作流（5.2 秒片，含音轨） | sycl8 自建 | sycl9 自建 | 整合包旧运行时 |
|---|---|---|---|
| Pika 六步 832×480 | 377 s | **104~112 s** | 111.8 s |
| Pika 六步 1344×768 | 529~536 s | **336 s** | 316.7 s |
| 基座二十步 832×480 | 448~460 s | **224 s** | 250.3 s |
| 基座二十步 1344×768 | 1073~1088 s | **920 s** | 1130.5 s |

sycl9 下六步蒸馏相对二十步基座的加速比：480p **2.0×**、768p **2.7×**。

输出稳定性（同栈同 seed 两次跑）：480p 六步**位级一致**；其余档位文件大小漂移 <0.3%（GPU 原子加法的正常数值抖动，画质无可见差异）。

## 4. 三条铁律（搭配说明）

1. **SYCL 配对**：torch 的 `syclN.dll` 是几，就用能链 syclN 的编译器代际（sycl9 → oneAPI 2026.x）。装完自查：`comfy_aimdo` 目录里应有 `sycl9.dll`。
2. **别叠加速 LoRA**：Pika H3 Flex 等已蒸馏适配器（六步是训练日程），再叠 turbo/Lightning 会弄坏输出。
3. **32 GB 内存机**：文本编码器用 nvfp4 档；页面文件是唯一可扩展的"内存"，留足。

## 5. 直接用现成的

**[Release 下载页](https://github.com/lygsam75-buddy/intel-arc-local-ai/releases/tag/xpu-runtime-sycl9-20261102)**：`pika-h3-flex-xpu-runtime-sycl9-win64.zip`（5.8 MB）——含 sycl9 链接的 `comfy-aimdo 0.6.0+xpu`、kitchen 0.2.40、sycl9 运行时 DLL 套件、一键 `install.ps1`。解压后：

```powershell
.\install.ps1 -Python "<整合包>\python_embeded\python.exe"
```

构建来源与许可：[xiangyuT/comfy-aimdo-xpu](https://github.com/xiangyuT/comfy-aimdo-xpu)（AIMDO 0.6.0 + XPU 移植，含一处 `dxcore.lib` 链接修复，建议上游合入）、[comfy-kitchen-xpu](https://github.com/xiangyuT/comfy-kitchen-xpu)；sycl9/UR DLL 为 Intel/torch 官方再分发组件。

## 出处

- 本页数据对应 `bench/data/2026-11-02_b70-32g_*`（见 [Pika H3 Flex 上机报告](comfyui-pika-h3-flex.md)）与当日对比实验记录（F 盘测试床）。
- 相关：[Pika H3 Flex on B70](comfyui-pika-h3-flex.en.md)。
