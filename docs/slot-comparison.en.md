**English** · [简体中文](slot-comparison.md)

# PCIe Slot Comparison: What the Second Slot Costs a Second Card

> One concrete question: a buyer already has one card and wants to add a second Intel Arc.
> The board's second PCIe slot is **chipset-attached x4** — 1/4 of the main slot's bandwidth.
> How much does that cost? Can the card even go there?

Measured numbers only, plus the conditions they hold under. Everything comes from one machine. Model and parameters are fixed below.

---

## 0. The Answer First

**With the right parameters, the two slots show no measurable difference.**

The main slot (PCIe 5.0 x8) and the second slot (PCIe 4.0 x4) differ by **4x** in bandwidth.
At the recommended operating point, `-ncmoe ≥ 8`, matched runs differ by only **−2.9%** (`-ncmoe 8`, the best-sampled setting).
Across the whole `-ncmoe ≥ 12` range the delta swings between **−3.5% – +6.3%** and **changes sign**.
More important: **that delta is smaller than the second slot's own run-to-run spread** (§3.3).
So there is **no difference to detect** — not "a small difference that is real".

**In one line**:

> "Two cards, one per slot. The PCIe spec difference (x8 vs x4, 4x the bandwidth) causes no measurable performance loss.
> What needs tuning is the parameters, not the slot."

**One gap remains.** Every number here measures **each card running alone in its own slot**.
**Whether two cards running inference at the same time interfere with each other — VRAM contention, interrupts, power delivery — is not measured.**
Settling that needs a separate run; see the caveats in §4.

---

## 1. Test Conditions (Do Not Skip)

| Item | Value |
|---|---|
| Motherboard | Gigabyte B850M FORCE WIFI6E |
| Main slot PCIE1 | CPU-attached, PCIe 5.0 x16 (B50 negotiates x8) |
| Second slot PCIE2 | **chipset-attached, PCIe 4.0 x4**, about 1/4 the main slot's bandwidth |
| Card under test | Intel Arc Pro B50 LP 16G (15.51 GiB usable), ECC off |
| Driver | 32.0.101.8976 |
| Backend | llama.cpp SYCL (OpenCL backend at runtime) |
| Model | Qwen3.6-35B-A3B **Q4_0**, 19.41 GiB |
| Fixed arguments | `-ngl 999 -fa on -ctk q8_0 -ctv q8_0 -p 512 -n 128` |
| Variables | `-ncmoe N` (first N expert layers on CPU), `-r` (repeat count), **slot** |

### The Two Groups (the slot is the only difference)

| Group | Configuration |
|---|---|
| **Main-slot group** | B50 alone in PCIE1, `ONEAPI_DEVICE_SELECTOR=opencl:0` |
| **Second-slot group** | B50 alone in PCIE2 (**main slot empty**), `opencl:1` |

> **The conclusion rests on that difference alone.** Which card sits in which slot, and whether another card sits next to it, is not evidence here. The evidence is the matched same-card, same-parameter pairing in §2 and §3.

**Sampling conditions for the two rounds**: the §2 sweep had the B50 in the second slot with another card in the main slot.
§3.1 adds a clean rerun with the B50 alone in the second slot and the main slot empty.
**The two agree at `-ncmoe 8`** (36.66 vs 35.89), so **a neighbouring card is not the source of the difference**.
The clean data in §3.2 is the final set.

> **Which card sits in which slot is not evidence here.** Do not read "the main slot must hold a particular card" as a precondition.
> Whoever buys two cards can place them either way. This page measures the effect of the bandwidth difference itself.

**Key precondition: do not skip `-ncmoe`.**
When VRAM runs short, `-ngl 999` makes llama.cpp offload **whole layers**, shuttling full layer weights back and forth over PCIe.
`-ncmoe N` moves experts only; attention, router and shared experts stay on the GPU, cutting traffic by an order of magnitude.
The second is the real fix at 16 GB. The first is a trap.

---

## 2. PCIe primary/secondary slot throughput gain-loss (first sweep · `-r 1` · decode tok/s)

> Capture state: B50 in the second slot, another card in the main slot. This matches the clean rerun in §3.1 (below).

