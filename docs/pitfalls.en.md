**English** · [简体中文](pitfalls.md)

# Pitfalls

Each entry records three things: **symptom → root cause → fix**. Appended continuously.

> Inclusion rule: hit it once, reproduced it, fixed it. Anything not fixed is marked `[unresolved]`.

---

## I. Environment and toolchain

### 1.1 oneMKL version must match the SYCL runtime

**Symptom**: it compiles, then fails at run time with a missing symbol, or crashes outright.

**Root cause**: the oneMKL and SYCL runtime ABIs are pinned together. oneMKL **2026.1 needs sycl9**, while this machine's DPC++ runtime is **sycl8**. Mix them and it breaks.

**Fix**: check the local SYCL runtime version first, then pick the matching oneMKL:

```powershell
# combination measured working on this machine
$mkl   = '<oneMKL directory>'
$dpcpp = '<SYCL runtime directory>'
$env:PATH = "$dpcpp;$mkl\bin;$env:PATH"
```

**Don't**: upgrade the moment a new version appears. Check the ABI mapping first.

---

### 1.2 First SYCL JIT compile on Arc takes tens of seconds

**Symptom**: the first launch hangs for a long time and looks dead.

**Root cause**: SYCL kernels JIT-compile on first run. AOT needs `ocloc`, which is not always present.

**Fix**:

```
SYCL_CACHE_PERSISTENT=1
```

With the persistent cache on, later launches hit it directly. **A slow first run is normal, not a fault** — do not rush to call it a failure.

---

### 1.3 Two runtimes want opposite PATH settings (llama.cpp needs it, torch does not)

On the same machine, **llama.cpp (SYCL) and torch (XPU) want opposite things from `<SYCL runtime directory>`**:

| Runtime | Requirement | Consequence if unmet |
|---|---|---|
| llama.cpp SYCL | **must be on PATH** | exit code `0xC0000005` (access violation), crashes within 1 s, stderr completely empty |
| torch XPU | **must not be first on PATH** | `torch.xpu.is_available()=False`, `device_count=0` |

**Root cause**: that directory ships `OpenCL.dll` + `cl.cfg` + `common_clang64.dll`.
- For torch: this `OpenCL.dll` overrides the system OpenCL ICD, Intel's GPU implementation gets displaced, and only the CPU device survives.
- For llama.cpp: `ggml-sycl.dll` (65.7 MB) is not self-contained; without this directory's DLLs it faults immediately.

**Measured comparison (2026-10-15)**:

```bash
# torch: add it and it breaks
export PATH="<oneAPI install directory>/Library/bin:$PATH"
python -c "import torch; print(torch.xpu.device_count())"   # → 0

# llama-bench: omit it and it breaks (0xC0000005, no output at all)
"<llama.cpp>/build/bin/llama-bench.exe" --version
```

**Fix**: **do not share one shell environment.** Run the two stacks separately.
- llama.cpp: `PATH=<SYCL runtime directory>;<oneMKL directory>;<everything else>`
- torch / ComfyUI: **do not add this directory**

The `xpu_bench.py` harness already encodes this: `--sycl-path` applies only to the
llama-bench subprocess by default and does not leak into the outer environment.

**Lesson**: when debugging "the GPU is not visible" or "the process dies instantly", **remove the environment variables you added and test again**.
Otherwise it is easy to blame hardware or the driver for a fault your own environment created, and waste hours on it.

---

### 1.4 Two Intel cards make llama.cpp crash on P2P

**Symptom**: after installing a second Intel card, llama-bench / llama-cli aborts outright:

```
ur_die: Experimental P2P feature is not implemented for OpenCL adapter.
```

**Root cause**: once SYCL enumerates several GPUs, llama.cpp tries to set up P2P access between the cards,
but the current driver runs the **OpenCL adapter** (not Level Zero), which does not implement this experimental feature.
Note: this has nothing to do with the cards themselves — **the wrong backend** triggers it.

**Fix**: pin to a single card.

```bash
ONEAPI_DEVICE_SELECTOR=opencl:0    # 0 = first card; index per sycl-ls enumeration
```

**Do not use `level_zero:0`** — even though the local SYCL toolchain builds with
`GGML_SYCL_SUPPORT_LEVEL_ZERO_API: yes`, at run time it prints:

```
SYCL GPU device 0 does not use Level Zero backend, disabling Level Zero memory API
```

Selecting a non-existent `level_zero:0` only gets you an access violation.

---

### 1.4b Windows PCIe link-width readings are **fake** on Arc

**Symptom**: you want the system to answer "is this card running at x4 or x8 right now",
and `Get-PnpDeviceProperty` returns **1** for `DEVPKEY_PciDevice_CurrentLinkWidth`.

```powershell
Get-PnpDeviceProperty -InstanceId $id |
  Where-Object KeyName -match 'LinkWidth|LinkSpeed'
# Intel(R) Arc(TM) Pro B50 Graphics
#   CurrentLinkWidth = 1     MaxLinkWidth = 1
#   CurrentLinkSpeed = 1     MaxLinkSpeed = 1     # 1 = 2.5 GT/s, clearly the idle state
```

**Root cause**: the Intel Arc driver does not populate these DEVPKEYs, so Windows can only return the device's idle defaults.
An AMD card in the same machine reads correctly (`16 / 4` = Gen4 x16), which proves the slot is fine —
**the Arc driver simply does not report it**. Reading again under load still returns 1.

**Fix**:
- **Do not** use these DEVPKEYs as evidence of whether a slot is x4 or x8, and do not put them into published write-ups.
- Only two substitutes exist: ① the motherboard spec (PCIE2 is a chipset x4 link);
  ② the **bus number** in `DEVPKEY_Device_LocationInfo` (separates primary from secondary slot, but says nothing about width).
- To actually measure link bandwidth you must run your own host↔device copy benchmark (e.g. `bandwidthTest`).
  **Not done**; see open question #8.

---

### 1.5 Cold SYCL JIT makes llama-bench numbers nearly 8x too low

**Symptom**: same card, same parameters, two runs differ by nearly 8x.

**Measured (B70 · Qwen3.6-35B-A3B Q4_0, 2026-10-15)**:

| Run | Prefill | Decode |
|---|---:|---:|
| `-r 1` (cold JIT) | 43.59 | 9.58 |
| `-r 3` (kernel cache hit) | 1341.36 | **75.92** |

**Root cause**: SYCL kernels JIT-compile on first run. The single sample in `-r 1` includes the compile cost.
The persistent cache from `SYCL_CACHE_PERSISTENT=1` is not shared between the kernel sets of llama-cli and llama-bench,
so switching tools means compiling again.

**Fix**:
- always sample with `-r 3` or more, and average;
- **no single-sample (`-r 1`) number goes into a benchmark table**;
- after changing tool, parameters, or driver, treat the first run as warm-up and discard it.

#### The reverse trap: `-r 1` can also read **high**, not only low

Cold JIT only explains "r=1 reads low". On 2026-10-15 the B50 hit the opposite direction:

| Config | `-ncmoe 8` r=1 | r=3 | Delta |
|---|---:|---:|---:|
| B50 primary slot x8 | 37.13 | 37.43 / 37.74 | +0.8% (normal) |
| **B50 second slot x4** | **36.66** | **25.67** | **−30%** |

Here r=1 was **30% faster** than r=3, and the drop happened **during** the same test run.
(Thermals and power were suspected at the time: a 70 W B50 LP next to a 290 W B70.
**A later re-test showed the 25.67 came from a dirty environment — the real cause is in 1.7** — so the inference itself was wrong.)

→ The rule has to cover both directions: **`-r 1` is neither a baseline (may read low) nor a peak (may read high). Sustained throughput comes from `-r 3` only.** If r=1 is clearly above r=3, that is a fault signal to record, not good news.

#### The second reverse trap: `-r 3` is not enough either — judge **per metric**

`-r 3` fixes the sample count, not the jitter. Within one record, **prefill and decode can have completely different usability**:

| B60 · `-ncmoe 8` · `-r 3`, three samples | prefill tok/s | decode tok/s |
|---|---|---|
| SYCL (`opencl:0`) | 309.5 / 425.7 / 488.2 → **range 58%** | 46.73 / 46.42 / 47.19 → range 1.6% |
| Vulkan (`-dev Vulkan1`) | 328.8 / 430.0 / 636.8 → **range 94%** | 51.71 / 52.67 / 52.37 → range 1.9% |

Decode holds within 2% on the same row while prefill swings 58%–94% (`stddev` 22% / 34%) — the averaged 407.82 / 465.20
**are worthless for comparison**. The mechanism makes sense: with experts offloaded, prefill waits on CPU-side expert weights over PCIe again and again,
and the cache state differs each time; decode is a per-token steady state and hides the effect.

→ Rule: **judge usability per metric, never per record.** Every number in a table must trace back to the range in
`raw[].samples_ts`. If the range exceeds the normal spread for that metric (about 2% for decode here), cite only the stable one
and state plainly in the text "this row reports decode only" — **never carry the prefill number along because decode looks good**.

---

### 1.7 Benchmarking right after killing a large process ruins the numbers

**Symptom**: same card, same slot, same parameters: `-ncmoe 12` produced **6.00** and **35.22**
(5.9x apart); `-ncmoe 8` gave one **OOM crash** and one **35.89**.
It nearly became a hardware conclusion: "the second slot is 32% slower than the primary".

