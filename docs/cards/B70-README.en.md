**English** · [简体中文](B70-README.md)

# GUNNIR Arc Pro B70 32G

> **¥18,999 · 32 GB VRAM · 608 GB/s · 367 TOPS · 290 W · 32 Xe2 cores**
>
> The only card of the four that **never has to budget its VRAM**: a 35B MoE, 720p images and 1080p video all fit into 31.16 GiB.
>
> **What one minute produces:** chat at **113 tok/s** (6,790 tokens a minute) ·
> one 720p image in **10.6 s** · a 5 s 1080p video in **14 min**.
> **What that costs in power:** one image **¥0.0008** · one 1080p video **¥0.043** ·
> an hour at full load **¥0.20**.
>
> The 32 GB tier B65 stays at ¥9,999 — the price arithmetic is in §9.

---

## 1. Specifications

| Item | Value |
| --- | --- |
| Tested model | **GUNNIR (蓝戟) B70 32G** |
| VRAM | 32 GB physical, **31.16 GiB** usable |
| Bandwidth / INT8 compute | 608 GB/s / **367 TOPS** |
| Power | TBP **290 W**, measured power limit **290 W** |
| Slot | CPU-attached PCIe x16 |
| Driver | **32.0.101.9150** (chat and backend) / **32.0.101.8976** (image and video) |

Picking a quant tier, offloading experts, reloading each round, `DEVICE_LOST` — none of these problems exists on this card.

---

## 2. Five numbers

| What you want to do | Measured on B70 | In plain terms |
| --- | --- | --- |
| Chat with a 35B model | **113.2 tok/s** (Vulkan) | 6,790 tokens a minute, the whole model resident in VRAM |
| Draw a 720p image (int8 · 25 steps) | **10.6 s** | 300 a day, **¥0.24** of power |
| Render a 5 s 480p video (6 steps · 864×480) | **2.5 min** | ¥0.011 a clip |
| Render a 5 s 1080p video (6 steps · 1920×1088) | **14.0 min** | ¥0.043 a clip, ¥0.43 for ten |
| One hour at full load | about **¥0.20** (290 W at ¥0.7/kWh, CSG reference rate) | 10 hours a day, ¥2 |

---

## 3. Chat and text

### 3.1 Baseline performance

`llama-bench -p 512 -n 128 -r 3`, weights fully resident:

| Model | Quant | Size | Decode | Prefill |
| --- | --- | ---: | ---: | ---: |
| Qwen3.6-35B-A3B | Q4_0 | 19.41 GiB | **75.92 tok/s** | 1,341.36 tok/s |

31.16 GiB fits 19.41 GiB, so **the 35B MoE is fully resident — every speed number below depends on that.**

### 3.2 Delivery configuration: Vulkan is 1.50× faster

| Backend | Decode | Prefill | Multimodal first image |
| --- | ---: | ---: | ---: |
| SYCL | 75.23 tok/s | 1,010 tok/s | 7.59 s (cold) |
| **Vulkan** | **113.18 tok/s (1.50×)** | **3,165 tok/s (3.1×)** | **4.15 s (warm)** |

> ⚠️ **The multimodal column is not a like-for-like comparison**: the SYCL 7.59 s is cold (server just started, first image), the Vulkan 4.15 s is warm (same server, same image, follow-up).
> 7.59 → 4.15 mixes "cold → warm" with "SYCL → Vulkan", **so it is not split and no multiplier is given**. The backend gain lives in the decode 1.50× and prefill 3.1× columns only.

Delivery command line: `-c 16384 -n 128 --fit off -ngl 999 -fa on -ctk q8_0 -ctv q8_0`.

Vulkan needs `-dev Vulkan1` — **card 0 in the enumeration is the iGPU**. Unpinned, the work lands on the iGPU silently and the log still looks complete.

**The 1.50× needs the weights fully resident**: offload experts to the CPU and it collapses, at `-ncmoe 8` only **1.05×** is left (Vulkan itself drops 43.3%).
**The 32 GB tier gets this multiplier — VRAM buys it, not the backend.**

### 3.3 Multimodal

