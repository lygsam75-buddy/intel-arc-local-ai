# 测试平台规格（Test Rig）

> 所有本机实测数据的**前提条件**。任何一组数字离开这份规格都无法比较，
> 引用数据时必须同时标明「跑在哪个槽」。

---

## 现役测试机（主台）

| 项目 | 规格 | 备注 |
|---|---|---|
| 主板 | 技嘉 **B850M FORCE WIFI6E**（micro-ATX） | 决定下面两个槽的规格 |
| 扩展槽 1 | **PCIe 5.0 x16**（CPU 直连） | 主槽，满链路 |
| 扩展槽 2 | **PCIe 4.0 x4**（芯片组直连） | 从槽，带宽 ≈ 主槽的 1/4 |
| 被测主力卡 | **Intel Arc Pro B50 LP 16G** | 实测可用 **15.51 GiB** |
| 平台 | AMD AM5（Ryzen） | **支持 AVX-512**，对 CPU 侧 MoE 专家计算有实质加成 |

> ⚠️ **「哪张卡放在哪个槽」不是本项目的结论依据，别再当成前提引用。**
>
> 本项目关于槽位的所有结论，只来自**同一张 B50 分别插主槽 / 插副槽**的对照
> （见 [`slot-comparison.md`](slot-comparison.md)）——结论是：
> **PCIe 规格差 4 倍（x8 vs x4）造成的损失落在测量噪声内，测不出来。**
>
> 所以买两张卡的客户**想怎么插怎么插**，不需要为了"哪张该放主槽"做决策。
> 本文件只登记平台规格与采集环境必填项，不规定卡的插法。

### 显卡机型身份（AIB 口径，2026-10-16 实测）

**Intel 走 AIB（板卡伙伴）模式：同一颗 GPU 芯片由不同厂商做板，型号名相同但板子不同。**
只写「Intel Arc Pro B50」不足以说明测的是哪块板——**板厂与板型号编码不同，
VBIOS、功耗墙、显存颗粒、散热都可能不同，性能未必一致。**

因此本仓库每条数据都要能追到 **芯片 DEV + SUBSYS**（两者合起来唯一确定一块板）：

| 卡 | 芯片 DEV | SUBSYS | 板厂 | 板型号编码 | 标称显存 | 驱动 | 状态 |
|---|---|---|---|---|---|---|---|
| Arc Pro B50 | `E212` | `25221EF7` | **GUNNIR 蓝戟**（vendor `1EF7`） | 2522 | 16 GB | 32.0.101.8976 | 已拆（历史） |
| Arc Pro B70 | `E223` | `27421EF7` | GUNNIR 蓝戟（`1EF7`） | 2742 | 32 GB | **32.0.101.9150** | **在位**（CPU 直连槽） |

> 读法：`SUBSYS_<板型号编码><板厂 vendor id>` —— 高 4 位是板型号编码
> （同芯片不同厂/不同批次会不同），低 4 位是板厂 PCI vendor id。
> 已知 `1EF7` = GUNNIR 蓝戟、`8086` = Intel 自家参考设计。

**对引用数字的影响**：

- 本机 **B70 与 B50 都是蓝戟 GUNNIR 板** → 两者横向对比是**同厂板对同厂板**，
  没有把板厂差异混进来。
- 引用本项目数字时**至少带上芯片 DEV 与 SUBSYS**；AIB 模式下只写型号名不唯一。
- 换一块**别家的同型号卡**（如 ASRock 的 B70），严格说要重测才能并排——
  与「换驱动 / 换 ECC 状态要全量重测」是同一条纪律。

**取证方式**（不需要管理员权限，不依赖 WMI / PowerShell）：

```bash
python bench/harness/gpu_identity.py          # 只在位设备（含上级链 → 槽位归属）
python bench/harness/gpu_identity.py --all    # 含历史（已拔）设备
python bench/harness/gpu_identity.py --topo   # 整棵在用 PCI 树，按总线排序
python bench/harness/gpu_sysman.py            # ECC / PCIe 能力 / 固件(VBIOS) / 物理显存
```

**VBIOS 版本：注册表取不到，改用 Level Zero Sysman 取。**

注册表显卡类键里确实没有 `BiosString`（只有 `qwMemorySize`），
但 `ze_loader.dll` 的 Sysman 固件枚举能把 VBIOS 直接读出来，**不需要开 IGS 界面截图**：

```bash
python bench/harness/gpu_sysman.py     # 看「固件」段
```

