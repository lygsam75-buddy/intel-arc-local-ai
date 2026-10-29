**English** · [简体中文](build.md)

# The machine we tested on

**In one sentence**: it is **a mainstream 2025 gaming PC**. Same platform, nothing added. The
**only part swapped was the GPU, for one with more VRAM** — because that is the only part that
decides whether a local LLM is usable.

So the numbers below did not come from a server. They came from **an ordinary desktop gaming PC**.
Copy this build and you do not need a workstation.

---

## 1. Current configuration (every row verified, not copied from a spec sheet)

| Part | Model / spec | How it was verified |
|---|---|---|
| **CPU** | AMD **Ryzen 5 9600X** · 6 cores / 12 threads · 5.0 GHz base · **with iGPU** · AVX-512 | `Win32_Processor` |
| **Motherboard** | GIGABYTE **B850M FORCE WIFI6E** (mATX · AM5) | `Win32_BaseBoard` |
| BIOS | **F8** (2026-05-21) | `Win32_BIOS` |
| **Memory** | **2 × 16 GB DDR5-6400** dual channel (part `PGD5U64A32XX7-KSWC`) | `Win32_PhysicalMemory` |
| Memory slots | **2 slots, both populated** (dual channel 2 × 16 GB; the only way up is replacing the pair) | physical inspection / board spec |
| **GPU** | **Intel Arc Pro B65 32 GB** (GUNNIR 蓝戟 · `DEV_E222` / `SUBSYS_27441EF7`) | `gpu_identity.py` |
| **GPU driver** | **32.0.101.9150** (driver date 2026-10-08 · INF `oem104.inf`) | `Win32_VideoController.DriverVersion` |
| GPU usable VRAM | **31.16 GiB** (ECC off) | `torch.xpu…total_memory` |
| **iGPU** | AMD `Radeon(TM) Graphics` (UMA) · fixed 512 MB + dynamic shared · driver **32.0.21045.5002** | `Win32_VideoController` |
| Display output | **handled by the iGPU**: 2560×1440 @ 144 Hz; the discrete card's resolution field is empty | `CurrentHorizontalResolution` |
| **Storage** | WD_BLACK **SN750 SE 1 TB** + WD **500 GB**, both NVMe SSD | `Get-PhysicalDisk` |
| **OS** | **Windows 11 Pro · 26H2 · Build 26300.9711** | `Win32_OperatingSystem` + `DisplayVersion` |
| Page file | **96 GB fixed (initial = max = 98304)**, commit limit 127.11 GiB (the floor for loading H3 video) | `Win32_PageFileUsage` |
| **PSU** | GIGABYTE **GP-UD850GM PG5 2.0** (850 W · ATX 3.0 / PCIe 5.0) | label on the unit |
| Case | **not recorded** | no effect on benchmark numbers |

> 🔴 **The driver version is mandatory, not optional.** A driver change or an ECC state change means
> **re-running everything** — every number in this handbook is tied to driver `32.0.101.9150`.
> On another version the numbers do not compare.

**Two PCIe slots**: 1 × **PCIe 5.0 x16** (CPU-attached) + 1 × **PCIe 4.0 x4** (chipset).
B70 sits in the **CPU-attached slot**.

> ⚠️ **Do not read slot count from WMI.** On this machine `Win32_PhysicalMemoryArray.MemoryDevices` reports **4**,
> but the board has **2** slots; and both modules report `DeviceLocator` = `DIMM 1` — the SMBIOS data on this
> board is wrong. Trust the physical board / the board spec. (Same for the 128 GB from `MaxCapacityEx`: ignore it.)

> ⚠️ **Do not read the OS version from `ProductName` alone.** Under
> `HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion`, `ProductName` still says **"Windows 10 Pro"**
> on this machine — an old key Microsoft never changed, and the same value appears on Win11. Read
> **`DisplayVersion` (26H2) + `CurrentBuild` (26300.9711)**, or `Win32_OperatingSystem.Caption`.

---

## 2. How it got here: one card swapped