**Root cause**: that round (round 1) started about **1 minute after killing a `llama-server` holding 22.6 GB**
(free system memory had just gone from **0.8 GB** back to **24.2 GB**).
Page-file writeback and the modified page list had not settled, so the 19.41 GiB of weights had to be pulled in from disk again —
the weights were **not resident in VRAM**; they were paged in and out layer by layer.

**The decisive criterion is prefill, not decode**:

| Config | `-ncmoe` | prefill | decode |
|---|---:|---:|---:|
| primary slot x8 | 4 | 439.81 | 15.03 |
| secondary slot (dirty) | 4 | **28.55** | 2.77 |
| secondary slot (clean) | 8 | 371.41 | 35.89 |

Prefill is pure GPU compute and barely touches PCIe. It dropped 15.4x — **that cannot be a bandwidth problem**.
It can only mean the weights were not being fed → memory / page-file pressure.

**Fix**:
- **After killing a large-memory process, wait for page-file writeback before measuring** (rule of thumb: wait until free memory is stable
  and `Win32_PageFileUsage.PeakUsage` stops growing — do not just check "the process has exited").
- **When prefill and decode both fall, check host memory first; do not blame PCIe.**
  Decode down with prefill normal → possibly bandwidth or offload;
  **both down → memory is not feeding the weights.**
- Any "slot X / config Y is suddenly N times slower" claim **must be reproduced at least 3 times** before it goes into a document.
  A one-line "single measurement" disclaimer is enough to ship contaminated data — do not do that.
- Reverse check: compare the slow reading against **fast readings of the same config from history**.
  A 5x gap with no hardware change should be treated as measurement contamination first, hardware degradation second.

---

### 1.6 `llama-bench` has no `-c` / `--ctx-size`

**Symptom**: `error: invalid parameter for argument: -c`

**Root cause**: `-c` / `--ctx-size` is a `llama-cli` / `llama-server` flag.
`llama-bench` takes `-b/--batch-size`, `-ub/--ubatch-size`, `-fitc/--fit-ctx`. Carrying over the cli habit fails.

**Fix**: check `llama-bench --help`; do not write flags from llama-cli memory.

---

### 1.8 "Reproduce 3 times" does not defeat a **persistent** contamination source (`-c 16384` cliff retracted)

**Symptom**: `-c 4096` decoded at **45.2**, `-c 16384` fell to **12.5** (−72%),
and prefill dropped from 42 to 11 at the same time. Three consecutive re-tests were rock stable:

```
-c 4096:  44.72 / 44.21 / 44.93   (range 1.6%)
-c 16384: 12.47 / 12.55 / 12.51   (range 0.6%)
```

By the 1.7 criterion, prefill and decode falling **together** means "memory is not feeding the weights".
It nearly became a hardware conclusion: "a 16 GB card hits a SYCL slow path at 16K context".

**Why the 1.7 discipline did not stop it**: 1.7 requires "reproduce at least 3 times".
That rule assumes **contamination is transient**. This source was a **resident** second
`llama-server` (started by the watchdog, see 3.4), and it steadily took compute from every measurement —
**reproducing 3 times only gives you 3 identical fake numbers.**

**The real criterion — cross-check on an independent code path**:

| Path | `-c 4096` | `-c 16384` | Follows the cliff? |
|---|---:|---:|---|
| `llama-server` (protocol B) | 45.20 | **12.5** | "yes" |
| `llama-cli -v` (same model, same parameters) | 45.25 | **45.40** | **no** |
| `llama-bench -p 512` (default ctx only) | 45.99 | — | — |

Same model, same `-fa/-ctk/-ctv`; `llama-cli` shows **no cliff at all** at `-c 16384`.
Two paths give opposite answers → one of them must be environment-affected, and this is not a property of the model.

**Clean-environment re-test (B50 16G primary slot · IQ2_M · `-ncmoe 0`)**:

| `-c` | 4096 | 16384 | 32768 | 65536 | 131072 | 262144 |
|---|---:|---:|---:|---:|---:|---:|
| decode tok/s | 45.21 | 45.07 | 45.07 | 44.47 | 44.75 | **44.93** |
| prompt tok/s | 43.24 | 44.63 | 42.88 | 41.91 | 42.51 | 43.78 |