| 固件槽 | 本机 B50 读数 |
|---|---|
| `OptionROM` | **`OPROM CODE VERSION:2304240000_OPROM DATA VERSION:2304240000`** ← **这一条就是 VBIOS** |
| `GFX`（GSC 固件） | `BMG_\x15_21.1182` ← 中间那个 `0x15` 是驱动写出来的非打印字节，**照抄，别"修"成 `BMG__21.1182`** |
| `FanTable` | `unknown` |
| `VRConfig` | `unknown` |

> 取证注意：本机驱动**没按公开规范布局**写 Sysman 的这两个结构体 ——
> `zes_firmware_properties_t`（规范里 `name` 在 offset 16，实测落在 **25**、版本在 **89**）
> 和 `zes_device_properties_t` 都是。按偏移读会读出 `brandName : 2]` 这种垃圾值。
> 所以工具里**一律按「可打印字符串段」取**，并把段偏移打出来供核对
> （`python bench/harness/gpu_sysman.py --raw`）。
> 顺带一个交叉验证：板卡属性段里能读到 `Intel(R) Graphics [0xe212]`，与注册表的 `DEV_E212` 对上。

→ 本机 B50 的 **VBIOS = `2304240000`**（CODE 与 DATA 同版本）。
至此 AIB 身份四项（**DEV / SUBSYS / 驱动 / VBIOS**）全部可程序化取证，不依赖任何 GUI。

### 两条槽的真实带宽

| 槽 | 链路 | 有效带宽 | 实测来源 |
|---|---|---|---|
| PCIE1 | PCIe 5.0 x16 | ≈ 31.5 GB/s | 规格推算（32 GT/s ×16，128b/130b） |
| PCIE2 | PCIe 4.0 x4 | ≈ 7.9 GB/s | 规格推算（16 GT/s ×4，128b/130b） |

> ⚠️ **B850M FORCE WIFI6E 不支持 x8/x8 拆分**。第二槽物理为 x16 长度、
> 电气仅 x4，且挂在芯片组下。这是 mATX 平台的标准配置，不是个体问题。

---

## 槽位对测试结果的影响（2026-10-15 已重写，见 slot-comparison.md）

**结论先说：参数调对的前提下，两条槽测不出差别。**
`-ncmoe ≥ 8`（专家一次性驻留）时主槽 x8 与副槽 x4 的最优值差 **−2.9%**，
而副槽自身重复测量的极差是 **13.9%** —— 槽位差比噪声还小，统计上无法区分。

**但「槽位无差别」有前提，分三种情况：**

| 测试类型 | x4 槽是否可用 | 原因 |
|---|---|---|
| 模型整块驻留显存（fit-in-VRAM） | ✅ 稳态几乎无影响 | PCIe 仅用于一次性加载权重 |
| MoE 专家卸载，`-ncmoe ≥ 8` | ✅ 实测无差别 | 推理时只跨 PCIe 传 activation（几十 KB 量级），带宽不是瓶颈 |
| MoE 专家卸载，`-ncmoe 4~7` | ❌ **副槽慢 41%~145%** | 权重在 PCIe 上来回搬，x4 带宽被完整放大 |

完整数据、配对方法与复现命令见 [`slot-comparison.md`](slot-comparison.md)。

**采集纪律（强制）：**

1. **`env.slot` 字段必须标注真实槽位**（`pcie5-x8` / `pcie4-x4`），
   两组数据可以并排进表，但必须成对标注、且**只在同一 `-ncmoe` 工作点比较**。
2. 跨 `-ncmoe` 比较槽位没有意义——同一个副槽，`-ncmoe 4` 与 `-ncmoe 8`
   能差 6 倍，那是参数效应，不是槽位效应。
3. 双卡共存时用 `ONEAPI_DEVICE_SELECTOR=level_zero:<idx>` 指定跑哪张卡，
   `idx` 以 `sycl-ls` 的实际枚举为准（**别假设顺序稳定**）。
4. 出正式数字前确认宿主内存不是刚被大进程腾出来的 1 分钟内
   （页面文件回写未落定会污染两边的数字，判定方法见 `pitfalls.md` 1.7）。

---

## Intel Arc Pro B50 LP 16G（已装机，2026-10-15 实测）

用于 16GB 档专项（见 `vram-16gb.md`）。