| `-ncmoe` | Second slot PCIe 4.0 x4 | Main slot PCIe 5.0 x8 | Delta (second slot vs main) |
|---:|---:|---:|---:|
| 4 | 6.08 | 14.87 | **-59.1%** |
| 5 | 8.29 | 19.07 | **-56.5%** |
| 6 | 10.29 | 21.00 | **-51.0%** |
| 7 | 14.61 | 24.83 | **-41.2%** |
| 8 | 36.66 | 37.13 | -1.3% |
| 12 | 29.22 | 34.52 | **-15.4%** |
| 16 | 34.45 | 33.02 | **+4.3%** |
| 20 | 32.74 | 32.49 | +0.8% |
| 24 | 32.55 | 30.62 | **+6.3%** |
| 32 | 29.32 | 29.22 | +0.3% |

**Both slots peak at the same split, `-ncmoe 8`**, and at that point they are level (1.3% apart).

The gap opens at **ncmoe 4 to 7**, where the second slot loses **41%–59%** throughput.

### What This Means

Smaller `-ncmoe` → more experts stay on the GPU → more likely to exceed 15.51 GiB → weights shuttle across PCIe →
**bandwidth becomes the bottleneck**, and x4 at 1/4 of x8 exposes the gap in full (a 41%–59% loss).

`-ncmoe 8` and above → everything that must move moves once, and inference passes only activations (tens of KB) →
**PCIe stops being the bottleneck**, so x4 matches x8 (1.3% apart, inside the noise).

> In one line: **the slot penalty is not a fixed percentage. It is a function of whether your parameters sit in the VRAM spill zone.**
> Tuned right, the second slot costs almost nothing. Tuned wrong, it costs you well over half your throughput.

---

## 3. Clean Rerun and Reproducibility (final numbers)

`-r 1` is skewed by SYCL cold JIT and is not a usable number (see `docs/pitfalls.md` 1.5).
This section uses `-r 3` and **keeps clean samples only**.
The test for a contaminated round is in `docs/pitfalls.md` 1.7 (a run started within 1 minute of killing a large-memory process).

### 3.1 Rerun Setup

The B50 was moved to **the second slot on its own** (no card in the main slot) and rerun, point by point against the main-slot-only configuration.

### 3.2 Matched Pairs (Q4_0 · clean samples · decode tok/s)

| `-ncmoe` | Main slot x8 | Second slot x4 (clean) | Second/main |
|---:|---:|---:|---:|
| 4 | 15.03 | 8.58 (2) | −42.9% |
| 5 | 19.07 | 8.29 (1) | −56.5% |
| 6 | 21.00 | 10.29 (1) | −51.0% |
| 7 | 24.83 | 14.61 (1) | −41.2% |
| **8** | **37.74** | 36.66 (3) | **−2.9%** |
| 12 | 36.49 | 35.22 (2) | −3.5% |
| 16 | 33.02 | 34.45 (2) | **+4.3%** |
| 20 | 32.49 | 32.74 (2) | +0.8% |
| 24 | 30.62 | 32.55 (2) | **+6.3%** |
| 32 | 29.22 | 29.32 (1) | +0.3% |

> The number in parentheses is the count of **clean** independent measurements at that `-ncmoe`.
> Excluded contaminated samples: second slot `-ncmoe 4` = 2.77, `-ncmoe 8` = 25.67, `-ncmoe 12` = 6.00
> (all page-file swap-in; see 1.7).

**How to read it**: past `-ncmoe ≥ 12` the second slot swings between **−3.5% – +6.3%** against the main slot,
**flipping sign** — that is noise, not a systematic loss.

### 3.3 The Decisive Part: the Second Slot's Own Spread Beats the Slot Delta

At the recommended point, `-ncmoe 8`, all clean samples laid out:

| Group | All values | Range/mean |
|---|---|---:|
| Main slot x8 | 37.13 / 37.43 / 37.52 / 37.74 | **1.6%** |
| Second slot x4 | 31.81 / 35.89 / 36.66 | **13.9%** |

**The slot delta is −2.9%. The second slot's own range is 13.9%.**
→ Re-measuring the second slot moves the number **4.8x more** than switching slots.
At that noise level, x4 and x8 **cannot be told apart**.

> That is what "no real loss" actually means:
> **not "a 3% loss is acceptable" but "the slot difference sits inside measurement noise and cannot be measured."**
> The first implies a quantity left to optimise. The second says the quantity does not exist.

