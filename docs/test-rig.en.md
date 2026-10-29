**English** · [简体中文](test-rig.md)

# Test Rig Specification

> The **preconditions** behind every on-machine measurement. No number means anything
> without this spec, and every quoted figure must name the slot it ran in.

---

## Current test machine (main bench)

> This file records **platform specs and how they are verified**. The full machine
> configuration table, and the story of "it is a 2025 gaming PC with only the GPU swapped",
> live in [`build.md`](build.en.md). Where the two disagree on a spec, the measured value in
> this section wins.

| Item | Spec | Notes |
|---|---|---|
| Motherboard | GIGABYTE **B850M FORCE WIFI6E** (micro-ATX) | Sets the spec of both slots below |
| Expansion slot 1 | **PCIe 5.0 x16** (CPU-attached) | Main slot, full link |
| Expansion slot 2 | **PCIe 4.0 x4** (chipset-attached) | Secondary slot, bandwidth ≈ 1/4 of the main slot |
| Card under test | **Intel Arc Pro B65 32G** (installed · CPU-attached slot) | **31.16 GiB** usable (ECC off). Cards seen on this machine: B70 (10-19 to 10-21 morning), B60 (10-20), B50 (removed) |
| Memory | **2 × 16 GB DDR5-6400** (dual channel) | **31.11 GiB** visible to Windows |
| Display adapters | **iGPU + discrete GPU coexisting**: AMD Radeon(TM) Graphics (UMA) + Arc Pro B65 under test | See the dedicated section below, **it affects reproducibility** |
| PSU | **GIGABYTE GP-UD850GM PG5 2.0** (850 W · ATX 3.0 / PCIe 5.0) | Two B65 at full load: 406.5 W peak on the GPU side |
| Page file | Initial 64 GB / max 128 GB | Mandatory companion for a 32 GB machine |
| Platform | AMD AM5 (Ryzen) | **AVX-512 support**, a real gain for CPU-side MoE expert compute |

### iGPU + discrete GPU: separate VRAM pools, desktop on the iGPU (**recommended configuration**)

This machine is **iGPU + discrete GPU**, not a single-GPU box. The pairing is
**deliberate**: the monitor goes into the motherboard (iGPU) output, so desktop, browser
and video decode all run on the iGPU, and **the discrete card's VRAM and GPU time stay
whole for the model**.

| Adapter | Role | Where its "VRAM" comes from | Measured |
|---|---|---|---|
| AMD Radeon(TM) Graphics | iGPU (`uma: 1` unified memory) | **System RAM**: **512 MB** fixed by BIOS + dynamic sharing by Windows | Adapter level under desktop load: 462 MB dedicated + 432 MB shared ≈ **0.9 GB**; process level about **1.1 GB** total |
| Intel Arc(TM) Pro B65 Graphics | Discrete GPU (under test) | 32 GB GDDR6 on board | **31.16 GiB** usable with ECC off; with the desktop idle, ComfyUI is the only process on it at **70 MB** |

**How to confirm which GPU drives the display and runs the desktop** (no guessing from Device Manager):

| Check | Measured result |
|---|---|
| Adapter that has a current resolution | **iGPU**: `2560x1440` |
| Resolution field on the discrete GPU | **empty** → the card under test drives zero display pixels |
| Processes on the iGPU's `0x14E3F` | `dwm` (desktop compositor) · browser · video player — **the whole desktop lives here** |
| Processes on the discrete GPU's `0x166F8` | only `python` (ComfyUI), **70 MB** |

Command: `Get-CimInstance Win32_VideoController | Select Name,CurrentHorizontalResolution,CurrentVerticalResolution`
— **the one with a resolution is the one actually driving the monitor**.

**Two rules. Do not swap them:**