**Across a 64x context range decode drops 1.6%, and `-c 262144` (the model's native full context) loads and runs.**
There is no cliff. **The numbers are retracted.**

> A misleading coincidence: if the context **really were filled to 19 × ten thousand tokens**, decode does fall to ≈12 tok/s
> (see the depth-vs-speed curve in [`vram-16gb.md` section D](vram-16gb.en.md)).
> But that probe's prompt was only about 50 tokens — **the depth never went up**,
> so 12.5 can only be an environment problem, not "normal behaviour for deep context".

**Fix (discipline upgrade)**:

- **"Reproduce N times" proves stability, not validity.** A persistent contaminant makes fake numbers equally stable.
- **You need a second independent path**, and each path must be sound on its own.
  This repo has three: `llama-bench` (protocol A), `llama-cli -v` (allocation evidence),
  `llama-server + probe` (protocol B). **When one produces an outlier, check it against the other two first.**
- Run each path **in a fresh process environment** once more; that costs far less than writing down one wrong conclusion.

### 1.9 Windows TDR kills long compute jobs within 2 seconds (the number-one "mystery crash" in AI inference)

**Symptom**: while running a large model, **the process vanishes without warning**. No OOM, no `UR_RESULT_ERROR_DEVICE_LOST`,
no Python traceback — the log stops mid-line during loading or compute, and then nothing.

**Root cause**: Windows **TDR** (Timeout Detection and Recovery) gives the GPU **2 seconds** by default.
Past that it declares the engine hung, grabs a live dump, and kills the process along with it.
A single kernel dispatch or weight load for a large model routinely exceeds 2 seconds — **this is not a bug; the default simply does not suit this workload.**

**Evidence gathering (three steps, in order)**:

```powershell
# ① is there a GPU watchdog dump, and when was the last one
#     ⚠️ the criterion is the timestamp in the FILE NAME, not the event-log TimeCreated —
#     WER flushes a backlog of old reports on some day, so TimeCreated is all flush time
Get-ChildItem "$env:WINDIR\LiveKernelReports\WATCHDOG" -Filter *.dmp |
    Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime

# ② the signature in the event log (LiveKernelEvent, P1 = 141 = video engine timeout)
Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=(Get-Date).AddDays(-7)} |
    Where-Object { $_.Message -match 'LiveKernelEvent' } | Select-Object -First 3 TimeCreated, Message

# ③ confirm stderr was captured — a traceback means a Python-level problem, not TDR
#     (the harness here writes stdout/stderr to one log, so "no traceback" is itself evidence)
```

**Fix**: raise the TDR timeout from 2 s to 60 s ([Intel oneAPI installation guide](https://www.intel.com/content/www/us/en/docs/oneapi-toolkit/installation-guide-windows/latest/gpu-adjust-timeout-detection-and-recovery-setting.html)
recommends "20 seconds or higher" for GPU compute):

```powershell
$k = 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers'
New-ItemProperty -Path $k -Name 'TdrDelay'    -Value 60 -PropertyType DWord -Force
New-ItemProperty -Path $k -Name 'TdrDdiDelay' -Value 60 -PropertyType DWord -Force
# takes effect after a reboot; roll back by deleting both values and rebooting (2 s is the default)
```

**Measured effect** (Arc Pro B70 32G, same ComfyUI, same model, same launch arguments):

| State | 864×480 · 6 steps · 5 s H3 |
|---|---|
| `TdrDelay` = default 2 s | **the process disappears mid-way through loading the text encoder, every time**; the log shows no error |
| `TdrDelay` = 60 s | **3 consecutive rounds completed** (188.81 / 152.54 / 159.62 s), 0 new dumps |

⚠️ **A longer TDR delay mitigates; it does not cure.** A real deadlock only stretches 2 seconds into 60.
If it still crashes afterwards, move to driver (clean WHQL install) / power / reseating the card — do not keep raising the number.

⚠️ **Do not confuse this with "not enough VRAM"**: OOM prints `UR_RESULT_ERROR_OUT_OF_RESOURCES`,
a TDR death **prints nothing at all**. The criterion is "is there a dump + is there a traceback", not a guess.

🔴🔴 **2026-10-21 addendum: the side effect of `TdrDelay`=60 s is a full machine reboot, not a silent reset.**
Two `WATCHDOG-20261021-{1231,1306}.dmp` the same day, both in **H3's VAE decode / write-out stage** (sampling had already finished),
57 s / 28 s later a hard **bugcheck `0x116` (VIDEO_TDR_FAILURE)**; the event log shows
`Kernel-Power 41` + `WER-SystemErrorReporting 1001`, minidumps `102126-{7625,7437}-01.dmp`.
**Read order**: timestamps in `LiveKernelReports\WATCHDOG\*.dmp` (the hang) → the minidump 30 to 60 s later (recovery abandoned).
So "the machine rebooted itself mid-benchmark" is the **expected shape** on a machine with `TdrDelay` raised; count dumps first, do not suspect the PSU first.
⚠️ **Both falls were in the decode stage, not the sampling stage**: `0x116` only proves "some stage did not recover within 60 s";
it **does not imply insufficient compute or insufficient VRAM** (VRAM left before the hang: **6.11 GB**; power sampling was off for this run; P90 across batches 10-19 of the same workload was 290.1 to 290.3 W, never over the 290 W limit).

**Third and fourth the same day (within 90 minutes)**: `WATCHDOG-20261021-1339` → 13:40:11 `0x116` (`102126-8296-01.dmp`, 30 s);
plus one **silent hang with no bluescreen**: the sampling progress bar reached 6/6 and then no further log, `/system_stats` still reachable,
but the worker thread never returned (gave up after 420 s, **no new dump in the WATCHDOG directory**) → **the same workload has two exit shapes**:
the driver reports the hang → 60 s → `0x116` full reboot; or it never reports and the thread simply hangs.

| Event that day | Time | Shape | Stage |
|---|---|---|---|
| 1 | 12:31:34 → 12:32:04 | `0x116` reboot | decode / write-out of case 1 |
| 2 | 13:06:02 → 13:06:30 | `0x116` reboot | decode / write-out of case 2 |
| 3 | 13:30 hang → 13:37 abandoned | **silent hang** (no dump) | sampling finished → decode starting |
| 4 | 13:39:41 → 13:40:11 | `0x116` reboot | service just started, text encoder loading |

🔴 **This is not new today; it is a long-standing problem on this card**: `LiveKernelReports\WATCHDOG` has accumulated
**89 dumps** since 09-22 (16 on 09-23 alone, 18 on 10-06, 14 on 10-17, **0 across three consecutive days 10-18 to 10-20**, 4 on 10-21).
⚠️ **But today is indeed worse than 10-19**: on 10-19 the same H3 workload at five resolutions (**10 decodes**) had **0 hangs**;
today **4 of 16 decodes failed**. So the card is not broken — **one path became fragile today**.

#### Layered run: everything that can be excluded has been excluded (2026-10-21)

After the fifth (`WATCHDOG-20261021-1352` → 13:53:05 `0x116`, `102126-18031-01.dmp`) the approach switched to
**bare torch, layer by layer**: each layer run alone, single process, exclusive card. Conclusion: **this card is stable under generic load.**

| Stress | Volume | Result |
|---|---|---|
| sustained compute (10×4096³ bf16 matmul loop) | 3,848 rounds / 40 s · **152 TFLOPS** | zero jitter; the only 0.065 s max was the first round |
| pageable host→device | 240 × 1 GiB = 240 GiB | 0.19 to 0.30 s, no outliers |
| **pinned** host→device (`pin_memory`) | 1,158 × 512 MiB = 566 GiB | 0.04 to 0.08 s, **≈12 GiB/s (2.4× pageable)** |
| VRAM filled to 26 / 31.16 GiB, then compute + copy | 2,046 rounds + 500 × 0.5 GiB uploads | 0.008 s/round, no outliers |
| 4 GiB allocate / fill / free | 996 times | 0.04 to 0.07 s |

→ **Compute path, copy path (including pinned), high VRAM occupancy, allocator: all four excluded.**
→ Also excluded: ComfyUI code (`site-packages` untouched since 10-14, `custom_nodes` since 10-16, **not one byte changed**),
the H3 model, VAE decode, system memory and page file (64 GB on E:, peak use **536 MB**), disk IO,
the harness scripts themselves, and config knobs (`fast_disk` / `CLIPLoader.device`).

⚠️ **One contamination to record**: from 13:50:35 to 13:50:49 two of my own probes **overlapped for 14 s** on the same card,
and the hang at 13:52:26 falls right after that overlap — **that one does not count as clean evidence**. Re-ran single-process for 150 s; all three stages passed.

#### Scope narrowed to this

Only **ComfyUI running H3** crashes, and three `WER-SystemErrorReporting 1019` entries name
**`igdkmdnd64.sys` (Intel display kernel driver)**. Only two explanations remain:

1. **an XPU custom kernel used by the H3 workflow** (`omni_xpu_kernel`'s int8 convrot convolution / VSA / SLA attention)
   locks the engine on some shape — these kernels have prior form (with CUTE attention enabled, H3 audio packing crashes every time, see `docs/comfyui-h3.md`);
2. driver 9150 has a defect on this path.

**The criterion is one bisection**: same H3 workload, disable the custom kernels one at a time (int8 convrot → bf16 / switch attention backend) and re-run;
whichever stops crashing is it. **Changing the driver (8976 is still a rollback option) comes after the bisection** —
because `driver: 32.0.101.8976` in the 10-19 records is a **back-filled inferred value**; the real driver was very likely already 9150,
so the premise "8976 is clean" does not hold.

⭐ **Reproducible minimal examples live in `_diag_xpu/` (outside the repo)**: `_repro_xpu_hang.py` (pure compute),
`_repro_xpu_highvram.py` (26 GiB occupancy), `_repro_xpu_pinned.py` (pinned), `_probe_xpu_stress.py` (all three combined). After a driver or card change, each layer verifies in 40 to 60 s instead of a 6-minute H3 run.

#### Control after switching to B65: no more crashes, **which does not mean "the B70 is broken"**

**Facts (recomputable)**: the last `0x116` on 10-21 was at **13:53:05** (`102126-18031-01.dmp`); after the card swap there are **no new
`WATCHDOG-*.dmp` and no new minidump** (the last entry in the whole directory is still `WATCHDOG-20261021-1352.dmp`).
From **14:28** B65 ran **7 service batches** back to back — H3 at three resolutions × cold/fresh/cached (**9 decodes**),
Qwen-Image 2.1 images, Krea-2, Music 3 twice (`reserve 4` and `reserve 2`) — **zero crashes, zero reboots**.
The `Device:` lines in the 10-21 logs from 12:26 to 13:30 that morning **are all `Arc(TM) Pro B70`**; B65's logs start only at 14:39
→ **all 4 bluescreens (100%) fall inside B70's time in the machine; the timelines do not overlap and there is no ambiguity.**

🔴 **But "no crash after a card swap" cannot decide "the card is broken"; three counter-arguments all hold**:

| Counter-argument | Detail |
|---|---|
| **The same B70 can finish** | On 10-19 the same H3 at five resolutions (864×480 → 1920×1088) ran **10 decodes with 0 hangs** (`bench/data/2026-10-19_h3_*_b70scan.json`). **A bad card does not finish the same job two days earlier.** |
| **Bare torch passes all four** | See the table above: 152 TFLOPS sustained, pinned 12 GiB/s, 26/31.16 GiB filled, 4 GiB × 996 allocations — **zero anomalies**. No evidence of hardware failure. |
| **Not a single variable** | The two batches where B70 crashed ran single-variable combinations of `fast_disk` / `CLIPLoader.device` (`b70A/B/C/D`), and group D explicitly logged "case 2 timed out during VAE decode"; B65 ran **standard H3 + image generation + music**. **The card changed, and the workload changed too.** |

⭐ **The real value of this control lies elsewhere**: B65 and B70 are **the same BMG-G31 die**, **the same driver 9150**,
**the same `omni_xpu_kernel` int8 convrot / VSA / SLA kernels**; only **Xe2 core count 20 vs 32** and
**power limit 200 W vs 290 W** differ. **Kernels and driver unchanged, cores and power limit changed, no more crashes** →
the scope narrows further to "**some kernel path tied to occupancy/timing**", and **not "an individual card failing"**.
(This also agrees with "B60 has the same 20 cores and has never crashed".)

**The only way to decide whether the card is bad**: put the B70 back and run the four layers in `_diag_xpu/` (40 to 60 s each).
**Pass = the card is fine, continue the kernel bisection; fail = only then may you say the card has a problem.**
Right now only B65 is in the machine: **that test cannot be run, no conclusion given.**

---

### 1.10 The first image-understanding run carries a clear one-off cost; cold and warm must be recorded separately

**Symptom**: same backend, same binary, same process arguments — **two runs back to back differ 2.4× in first-image wall time**.

**Measured (Arc Pro B60 24G · Qwen3.6-35B-A3B Q4_0 + mmproj · `--image-min-tokens 1024` · 640×360 image · 1113 image tokens)**:

| Backend | Cold (that backend's first run on this machine) | Warm (runs 2, 3) | Ratio |
|---|---:|---:|---:|
| SYCL (build 11431) | 17.28 s / 65.21 tok/s | **7.0 / 7.1 s** · 164.3 / 161.8 tok/s | 2.4× |
| Vulkan (build 11753) | 11.34 s / 99.29 tok/s | **4.8 / 4.9 s** · 237.9 / 234.8 tok/s | 2.4× |

**Explanations ruled out**: not the model file's page cache — model load time was identical in both runs (SYCL 19.1 / 19.1 s,
Vulkan 15.1 / 14.6 s); the entire difference sits in the image-encode / prefill phase.
**Mechanism unidentified**: neither log contains a JIT / compile / cache line (compile-time kernel cache is the suspect, with no evidence).
Filed as open, not written as a conclusion.

**Rules**:

1. **Always state cold or warm when reporting first-image time.** Reporting only 17.3 s makes people think Vulkan is that slow too;
   reporting only 4.8 s makes people think it is that fast out of the box.
2. **Compare across cards / backends only within the same state.** There is no warm-state data for B50 (card removed),
   so "B60 warm 7 s" cannot be compared with "B50 cold 103 s" — that would charge a one-off cost to the card.
3. **The backend ratio is nearly identical in both states (cold 1.52× / warm 1.45×)**, so the direction "Vulkan is faster than SYCL"
   is unaffected. Verifying that still requires at least two runs per backend.

**Why this is in the pitfalls list**: the first version wrote "in the cold state Vulkan 11.34 vs SYCL 17.28" into the docs as a backend difference,
while the same backend differed 2.4× between its own two runs — **without the second run you cannot know how much of that gap is warm-up**.

---

### 1.11 Reasoning models get their answer cut off inside the thinking by `-n`, which looks like "vision failure"

**Symptom**: B70 multimodal first round, all 4 groups `content_check.pass = false`, only `red` / `green` hit,
`blue` missing. The record says `status: active`, decode normal, VRAM normal — it reads like "this card cannot do vision".

**Real cause**: `n_predict = 96` was spent entirely on `reasoning_content`; `content` is an empty string and
`finish_reason = length`. The model had in fact already read out "red square / green circle / the third (blue) not finished yet" —
**the third colour sits past the cut**.

**Criterion (all three at once)**:

1. `content` / `answer` both empty;
2. `reasoning_head` non-empty;
3. `finish_reason == "length"`.

**Fix**:

- always add `--no-think` when checking answers (pass `enable_thinking=false` to the chat template),
  so output lands directly in `content`;
- or raise `-n` above 256 (the thinking itself takes tens to hundreds of tokens).

**Two fixes landed (2026-10-20)**:

- `vision_probe.py` `--n-predict` default **96 → 256**;
- when a check fails and the three conditions above hold, write `content_check.reason = "answer_truncated_in_reasoning"`
  automatically and print one explicit line, so a record no longer "sits at FAIL without saying why".

**Lesson**: this kind of record is the most dangerous — **every field present, status active, verdict false**, and nobody suspects the sampling parameters.
Every automated check that can return false must also write a **reason field**; otherwise three months later the only option is to run it again.

---

## II. VRAM and memory accounting

### 2.1 ECC on reserves about 4 GB (a 32 GB card reports only 27.25 GB)

**Symptom**: the card is 32 GB, but programs see only 27.25 GB.

**Root cause**: **ECC is on** on this card.

> ★ **ECC defaults to off in the Intel driver; it has to be enabled by hand in IGS.**
> So 27.25 GB is not "how it ships" — **ECC was turned on on this machine**.
> Conversely: on a new install the card should read "off"; if it reads 27.25 GB, check IGS for ECC first.

**Fix**: turn ECC off (IGS → Graphics → ECC → off → **reboot**) → 31 GB usable.

**Self-check**:

```python
import torch
print(torch.xpu.get_device_properties(0).total_memory)
# ECC off should report ~31.16 GiB (measured 31,920.4 MB)
```

**Note**: ECC affects capacity only, **not compute** (measured difference within 6%; ECC off is slightly faster).
But **record the usable VRAM figure before any performance run**, otherwise records are not comparable.

---

### 2.2 On a 32 GB machine, "add more RAM" is not a solution

**Root cause**: most target users run "8 GB VRAM + 32 GB RAM", and **many machines have only two DIMM slots**, so there is little room to add anyway. RAM prices have little room to fall either.

**Fix**: do not propose "add RAM". At 32 GB, **the model tier decides whether it runs at all**,
and **the page file is the only expandable "memory"** — it is a hard delivery item and must be in the configuration.

---

### 2.3 Arc Pro B50 is rated 16 GB, 15.51 GiB usable

**Symptom**: sizing a model against "16 GB" gives the wrong answer.

**Measured (2026-10-15, torch 2.12.0+xpu, driver 32.0.101.8976)**:

```
xpu:1  Intel(R) Arc(TM) Pro B50 Graphics   15.51 GiB
```

**B50 and B70 scale the same way**: B70 is rated 32 GB and measures 31.16 GiB (ECC off);
B50 is rated 16 GB and measures 15.51 GiB. **Usable capacity is about 97% of rated — ECC off is confirmed** (2026-10-16).
(For contrast: B70 with ECC on loses 12.5% of visible capacity; a B50 with ECC on should read about 13.3 GiB.)

**Fix / discipline**:
- For the 16 GB tier, always size models against **15.51 GiB**, never 16.
- **The first thing after installing a card is to record its real VRAM**; do not use the rated number downstream.
- ECC state needs **no IGS screenshot**; one command reads it: `python bench/harness/gpu_sysman.py` (Level Zero Sysman).
  Note `zes_device_ecc_state_t` has opposite enum numbering across the two generations — **decide from physical capacity, not the enum value** (see 2.3).

**Direct consequence**: Qwen3.6-35B-A3B Q4_0 = **19.4 GiB > 15.51 GiB**
→ on B50 **expert offload (`-ncmoe`) is mandatory**; that is why the 16 GB tier exists as its own topic.

---

### 2.4 `llama-bench` and `llama-server` numbers are not comparable

**Symptom**: same B70, same model: one side reports 75.92 tok/s, the other 39.82 tok/s — nearly double.

**Root cause**: the two timing protocols are fundamentally different —
- `llama-bench`: batched prefill, warmup, `-r` runs averaged, no sampling overhead;
- `llama-server /completion`: one real request, prompt length set by user input, includes sampling and streaming overhead.

The prefill gap is wider (1341 vs 118 tok/s), because bench used `-p 512` as a single batch,
while that server request had only 48 tokens of prompt.

**Fix**:
1. **every benchmark table carries a protocol tag** (`tool` field: `llama-bench` / `llama-server` / `llama-cli`);
2. quote `llama-bench` figures for headline numbers and list server figures separately;
3. before quoting someone else's number, ask which tool measured it.

---

### 2.5 `vram_shared_mb` is **not** the spill amount (when `-ncmoe > 0`)

**Symptom**: B50 16G (15.51 GiB usable) running Q4_0 + `-ncmoe 8` + `-c 16384`:
`xpu_vram.py` reports "shared 3848 MB, **VRAM spilling into host memory**" —
read the old way, that means "3.8 GB already spilled". **But the same config runs at full speed.**

**Root cause**: `-ncmoe 8` **deliberately** moves the first 8 layers' expert weights into `SYCL_Host`.
That is **by design**, not eviction, but it **also counts in `vram_shared_mb`**. The log says it plainly:

```
-ncmoe 0: SYCL0 model buffer size = 18731.34 MiB   SYCL_Host model buffer size =   272.81 MiB
-ncmoe 8: SYCL0 model buffer size = 15195.34 MiB   SYCL_Host model buffer size =  3808.81 MiB
```

The 3848 MB shared at `-ncmoe 8` ≈ 3808.81 MiB of `SYCL_Host` buffer + 39 MB of real spill.
**Reading shared directly as spill turns "no spill at all" into "3.8 GB spilled".**

**Fix (accounting)**:

> **Any spill figure must state three things: the raw `vram_shared_mb`, the `SYCL_Host model buffer size` subtrahend, and the difference between them.**
> Only with `-ncmoe 0` (where `SYCL_Host` is down to ≈273 MiB) is shared approximately equal to spill.

**Real spill after subtraction** (measured 2026-10-16, Q4_0 + `-ncmoe 8`):

| `-c` | shared | minus SYCL_Host 3808.81 | decode |
| ---: | ---: | ---: | ---: |
| 16384 | 3,848 MB | **≈39 MB** | 37.5 (full speed) |
| 32768 | 3,864 MB | **≈55 MB** | 37.57 (full speed) |
| 65536 | 4,206 MB | **≈397 MB** | 26.62 (**−29%**) |
| 262144 | 7,160 MB | **≈3,351 MB** | 10.35 (**−72%**) |

**The part that does not add up is filed as `[open]`**: after subtraction it still differs by 0.8 to 1.4 GB from "the computed overflow over card capacity"
(15881.88 MB usable here vs `SYCL0 model buffer` 18731.34 MiB at `-ncmoe 0`).
Where the gap goes has not been investigated, **no explanation offered**; but "the residual grows in step with the slowdown" is already enough.

**`-v` side effect (found the same round)**: `llama-server -v` writes one log line per token.
Same config with `-v` 35.55 tok/s / without 37.45 to 37.55 tok/s.
**Never take speed readings with `-v`**; open a separate round when you need mechanism evidence.

---

### 2.6 "Steady state" does not mean "the model was never moved": read `offload` first, then the `Unloaded partially` lines

The `first` / `resident` / `newprompt` protocol only says whether a round needs a full load;
**it does not guarantee the model stays put during `resident` rounds**. The real shape can be:

| | B50 16G (15.51 GiB) | B70 32G (31.16 GiB) |
|---|---:|---:|
| DiT residency | 6,921 MB **complete** | 6,920 MB **complete** |
| `offload` in the record | **1 (every round is 1)** | **0** |
| `Unloaded partially` in the log | **3,837.80 MB freed / 5,079.68 MB remains**, 4 times in 4 rounds | **not one line** |
| Non-sampling part of "steady state" | **21.5 to 24.0 s** | **1.6 s** |

Mechanism: 15.51 GiB cannot hold DiT 6,920 + TE 8,709 + VAE 629 MB. **The DiT is indeed fully resident**,
but **the text encoder is evicted 3.8 GB every round and read back from disk** — those seconds all count inside `resident`.
So of that "steady state 51.75 s" only **29 s** is sampling.

**Three criteria; miss one and you report a reload as performance**:

1. **check `samples[].offload` item by item**, not just the average seconds of the sampling rounds; `offload > 0` means something moved that round.
2. **the count of `Unloaded partially` / `Requested to load X` must match the round count**
   (`grep -c "Unloaded partially" log` should equal rounds × 1).
3. **compare `server_sec − sampling_sec` (the fixed part) across cards**:
   for the same workload a 10x gap between two cards is transfer, not compute.

⚠️ **Do not read `DiT resident = complete` as `no transfer needed`.** One workload can hold two or three models
(DiT / TE / VAE); the capacity budget is **per combination**, not just the largest one.

> Pitfall record: README and two docs carried "the ratio comes entirely from the sampling stage: neither card offloads" for a long time,
> because only the `offload 0` on the DiT line was checked. Found on 2026-10-20 by setting three batches of logs side by side (see `test-registry.md` §3).

---

### 2.7 B60 BS SKU needs the power wall pulled to 120% (144 W) to run bf16 — the power wall gates model residency

**Symptom**: B60 BS SKU (factory 120 W wall) running Qwen-Image 2.1 bf16 (22.6 GB): the `first` round runs full speed at 1.30 s/it, but `resident` rounds drop to **45.95 to 46.11 s/it** (~1,244 s/image), shuffling data every step (GPU duty 0%). It looks like it "fits", but ComfyUI unloads the model every round.

**Root cause**: at the factory 120 W wall the GPU is power-starved → sampling slows → ComfyUI's memory manager decides the workload is too heavy → unloads the model between rounds → next round reloads + shuffles during sampling. **Not a VRAM shortage** — on the same card the `first` round runs full speed with the model fully loaded (`full load: True`).

**Fix**: **set the power limit to 120% (144 W) in IGS** and re-run:
- Qwen bf16 steady state **24.3 to 27.5 s/image** (`loads=0` fully resident, GPU duty 80 to 89%)
- Music 3 fp16 DiT + bf16 TE steady state **204.6 to 205.2 s** (`loads=1`)
- P90 pinned at **144 W** (factory-wall batch P90 ≈ 111 W)

**How to verify**:
1. `card_wall.py` reads `defaultLimit` (factory value) — still reports 120000 after the pull; **cannot** use it to verify
2. **Check measured P90 only**: 120 W wall ≈ 111 W, 144 W wall ≈ 145 W
3. `resident` round `loads` values: factory wall `loads=3` (full reload), pulled wall `loads=0~1` (resident)

⚠️ **TF SKU (factory 200 W) has no such issue** — bf16 just runs. BS SKU's 120 W wall is the factory spec; pulling to 144 W is IGS tuning (120%), single 8-pin rated 150 W with 4% margin. See `B60-README` §4.

## III. Processes and background jobs

### 3.1 Long jobs must go through one background command

**Symptom**: starting the service detached (`DETACHED_PROCESS`); as soon as the outer command returns, the process is wiped.
The log stops at one line and it dies silently.

**Root cause**: the child is reaped when the parent exits.

**Fix**: use one script that does **start + run + clean up**, not two commands.

```bash
python run_suite.py --tag b70-6step --shots 4   # internally: start service / wait ready / run shots / clean up
```

---

### 3.2 Foreground commands get SIGTERM after about 120 seconds

**Symptom**: a long test is killed mid-way, with no result.

**Fix**: **run every long test in the background** (background tasks have a task_id, output capture, and a completion notice).
Do not use `nohup` or a trailing `&` to detach yourself; that puts the process outside the task protocol.

---

### 3.3 Without `-u`, outer Python shows no progress in the background

**Symptom**: the backgrounded script looks stuck; the log is blank.

**Root cause**: stdout is buffered.

**Fix**: the outer layer needs `-u` too.

```bash
python -u run_suite.py ...
```

---

### 3.4 The deployment watchdog refills the GPU you just emptied within 15 seconds

**Symptom**: `Stop-Process` kills `llama-server`; the process really disappears and memory comes back,
but a dozen seconds later `Get-Process llama-server` shows a **new PID**, already loading a model.
You think you are running an "exclusive GPU" benchmark; the whole time a 20 GB service is taking VRAM and RAM.

**Root cause**: the delivery install ships a keep-alive script (on this machine
`<deployment directory>\watchdog.bat`, launched by `cmd.exe` / `watchdog_silent.vbs`). Its loop is:

```
every 15 seconds: probe 127.0.0.1:8080
  port serving → do nothing, keep waiting
  port not serving → start llama-server immediately, then wait 45 seconds
```

It **only sees the port, not who you are**. So a casual `Stop-Process` looks like "the service went down" and it gets restarted.
Measured here: kill PID 24048, new process PID 24704 appears within 15 seconds.

**Fix**: do not hard-kill `llama-server`; use the deployment's own stop path —
on this machine `<deployment directory>\stop_model.ps1` (the equivalent of double-clicking the stop-local-model batch file).
It handles three things, none optional:

| Target | Why it cannot be skipped |
|---|---|
| `llama-server.exe` | holds ≈20 GB of VRAM and RAM |
| the `cmd.exe` running watchdog | skip it and the server is back in 15 seconds |
| `wscript.exe` (`watchdog_silent.vbs`) | hidden autostart host; it returns after a reboot |

It also writes a **`model_off.flag`** that marks this stop as "intentional", so the 2-hour health check does not repair it.
**The flag has a 6-hour TTL** — past 6 hours it is treated as "forgot to switch back" (this once hid a real fault for 13.7 hours),
and the health check restarts the service. So watch that window during long benchmarks.

**Discipline for benchmarks**:
- before measuring, confirm there is **no** `llama-server`, **no** `cmd.exe` running `watchdog`,
  and **no** `wscript` host; all three cleared before you start;
- to restore the service afterwards, use the deployment's switch script (here `switch_to_qwen.ps1` /
  the switch-to-Qwen batch file); it clears `model_off.flag`;
- this pairs with 1.7: **1.7 is "cleared but did not wait it out", 3.4 is "never cleared at all".**
  Both present as "nothing changed yet everything got much slower", and in both cases the order is **check host processes and memory first, suspect hardware second.**

> For rigour, the evidence boundary: what this measurement proves is "the watchdog restarts a killed server within 15 seconds".
> Several anomalous reading rounds in the past **did feature an unidentified `llama-server` holding the card**,
> but there is **no process-tree evidence** that this watchdog caused it, so no conclusion is drawn.

---

## IV. Logs and timing

### 4.1 Progress bars contaminate `s/it` sampling

**Symptom**: the parsed `s/it` numbers are clearly wrong.

**Root cause**: the log carries **two** progress bars, **sampling** and **VAE**, in the same format.

**Fix**: take only the one whose total equals the target step count.

```
regex:  (\d+)/(\d+) \[.*\] (\d+\.\d+) s/it
filter: total after the split == target step count
```

---

### 4.2 A failure also returns a "duration"

**Symptom**: the score looks great, but nothing was written to disk.

**Root cause**: a failed render / empty response returns a timestamp just the same.

**Fix**: **every run must check the error count and confirm the output really exists**.
Without that check you are scoring failures as results.

---

### 4.3 Server-side and client-side timing must agree

**Symptom**: `Prompt executed in X seconds` in the report differs a lot from the client stopwatch.

**Root cause**: two timing sources.

**Fix**: capture both; **only when they agree is it a real render**.

#### 4.3b ⚠️ `Prompt executed in …` has two formats; **past 10 minutes it switches format**

**Symptom**: the evidence script reports "no matching log" for the 1920×1088 and 10 s / 15 s video runs,
although the log file is in the directory and the `Prompt executed` line is right there.

**Root cause**: ComfyUI switches to `HH:MM:SS` for jobs **over 10 minutes**, instead of seconds:

```
Prompt executed in 301.75 seconds     ← 5 minutes, seconds
Prompt executed in 00:11:59           ← 12 minutes, hh:mm:ss
```

A regex that only matches `([\d.]+) seconds` **skips the whole line**, so evidence collection fails for every run ≥10 minutes,
and the failure mode is "no matching log" — **it looks like the log is missing when the parser simply cannot read it**.

**Fix**: match both formats, convert to seconds, then compare:

```python
RE_EXEC = re.compile(r"Prompt executed in (?:(\d+):(\d+):(\d+)|([\d.]+) seconds)")
```

**Criterion**: grep the log for `Prompt executed in 00`; a hit means you are on it.

---

### 4.4 `vram_total` is in bytes

**Symptom**: VRAM numbers are absurdly large.

**Root cause**: `vram_total` from ComfyUI `/system_stats` is in **bytes**, not MB.

**Fix**: divide it yourself. Do not print it as MB.

---

### 4.5 `llama-server` default logs carry no allocation info; with `-v` you must **read the second pass**

**Symptom (first layer)**: you want to know "why is it slow", open the `llama-server` log, and the whole file is **38 lines** —
no `offloaded N/N layers`, no `KV buffer size`, no `compute buffer size` — **not a single piece of inference evidence**.

**Root cause**: `llama-server` defaults to verbosity 3
(the log itself says `verbosity = 3 (adjust with the '-lv N' CLI arg)`), and backend tensor allocation details stay hidden.

**Fix**: add `-v` explicitly. Only then do you get:

```
load_tensors: offloaded 41/41 layers to GPU
llama_context: flash_attn            = enabled
llama_kv_cache: layer   0/1/2: filtered             ← linear attention layers, no KV
llama_kv_cache: layer   3/7/11/.../39: dev = SYCL0  ← only 10 of 40 layers carry KV
llama_memory_recurrent: layer 1/2/4/5/6/...: dev = SYCL0
llama_memory_recurrent: layer 3/7/11/.../39: skipped
srv llama_server: n_parallel is set to auto, using n_parallel = 4 and kv_unified = true
```

**Symptom (second layer)**: with `-v` the `buffer size` lines **do** appear, but they are **printed twice in the same log**, and the first pass is all `0.00 MiB`:

```
load_tensors:        SYCL0 model buffer size =     0.00 MiB     ← first pass (dry run), fake
load_tensors:    SYCL_Host model buffer size =     0.00 MiB
llama_kv_cache:      SYCL0 KV buffer size =     0.00 MiB        ← 0 even at -c 262144
...
load_tensors:   CPU_Mapped model buffer size =   333.44 MiB     ← second pass (real load), real values
load_tensors:        SYCL0 model buffer size = 10644.99 MiB
llama_kv_cache:      SYCL0 KV buffer size =  2720.00 MiB        ← -c 262144 = 2720 MiB
```

**The real root cause**: `--fit` (automatic memory fitting) is **on** by default. fit first performs a
**dry-run load**; weights and KV are not actually allocated yet, so the `model` and `KV` buffers — the ones that
**depend on the real allocated size** — report `0.00 MiB`, while `output` / `RS` / `compute` — **computed from the config** — already show real values in the first pass (3.79 / 251.25 / 824.29 MiB).
The dry run is followed by the **real load**, which prints both groups with real values.

**Criterion (three, verified by measurement)**:

1. **`llm_load_tensors` appears twice in one log** — count how many times
   `load_tensors: offloaded N/N layers to GPU` shows up. **2 = fit on**, and the second occurrence is the real one.
2. the log also carries `common_fit_params: successfully fit params to free device memory`
   / `fitting params to free memory took X seconds`.
3. **in `-v` logs, trust the buffer numbers from the "later pass"**. Take the 10-15 batch (fit on):
   `SYCL0 model buffer size = 10644.99 MiB` (IQ2_M) + `KV 2720.00 MiB` (`-c 262144`)
   — these agree with `xpu_vram.py`.

**Contrast (`--fit off`)**: everything on 2026-10-16 explicitly carried `--fit off`;
`llm_load_tensors` appears **exactly 1 time**, there is no `common_fit_params` line,
and the real values print directly: `SYCL0 model buffer size = 15195.34 MiB` /
`SYCL_Host = 3808.81 MiB` / `KV = 170.00 MiB` (`-c 16384`).
**No leading 0.00 pass**, because `--fit off` skips the dry run.

**Fix**:

- **with `--fit off`**: the `buffer size` lines in the log are directly usable — one pass, real values.
- **with fit on (default)**: scroll down to the **second** `llm_load_tensors` and use those numbers;
  the first pass's `0.00 MiB` is a dry run, not "not implemented".
- layer counts, `flash_attn`, `layer N: dev/filtered` — **trustworthy in both passes**.
- if unsure, cross-check with `torch.xpu.get_device_properties(0).total_memory` or `xpu_vram.py`
  (the rule here: log numbers count only when an independent reading agrees).
- **`--fit` is on by default** (direct evidence: not passing it triggers the dry-run pass).
  The default is not visible in `--help`; do not judge from `--help`.

---

### 4.6 `failed to fit params ... abort` is not a process exit

**Symptom**: the log shows

```
W common_fit_params: failed to fit params to free device memory:
  n_gpu_layers already set by user to 999, abort
```

It is easy to read as "startup failed" and go change parameters.

**Reality**: the object of that `abort` is **auto-fit**, not the process.
The lines right after it are `model loaded` + `listening on http://127.0.0.1:8080` — **the service is up**.

**Meaning**: **once the user sets `-ngl 999` explicitly, llama.cpp stops doing automatic layer placement**.
When the weights do not fit in VRAM it will not adjust for you; it puts everything there as instructed and relies on driver-side spill
(WDDM paging VRAM pages into host memory) to "get through" — exactly the cause of the 4.14 tok/s collapse at `-ncmoe 0` in
[`vram-16gb.md` section B](vram-16gb.en.md).

> **Relation to 4.5**: the `abort` line itself shows **`--fit` is on by default** —
> with it off there would be no auto-fit to abort. With `--fit off` the line never appears
> (measured 2026-10-16: no `common_fit_params` line at all in the 10-16 batch).

**Criterion**: on seeing `abort`, read a few lines further and **trust only `model loaded` / `listening`**.
The deployment directory here (`<deployment directory>\watchdog.bat`) uses a bare `-ngl 999`, so this line repeats in its `server.log`
while the service stays healthy.

---

### 4.7 `--api-key` set on the server only → every speed empty, but **everything else normal**

**Symptom (2026-10-16, a wasted round)**: 4 configs started servers in turn, loaded fine, VRAM readings sensible,
no log errors. **Every `decode` field was `None`.**
Opening the records showed every probe was `HTTP Error 401: Unauthorized`.

**Root cause**: `--api-key local` went into the server's launch arguments but **was not passed to the probe scripts**.
The server demands auth; the client sent no credentials. **Loading and VRAM sampling do not go over HTTP at all, so they all looked fine** —
which makes a failure look like success.

**What llama-server actually accepts** (each tried, do not guess):

| Client behaviour | Result |
| --- | --- |
| `Authorization: Bearer local` | ✅ 200 |
| `X-Api-Key: local` | ✅ 200 |
| `Authorization: bearer local` (lowercase scheme) | ❌ 401 |
| `{"api_key": "local"}` in the body | ❌ 401 |
| no credentials at all | ❌ 401 |

**Fix**:
1. when sweeping configs, give `--api-key` **to both server and client**;
2. **make probe failure loud**: `decode: None` does not mean "not measured yet", it means "this round is void"; never read it as 0 or skip it.

---

### 4.8 Reasoning models spend the whole token budget thinking → `content` is an **empty string**

**Symptom**: a multimodal probe sends an image plus a question and gets back `completion_tokens: 96`, normal speed,
normal `finish_reason`, **but `content` is `""`**.
It looks exactly like "multimodal does not work" — the service is fine and the image really was encoded.

**Root cause**: `max_tokens: 96` was consumed entirely by the **thinking phase**, hitting the cap before the answer starts.
(The model this round, Qwen3.6-35B-A3B, has thinking; `message` carries only `content` and `role`,
so the thinking did not even land in `reasoning_content` — it looks like "nothing was answered".)

**Fix**:
1. give `max_tokens` enough room (512 is enough in measurement; with thinking off it answered **using only 9 tokens**);
2. or pass `chat_template_kwargs: {"enable_thinking": false}`;
3. **when reporting speed, check `predicted_n` and whether the answer is empty** — "has tok/s" does not mean "it answered".

---

### 4.9 The same config drifts about ±5% across sessions; do not quote decimals

**Symptom**: same card, same model, same parameters (Q4_0 + `-ncmoe 8` + `-c 16384` + text only),
three sessions gave **35.55 / 37.45 / 37.55 tok/s**. Within-session range was only 0.7 to 3.5%.

**Meaning**:

- **report "about 37 tok/s"; do not quote one decimal place** — the precision is an illusion;
- **ratios are valid only within a session.** A "5% difference" computed across sessions may be noise or may be real;
  you cannot tell. To settle it, put both configs into the same sweep;
- more samples only shrink **within-session** variance; they cannot remove that 5% between sessions.

---

## V. Small scripting traps

### 5.1 `-51.2%` inside Python percent formatting raises `ValueError`

**Fix**: write `%%`.

---

### 5.2 Chinese output on a Windows console

**Fix**:

```bash
PYTHONIOENCODING=utf-8 python -u script.py
```

---

### 5.2b `open(..., newline='\n')` rewrites the whole file's CRLF to LF

**Symptom**: you meant to change a few dozen lines, and `git diff --stat` reports "2,638 insertions / 2,562 deletions";
the whole file turns red and green and the real change is buried.

**Root cause**: the repo's `.md` files are **CRLF** (Windows), and the script says

```python
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)   # ← converts the whole file to LF
```

`newline='\n'` does not mean "keep as is"; it **forces every newline to be written as LF**.

**Fix**:
- always edit text with an editor tool (which preserves line endings); do not rewrite the whole file from a script;
- when a script must write, read the original bytes first to detect the line ending, and restore afterwards with
  `b.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')`;
- **check `git diff --stat` immediately after writing**: a line count far above the change size means the line endings were rewritten; do not wait until after the commit.

Same family: `json.dump` writes no indent or newlines by default, turning a human-readable diff into a single line — same problem.

---

### 5.3 PowerShell tools echo no stdout in some environments

**Fix**: write with `Out-File` and read the file back; do not expect to see the output directly.

---

### 5.4 Git Bash coreutils may be incomplete

**Symptom**: `dirname` / `head` / `ls` report command not found in Git Bash.

**Fix**: write file scans and commands as Python scripts; do not depend on shell tools.

### 5.5 Filtering records by filename **silently drops a whole batch**

**Symptom**: the audit script reports "power summary 6/102" when there should be 13 entries.
Evidence coverage is chronically undercounted too — with no error at all.

**Root cause**: the filter was written as a filename substring match:

```python
comfy = [f for f in files if "comfyui" in os.path.basename(f)]   # ❌
```

Video-domain records are named `<date>_h3_<WxH>_<marker>.json`, **which contains no "comfyui"** —
27 records were never visited by the audit script, and the missing `timing_breakdown` went unnoticed.

**Fix**: **filter by content, not by filename**:

```python
if json.load(open(f, encoding="utf-8")).get("schema") == "comfyui-xpu-bench/1":
```

**Criterion**: when "a script's count is smaller than expected", count the `glob` hits,
then count the content-filtered hits; if the two differ you are on it.
The same mistake appeared twice elsewhere (evidence script, migrator) — **remember, a filename is only a hint**.

### 5.6 Migrator "dry-run passed" ≠ "migrated"; source files starting with an underscore are skipped by glob

**Symptom**: three batches of finished data (B70 five resolutions, B70 TDR verification three buckets, B50 864×480)
are nowhere in the repo, yet it felt like they had been "migrated".

**Two independent causes, both silent**:

1. **only looked at the dry run, never ran it for real**. The dry run prints a per-item comparison table that looks exactly like a real run,
   it just **does not write files**. Days later, scrolling terminal history, you conclude it was already in the repo.
2. **the source filename starts with `_`** (`_h3_864x480_ok_cold.jsonl`, tagged by hand as "keep this tier aside"),
   and the migrator's glob is `*.jsonl` — no match, **no error, one file silently unprocessed**.

**Fix / discipline**:

- the migrator must print **"source N → written M"**; if the two numbers differ, stop and investigate;
- for any script with a dry run, **run it for real immediately after the dry run**; do not treat the dry run as the finish line;
- after migrating, do a **traceable check**: take every timing value in the source jsonl (e.g. `server_sec`)
  and **compare sets** against `samples[].server_sec` in the repo; every item in the difference must be explainable
  (a smoke test? a voided batch? or a real miss?).

```python
# criterion: timings present in the source but absent from the repo, listed one by one
src = {round(float(r["server_sec"]), 2) for r in map(json.loads, open(src_jsonl))}
dst = {round(float(s["server_sec"]), 2) for f in glob("bench/data/*.json")
       for s in json.load(open(f))["samples"] if s.get("ok")}
print(sorted(src - dst))
```

### 5.7 One field written in two shapes is harder to chase than a missing field

**Symptom**: the stats script raises `AttributeError: 'str' object has no attribute 'get'`.

**Root cause**: the `log_evidence` field — one script writes a **bare string** (a paragraph of evidence notes),
three others write a **`{status, note}` object**. Reading it with `obj.get("status")` blows up.

It is harder to chase than a missing field because the data **looks present**: non-empty checks all pass,
coverage reports 100%, and it only explodes when you actually read a subkey.

**Fix**: one field, one shape, across the whole repo. Standardise on `{status, note}`,
with `status` from a closed set (`annotated` / `missing` / `pending`),
and the prose moved into `note`. During conversion, **move shape only, never content**, and verify item by item
that "nothing differs except this field".

**Criterion**: before writing any cross-record stats script, run a **shape census**:

```python
c = collections.Counter(type(json.load(open(f)).get("log_evidence")).__name__
                        for f in glob("bench/data/*.json"))
```

Two or more type names in the `Counter` means there is a trap.

### 5.8 A "pending backfill" state must be able to turn into "cannot be filled"

**Symptom**: a record's status sits at `pending` ("waiting for the evidence script") forever,
while its logs were long since overwritten by later batches — readers keep assuming "one more run will fill it".

**Root cause**: when the evidence script cannot find the log it **returns without writing anything**, so the initial state
written by the migrator is never updated.

**Fix**: when the evidence script finds "**there were rounds that succeeded, but the logs are not in the given directory**",
it writes status `missing` and states in the note that "the timing breakdown is unavailable, without pretending evidence was collected";
records where no round succeeded are left alone (empty evidence is correct for those).

Downstream auditing accordingly **stops reporting `missing` as "should have been backfilled but was not"** —
it cannot be filled, and repeating the warning makes people think clearing the alert is just one more run.

---

## VI. Backend notes

### 6.1 Numbers from different backends are not comparable

SYCL / Vulkan / HIP / IPEX decode speeds differ widely. **The same parameters on a different backend is a new record**;
it must not overwrite the old one — the two have to be visible side by side.

How wide the gap is: same Arc Pro B60, same llama.cpp build 11753, same delivery command line,
**Vulkan 85.59 vs SYCL 51.79 tok/s (1.65×)** (`server-config.md` §8).
So "which backend" matters more than almost any parameter; **always name the backend when reporting a number**.

Three practical notes:

1. **On Vulkan the 0th enumerated device is not your card**. Here `Vulkan0 = AMD Radeon(TM) Graphics`
   (iGPU, `uma: 1`, reports a fake 16,185 MiB) and `Vulkan1 = Intel Arc Pro B60` (24,382 MiB).
   You must use `-dev Vulkan1`, and **run `--list-devices` to check the name every time you swap cards** — enumeration order is decided by the driver,
   and picking the wrong card still gives a complete log and plausible speeds.
2. **`ONEAPI_DEVICE_SELECTOR` means nothing to Vulkan**. Its only effect is to add a field to the record that
   "looks like a card was selected when this backend does not read it at all".
3. **Only the same build is comparable**. llama.cpp changes kernels every nightly; comparing backends across versions folds the version difference into the backend difference.
   The baseline here is the official prebuilt build 11753 (commit `d8d92973c`).
4. 🔴🔴 **A backend ratio is not an intrinsic property of the backend**; it moves with two things: **whether it fits**, and **which card**.
   - Whether it fits: B60 `-ncmoe 0` is 1.65×, `-ncmoe 8` only **1.12×**; B70 is 1.51× → **1.05×**;
     **B50 measures 1.10×, and with `-c` at 65536 it inverts to 0.64×** (Vulkan spills 408 MB more and drops 59%, SYCL spills 432 MB more and drops only 29%).
     On B60, Vulkan with experts offloaded decodes **bit-for-bit the same as SYCL with experts resident**.
   - Which card: B50 **1.22×** → B60 **1.65×** → B70 **1.50×** (decode is not monotonic in core count),
     while prefill rises monotonically with cores **2.59× → 2.93× → 3.13×**.
   - Which workload: on the same "does not fit" B50 config, **the first image in image-to-text is 8.4×** (Vulkan 8.95 s vs SYCL 75.46 s),
     while decode is only **1.17×**. **Ask which workload before switching backends.**
   → Any "how much faster is the other backend" claim must state **which card + which VRAM tier + which phase**.
   On a card that cannot hold the model, budget 1.05 to 1.12× for this optimisation, not 1.65×.

### 6.2 How fast Intel support arrives

Upstream (llama.cpp / vLLM / ComfyUI / new inference engines) is generally slow to support Intel officially.
When "a new model or engine does not mention Intel", first check for a community fork, or build it yourself.
**This is normal, not an anomaly.**

---

## Open questions

| # | Question | Status |
|---|---|---|
| 1 | Real-world behaviour of the llama.cpp Vulkan backend on Arc Pro (vs SYCL) | **`[resolved · B60]` 2026-10-20**: same build 11753, delivery config **85.59 vs SYCL 51.79 = 1.65×** (llama-bench 1.68×, prefill 2.93×, multimodal first image 1.52×), see `server-config.md` §8. ⚠️ **Spill volume is not the cause** (3,862 MB loses 9.9% vs 390 MB loses 40%). **B70 32G measured (2026-10-20)**: delivery **113.18 vs SYCL 75.23 = 1.50×**; llama-bench 115.56 vs 75.97/77.11 = 1.51×, prefill 3.13×, warm first image 1.83×. 🔴 **The ratio follows core count, not bandwidth**: **B65 32G measured (2026-10-21, `llama-bench` only)** — Vulkan 2013.51/89.27 vs SYCL 670.06/53.09 = decode **1.68×**, prefill **3.00×**; B65 and B60 both have 20 cores → identical ratio (1.68×), while **B65 and B70 share 608 GB/s yet land on opposite sides**. 🔴 **The old inference in §8.6 — "decode is bandwidth-bound and Vulkan already saturates bandwidth on B60" — is refuted by B65** (B60→B65 bandwidth +33%, both backends' decode moved only 2%). See `server-config.md` §8.6 — **do not read one card's ratio as "Vulkan's capability"**. 🔴 **1.5 to 1.65× only holds with weights fully resident in VRAM**: at `-ncmoe 8` B60 keeps 1.12× and **B70 only 1.05×** (Vulkan itself loses 43.3%, SYCL only 17.9%) → **on a card that cannot hold the model (16 GB tier), switching to Vulkan is worth 5%–10%**. ⭐ **B50 16G measured 2026-10-22 (build 11753 · driver 9150)**: IQ2_M fully resident **57.78 vs 47.38 = 1.22×** (prefill 2.59×); Q4_0 `-ncmoe 8` **39.75 vs 37.70 = 1.05×**; delivery command line c16384 **41.81 vs 38.08 = 1.10×**, **c65536 inverted 17.25 vs 26.88 = 0.64×**, vision tower **41.83 vs 31.90 = 1.31×**. 🔴 **Multimodal is a different matter: warm first image 8.95 s vs 75.46 s = 8.4×** (image prefill 8.65×, answers 4/4 PASS; the two SYCL records on 10-16 are 102.93 / 114.24 s, reproduced). 🔴 **"The ratio follows core count" is void**: the 16-core B50 is only 1.22×, and ordering the four cards by "cores ÷ bandwidth" is inverse-monotonic with the ratio (0.071→1.22, 0.053→1.52, 0.044→1.68, 0.033→1.68) — **n=4, and B50 also changed quantisation tier, so read it as an ordering observation only**. **Remaining**: B65 was measured with `llama-bench` only, **the delivery command line is untested**; on Arc, Vulkan reports `bf16: 0` / `fp4: 0`, bf16 weight models unverified |
| 2 | Optimal split point for MoE expert offload on the 16 GB tier (`-ncmoe`) | **`-ncmoe 8`** (Q4_0 19.41 GiB, identical across both slots). **Knees for other quantisation tiers are in `docs/vram-16gb.md` section B** (IQ2_M / Q3_K_S measured; the knee moves with weight size) |
| 3 | Recommended page-file size at 32 GB RAM + B50 16G | `[unresolved]` to be measured |
| 7 | B50 second slot: r=3 differs from r=1 by 30% on the same config | **Measurement contamination**; the real cause is page-file paging (see 1.7). Conclusion: **the slot difference −2.9% is smaller than the secondary slot's own reproduction range 13.9%** → x4 and x8 are **statistically indistinguishable** (see `slot-comparison.md` §3.3) |
| 4 | Strata's Windows path on Arc (no official support; WSL2 cannot see the card either) | `[unresolved]` |
| 5 | `sycl-ls` in a clean environment still lists only `opencl:*` with no Level Zero, while `torch.xpu` sees 2 cards → the local SYCL toolchain is probably missing the PI Level Zero plugin; **llama.cpp SYCL may have been running the OpenCL backend rather than Level Zero**, and if so the B70's 42.45 tok/s still has untapped headroom | **`[partially resolved]` 2026-10-20**: with the official b11753 prebuilt **both work** — `opencl:0` reports 23,894 MiB / decode 52.25, `level_zero:0` reports 24,382 MiB / decode 50.69, **3% apart** (opencl slightly faster). So "llama.cpp SYCL only sees OpenCL" is false; the two selectors reach different runtimes (different visible VRAM proves it), but **the speed difference is not enough to be headroom**. ⚠️ The observation "`sycl-ls` lists only `opencl:*`" is itself **unexplained** (it does not contradict the results, so not seeing it in `sycl-ls` does not mean llama cannot use it) |
| 6 | Current ECC state on B50 | **ECC off**. Level Zero Sysman evidence (`gpu_sysman.py`) gives `EccAvailable=true` / `EccConfigurable=true` / `currentState=2`, `pendingAction=NONE`; the enum numbering is inverted between the two generations so it is not used for the verdict — **judge from physical capacity** (visible 15881.88 MB / rated 16 GB = the off side; on should read ≈13.3 GiB). Consistent with "off by default, must be enabled by hand" |
| 8 | **Host↔device real bandwidth** for primary vs secondary slot has never been measured directly (Windows PCIe DEVPKEY is unusable on Arc, see 1.4b). Currently "secondary slot = x4" rests only on the motherboard spec, with no self-measured data | `[unresolved]` to be measured. **Level Zero `zesDevicePciGetState` also returns nothing here** (all 0 / `status=UNKNOWN`); only the capability value from `zesDevicePciGetProperties` (Gen5 x8) is available → the negotiated width really is unreadable; only a measured bandwidth will do |
| 9 | `-ncmoe 8` crashed once with OOM in the secondary slot (not reproduced). Is allocation failure more likely in the secondary slot on memory-tight machines? | `[unresolved]` to be re-tested |
| 10 | The deployment watchdog (`watchdog.bat`) starts `llama-server` during benchmarks and takes the GPU (mechanism in 3.4, proven to revive within 15 seconds). Whether past anomalous readings were affected **has no process-tree evidence, so no retrospective conclusion** | `[mechanism located]` stopping must go through `stop_model.ps1`; the flag expires after 6 hours |
| 11 | Context ceiling on the 16 GB tier (how large `-c` can go, how much deep context costs in decode) | See [`vram-16gb.md` section D](vram-16gb.en.md): `-c 262144` loads and runs, and **`-c` from 4096 to 262144 costs only 1.6%** (context **allocation** is free). The real cost is in **actual depth**: decode falls roughly linearly with depth. **Boundary condition**: this "free" holds only for tiers where **the weights fit**; on Q4_0 (which relies on `-ncmoe` offload), `-c` from 16384 to 262144 costs **72%** of decode (see `vram-16gb.md` D.5) |
| 12 | The "72% cliff" at `-c 16384` | **Not a `-c` effect**: it does not reproduce in a clean environment; it was resident-process contamination (see 1.8); the same config never showed a cliff on the `llama-cli` path |
| 13 | Measured q8_0 KV is **1.35 B/value**, **24%** above the textbook 1.0625 B/value (f16 measures 2.08 B/value, matching theory) | `[unresolved]` mechanism unclear. **Budget VRAM with the measured 13.5 KiB/token, not the theoretical value** |
| 14 | Measured total occupancy at `-c 262144` exceeds "weights + KV formula" by about **1 GiB**, and part of that **grows with context** (the large-context slope is above the 13.5 KiB/token of small contexts) | `[unresolved]` suspected compute buffers / recurrent state; not located |
| 15 | Windows allows **VRAM oversubscription**: exceeding it does not OOM; the driver pages and speed falls (spilling 2,332 MB → 58% drop). So "15.51 GiB usable" in `docs/test-rig.md` is a **soft limit**, not a hard one | `[confirmed]` see [`vram-16gb.md` sections C/D](vram-16gb.en.md). **Criterion: prefill and decode falling together = spill** |
| 16 | Install state recorded in `docs/test-rig.md` (which card in which slot) | `[not used as evidence]` "which card sits in which slot" is not used as evidence for any conclusion here. Slot conclusions come only from the "same B50 in the primary vs the secondary slot" control |
| 17 | `vram_shared_mb` cannot be read directly as spill (with `-ncmoe > 0` it includes expert weights deliberately placed in `SYCL_Host`) | `[accounting fixed / gap unresolved]` subtraction rule in 2.5: **a spill figure must state the raw shared value + `SYCL_Host model buffer size` + the difference**. After subtraction it still misses "over card capacity" by 0.8 to 1.4 GB, `[unresolved]`, no explanation offered |
| 18 | `-ncmoe 0` differs **2.6×** between two protocols: `llama-bench` (`docs/vram-16gb.md` section B, `load_mode=auto`) = **4.14**; `llama-server` (with `-lm dio`) = **10.71** | `[unresolved]` suspected to involve `-lm dio` (with full-layer offload, mmap pages get evicted and disk reads continue), **unverified**. When quoting "how bad `-ncmoe 0` is", give both numbers |
| 19 | `-c 32768` (37.57) is 5.7% faster than `-c 16384` (35.55), above each one's within-session range (1.9% / 3.5%) | `[treated as session variance]` in repeat experiments 16384 also reached 37.45 / 37.55 → more like between-session variance (4.9), **no mechanism found at the `-c` level** |
| 20 | With `--mmproj` attached, **text-only** prefill drops from 42.93 to 27.94 (**−35%**) while VRAM grows only +204 MB | `[unresolved]` suspected extra vision-tower nodes in the graph, mechanism unclear. "Attach it and it drops" is measured |
| 21 | The same delivery config differs 2.3× between two machine states (secondary slot x4 + 5.2 GB free → 2.47 tok/s; primary slot x8 + 20.9 GB free → 5.76 tok/s) | `[unresolved]` slot and free memory **change together**, so no attribution is possible. When quoting a ratio, always use the primary-slot / plenty-of-memory figure (see `server-config.md` §1) |
| 22 | The **default value** of `--fit` on this build | **`--fit on` by default**. Evidence: without `--fit`, `llm_load_tensors` runs **twice** and `common_fit_params: successfully fit params to free device memory` appears (see 4.5); with explicit `--fit off` it runs once with no such line. **The default is not visible in `--help`; do not judge from it.** Whether the `abort` in 4.6 and the `watchdog.bat` comment (fit clamps `-c` back to 16384) still hold in this version is `[unresolved]` |
| 23 | Image understanding **first image** carries a one-off cost: two back-to-back runs on the same backend differ **2.4×** (B60: SYCL 17.28 → 7.0 s, Vulkan 11.34 → 4.8 s), mechanism unidentified | `[unresolved]` model-file page cache ruled out (load time identical in both runs), no JIT/compile/cache lines in the logs. **Accounting rule fixed** (see 1.10): first image must be split cold/warm, cross-card comparison only within the same state. ⚠️ Also unresolved: no warm-state data for B50 (card removed), so B50 vs B60 first images can only be cold vs cold |