### 3.4 A False Signal That Reads as "the Second Slot Is Unstable"

Under `-r 3` the second slot at `-ncmoe 8` once dropped **30%** inside one configuration (36.66 → 25.67).
**That is not a property of the slot.** The cause: **the round started about 1 minute after killing a `llama-server` holding 22.6 GB**
(free memory had just climbed from 0.8 GB back to 24.2 GB), and page-file writeback had not settled.

**The decisive criterion is prefill** (pure GPU compute, almost no PCIe traffic):

| Configuration | `-ncmoe` | prefill | decode |
|---|---:|---:|---:|
| Main slot x8 | 4 | **439.81** | 15.03 |
| Second slot, contaminated | 4 | **28.55** | 2.77 |
| Second slot, clean | 4 | 274.65 | 8.58 |

Prefill fell 15.4x, which only fits **weights not resident, swapped in layer by layer from the page file** — host memory pressure, not link bandwidth.

The other candidate, `SYCL_CACHE_PERSISTENT=1`, is **not** the source either —
with the variable unset the runs still gave 35.89 / 32.80 / 32.50 / 31.66.

---

## 4. Conclusions and Caveats

### Conclusions

1. **The second slot works, and the cost is inside the noise.** At `-ncmoe 8` the main slot reads 37.7 and the second slot 36.7 (a 2.9% gap),
   while the second slot's own repeat range is 13.9% — **the slot difference is not measurable**.
2. **Parameters come first, the slot second.** In the same second slot, `-ncmoe 4` gives 6.08 to 8.58 and
   `-ncmoe 8` gives 36.66 — **a 6x swing inside one slot**. Fix `-ncmoe` before considering a slot change.
3. **`-ncmoe 8` is the optimum for Q4_0 at 19.41 GiB on the B50**, verified in both slots,
   and the parameter that should ship as the default at 16 GB.
4. **A second slot is no reason to change motherboard or platform.** A 4x bandwidth gap produces no measurable loss,
   so a platform migration is not worth it.
5. **Two cards in two slots carry no performance risk** — the PCIe spec difference lands inside the noise.

### Caveats (read these with the numbers)

- **Two cards running inference at the same time, and whether they interfere, is not measured.** Every number here is
  one card alone in its own slot. VRAM contention, interrupts and power delivery under concurrency
  are a separate question and need their own run. **This caveat travels with the numbers.**
- **The second slot repeats worse than the main slot** (range 13.9% vs 1.6%). The direction is "the second slot is more
  sensitive to its environment", but no cause was isolated (sample too small; no conclusion).
- **Below the threshold (`-ncmoe 4–7`) the second slot is worse and less stable**: the main slot read 15.0 twice,
  the second slot 6.08 and 8.58. Weights shuttle in that range, so it is bandwidth-sensitive.
  "The second slot is fine" therefore **holds only with the right parameters**.
- **`-ncmoe 8` crashed once with OOM in the second slot** (not reproduced). On a memory-tight machine
  the second slot's usable VRAM may be harder to satisfy than the main slot's. Give the page file room.
- **Long-context behaviour in the second slot is not measured.** Everything here uses the short-context setting
  `-p 512 -n 128`. Whether that stays insensitive once the KV cache grows has no data.

---

## 5. Reproduce the Numbers

```bash
# main slot (B50 alone in PCIE1)
python bench/harness/scan_ncmoe.py \
  --model <model dir>/Qwen_Qwen3.6-35B-A3B-Q4_0.gguf \
  --bin <llama.cpp>/build/bin \
  --gpu "Intel Arc Pro B50 LP 16G" --driver 32.0.101.8976 --ecc off --quant Q4_0 \
  --device-selector opencl:0 \
  --sycl-path "<SYCL runtime dir>;<oneMKL dir>" \
  --ncmoe 4,5,6,7,8,12,16,20,24,32 --reps 3 \
  --tag b50-16g-ncmoe-scan-pcie5x8 --outdir bench/data

# second slot (B50 alone in PCIE2, main slot empty)
#   same as above with --device-selector opencl:1 --tag ...-pcie4x4

# build the comparison table
python bench/harness/compare_slots.py \
  --tag-a "b50-16g-ncmoe-scan-pcie4x4,b50-16g-ncmoe-fine-pcie4x4" \
  --tag-b "b50-16g-ncmoe-scan-pcie5x8,b50-16g-ncmoe-fine-pcie5x8" \
  --label-a "Second slot PCIe 4.0 x4" --label-b "Main slot PCIe 5.0 x8"
```