1. ✅ **The iGPU does not consume the discrete card's VRAM.** The two are physically separate — `torch.xpu` reports `total_memory` for the card under test at the full **31.16 GiB**, none of it taken by the iGPU. So "does it fit in VRAM" is decided without regard to the iGPU.
2. ⚠️ **The iGPU does eat system RAM.** It has no VRAM of its own; desktop compositing, browser hardware acceleration and video decode all draw on a slice carved out of system RAM. So of the **32 GB of RAM**, what is left for ComfyUI to offload weights into, and for the page file, is **what remains after the iGPU's share**.

**How this differs from a single-GPU machine:**

| | iGPU + discrete (this machine) | Discrete only |
|---|---|---|
| System RAM | Minus the iGPU's slice (0.5 to 1 GB and up, more with heavier desktop load) | **All of it available to the CPU side**, more room to page |
| Discrete VRAM | Full amount for compute | Desktop compositing eats a few hundred MB and competes for GPU time |

→ **On a discrete-only reader's machine** (iGPU disabled / server with no iGPU), the same 32 GB goes further than here, and the 16 GB "does not fit" line may shift slightly. Conversely, **raising the iGPU UMA size in BIOS** (1G / 2G / 4G) tightens system RAM and pushes you into paging sooner.

> **This is the recommended configuration, not a compromise.** With the desktop on the iGPU,
> the discrete card stays whole for compute — measured: desktop + browser + video playback all
> on the iGPU side, ComfyUI the only process on the discrete card at **70 MB**. The cost is a
> little system RAM (table above); the gain is VRAM free of display output.
>
> ⚠️ **Comparison not run**: the monitor was never moved onto the **card under test** to run the
> same task, so there is no "saved N MB / gained N %" figure. The reasoning rests on the measured
> tables above plus the mechanism that WDDM allocates a frame buffer for display output.
> **This file states numbers only where numbers exist.**

> Verification (no GUI):
> `Get-CimInstance Win32_VideoController` for adapters and `AdapterRAM`;
> `llama-bench --list-devices` for the `uma:` flag; `torch.xpu...total_memory` for the discrete card's usable size.

> ⚠️ **Which card sits in which slot is not evidence for any conclusion in this project. Do not cite it as a premise.**
>
> Every slot conclusion here comes from **one B50 run in the main slot, then in the secondary
> slot** (see [`slot-comparison.md`](slot-comparison.en.md)) — and the conclusion is:
> **the 4× PCIe spec gap (x8 vs x4) is lost in measurement noise; it cannot be measured.**
>
> So a customer buying two cards **can seat them however they like**. There is no "which one
> belongs in the main slot" decision to make. This file registers platform specs and the
> required capture environment only. It does not prescribe card placement.

### Card identity (AIB, measured 2026-10-16)

**Intel ships in AIB (board partner) mode: the same GPU die goes onto boards built by different vendors. The model name is identical, the board is not.**
"Intel Arc Pro B50" alone does not say which board was measured — **board vendor and board
model code differ, and VBIOS, power limit, memory chips and cooling can all differ. Performance
need not match.**

So every data point in this repo must trace to **die DEV + SUBSYS** (together they uniquely
identify a board):

| Card | Die DEV | SUBSYS | Board vendor | Board model code | Nominal VRAM | Driver | Status |
|---|---|---|---|---|---|---|---|
| Arc Pro B50 | `E212` | `25221EF7` | **GUNNIR 蓝戟** (vendor `1EF7`) | 2522 | 16 GB | 32.0.101.8976 | Removed (historical) |
| Arc Pro B60 | `E211` | `25421EF7` | GUNNIR 蓝戟 (`1EF7`) | 2542 | 24 GB | **32.0.101.9150** | Measured (10-20) |
| Arc Pro B65 | `E222` | `27441EF7` | GUNNIR 蓝戟 (`1EF7`) | 2744 | 32 GB | **32.0.101.9150** | **Installed** (CPU-attached slot) |
| Arc Pro B70 | `E223` | `27421EF7` | GUNNIR 蓝戟 (`1EF7`) | 2742 | 32 GB | **32.0.101.9150** | Measured (10-19 to 10-21 morning) |