Feed it a program-generated image with one correct answer and check the answer itself: **three for three**.
The first image carries a one-time cold-start cost: **7.59 s (cold) → 4.15 s (warm)**. A follow-up on the same image runs at the **0.24 s** level.

### 3.4 Long context

**Not measured.**

### 3.5 The other three at 32 GB: the B70's matchup is the R9700, not the 4500

> ⚠️ **Method first**: the three columns below are **not measured on this machine** — they are vendor datasheet
> specifications (sources and capture dates in
> [`bench/notes/external-32gb-competitors-2026-10.md`](../../bench/notes/external-32gb-competitors-2026-10.md)).
> This page does not put external numbers next to local ones to draw conclusions; it lays out specs and ratios only.
> Prices are October 2026 e-commerce list prices, used as a single basis for cost-effectiveness comparison. **Street prices move with platform discounts — check before ordering.**

| | **Arc Pro B70** (local) | RTX PRO 4500 Blackwell | RTX 5090 32G | Radeon AI PRO R9700 |
| --- | --- | --- | --- | --- |
| Memory / ECC | 32 GB GDDR6 · **ECC needs a manual switch** | 32 GB GDDR7 · **ECC standard** | 32 GB GDDR7 · no ECC | 32 GB GDDR6 · **ECC is Linux-only** |
| Bandwidth | 608 GB/s | 896 GB/s | **1,792 GB/s** | 640 GB/s |
| Power / form factor | 290 W · blower | **200 W** · dual-slot full height | 575 W · triple-slot consumer card | 300 W · dual-slot blower |
| JD price | ¥18,999 | **¥30,999** | ¥52,999 | ¥17,900 |
| Bandwidth per yuan (GB/s per ¥) | 0.032 | 0.029 | 0.034 | **0.036** |
| Bandwidth per watt (GB/s per W) | **2.10 ← lowest of the four** | **4.48** | 3.12 | 2.13 |
| Vendor compute figure | 367 TOPS **INT8** | 1,617 AI TOPS (**FP4 sparse**) | — | 383 TOPS **INT8** |
| Lowest precision | to FP4 | to FP4 | to FP4 | **INT4 only** |

🔴 **The three vendors' TOPS cannot be divided**: Intel and AMD quote **INT8**, NVIDIA quotes **FP4 sparse**. Getting "4.4×" from 1,617 ÷ 367 means measuring with two different rulers.

- **Bandwidth per watt of 2.10 is the lowest of the four**: 290 W is what 32 cores cost. The B65, same capacity and same bandwidth, scores **3.04** ([see `B65-README.en.md` §3.5](B65-README.en.md), which plays a 3.1× price gap against the 4500).
- **Bandwidth per yuan is not competitive either** (see the table above).

**The matchup is the R9700, four numbers within ±6%:**

| | B70 | R9700 | B70 ÷ R9700 |
| --- | ---: | ---: | ---: |
| JD price | ¥18,999 | ¥17,900 | **1.06×** (6% dearer) |
| Bandwidth | 608 GB/s | 640 GB/s | **0.95×** (5% less) |
| Power | 290 W | 300 W | **0.97×** (3% lower) |
| INT8 compute | 367 TOPS | 383 TOPS | **0.96×** (4% less) |

Not one favours us on specs; the difference is **"it runs on a Windows workstation"**:

1. **ECC can be switched on** — the R9700's own spec page reads `Memory ECC support: Yes (Linux Only)`, so **a Windows deployment has no ECC at all**.
2. **It has FP4** — the R9700 goes down to **INT4** only. This page's H3 workflow runs on a 32 GB machine only with the **nvfp4 14.61 GB** encoder tier; on AMD you fall back to int8/int4 software paths, and **that configuration is unmeasured here — no numbers given**.
3. **Two cards work on Windows** — on Win11 the R9700 reports `hipDeviceCanAccessPeer = false`, all cross-card traffic goes through host memory, and tensor parallelism is **2.15× slower than a single card**; in other words, **a second R9700 on Windows adds capacity but not speed**. Dual B-series here measures "layer split +12 to 19%, concurrent dual-card +6.0%".
4. **The full measured set is on this page** — for the R9700 on H3 and image generation, this project has **nothing, and there is no public data either**.