> Device indices change with the physical layout. Before running, check
> `<SYCL runtime dir>\sycl-ls.exe` to see which card each `opencl:N` maps to,
> then confirm against `raw_meta.gpu_info` in the finished JSON (both groups here resolved to
> `Intel(R) Arc(TM) Pro B50 Graphics`, not the other card).

> **Filter by model + quant when pairing.** The same batch holds records for Qwen3-VL-4B alongside
> IQ2_M / Q3_K_S ones; quant names can coincide (all `Q4_0`) while the model differs, and
> `-ncmoe` values are not comparable across models. This comparison uses Qwen3.6-35B-A3B only.

## 6. Two Cards at Once: 2× B65, One Model Each (2026-10-23)

> Registry T-11. Concurrency here means **two cards, one job each** — not one job split across two cards,
> because ComfyUI and `torch.xpu` use only the first card and cannot split a job.
>
> The full two-card report — why compute does not double, whether one card can run H3 alone, one B70 versus two B65,
> and the working parameters and pitfall list — is in [`dual-b65-report.md`](dual-b65-report.en.md).

### 6.1 Configuration

| Item | Value |
|---|---|
| Card 0 | GUNNIR B65 32G · CPU-attached x16 · ComfyUI + MiniMax H3 (port 8190) |
| Card 1 | GUNNIR B65 32G · chipset x4 · llama.cpp + Qwen3.6-35B-A3B Q4_0 (port 8099) |
| Pinning | Both sides use `ONEAPI_DEVICE_SELECTOR=level_zero:N` and assert the model name |
| Load | H3 1280×720 · 6 steps · 5 s; Qwen `-p 512 -n 128` · r=3 |
| VRAM | 31.16 GiB usable per card · ECC off · driver 9150 |
| PSU | 850 W (2×200 W cards + CPU peak about 550 W) |

### 6.2 Results

| Case | H3 end-to-end (s) | Per step (s/it) | Qwen decode (tok/s) |
|---|---:|---:|---:|
| Single-card baseline (2026-10-21) | 394.06 | 42.30 | 53.09 |
| Two cards · H3 only (first round of the day) | 501.72 | 42.36 | — |
| Two cards · Qwen resident + H3 running (first round of the day) | 543.31 | 42.37 | — |
| Two cards · Qwen resident + H3 running (warm cache) | **406.29** | 42.41 | — |
| Two cards · both at full load | **417.78** | 42.41 | **50.47** |
| Two cards · Qwen only (card 1 · x4 slot) | — | — | 50.56 |
| Two cards · H3 only (card 1 · x4 slot) | **458.46** (rerun 458.87) | 42.31 | — |

### 6.3 Conclusions

1. **Concurrency works**: with both cards at full load, both sides deliver — H3 end-to-end 417.78 s (+6.0% over one card), Qwen 50.47 tok/s (−0.2% over running alone).
2. **Sampling compute is untouched**: every round ran 42.3 to 42.7 s/it per step, matching the single-card 42.30. The whole difference sits in **fixed per-round overhead** (re-reading the 15 GB text encoder).
3. **The 501 / 543 second first rounds are the price of a cold page cache**, not of two cards: the same configuration returns to 406.29 s once the cache is warm.
4. **The chipset x4 slot costs only 4.8% of decode** (50.56 vs 53.09): weights are fully resident, so decode never touches PCIe.
5. **Video on card 1: 458.46 s steady state**, 42.31 s/it per step against card 0's 42.41 s/it — the sampling phase is identical.
   Subtract sampling and the non-sampling phase is 204.60 s against 151.83 s for card 0 with a warm cache, **52.77 s** more;
   the entire delta sits in the per-round text-encoder reload (both sides show `loads=3 / offload=1` on `fresh` rounds).
   **No single-variable test was run (same card swapped between the two slots), so this is not attributed to PCIe link width.**