> Reading it: `SUBSYS_<board model code><board vendor id>` — the high 4 digits are the board
> model code (same die, different vendor or batch, different code), the low 4 are the board
> vendor PCI vendor id. Known: `1EF7` = GUNNIR 蓝戟, `8086` = Intel's own reference design.

**What this means for quoted numbers:**

- All four cards here — **B50 / B60 / B65 / B70 — are GUNNIR boards** → cross-card comparison is **same vendor against same vendor**, with no board-vendor difference mixed in.
- When quoting numbers from this project, **include at least die DEV and SUBSYS**. Under AIB mode a model name alone is not unique.
- Swapping in **another vendor's card of the same model** (an ASRock B70 for instance) strictly requires a re-measure before side-by-side use — the same logic as "a new driver or a new ECC state means re-measure everything".

**How to verify** (no admin rights, no WMI / PowerShell):

```bash
python bench/harness/gpu_identity.py          # installed devices only (with parent chain → slot ownership)
python bench/harness/gpu_identity.py --all    # include historical (pulled) devices
python bench/harness/gpu_identity.py --topo   # whole in-use PCI tree, sorted by bus
python bench/harness/gpu_sysman.py            # ECC / PCIe capability / firmware (VBIOS) / physical VRAM
```

**VBIOS version: the registry does not have it. Read it through Level Zero Sysman.**

The registry's display class key genuinely has no `BiosString` (only `qwMemorySize`), but the
Sysman firmware enumeration in `ze_loader.dll` reads VBIOS straight out, **no IGS screenshot
needed**:

```bash
python bench/harness/gpu_sysman.py     # see the "firmware" block
```

| Firmware slot | Reading on this machine's B50 |
|---|---|
| `OptionROM` | **`OPROM CODE VERSION:2304240000_OPROM DATA VERSION:2304240000`** ← **this is the VBIOS** |
| `GFX` (GSC firmware) | `BMG_\x15_21.1182` ← the `0x15` in the middle is a non-printable byte the driver emits. **Copy it as-is, do not "fix" it to `BMG__21.1182`** |
| `FanTable` | `unknown` |
| `VRConfig` | `unknown` |

> Verification note: this machine's driver **does not lay out** those two Sysman structs per the
> public spec — neither `zes_firmware_properties_t` (spec puts `name` at offset 16 and measured at
> **25**, version at **89**) nor `zes_device_properties_t`. Reading by offset yields garbage such
> as `brandName : 2]`. So the tool **always reads by printable-string segment** and prints the
> segment offsets for checking (`python bench/harness/gpu_sysman.py --raw`). One cross-check falls
> out of it: the board property segment shows `Intel(R) Graphics [0xe212]`, matching `DEV_E212` in
> the registry.

→ VBIOS of the B50 here = **`2304240000`** (CODE and DATA the same version).
That makes all four AIB identity fields (**DEV / SUBSYS / driver / VBIOS**) programmatically
verifiable, with no GUI.

### Real bandwidth of the two slots

| Slot | Link | Effective bandwidth | Where the figure comes from |
|---|---|---|---|
| PCIE1 | PCIe 5.0 x16 | ≈ 31.5 GB/s | computed from spec (32 GT/s ×16 with 128b/130b) |
| PCIE2 | PCIe 4.0 x4 | ≈ 7.9 GB/s | computed from spec (16 GT/s ×4 with 128b/130b) |

> ⚠️ **B850M FORCE WIFI6E does not support x8/x8 bifurcation.** The second slot is physically
> x16 long, electrically x4 only, and hangs off the chipset. That is standard for mATX
> platforms, not a defect of this board.

---

## Slot impact on results (rewritten 2026-10-15 — see slot-comparison.md)