| 项 | 值 |
|---|---|
| 型号 | Arc Pro B50 **LP** 16G（蓝戟/GUNNIR 单槽版） |
| Device ID | `PCI\VEN_8086&DEV_E212` · **SUBSYS `25221EF7`**（板厂 `1EF7` GUNNIR · 板码 `2522`） |
| 驱动 | 32.0.101.8976（装机自动识别，零安装） |
| **实测可用显存** | **15.51 GiB**（约标称 16 GB 的 97%，口径见 pitfalls 2.3） |
| 规格显存 | 16 GB GDDR6 · 128-bit · **224 GB/s** · 14 Gbps |
| 算力 | 10.65 TFLOPS FP32 · **170 TOPS INT8** · 128 XMX |
| 接口 | **PCIe 5.0 x8**；插副槽时物理链路只有 **PCIe 4.0 x4**（槽为 x16 长度、电气 x4） |
| PCIe 位置 | **总线 3、设备 0、功能 0**（`domain 0`） |
| 槽位归属 | **CPU 直连槽**——上级链直达 CPU 根端口 `1022:14DB`（总线 0），不经过芯片组 |
| 功耗 | **70 W，无外接供电**（仅 PCIe 插槽取电） |
| 物理 | 167 × 69 × 18.4 mm · **单槽半高** · 附矮/全高挡板 |
| VBIOS | **`OPROM CODE VERSION:2304240000_OPROM DATA VERSION:2304240000`** |
| ECC | 支持且**可配置**；**当前为关闭态**（驱动出厂默认关闭，需人工到 IGS 开启） |

> 形态优势：单槽半高 + 免供电，可无损插入本机第二条槽（芯片组 x4），不占主槽位置。

#### ECC 读数（2026-10-16 实测）

**本机 B50：ECC 支持、可配置，当前为关闭态。**

Intel 驱动 **ECC 出厂默认 = 关闭，需人工到 IGS 开启**。取证命令：

```bash
python bench/harness/gpu_sysman.py     # 看 ECC 段
```

| 项 | 读数 |
|---|---|
| `zesDeviceEccAvailable` | `true`（支持） |
| `zesDeviceEccConfigurable` | `true`（可配置） |
| `zesDeviceGetEccState` → `currentState` | **`2`** |
| `pendingAction` | `0`（`NONE`：无待生效变更，状态已落定） |
| 物理容量反证 | 可见 **15881.88 MB = 15.51 GiB**，占标称 16 GB 的 97% |

> ⚠️ **`currentState` 的枚举值不能单独当结论。** Level Zero 的 `zes_device_ecc_state_t`
> 在两代规范里编号不同（新 4 值：`2=ENABLED, 3=DISABLED`；旧 3 值：`1=ENABLED, 2=DISABLED`），
> 同一个 `2` 解出的意思正好相反。定论靠**物理容量**：
> ECC 开启会让可见显存明显缩水（B70 对照 **31.16 GiB → 27.25 GiB，−12.5%**），
> 若本卡开着 ECC，可见容量应落在 ~13.6 GiB —— 实测 15.51 GiB，落在关闭态一侧。
> 容量证据 + 驱动默认值口径一致 → **ECC 关闭**。

### 槽位拓扑：怎么判定卡插在 CPU 直连槽还是芯片组槽（2026-10-16 实测）

**结论先说：判定槽位归属只能回溯父设备链，既不能看总线号，也不能只看根端口型号。**

B50 的上级链（`python bench/harness/gpu_identity.py`）：

```
B50 (bus3:00.0 · 8086:E212)
 ↑0  PCI\VEN_8086&DEV_E2F0 ...  PCI Express Downstream Switch Port
 ↑1  PCI\VEN_8086&DEV_E2FF ...  PCI Express Upstream Switch Port
 ↑2  PCI\VEN_1022&DEV_14DB ...  PCI Express Root Port   ← CPU 根端口（总线 0，00:01.1）
 ↑3  ACPI\PNP0A08\0
```

两个坑，踩过一次：

1. **总线号会变。** 同一张卡换槽后总线号会重新分配，`bus 3` 只是当前这次枚举的结果，
   不是卡的固定属性，别写死进结论。
2. **根端口型号不能当判据。** 本机 **芯片组上行** 用的也是 `1022:14DB`
   （00:02.1，实例 `...&0&11`；B50 在 00:01.1，实例 `...&0&09`）——型号相同、只差位置。
   真正的判据是**上级链里有没有 `1022:43F4`/`43F5`（AMD 芯片组交换端口）**：
   有 → 芯片组槽；没有、直接落到总线 0 的 CPU 根端口 → CPU 直连槽。

**本机当前拓扑**（`python bench/harness/gpu_identity.py --topo` 可复现）：