6. **Power adds up; the cards do not throttle each other**: both at full load together draw **P90 400.8 W / peak 406.5 W**, and each card's own P90 matches its solo run (§6.6). An 850 W PSU is enough, but budget for the **400 W class on the GPU side**, not 200 W.
7. **Vision Q&A fits alongside**: one card renders video while the other answers questions about an image, with Q&A decode at −0.2% and H3 per step at −0.14% (§6.7).
8. **In one line**: a second card buys **throughput and capacity**, not single-task speed. For speed, buy a faster single card. Add a second card for parallel jobs and larger resident models.

### 6.4 Image Generation: Two Instances, Zero Loss

Two ComfyUI instances (8190 / 8191), one per card, each pinned to its card with its own `SYCL_CACHE_DIR`,
rendering Qwen-Image 2.1 · 1280×720 · int8 · 25 steps at the same time:

| Instance | First round (incl. load) | Steady state, image 1 | Steady state, image 2 | New prompt |
|---|---:|---:|---:|---:|
| Single-card baseline (xpu:0 exclusive) | 34.37 s | 16.20 s | 16.31 s | 16.87 s |
| Card 0 (xpu:0), concurrent | 57.31 s | 16.14 s | 16.18 s | 16.82 s |
| Card 1 (xpu:1 · x4), concurrent | 44.79 s | 16.00 s | 16.05 s | 16.66 s |

- All three steady-state columns land inside **16.0 to 16.2 s**, level with the single-card baseline on both sides — **zero loss from concurrency**.
- **First rounds are not comparable**: both instances load at once and fight over disk and page cache (34.37 → 57.31 / 44.79 s). Compare `resident` instead.
- No power number for this batch: the sampler caught only 2 rounds, `busy_share`=0, and the 45.5 W mean clearly does not match single-card image generation.

### 6.5 Video on Both Cards at Once: Does Not Work (32 GB Memory Wall)

Same two-instance setup, both sides switched to H3 720p · 6 steps · 5 s — **2/2 failed**.

| Item | Result |
|---|---|
| Failure point | After both instances reach `loads=2` (DiT + text encoder loaded) |
| Exit code | `3221225477` (`0xC0000005`, access violation), same code 2/2 |
| Page file peak | 48.7 GB |
| With SYCL cache isolated | Still crashed → **not a cache conflict** |

- One H3 instance needs ≈25 GB of virtual memory (DiT 19.53 GiB + 32B text encoder + VAE); two need about 50 GB.
  This machine's 32 GB of physical RAM plus page file cannot carry it. **This is a memory wall, not a weak GPU.**
- Contrast: image generation (§6.4) needs about 16 GB per instance and fits, so two image instances are no problem.
- **Two cards are not two machines.** On a 32 GB box the limit is one video job plus one light job; two video lines at once needs 64 GB of RAM first.

### 6.6 Power: Adds Up, Does Not Throttle

Two instances, one per card, rendering at the same time, sampled **per card across its whole-card power domain** (1 s interval, `power_probe_multi.py`):

| Case | Card 0 (bus 3 · x16) | Card 1 (bus 16 · x4) | Both cards |
|---|---|---|---|
| Card 0 only | mean 195.6 / P90 205.5 / peak 208.0 W | idle 44.9 W | — |
| Card 1 only | idle 51.3 W | mean 185.7 / P90 200.0 / peak 201.9 W | — |
| **Both at once** | mean 196.1 / P90 **206.0** / peak 208.4 W | mean 190.3 / P90 **201.3** / peak 203.3 W | **P90 400.8 / peak 406.5 W** |

- **No mutual throttling**: at full load together each card's P90 matches its solo run, and render time does not move → the 200 W card limit is each card's own.
- **PSU**: 406.5 W peak on the GPU side, roughly 550 to 600 W with CPU and peripherals. The 850 W unit here (ATX 3.0 / PCIe 5.0) covers it.
- ⚠️ Do not read `power_sampler.py` as two-card power: it samples only Sysman device 0,
  and here dev0 = bus 16 = card 1, so **with H3 on card 0 it reports card 1 idling at 42 to 46 W**.

### 6.7 Vision Q&A Alongside Video: No Regression

Card 1 runs llama-server with `mmproj` (Qwen3-VL-4B · Q4_0 · ctx 8192) while card 0 renders H3 720p.
The Q&A uses an image with **one unambiguous answer** (white ground, a red square, a green circle, a blue square), every round a real run (`cache_prompt: false`):