**Bottom line: with parameters set correctly, the two slots cannot be told apart.**
At `-ncmoe ≥ 8` (experts resident in one go) the best result differs by **−2.9%** between
main x8 and secondary x4; repeated runs in the secondary slot alone span **13.9%**. The slot
difference is smaller than the noise, statistically indistinguishable.

**But "no slot difference" has preconditions, in three cases:**

| Test type | Is the x4 slot usable | Why |
|---|---|---|
| Model fully resident in VRAM (fit-in-VRAM) | ✅ almost no steady-state effect | PCIe only carries the one-time weight load |
| MoE expert offload, `-ncmoe ≥ 8` | ✅ no measurable difference | Only activations cross PCIe during inference (tens of KB); bandwidth is not the bottleneck |
| MoE expert offload, `-ncmoe 4–7` | ❌ **secondary slot loses 41%–59% throughput** | Weights shuttle back and forth across PCIe; x4 bandwidth is fully exposed |

Full data, pairing method and reproduce commands in [`slot-comparison.md`](slot-comparison.en.md).

**Capture requirements (mandatory):**

1. **`env.slot` must record the real slot** (`pcie5-x8` / `pcie4-x4`). The two groups may share a table, but every row must be labelled, and comparisons **only at the same `-ncmoe` operating point**.
2. Comparing slots across `-ncmoe` is meaningless — on the same secondary slot, `-ncmoe 4` and `-ncmoe 8` differ 6×. That is a parameter effect, not a slot effect.
3. With two cards installed, select the card with `ONEAPI_DEVICE_SELECTOR=level_zero:<idx>`; `idx` follows the actual `sycl-ls` enumeration (**do not assume the order is stable**).
4. Before recording official numbers, confirm no large process released host memory in the past 1 minute (page-file write-back still settling pollutes both sides; see `pitfalls.md` 1.7).

---

## Intel Arc Pro B50 LP 16G (removed; measured 2026-10-15)

Used for the 16 GB bracket (see `vram-16gb.md`).

| Item | Value |
|---|---|
| Model | Arc Pro B50 **LP** 16G (GUNNIR 蓝戟 single-slot) |
| Device ID | `PCI\VEN_8086&DEV_E212` · **SUBSYS `25221EF7`** (vendor `1EF7` GUNNIR · board code `2522`) |
| Driver | 32.0.101.8976 (recognised on install, zero setup) |
| **Usable VRAM (measured)** | **15.51 GiB** (about 97% of the nominal 16 GB; see pitfalls 2.3) |
| Nominal VRAM | 16 GB GDDR6 · 128-bit · **224 GB/s** · 14 Gbps |
| Compute | 10.65 TFLOPS FP32 · **170 TOPS INT8** · 128 XMX |
| Interface | **PCIe 5.0 x8**; in the secondary slot the physical link is **PCIe 4.0 x4** only (slot is x16 long, x4 electrical) |
| PCIe location | **bus 3 · device 0 · function 0** (`domain 0`) |
| Slot ownership | **CPU-attached slot** — the parent chain runs straight to CPU root port `1022:14DB` (bus 0), never through the chipset |
| Power | **70 W, no external power** (slot power only) |
| Physical | 167 × 69 × 18.4 mm · **single-slot low profile** · low and full-height brackets included |
| VBIOS | **`OPROM CODE VERSION:2304240000_OPROM DATA VERSION:2304240000`** |
| ECC | Supported and **configurable**; **currently off** (driver default is off; enable by hand in IGS) |

> Form-factor advantage: single-slot low profile, no power connector, so it drops into the
> machine's second slot (chipset x4) with nothing lost, and never takes the main slot.

#### ECC reading (measured 2026-10-16)

**On this machine's B50: ECC supported, configurable, currently off.**

Intel's driver **defaults ECC to off; enable it by hand in IGS**. Verification command:

```bash
python bench/harness/gpu_sysman.py     # see the ECC block
```