| | Before | Now |
|---|---|---|
| GPU | a 2025 gaming card (**removed**, model not recorded) | **Arc Pro B70 32 GB** |
| CPU / motherboard / memory / storage | — | **nothing touched** |

> That is also why the conclusions in this handbook — "16 GB cards have to offload experts", "32 GB of RAM
> plus a large page file" — are worth reading. They all come from **an ordinary desktop that was never
> stripped down or specially tuned**, not a purpose-built test bench.

---

## 3. Why swap the GPU, not add RAM or change platform

All four options were costed:

| Idea | Why it was not taken |
|---|---|
| **Add RAM** | **Both slots are already full.** More memory means replacing both 16 GB modules (double the cost), and 2026 is a memory price upcycle |
| **More RAM would not help** | H3 does not run because **VRAM** is short, not system RAM. Doubling RAM will not squeeze 19 GB of weights into less VRAM |
| **New platform / new CPU** | That is whole-system cost; and the CPU is not the main bottleneck (MoE decode is bandwidth-bound, only prefill is compute-bound) |
| **Two cards** | The board has only 1 CPU-attached x16 + 1 chipset x4, so two cards cannot both run at full speed; and a second card buys **capacity**, not speed |

→ Conclusion: **only one variable changes "usable or not" — VRAM capacity.**
So the move is "swap in a 32 GB card" and leave everything else alone.

**Why 32 GB is the line**: at 16 GB, H3 has to offload experts to the CPU (speed drops, and Vulkan's advantage
collapses from 1.65× to 1.12×); only at 32 GB does the model stay fully resident. Measured — see
[`comfyui-h3.md`](comfyui-h3.en.md).

---

## 4. Display wiring: monitor into the motherboard, not the GPU

```
Monitor ──HDMI/DP──> motherboard (iGPU, AMD Radeon)   ← desktop, browser, video decode all live here
                         │
Arc Pro B65 (discrete) ──┘ drives no display; all its VRAM and GPU time go to the model
```

Measured with this wiring: ComfyUI is the only process on the discrete card, at **70 MB**; VRAM is the full
**31.16 GiB**. For the full evidence and for how to check a miswired setup, see the "iGPU + discrete GPU" section
of [`test-rig.md`](test-rig.en.md) and [`install.md`](install.en.md) §6.1.

---

## 5. Where this machine's limits are (and where this document's conclusions stop)

| Item | Measured so far |
|---|---|
| Memory | **32 GB** (31.11 GiB visible, of which about 0.9 GB is taken by the iGPU) |
| H3 video | **Resolution ladder measured on all four cards**: B70 all five tiers (max 1920×1088 / 841.55 s), B50 all six (→ 1080p 2,259.86 s), B65 five (→ 1080p 1,326.17 s), B60 three (→ 1,327.67 s). Steady state except B50's first data point |
| **2560×1440 and above** | **not measured** (VRAM and time cost too high) |
| Sustained full load (> 1 h) | **not measured** (single-task peaks only) |
| Two cards at once | **2× B65 measured**: both at full load on H3, end-to-end +6.0%, Qwen decode −0.2%, sampling per step unchanged; two image instances, zero loss; both at full load **combined P90 400.8 W / peak 406.5 W**, with no clock interference between them (`docs/slot-comparison.md` §6); B70/B50/B60 have no same-model second card |

---

## 6. The two items not recorded

| Item | Why |
|---|---|
| **Case** | Windows cannot read it, no effect on benchmark numbers, not recorded |

> The PSU is recorded from the unit itself: **GIGABYTE GP-UD850GM PG5 2.0 (850 W · ATX 3.0 / PCIe 5.0)**.
> Whole-card P90 at single-card full load: B70 290 W, B65 200 W (pinned to the wall); **two B65 at full load
> measured 400.8 W P90 combined, 406.5 W peak** (`comfyui-power.md` §3e). Size the build with headroom above
> that number, not above the single-card figure.

---

## Related

- Platform spec and how the card was identified: [`test-rig.md`](test-rig.en.md)
- What to install before you start: [`install.md`](install.en.md)
- One-page summary: [`at-a-glance.md`](at-a-glance.en.md)