| Case | Wall clock | prefill | decode | Correct |
|---|---:|---:|---:|---:|
| solo (H3 not running) | 0.72 s | 393.6 to 394.2 tok/s | **115.02 tok/s** | 3/3 |
| H3 loading | 0.75 to 0.90 s | 385.7 to 387.3 tok/s | 114.6 to 115.7 tok/s | 3/3 |
| **H3 sampling (step 2/6)** | **0.76 s** | 389.8 to 394.6 tok/s | **114.79 tok/s (−0.2%)** | 6/6 |

- Same H3 run: `cold` end-to-end **518.59 s**, 42.58 s/it per step — matching 525.73 s / 42.64 s/it when H3 has card 0 to itself.
- **Neither side regresses**: Q&A decode differs by −0.2% (within jitter), H3 per step by −0.14%. This is one card rendering while the other answers questions.
- ⚠️ **Leaving the prompt cache on manufactures false numbers**: repeat the same image and from round 2 the cache hits, giving 0.13 s wall clock and 115 tok/s decode —
  that is a cache hit, not this card decoding that fast. This batch forces a recompute every round with `cache_prompt: false`.
- ⚠️ The vision tower is verified with an image that has **one unambiguous answer**: a wrong or vague reply means mmproj did not really decode (the model will still invent a fluent description).

### 6.8 Context Capacity: Two Cards Buy 3x, Not 2x

Same model (Qwen3.6-35B-A3B · Q4_0 · 19.41 GiB), same KV (q8_0); only `-c` and `--parallel` change.
Two criteria: **it starts**, and **VRAM scales with ctx** — meeting the first alone does not count as fitting (item 6 below).

**One card (1× B65)**

| ctx · token | Starts | Card 0 free | KV used | Note |
|---|---:|---:|---:|---|
| 262144 | ✅ | 9.50 | 3.34 | 4 sessions of 65K |
| 524288 | ✅ | 6.09 | 6.75 | |
| 786432 | ✅ | 3.25 | 9.59 | 3 full-length sessions |
| **1048576** | ✅ | **0.03** | **12.81** | **4 full-length sessions, against the wall** |
| 1572864 | ✅ | 0.16 | 12.68 | VRAM did not grow → not really allocated |
| 2097152 | ✅ | 0.21 | 12.63 | same as above |
| 3145728 | ❌ | — | — | does not start |

**Two cards (2× B65 · `-dev SYCL0,SYCL1 -sm layer`)**

| ctx · token | `--parallel` | `kv_unified` | Starts | Free on both | KV used | Per M token |
|---|---:|---|---|---:|---:|---:|
| 262144 | default | true | ✅ | 18.99 / 19.81 | 5.20 | 20.8 |
| 524288 | default | true | ✅ | 16.16 / 16.98 | 10.86 | 21.7 |
| 1048576 | default | true | ✅ | 10.50 / 11.32 | 22.18 | 22.2 |
| 1048576 | **4 (explicit)** | **false** | ✅ | 13.51 / 14.33 | 16.16 | 16.2 |
| 1835008 | default | true | ✅ | 2.01 / 2.83 | 39.16 | 22.4 |
| 1835008 | 7 (explicit) | false | ✅ | 7.91 / 8.75 | 27.34 | 15.6 |
| 2097152 | default | true | ❌ | — | — | — |
| 2097152 | 8 (explicit) | false | ✅ | 6.07 / 6.90 | 31.03 | 15.5 |
| 2621440 | 10 (explicit) | false | ✅ | 2.33 / 3.17 | 38.50 | 15.4 |
| **3145728** | **12 (explicit)** | **false** | ✅ | **0.19 / 0.22** | **43.59** | **14.5** |
| 4194304 | 16 (explicit) | false | ❌ | — | — | — |

> KV used = total held after the server starts minus 18.32 GiB (measured on one card at the 4096 setting: 19.41 GiB of weights + compute buffers).
> Every row marked as starting actually sent a `/v1/chat/completions` request and got HTTP 200.