| Item | Reading |
|---|---|
| `zesDeviceEccAvailable` | `true` (supported) |
| `zesDeviceEccConfigurable` | `true` (configurable) |
| `zesDeviceGetEccState` → `currentState` | **`2`** |
| `pendingAction` | `0` (`NONE`: no pending change, state settled) |
| Physical capacity cross-check | **15881.88 MB = 15.51 GiB** visible, 97% of the nominal 16 GB |

> ⚠️ **Do not read the `currentState` enum value as a conclusion on its own.** Level Zero's
> `zes_device_ecc_state_t` is numbered differently in the two spec generations (new, 4 values:
> `2=ENABLED, 3=DISABLED`; old, 3 values: `1=ENABLED, 2=DISABLED`), so the same `2` decodes to
> opposite meanings. Settle it on **physical capacity**: ECC on visibly shrinks VRAM (B70:
> **31.16 GiB → 27.25 GiB, −12.5%**). With ECC on, this card should land near ≈13.6 GiB — measured
> 15.51 GiB, on the off side. Capacity evidence and the driver default agree → **ECC off**.

### Slot topology: CPU-attached slot or chipset slot (measured 2026-10-16)

**Bottom line: slot ownership can only be decided by walking the parent device chain. Bus number
is useless for it, and so is root port model alone.**

The B50's parent chain (`python bench/harness/gpu_identity.py`):

```
B50 (bus3:00.0 · 8086:E212)
 ↑0  PCI\VEN_8086&DEV_E2F0 ...  PCI Express Downstream Switch Port
 ↑1  PCI\VEN_8086&DEV_E2FF ...  PCI Express Upstream Switch Port
 ↑2  PCI\VEN_1022&DEV_14DB ...  PCI Express Root Port   ← CPU root port (bus 0 · 00:01.1)
 ↑3  ACPI\PNP0A08\0
```

Two traps, each hit once:

1. **Bus numbers move.** The same card in a different slot gets a new bus number; `bus 3` is only this enumeration's result, not a fixed property of the card. Do not hard-code it into a conclusion.
2. **Root port model is not a criterion.** This machine's **chipset uplink** also uses `1022:14DB` (00:02.1 · instance `...&0&11`; the B50 sits at 00:01.1 · instance `...&0&09`) — same model, different position. The real criterion is **whether the parent chain contains `1022:43F4`/`43F5` (AMD chipset switch ports)**: present → chipset slot; absent, landing directly on a bus-0 CPU root port → CPU-attached slot.

**Current topology** (reproduce with `python bench/harness/gpu_identity.py --topo`):

```
CPU (bus 0)
├─ 00:01.1  1022:14DB ─► 8086:E2FF / E2F0 / E2F1 ─┬─► 8086:E212  Arc Pro B50 graphics  (bus 3)
│                    (in-card PCIe bridge)         └─► 8086:E2F7  audio controller     (bus 4)
└─ 00:02.1  1022:14DB ─► 1022:43F4 ─► 1022:43F5 ×10 ─► (chipset branch: no GPU present)
                     (AMD chipset switch port family)
```

→ **The GPU is in the CPU-attached slot**; the chipset branch holds no GPU, so the secondary slot is empty.
→ Consistent with [`slot-comparison.md`](slot-comparison.en.md): main slot = CPU branch, secondary slot = chipset `x4` branch.

> **The card carries its own PCIe bridge. That is normal.** `8086:E2FF` / `E2F0` / `E2F1` are not
> the motherboard chipset but the PCIe bridge **inside** the Arc card (declared by Intel's graphics
> INF): graphics functions land on bus 3 and audio on bus 4 — a switch port sitting above
> the GPU is not a riser and not a motherboard fault.