**The 4500 has the strongest foundation** (see the table above), but moving to it costs **¥12,000 more** for **1.47× the bandwidth**, and this workflow **does not consume bandwidth**:

- H3 video measured **24.9 GB/s, 3.9% of spec** (peak 124.2 = 19.5%);
- LLM decode is bandwidth-bound, but **across cards it tracks core count and power, not bandwidth** (the B60 and B65 share a bandwidth figure and differ by core count).

→ **That money buys nothing on video or decode.** For the 32 GB professional-card price comparison, see [`B65-README.en.md`](B65-README.en.md) §3.5.

---

## 4. Image generation

Qwen-Image 2.1 · 1280×720 · 25 steps:

| DiT tier | First round (incl. load) | **Steady state** | New prompt | of which sampling |
| --- | ---: | ---: | ---: | ---: |
| `bf16` | 76.67 s | **13.80 / 13.84 s** | — | — |
| **`int8`** | 52.94 s | **10.61 / 10.64 s** | 11.03 s | **9 s (0.36 s/step)** |

**int8 is 23% faster than bf16** — the opposite of the instinct that quantization only saves VRAM, not time.
It holds only with the right kernel build (`torch212.bmg` kernel + `omni_int8fix`).

| Krea-2 Turbo · 1280×720 · 8 steps | Steady state |
| --- | ---: |
| `int8` | **6.04 s** (three variants 6.04 / 6.04 / 6.07, spread 0.5%) |
| `bf16` | data not converged, no number given |

**Image generation is compute-bound**: once the model is resident, sampling is **78 to 90%** of end-to-end (85% at the int8 tier).
So **step count scales straight through** — 25 steps down to 10 cuts the time by sixty percent.
(Video is the opposite; see §6.)

---

## 5. Music generation

MiniMax Music 3 · 120 s · 30 steps. **DiT quantization is the performance lever; text-encoder quantization is only a capacity lever.**

| Combination | Steady state | Note |
| --- | --- | --- |
| `int8` DiT + `bf16` text encoder | **61.95 / 61.97 / 61.83 s** (spread 0.24 s) | 18,307 MB, fits |
| `int8` DiT + `int8` text encoder | **61.4 to 66.7 s** | 11,145 MB |
| `fp16` DiT + `int8` text encoder | **78.7 s** | 13,445 MB |
| `fp16` DiT + `bf16` text encoder | ❌ **does not fit** | 20,608 MB, past what is usable |

**int8 DiT is 16 to 21% faster than fp16 DiT**; moving the text encoder from bf16 to int8 shifts steady state by only 0.6% and **affects the load phase only**.

---

## 6. Video generation

MiniMax H3 · 6 steps · 5 s (124 frames) · all five resolutions pass · end-to-end incl. loading:

| Resolution | Cold start (first clip) | **Steady state** | Per step | Efficiency |
| --- | ---: | ---: | ---: | ---: |
| 864×480 | 188.8 s | **152.5 s** | 6.64 s/step | 20.2 |
| 1024×576 | 216.5 s | **182.6 s** | 11.45 s/step | 24.0 |
| **1280×720** | 304.2 s | **276.7 s** | 25.30 s/step | **24.8** |
| 1536×864 | 453.6 s | **445.0 s** | 48.86 s/step | 22.2 |
| **1920×1088** | **844.1 s** (14.1 min) | **841.6 s** (14.0 min) | 113.73 s/step | 18.5 |
| 2560×1440 | _not measured_ | _—_ | _—_ | _—_ |

> `Efficiency` = M of "pixels × frames" produced per minute. **Higher is faster.** (Computed from **steady state**.)

**720p is the most efficient tier**; 1080p costs **3.0× the time for 2.27× the pixels**.

**Loading verdict**: at 480p / 576p / 720p the video model is **fully resident** (0 offload);
**partial from 1536×864 on** (offloads 2,932 MB), 1920×1088 offloads **7,564 MB** — the high-resolution tiers are already moving weights.

**Duration axis** (1280×720):

| Duration | End-to-end | Per step | Efficiency |
| ---: | ---: | ---: | ---: |
| 5 s | **276.7 s** (4.6 min) | 25.30 s/it | **24.8** |
| 10 s | **705.5 s** (11.8 min) | 90.54 s/it | 19.0 |
| 15 s | **1,309.8 s** (21.8 min) | 187.98 s/it | 15.3 |