1. **The real ceiling on one card is 1M token**: KV takes 12.81 GiB and only 0.03 GiB is left. That is **4 full-length sessions**.
2. **Two cards, default (no `--parallel`) = 1.75M token** (7 full-length sessions), 2.01 / 2.83 GiB free; 2M goes straight to OOM.
3. **Writing `--parallel` explicitly flips `kv_unified` to `false` and drops KV per M token from 22.2 to 22.4 to 14.5 to 15.6 GiB**
   → the ceiling moves from 1.75M to **3M token (12 full-length sessions)**, with 0.19 / 0.22 GiB left.
4. **Single-variable control**: same 1M, same 4 slots, only `kv_unified` differs —
   `true` 40.50 GiB vs `false` 34.48 GiB, **a 6.02 GiB gap**.
5. **So 3x, not 2x**: on one card 18.32 GiB of 31.16 GiB goes to weights and compute buffers, leaving 12.8 GiB for KV;
   with two cards each carries about 9.7 GiB of weights, freeing roughly 42.9 GiB for KV across both.
   **That extra 1x is not more VRAM. It is weights no longer paid for twice.**
6. **The criterion trap: starting is not fitting.** On one card, `-c` at 1.5M / 2M still starts and still answers,
   but VRAM does not grow at all (12.68 / 12.63 vs 12.81 at 1M) → the extra context was **never allocated**, so it does not count.
   **Watch whether VRAM scales, not whether the process comes up.**
