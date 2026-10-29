**English** · [简体中文](install.md)

# Before you start: what actually needs installing

**In one line**: what you install depends on which route you take. The **one shared must-install across all three routes is the Intel graphics driver**.

The numbers in this guide do not vary with how cleanly you installed things. On the same card, a correct setup behaves as described; a wrong one runs an order of magnitude slower or crashes outright. Pin down the environment first, then read the numbers.

---

## 1. Three routes, pick one

| Route | Who it suits | Install | No need to install | Cost |
|---|---|---|---|---|
| **A · All-in-one bundle** | You want images today and no command line | Driver + unzip one package | torch, XPU runtime, patch, Python — **all bundled** | 6.0 GB package; do not touch the "repair environment / update" entries in the launcher (see §3) |
| **B · Stock ComfyUI + XPU wheels** | You want to control versions and follow upstream | Driver + Python 3.13 + 3 `+xpu` wheels + pinned-memory patch | — | Every ComfyUI upgrade means re-applying the patch |
| **C · llama.cpp only** | Chat and code only, no image or video generation | Driver + one zip | **No Python at all** | No GUI — command line and API only |

> On Linux there is a fourth route: the **Docker image** (§5.1). It exists only for Linux and **does not work on Windows**.

The ComfyUI numbers in this project come from the **0.39.0 stack** (the shape of route B). Route A is the **0.34.0 stack**. The two differ materially on whether int8 runs natively — see
[`comfyui-capability.md`](comfyui-capability.en.md) §3.2 — **do not mix numbers from the two stacks.**

---

## 2. Required on all three routes: the graphics driver

| Item | Value |
|---|---|
| Driver version tested | **32.0.101.9150** (B70 32G) · **32.0.101.8976** (B50 16G) |
| Source | Intel's **Arc Pro** driver package (not the consumer Arc page) |
| Post-install check | Intel Graphics Software (IGS) lists `Arc(TM) Pro B70 / B60 / B50 Graphics` |
| Reboot | Follow the installer's prompts. Any driver version change **voids all historical numbers — retest** (see §7) |

**ECC is off by default** (Intel ships it disabled; it must be turned on manually in IGS).

- Off: B70 shows **31.16 GiB** (the full 32 GB SKU)
- On: only **27.25 GB** remains, and it **does not increase compute throughput** (measured difference within 6%; off is slightly faster)

Every VRAM figure in this guide assumes **ECC off**. On a machine that has run with ECC enabled, do not map your own usable VRAM onto the fits / does-not-fit calls here.

---

## 3. Route A: the all-in-one bundle (the easy one)

The community build in circulation is the **Intel × Aki custom edition**; the package name looks like `ComfyUI-intel-aki-v1.x`.
Its value is that it **preinstalls the whole §4 setup** (Python + `+xpu` wheels + patch) — unzip and run.

### 3.1 Download

**Intel + ComfyUI 0.34 · Aki custom build**

| Channel | Link | Access code |
|---|---|---|
| Baidu Netdisk (China) | <https://pan.baidu.com/s/1iqa_jrPrLM6DjvhrP8wMoQ?pwd=aaki> | **`aaki`** |
| Quark Netdisk (China) | <https://pan.quark.cn/s/0ef85e3bb6d6> | none |

⚠️ **This is third-party work, not released by this project.** This guide only tests it and documents how to use it and what not to touch.
**No mirroring, no repackaging**; the publisher's version is authoritative.