**Another known limit: the negotiated width cannot be read here.**
Level Zero's `zesDevicePciGetState` (Sysman) and Windows'
`DEVPKEY_PciDevice_CurrentLinkWidth` both return nothing on this machine: the former gives all
0 / `status=UNKNOWN`, the latter `CR_NO_SUCH_VALUE (0x25)`. All that is available is the
**capability** reported by `zesDevicePciGetProperties`: **PCIe Gen5 x8 · 31.51 GB/s**.
→ Arguing "does the x4 slot cost performance" can only rest on **measured bandwidth / wall time**
(see `slot-comparison.md`), never on the negotiated width.

### Device enumeration order is not guaranteed

⚠️ With more than one card, the `0` / `1` order of `torch.xpu` / `sycl-ls` **is not guaranteed**.
Before every run, check with `torch.xpu.device_count()` + `get_device_properties(i).name`. Do not
hard-code `0/1`. And **do not add `<SYCL runtime dir>` to PATH** — every card disappears (see
`pitfalls.md` 1.3).

---

## Required environment fields for capture

Per the `arc-xpu-bench/1` schema in `bench/README.md`, the `env` block must contain:

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
  "igpu": "AMD Radeon(TM) Graphics (UMA, 512 MB fixed)",
  "os": "Windows 11 Pro 26H2 (26300.9711)",
  "backend": "SYCL",
  "llama_cpp_commit": "c25030496"
}
```

**Measured values on this machine (filled in 2026-10-16):**

| Field | Measured value | Source |
|---|---|---|
| `cpu` | **AMD Ryzen 5 9600X** · 6 cores / 12 threads · AM5 | `Win32_Processor` |
| `cpu_isa` | **AVX-512** (a real gain for CPU-side MoE expert compute) | spec |
| `driver` | **32.0.101.9150** (B65 · 2026-10-08 · INF `oem104.inf`); 32.0.101.8976 during the B50 / B70 period | `Win32_VideoController.DriverVersion` |
| `os` | **Windows 11 Pro 26H2 · Build 26300.9711** | `Win32_OperatingSystem` + `DisplayVersion` |
| `ram_gb` | **32** (`TotalPhysicalMemory` = 31.1 GiB) | `Win32_ComputerSystem` |
| `pagefile_gb` | **96** (`<non-system-drive>:\pagefile.sys`, initial = max = 98304 MB, **fixed size, not auto-managed**) → commit limit 127.11 GiB. Peak loading for H3 video needs 88 to 99 GiB; 64 GB stalls at 96.8% | `Win32_PageFileUsage` |
| `vram_gib_visible` | **31.16** (B65 32G, ECC off); 15.51 for B50 16G | `torch.xpu.get_device_properties(0).total_memory` |
| `igpu` | **AMD Radeon(TM) Graphics** (UMA; 512 MB fixed in BIOS + dynamic sharing) | `AdapterRAM` from `Win32_VideoController` (512 MB) + `uma: 1` from `llama-bench --list-devices` |

> ⚠️ **`igpu` is not optional.** The iGPU has no VRAM of its own; its "VRAM" is **system RAM** —
> so on an iGPU + discrete machine, the part of `ram_gb` available to model offload / the page
> file is what is left after the iGPU's share (about 0.9 GB under desktop load as measured).
> Reading only `ram_gb: 32` overstates usable memory. On a discrete-only machine record
> `"igpu": null` and note "no iGPU".

> ⚠️ **The page file sits off the system drive (`<non-system-drive>`) and is fixed at 64 GB, with
> automatic management off.** On a 32 GB machine it is the **only expandable "memory"**, so its
> size and its volume must be recorded with the data: switching to "system managed" or to another
> volume changes the numbers for MoE-offload tests.

> `slot` and `ecc` are the two fields most often missed and most damaging to comparability.
> **Neither may be empty.** `slot` takes `pcie5-x8` (main slot, CPU-attached) / `pcie4-x4`
> (secondary slot, chipset).
> ⚠️ Right now `slot` **mostly lives only in the file name** (e.g. `...-pcie4x4-ncmoe8.json`) and
> `env.slot` itself is empty in most records — a gap still to be closed, see `test-registry.md`.