7. **The per-request ceiling is still 262144** (the model's training context): 1M / 3M are **aggregate across concurrent sessions**,
   i.e. 4 or 12 full-length conversations held at once. A longer single conversation needs RoPE extrapolation, which this batch did not test.
8. **In one line**: two cards give **3x** the context of one (1M → 3M),
   provided `--parallel` is set explicitly to `ctx / 262144`; left unset it is only 1.75x, and OOM comes sooner.

> Scope caveat: the 12 slots were checked for starting, for VRAM actually held, and for one request answered —
> **12 conversations were never run to full at the same time**, so "12 sessions usable at once" is unverified.

### 6.9 Q8_0 Large Weights: Two Cards Fit, and Layer Splitting Costs No Speed

Matrix B1. Model Qwen3.6-35B-A3B **Q8_0**, weights **34.37 GiB**
(`unsloth/Qwen3.6-35B-A3B-GGUF`, 36,903,140,320 bytes, sha256 `d1a3958…94a59` checked against the upstream lfs.oid).
One card has 31.16 GiB usable — **does not fit**. Two cards have 62.32 GiB — fits.

| Configuration | Where VRAM goes | pp512 | tg128 | vs fastest single card |
|---|---|---:|---:|---:|
| Q4_0 one card (baseline) | 18.32 GiB fully resident | 992.67 | 53.09 | — |
| Q8_0 one card `-ngl 37` | ≈30 GiB on card, about 4 GiB of layers on CPU | 493.07 | **30.83** | 1.00 |
| Q8_0 one card `-ngl 34` | more layers on CPU | 325.83 | 28.45 | 0.92 |
| Q8_0 one card `-ngl 30` | more layers on CPU | 244.32 | 25.24 | 0.82 |
| Q8_0 one card `-ngl 99` | 31.13 GiB on card + about 2.4 GiB on CPU | 405.01 | 12.98 | 0.42 |

> All runs use `-fa on -ctk q8_0 -ctv q8_0 -p 512 -n 128 -r 3`. Decode over three repeats: one card at `-ngl 37` gives 30.79 / 31.20 / 30.51,
> tight. **Prefill scatters widely** (`-ngl 37` over three runs: 373.4 / 534.2 / 571.5), so conclusions rest on decode; prefill is only an order-of-magnitude reference.
>
> 🔴 **The "two cards, 6.37 tok/s" row is gone from the table. It was a capture error**: llama-bench's `-dev` means
> **run once per device** (the record carries `tensor_split: 0.00`), so that 6.37 was **one card — card 1, in the chipset x4 slot** —
> not a layer-split two-card run. llama-bench cannot run two cards as one; two-card numbers need llama-server, as below.
>
> **Real layer-split speed** (llama-server · prompt 19 token / 128 generated / median of 3):
>
> | Configuration | Where VRAM goes | prefill tok/s | decode tok/s | vs fastest single card |
> |---|---|---|---:|---:|---:|
> | Q8_0 one card `-ngl 37` | 30.78 GiB on card, about 4 GiB on CPU | 56.54 | 31.46 | 1.00 |
> | Q8_0 one card `-ngl 99` | 31.14 GiB on card, tail layers pushed to CPU | 6.96 | 13.80 | 0.44 |
> | **Q8_0 two cards `-sm layer -ts 50,50`** | **33.53 GiB fully resident** (17.47 / 16.06) | 59.40 | **35.14** | **1.12** |
> | Q8_0 two cards `-sm layer -ts 70,30` | 33.53 GiB fully resident (24.20 / 9.33) | 61.14 | 36.44 | 1.16 |
> | Q8_0 two cards `-sm layer -ts 85,15` | 33.53 GiB fully resident (29.25 / 4.28) | 62.56 | 37.30 | 1.19 |
> | Q8_0 two cards `-sm row` | fails on load | — | — | ggml assert |

1. **"Does not fit" is not "does not start".** At `-ngl 99` on one card, llama.cpp packs 31.13 GiB into VRAM (0.03 left)
   and puts the remaining ≈2.4 GiB of layers on the CPU — **it still answers** (probe returns HTTP 200). Decode just falls to 12.98 tok/s.
2. **Two cards do fit it**: `-sm layer` puts the whole 34.37 GiB model in VRAM, 17.45 / 16.05 GiB per card,
   with 13.71 / 15.11 GiB free. This is the most direct demonstration of buying capacity.
3. 🔴 **Layer splitting costs no speed** (llama-server): with 33.53 GiB fully resident across two cards, decode is **35.14 tok/s**,
   **1.12×** the fastest fully-resident single-card tier at 31.46, and **2.55×** the single card forced into spill (13.80).
   The three `-ts` settings give 35.14 / 36.44 / 37.30 — the small rise only reflects more layers landing on the faster x16 card,
   **not a cross-card cost**, so cross-card traffic is not the bottleneck. `-sm row` fails on load (an assert in `ggml-backend.cpp:1081`); fine-grained splitting does not work today.
4. **No fully-resident Q8_0 configuration exists on one card** (34.37 > 31.16), so even the fastest single-card tier carries about 4 GiB of CPU layers.
5. **In one line**: on this path two cards buy **it fits, and it is no slower**. To run two models or two sessions at once,
   the right shape is still **one instance per card** (§6.4 image generation at zero loss, §6.7 vision at no regression) —
   that buys throughput. Layer splitting buys capacity. The two do not conflict, but neither makes a **single** task faster.
6. **Scope caveat**: no single-variable slot swap was run, so **this is not attributed to the x4 link**. For reference —
   the same x4 card on Q4_0 alone decodes at 50.56 against 53.09 on x16 (4.8% loss), nothing like the 6.37 once recorded in error.

### 6.10 Where the Data Comes From

- H3, four runs: `bench/data/2026-10-23_h3_1280x720_dual{d1,d4,d4b,d6}.json`
- Qwen, two runs: `bench/data/2026-10-23_b65-32g-q4_0-dual-c1.json` (alone), `...-concurrent.json` (with H3)
- H3 on card 1: `bench/data/2026-10-23_h3_1280x720_dualc1.json`, `..._dualc1b.json` (same config, rerun)
- Image generation, three concurrent runs: `bench/data/2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2{solo,c0,c1}-comfyui.json`
- Power, three cases and four runs: `bench/data/2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3{s0,s1,b0,b1}-comfyui.json`; sampler `bench/harness/power_probe_multi.py`
- Vision alongside video: `bench/data/2026-10-23_dual-a4-vision-under-h3.json` (12 Q&A rounds + one H3 cold run); collector `bench/harness/vision_under_load.py`
- Capture scripts: `bench_f_h3.py` (H3, pinning cards with `--expect-index`) + `llama-bench` (Qwen)
- Context capacity, 24 cells: `bench/data/2026-10-23_b65-32g_q4_0-ctxcap-dual.json`; raw logs `bench/logs/b2_capacity.log` + per-setting `bench/logs/b2_*.log`
- Q8_0 large weights, five runs: `bench/data/2026-10-23_b65-32g-q8_0-{dual-layer,single-spill,single-ngl37,single-ngl34,single-ngl30}-qwen3.6-35b-a3b.json`; raw logs `bench/logs/b1_q8.log` + `ctxcap_b1_q8_{single,dual}.log`
- Bench notes: `bench/notes/dual-b65-prep.md`