Frames grow 2.919× → per step grows **7.43×**, so **per step against frames is p ≈ 1.87** (steeper than p ≈ 1.78 on the resolution axis).
**That exponent belongs to per step, not to end-to-end. Above 20 s is not measured, so no number is given.**

**Video on this card is loading-dominated, but how many seconds loading costs depends on two conditions**: whether the text encoder sits in VRAM or in host memory, and whether the server is freshly started. Fresh server, clip 1, text encoder in VRAM: **151.0 s**;
moved to host memory: **190.6 s (+26%)**; same server, clip 2: **122.7 s**.

→ **To make this card cheaper, do not restart the service and keep the text encoder in VRAM.**

**Cost is superlinear in pixels**: **p ≈ 1.78** per step (the sampling phase), only **p ≈ 1.07** end-to-end — fixed overhead grows with resolution too and dilutes the exponent.

### How long a clip: duration ceilings at 480p and 720p (one batch · cold start)

MiniMax H3 · 6 steps · one continuous batch · cold start (fresh server, clip 1) · end-to-end incl. loading · default fan curve:

| Resolution | Duration | Frames | Pixels·frames | End-to-end | Per step | Efficiency | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| 1280×720 | 5 s | 124 | 114.3 M | 5.4 min | 25.38 s | 21.1 | pass |
| 864×480 | **50 s** | 1,212 | **502.6 M** | **44.9 min** | 404.70 s | **11.2** | pass · longest at 480p |
| 1280×720 | **24 s** | 583 | **537.3 M** | **50.1 min** | 460.57 s | 10.7 | pass · longest at 720p |
| 1280×720 | _░ 26 s_ | _634_ | _584.3 M_ | _tested · does not fit_ | _—_ | _—_ | does not run |

**Ceilings: 480p ≤ 50 s · 720p ≤ 24 s** (verdicts in the table).
**1080p ≤ 10 s / 1440p ≤ 5 s carry over from the B65 measurements** — those two tiers are set by VRAM capacity, not by compute: B70 and B65 both have 31.16 GiB usable, and 720p·26 s fails on both cards with a **byte-identical** signature (`XPU out of memory. Tried to allocate 2.33 GiB`,
stack at `attention_pytorch → ops.py:63 scaled_dot_product_attention`).

**One scalar holds**: **T ∈ (537.3, 584.3) M** — the criterion is the single quantity pixels × frames, not resolution itself.

> ⚠️ **This table is a different batch from the two above; do not subtract across them.** The same 720p·5 s tier is **17%** slower cold start — end-to-end is sensitive to whether the server is freshly started.

**Power and memory for this tier**: across 480p·50 s, **273.5 W average / 320.1 W peak**; one clip uses **736.9 kJ** (≈ ¥0.14);
peak process commit **85.60 GiB**, and a 96 GB pagefile covers it.

> ⚠️ **Concurrency triggers `DEVICE_LOST`** (seen with llama-bench hitting the card at the same time); run alone and it passes in 44.9 minutes.

**How to choose — three sentences:**

1. **One clip → 720p · 5 s**: efficiency 24.8, the card's highest. 576p is close behind, good for draft batches.
2. **Long video → stitch clips**: a stretched 720p·15 s clip costs **1.58×** the stitched total.
3. **Higher resolution → render at 720p, then upscale**: 1080p directly takes **3.0×** the time; upscale is not measured on this page.

2560×1440 and above: not measured.


---

## 7. Power

Whole-card power-domain energy counters, 1 s window:

| | Value |
| --- | --- |
| Idle | **51.0 W** (variation < 0.3 W, like a light bulb) |
| Video at full load | all five resolutions **P90 within 290.3 to 291.1 W** (1 W apart) |
| 1 s peak | **291.5 to 325.6 W**; music peaks at **327.1 W** |
| Energy per job | 5 s 720p video **58 kJ ≈ ¥0.011**; 5 s 1080p **218.6 kJ ≈ ¥0.043**; one image **≈ ¥0.0008** |