```
CPU（总线 0）
├─ 00:01.1  1022:14DB ─► 8086:E2FF / E2F0 / E2F1 ─┬─► 8086:E212  Arc Pro B50 图形  (bus 3)
│                    （卡内 PCIe 桥）              └─► 8086:E2F7  音频控制器       (bus 4)
└─ 00:02.1  1022:14DB ─► 1022:43F4 ─► 1022:43F5 ×10 ─► （芯片组分支：当前无显卡）
                     （AMD 芯片组交换端口族）
```

→ **显卡在 CPU 直连槽**；芯片组分支当前没有显卡，即副槽空置。
→ 与 [`slot-comparison.md`](slot-comparison.md) 的口径对齐：主槽 = CPU 分支，副槽 = 芯片组 `x4` 分支。

> **卡自带一层 PCIe 桥，这是正常的。** `8086:E2FF` / `E2F0` / `E2F1` 不是主板芯片组，
> 而是 Arc 卡**内部**的 PCIe 桥（Intel 显卡驱动 INF 自己声明）：图形功能落 bus 3、音频落 bus 4。
> 看到「显卡上面还挂着一层 Switch Port」不要当成转接卡或主板故障。

**另一个已知限制：实际协商宽度本机读不到。**
Level Zero 的 `zesDevicePciGetState`（Sysman）与 Windows 的
`DEVPKEY_PciDevice_CurrentLinkWidth` 在本机都取不到值：
前者返回全 0 / `status=UNKNOWN`，后者返回 `CR_NO_SUCH_VALUE (0x25)`。
能拿到的只有 `zesDevicePciGetProperties` 报的**能力值**：**PCIe Gen5 x8 · 31.51 GB/s**。
→ 要论证「x4 槽掉不掉性能」，只能靠**实测带宽/耗时**（见 `slot-comparison.md`），不能靠读协商宽度。

### 设备枚举顺序不保证稳定

⚠️ 多卡时 `torch.xpu` / `sycl-ls` 的 `0` / `1` 顺序**不保证稳定**。每次跑之前用
`torch.xpu.device_count()` + `get_device_properties(i).name` 实核一遍，别按 `0/1` 硬编码。
且**不要把 `<SYCL 运行时目录>` 加进 PATH**，否则多卡全灭（见 `pitfalls.md` 1.3）。

---

## 采集时必填的环境字段

参考 `bench/README.md` 的 `arc-xpu-bench/1` schema，`env` 段必须包含：

```json
{
  "gpu": "Intel Arc Pro B50 LP 16G",
  "driver": "32.0.101.8976",
  "ecc": "off",
  "vram_gib_visible": 15.51,
  "slot": "pcie5-x8",
  "cpu": "AMD Ryzen 5 9600X (6C/12T)",
  "cpu_isa": "AVX-512",
  "ram_gb": 32,
  "pagefile_gb": 64,
  "backend": "SYCL",
  "llama_cpp_commit": "c25030496"
}
```

**本机实测值（2026-10-16 填齐）：**

| 字段 | 实测值 | 来源 |
|---|---|---|
| `cpu` | **AMD Ryzen 5 9600X** · 6 核 / 12 线程 · AM5 | `Win32_Processor` |
| `cpu_isa` | **AVX-512**（对 CPU 侧 MoE 专家计算有实质加成） | 规格 |
| `ram_gb` | **32**（`TotalPhysicalMemory` = 31.1 GiB） | `Win32_ComputerSystem` |
| `pagefile_gb` | **64**（`<非系统盘>:\pagefile.sys`，初始 65536 MB / 上限 131072 MB，**固定大小、非自动管理**） | `Win32_PageFileUsage` |
| `vram_gib_visible` | **15.51**（B50，ECC 关闭态） | `torch.xpu.get_device_properties(0).total_memory` |

> ⚠️ **页面文件在系统盘之外（`<非系统盘>`），且是固定 64 GB、没开自动管理。**
> 32 GB 内存的机器上这是**唯一可扩展的"内存"**，所以它的大小与所在卷必须随数据一起记录：
> 换成"系统托管"或换卷，MoE 卸载类测法的数字会跟着变。

> `slot` 与 `ecc` 是两份最容易漏、又最影响可比性的字段，**不得为空**。
> `slot` 取值 `pcie5-x8`（主槽，CPU 直连）/ `pcie4-x4`（副槽，芯片组）。
> ⚠️ 当前仓库里 `slot` **多数只写进了文件名**（如 `...-pcie4x4-ncmoe8.json`），
> `env.slot` 字段本身大半为空 —— 这是一处待补的口径缺口，见 `test-registry.md`。