🌍 **Outside China, or the two netdisks will not open** → install it yourself per [§4](#4-route-b-stock-comfyui--xpu-wheels).
That is exactly why the section exists: no netdisk dependency.

Environment measured for this build (bundled, nothing extra to install):

| Item | Value |
|---|---|
| Python | 3.13.14 (bundled `python_embeded`) |
| torch | **2.13.0+xpu** (not `+cuXXX`) |
| ComfyUI | 0.34.0 + local XPU patch |
| Size | **6.0 GB** (`python_embeded` alone takes 4.4 GB) |
| Launch | Double-click `run_intel_gpu.bat` in the package root |

The launch script sets 7 environment variables. **Miss one and it degrades silently** — no error, just slower:

```
OMNIXPU_ENABLE=1
OMNIXPU_PROVIDER_BOOTSTRAP=required
OMNI_IMAGE_XPU_TARGET=bmg
OMNI_ATTN_BACKEND=cute
SOL_ATTN_XPU_EXPERIMENTAL=1
OMNIXPU_INTERPOLATE_FIX=0
OMNI_COMFYUI_RESERVE_VRAM_GB=4
```

Going through `run_intel_gpu.bat` sets them all. **Bypass it and hand-build the command line, and the entire set is lost.**

🔴 **The two entries in the bundle must never be clicked**:

| Entry | What happens |
|---|---|
| "Repair environment / install torch" | It knows CUDA / ROCm logic and **does not know `+xpu`** → it swaps you onto `+cu130` wheels, the XPU environment is wrecked, and you rebuild from scratch |
| "Update ComfyUI" | Runs `git pull` → upstream overwrites the bundled local XPU patch |

Likewise `install_torch_cu130.sh`, `升级_pytorch_cu130.bat`, `wheels\` and
`.launcher\*.extpack` (ROCm kernel packs / ZLUDA) in the package are all CUDA/AMD-era leftovers. **Do not run them.**

**Why this project does not mirror the package**
It is third-party work (closed-source launcher + ComfyUI itself + models under their own licenses), and **GitHub cannot hold 6.0 GB**
(100 MiB per file in a normal repo, 2 GB per file in Releases).
So the approach here is **link to the official share (§3.1) and document how to use it and what not to touch**, rather than upload another copy.

---

## 4. Route B: stock ComfyUI + XPU wheels

### 4.1 Verified wheel combination

Windows · CPython 3.13 · `win_amd64`. It only works as one matched set — versions must line up, no mixing and matching:

| Package | Version |
|---|---|
| `torch` | **2.12.0+xpu** or **2.13.0+xpu** |
| `torchvision` | 0.27.0+xpu |
| `torchaudio` | 2.11.0+xpu |

Both torch versions run on the B70 (one environment each for 2.12 and 2.13).
🔴 **To tell whether the install is right, look only at the version suffix**: `+xpu` is correct, `+cpu` quietly runs on CPU only,
`+cuXXX` is for NVIDIA. Neither wrong option errors out — it is just slow, and easily read as "the Intel card is bad".

### 4.2 Pinned-memory patch: the three edits

In ComfyUI's `comfy/model_management.py`, the gate on the pinned-memory cap `MAX_PINNED_MEMORY` is
`is_nvidia() or is_amd()` — **Intel XPU never gets in**, so every model load and offload goes through pageable memory.
The patch is three things:

1. **Gate** — add `is_intel_xpu()`, with the cap computed by ComfyUI's own formula (Windows: `RAM × 0.40`)
2. **`pin_memory()`** — add an XPU branch. torch's XPU backend has no in-place registration like `cudaHostRegister`,
   so it has to "allocate pinned memory + swap the tensor's storage over"
3. **`unpin_memory()`** — add the symmetric branch: swap the storage back to normal memory and return the physical pages

⚠️ **The payoff depends on the case — do not copy the "19% faster" figure.** That number comes from situations where
**weights have to be swapped in and out repeatedly**. Measured on this machine (2 steps · 5 s · B70):

| Group | End-to-end | vs baseline |
|---|---:|---:|
| Default (pin on) | 240.66 s | baseline |
| `nopin` (pin off) | 241.02 s | **+0.1%** |

**When the DiT is fully resident and no offload happens, this switch buys nothing.** And on a 32 GB machine, pinned memory
cannot be swapped out and sits hard on physical RAM, which adds risk. So:

- **32 GB tier (B70/B65), model fully resident** → either way works, **no need to enable it**
- **16 GB tier (B50), weights must be offloaded** → worth turning on

**External corroboration (same direction)**: the third-party project behind the B70 XPU image states two things —
"pinned memory occupies at most **90%** of RAM" and "below 64 GB of RAM, add `OMNIXPU_PIN_MEMORY=0`; a single H3 run alone pins about **52 GB**".
In other words, pinning **trades physical RAM for transfer**: with no transfer, all it leaves behind is the occupancy.
One H3 on a 32 GB machine would want 52 GB of pinned memory — which is why this is a bad deal at desktop tier.

Full measurements: the "switch group" section of [`comfyui-h3.md`](comfyui-h3.en.md).

---

## 5. Route C: llama.cpp (the lightest one)

llama.cpp's official prebuilt packages **ship their own runtime**. No Python, no oneAPI:

| Backend | Package | How to pin the device |
|---|---|---|
| **SYCL** | `llama-b11753-bin-win-sycl-x64.zip` | `opencl:0` (`level_zero:0` also works) |
| **Vulkan** | `llama-b11753-bin-win-vulkan-x64.zip` | 🔴 **`Vulkan1`** |

🔴 **Under Vulkan, device 0 is the integrated GPU.** A default run picks `AMD Radeon(TM) Graphics` — absurdly slow, no error.
Run `llama-bench.exe --list-devices` once, read the order, then pin:

```
Vulkan0 = AMD Radeon(TM) Graphics   (uma: 1, matrix cores: none)
Vulkan1 = Intel(R) Arc(TM) Pro B70  (matrix cores: KHR_coopmat)
SYCL0   = Intel(R) Arc(TM) Pro B70
```

Which one to pick on each backend, and where the 1.5 to 1.7× gap comes from: §8 of [`server-config.md`](server-config.en.md).

---

## 5.1 Linux has a fourth route: the Docker image (not usable on Windows)

On a Linux machine (or LXC container) the whole environment fits into an image, and one `docker run` starts the service.
This is Intel's route for **production**, not for a personal desktop.

| Image | What is inside | Size |
|---|---|---|
| `intel/llm-scaler-omni:0.2.0-b1` ([official](https://github.com/intel/llm-scaler)) | ComfyUI **0.31** + torch **2.11** + `omni_xpu_kernel` | — |
| `gerrywang/comfyui-b70-xpu:0.1.0-b1` ([third-party build](https://github.com/igerry/comfyui-b70-xpu)) | The official image upgraded to ComfyUI **0.39** + torch **2.13** | **10.8 GB / 17 layers, 4.05 GB actual download** |

**"10.8 GB" does not mean downloading 10.8 GB.** Docker shares layers, and a fair share of those 17 layers come from Intel's official base image;
version changes usually pull only the differing layers. This also shows **how a large environment should be distributed**: not stuffed into a Git repo
(100 MiB per file), but into an image registry — of a 10 GB image, a user may download only a few hundred MB more.

🔴 **Windows users cannot use this**: it needs `--device=/dev/dri` (the Linux DRM device node) and
`--memory=<physical RAM>`, and the repo states `Requirements: Linux, an Intel Arc B-series GPU with working drivers, Docker`.
This guide targets Windows with 32 GB of RAM, so the route holds only for servers / Linux workstations.

⚠️ **This project has not run either image on local hardware** (local is Windows, no Docker). It is cited only as
"how upstream configured it" — **none of its performance numbers entered any table in this guide**.

### What this project's 0.39 stack is

Among the image / video numbers here, the batch labeled "0.39 stack" consists of (read off this machine):

| Component | Version |
|---|---|
| ComfyUI | **0.39.0** |
| torch | **2.12.0+xpu** |
| `omni_xpu_kernel` | Installed (XPU operators from Intel's omni ecosystem) |
| `comfy_kitchen` | Installed (includes the XPU backend) |

⚠️ **It is not the same set as the image above**: the image has torch **2.13**, this project has torch **2.12**.
Numbers from the three stacks (Intel official 0.31/2.11 → third-party image 0.39/2.13 → this project 0.39/2.12) **cannot be quoted side by side**.

---

## 6. Unavoidable on every route: RAM and the page file

**The target machine starts at 32 GB of RAM**, and many have only two DIMM slots — no upgrade path.
So "add more RAM" is not an answer. **The page file is the only expandable part.**

| Item | Measured | Notes |
|---|---|---|
| Physical RAM | 31.1 GiB usable | 32 GB machine minus iGPU and OS overhead |
| Page file | **64 GB initial / 128 GB max** | Every ComfyUI measurement in this project ran under this setting |
| Why so large | The 16 GB tier must offload weights; the 32 GB tier hits the paging area at high resolution | Too small a page file → loading fails outright |

### 6.1 Recommended: iGPU drives the display, dGPU does compute only

**This project recommends iGPU + dGPU, not dGPU alone. The reason is one thing: use every byte of the dGPU's VRAM.**

Plug the monitor into the **motherboard (iGPU)** video port → desktop composition, browser and video decode all run on the iGPU →
the dGPU drives no display output, and its VRAM and GPU time go entirely to the model.

Measured on this machine (this is the basis for making that recommendation):

| Check | Measured result |
|---|---|
| Who drives the display | **The iGPU**: **2560×1440** is output by `AMD Radeon(TM) Graphics` |
| Is the dGPU driving a display | **No**: the B70's `CurrentHorizontalResolution` is empty |
| Processes on the dGPU | Only ComfyUI, using **70 MB** |
| Usable dGPU VRAM | **31.16 GiB, full** (ECC off) |

**Three conditions for this setup**:

1. **A CPU with an iGPU** — AMD Ryzen non-`F` models, Intel non-`F` models (an `F` part has no iGPU, so output must come from the dGPU)
2. **A motherboard with video output** (HDMI / DP)
3. **The iGPU not disabled in BIOS**

**Cost: the iGPU eats system memory.** It has no VRAM of its own; its share is carved out of system RAM
(this machine: BIOS fixed 512 MB + dynamic sharing; about **0.9 GB** measured under desktop load, and it grows with a video site open).

| | iGPU (AMD Radeon / Intel UHD class) | dGPU (Arc Pro B70) |
|---|---|---|
| Where its "VRAM" comes from | **System memory**: a BIOS-fixed carve-out + on-demand dynamic sharing | Its own 32 GB GDDR6 |
| Does it consume dGPU VRAM | **No** — the two are physically separate | — |
| Impact while running models | Takes a slice of **system memory** | Full VRAM left for compute |

**So "32 GB of RAM" needs a qualifier:**

| Machine shape | System RAM actually usable | Consequence |
|---|---|---|
| **iGPU + dGPU** (recommended) | Minus the iGPU's share | Every number in this document was measured under this condition |
| **dGPU only** (monitor on the dGPU / no iGPU) | All of it goes to the CPU side, **roomier** | The 16 GB tier's "does not fit" boundary may loosen slightly, but display output eats part of the VRAM |
| iGPU memory raised in BIOS (1G / 2G / 4G) | **Tighter** | Enters the paging area sooner; loading fails more easily |

⚠️ **One comparison not run, stated plainly**: this project **did not plug the monitor into the B70 and run the same task for comparison**,
so it cannot give specific numbers for "how much VRAM this saves / how much faster it gets".
The basis is the measurement table above (the desktop really is not on the dGPU) plus the mechanism by which WDDM allocates a frame buffer for display output.
Where there are numbers, this guide gives numbers.

**How to confirm the wiring yourself** (not by looking at Device Manager):

```
Get-CimInstance Win32_VideoController | Select Name, CurrentHorizontalResolution, CurrentVerticalResolution
```

**The adapter that reports a resolution is the one actually driving the monitor.** Expect a resolution on the iGPU and an empty value on the Arc card.
If it is reversed — monitor plugged into the graphics card — move the cable to the motherboard port. No settings need changing.

Check before benchmarking, so you do not find out halfway through that it is a memory problem:
`Get-CimInstance Win32_PageFileUsage` and look at `AllocatedBaseSize` (in MB).

---

## 7. Three self-checks after install

**① Is the card detected, and how much VRAM**

```
python_embeded\python.exe -c "import torch; print(torch.__version__, torch.xpu.is_available(), torch.xpu.get_device_name(0), round(torch.xpu.get_device_properties(0).total_memory/2**30, 2))"
```

Expected output (B70 · ECC off):

```
2.13.0+xpu True Intel(R) Arc(TM) Pro B70 Graphics 31.16
```

If you see `False`, or VRAM around 27.2 — go back to §2 and check the driver and ECC.

**② Does llama.cpp enumerate correctly**

`llama-bench.exe --list-devices` — the line for your card must read `Vulkan1` or `SYCL0`.
(`llama-bench.exe` must run from its own directory, otherwise `*-impl.dll` fails to load with rc=127)

**③ Is the page file large enough** — this one bites during loading; §6 has the numbers.

---

## 8. When it will not install, read this table first

| Symptom | Most likely cause | Go to |
|---|---|---|
| `torch.xpu.is_available()` is `False` | `+cpu` or `+cuXXX` wheels were installed | §4.1 |
| VRAM reports only 27.2 GB | ECC is on | §2 |
| Runs, but an order of magnitude slower | Vulkan picked the iGPU (`Vulkan0`) | §5 |
| Slower with no error, right after clicking "repair environment" in the launcher | `+xpu` was replaced with CUDA wheels | §3 |
| Behavior changed after updating ComfyUI | The local XPU patch was wiped by `git pull` | §3 / §4.2 |
| Loading fails outright / OOM | Page file too small | §6 |
| The process "silently vanishes" mid-run with no traceback | Not a Python crash — a GPU engine timeout (TDR) killed the process along with it | [`pitfalls.md`](pitfalls.en.md) |

---

## Related

- One-page summary: [`at-a-glance.md`](at-a-glance.en.md)
- Pitfall list: [`pitfalls.md`](pitfalls.en.md)
- Test-rig specs and card identity forensics: [`test-rig.md`](test-rig.en.md)