1. **Full-load power does not depend on the job**: 480p to 1080p is 5.04× the pixels, and P90 sits at the 290 W level in both; what changes is the **duty cycle** (32% → 86%). **"Small images save power" is an illusion — you save time, not watts.**
2. **Quantization changes time, not power**: int8 and bf16 share the same 290 W, so power saved ≈ time saved. Not more work per watt.

**Do the math per clip, not per watt.**

Cooling is designed for **290 W sustained + 325 W transient**; use at least a 550 W PSU.

---

## 8. What fits

31.16 GiB of usable VRAM:

| Combination | Resident | B70 |
| --- | ---: | --- |
| Qwen-Image 2.1 int8 (6.9 + 8.7 + 0.6 GB) | 16.2 GB | ✅ fully resident, 0 offload per round |
| Krea-2 int8 (12.6 GB) | 12.9 GB | ✅ fully resident |
| Music 3 int8 DiT + bf16 text encoder | 18.3 GB | ✅ |
| Music 3 fp16 DiT + bf16 text encoder | 20.6 GB | ❌ does not fit |
| H3 video model 19.53 GB | 20.0 GB | ⚠️ depends on resolution: 480p / 576p / 720p fully resident; 1536×864 offloads 2,932 MB, 1920×1088 offloads 7,564 MB |

**Three hard limits:**

1. **Music 3 with `fp16` DiT + `bf16` text encoder does not fit**; drop the DiT to int8.
2. **2560×1440 video is not measured**; do not assume it runs.
3. **`bf16` is unavailable on Vulkan** (Arc's Vulkan reports fp16 only); the Vulkan path for bf16-weight models is unverified.

**Every model tier runs at its highest-precision tier on this card.**

---

## 9. How to choose

| What you care about | Measured |
| --- | --- |
| Fastest image / music | **B70**: same int8 image job, 1.70× faster than B60, 4.87× faster than B50 |
| Fastest chat | **B70** (Vulkan 113 tok/s, 1.32× B60) |
| But 4.87× is not all compute | Part of it is "the B50 does not fit, reload every round" (decomposition on the B50 page §4) |
| Budget under ten thousand | **B65** (¥9,999): same chip, **20 cores**. Chat 53.09 tok/s (0.70×), H3 480p 198.1 s (1.21×), image 16.16 s (1.52×) |
| Cost per tok/s | B70 **¥250**, B65 **¥188** — B70 buys the ceiling itself: 32 cores + 32 GB |

**B70 and B65 are the same chip; B65 has 12 fewer cores, half the price, thirty percent slower.**

---

## 10. Test conditions

> The four-row "how long a clip" table and the 480p·50 s row come from the minimal queue (default fan curve, no concurrency,
> `COMFY_PORT=8190`, `reserve-vram 4`, `--limit-gib 116`); power in that batch averaged 273.5 W (lower resolution, lower duty cycle). Data file `bench/data/2026-10-26_b70-32g-h3-ceiling-tiers.json`.

| Item | Value |
| --- | --- |
| Collection dates | image 2026-10-17 / 10-19; video 2026-10-19; chat and backend 2026-10-20 |
| OS | Windows 11 Pro 26H2 · Build 26300 |
| Software stack | ComfyUI 0.39.0 + `comfy_kitchen` 0.2.37 + XPU provider 0.2.33 + `torch 2.12.0+xpu` |
| llama.cpp | official prebuilt **b11753** |
| Driver | **32.0.101.9150** (chat and backend) · **32.0.101.8976** (image and video) |
| VRAM | ECC off · **31.16 GiB** visible · power limit **290 W** |
| Test machine | Ryzen 5 9600X · B850M · **2×16 GB DDR5-6400 (both slots populated)** · display driven by the iGPU, the whole discrete card left to the model |
| Raw records | [`bench/data/`](../../bench/data/) (every entry carries environment fields: driver, kernel, ECC, usable VRAM) |

Install steps, drivers and patches -> [`../install.md`](../install.en.md); full system configuration -> [`../build.md`](../build.en.md).

---

<sub>MIT · handbook content may be reused freely with attribution. Author: Yonggang Lin · `lygsam75@gmail.com`</sub>
