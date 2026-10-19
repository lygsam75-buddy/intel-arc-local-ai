**English** · [简体中文](README.zh-CN.md)

# Intel Arc Local AI Handbook

Field-measured local AI on Intel Arc Pro **B50 (16 GB)** and **B70 (32 GB)** —
`llama.cpp` on SYCL, `ComfyUI` for video / image / audio generation, and the power draw behind all of it.

Not vendor documentation. Not a tutorial rewrite.
**Only the configurations we actually ran, and the numbers we actually measured** — with raw logs,
machine-readable data, and a test registry that states what was tested *and what was not*.

> 📖 **This page is the English entry point.** The full documentation (6,400+ lines) is written in
> Chinese — the map is below. Numbers, tables, and code are language-independent, and every number
> here traces back to a file in [`bench/data/`](bench/data/).

---

## Hardware actually tested

| Card | VRAM visible | Bandwidth | INT8 TOPS | TBP | Chip DEV | Board |
|---|---:|---:|---:|---:|---|---|
| Arc Pro **B50** LP 16G | 15.51 GiB | 224 GB/s | 170 | 70 W | `E212` | GUNNIR `SUBSYS_25221EF7` |
| Arc Pro **B70** 32G | 31.16 GiB | 608 GB/s | 367 | 290 W | `E223` | GUNNIR `SUBSYS_27421EF7` |

> ⚠️ **Intel cards are built by board partners (AIB).** Same chip and same model name from a different
> vendor can have a different VBIOS, power limit, memory vendor, and cooling — and may not perform
> identically. We record `DEV` + `SUBSYS` + VBIOS on every record for this reason.
>
> VRAM figures assume **ECC off** (Intel's default; ECC is opt-in via IGS and costs ~4 GB of capacity).

---

## Both cards, one table

| Workload | B50 16 GB | B70 32 GB | B70 vs B50 |
|---|---:|---:|---:|
| LLM decode · Qwen3.6-35B-A3B Q4_0 | 37.6 tok/s | 75.92 tok/s | **2.0×** |
| Video · MiniMax H3, 864×480 · 6 steps | 399 s | 318 s | **1.25×** |
| Image · Qwen-Image 2.1 INT8, 1280×720 | 51.75 s | 10.62 s | **4.87×** |

> **The spread is the point.** One fixed ratio between the two cards does not exist: video is
> *loading*-dominated (both tiers spend 233–275 s on fixed overhead, so the compute gap gets diluted),
> image generation is *compute*-dominated once the model is resident. Quoting a single "B70 is N× faster"
> is how people end up disappointed. **Pick the workload first, then look at the ratio.**

## Headline numbers

### LLM inference — `llama-bench -p 512 -n 128 -r 3`

| Card | Model | Quant | Size | Decode | Prefill | Notes |
|---|---|---|---:|---:|---:|---|
| B70 32G | Qwen3.6-35B-A3B | Q4_0 | 19.41 GiB | **75.92 tok/s** | 1341 tok/s | primary slot ×16 |
| B50 16G | Qwen3.6-35B-A3B | Q4_0 | 19.41 GiB | **37.6 tok/s** | ~425 tok/s | `-ncmoe 8` (experts offloaded) |
| B50 16G | Qwen3.6-35B-A3B | Q3_K_S | 14.30 GiB | **37.99 tok/s** | 590 tok/s | fully resident |
| B50 16G | Qwen3.6-35B-A3B | IQ2_M | 10.73 GiB | **45.99 tok/s** | 552 tok/s | fully resident |

**On 16 GB, changing the quant does not buy speed.** Three quant levels all land in a
37.7 – 46.0 tok/s band: shrinking weights from 19.41 to 10.73 GiB and moving everything into VRAM
buys only **+22%**. The B50 is *compute*-bound at this size, not bandwidth-bound (the fully resident
IQ2_M uses 19% of 224 GB/s). **Pick a quant for quality and VRAM headroom, not for speed.**

### Long context on a ~¥3,499 16 GB card

A 16 GB card runs the model's native **262,144** context, and *allocating* it is nearly free
(**−1.6% decode across a 64× context range**, 10.5 s to load).

What actually costs is how deep the context is *filled*:

| Filled depth (tokens) | 508 | 31,323 | 59,918 | 119,902 | 181,454 | 244,098 |
|---|---:|---:|---:|---:|---:|---:|
| decode tok/s | 44.35 | 30.82 | 24.26 | 17.02 | 13.01 | **10.48** |

Fit (max residual 2.4%): `decode_ms ≈ 22.95 + 0.000298 × depth`. The intercept is a 43.6 tok/s ceiling;
the slope is the cost of attention.

### Video generation — ComfyUI, MiniMax H3

Fixed workload: 864×480 · 124 frames @ 24 fps · 6 steps · fresh.

| | B70 32G | B50 16G |
|---|---:|---:|
| DiT loading | **fully resident** 19,996 MB | **partial** 7,010 MB + 12,985 MB offloaded |
| End-to-end | **318 s** | **399 s** |
| Sampling (steady) | **7 s/step** | **22 s/step** (first step 54 s) |
| Sampling share of end-to-end | 14% | **41%** |

**The two tiers fail in opposite ways** — B70 is *loading*-dominated (fixed overhead 87–95%, so adding
steps costs almost nothing in relative terms), B50 is not (13 GB of weights live in host memory and get
shuttled every step), which flips the whole optimization priority.

**B50 resolution ceiling** (cold single run, 6 steps, 5 s): 864×480 = 283.82 s → **1920×1088 = 2,259.86 s
(37.7 min for a 5-second clip)**. Cost is super-linear in pixels, **exponent p ≈ 1.7**. 1080p is
reachable at 16 GB — it just takes half an hour. **Above 1920×1088 we have no data and give no numbers.**

### Image generation — Qwen-Image 2.1, INT8, same code, same stack

| | B50 16G | B70 32G | Ratio |
|---|---:|---:|---:|
| Steady state (1280×720, 25 steps) | **51.75 s** | **10.62 s** | **4.87×** |
| Sampling | 29 s (1.16 s/step) | 9 s (0.36 s/step) | **3.2×** |
| DiT resident / offloaded | 6,921 MB / **0** | 6,920 MB / **0** | identical |

The entire gap comes from the sampling segment: both cards hold the model fully resident with zero
offload, so this is compute + bandwidth — **not** "16 GB can't fit it".

> 🔴 **A widely repeated claim is a kernel artifact, not the card.** An earlier batch measured INT8 as
> *37% slower* than bf16 on B70. After switching to the `torch212.bmg` kernel with `int8fix`, INT8 is
> **23% faster** — the sign of the result flipped. That batch was measuring the kernel.

### Power — whole-card energy counter, 1 s integration

| | Value |
|---|---|
| Idle | **51.0 W** (fluctuation < 0.3 W) |
| H3 full load | **P90 = 290.3 – 291.1 W** across all five resolutions |
| Peak (1 s window) | 291.5 – 327.1 W (range ceiling 348 W) |
| Do **not** use TBP for cooling sizing | single-task peaks only — **no > 1 h sustained data** |

**Quantization does not change power; it changes time.** INT8 and bf16 share the same 290 W P90,
so the energy saving ≈ the time saving (< 1 percentage point apart). INT8 finishes faster, so each
job spends less electricity — it is not "more power-efficient per watt".

---

## Documentation map (Chinese, 16 files / 6,489 lines)

| # | File | What's in it |
|---|---|---|
| 1 | [`README.zh-CN.md`](README.zh-CN.md) | The full front page (Chinese): every measured number, every tier |
| 2 | [`docs/vram-16gb.md`](docs/vram-16gb.md) | **16 GB tier tuning** — the main tier: quant selection, `-ncmoe`, context |
| 3 | [`docs/server-config.md`](docs/server-config.md) | **Delivery-ready server config** — without `-ncmoe` it is 15× worse |
| 4 | [`docs/slot-comparison.md`](docs/slot-comparison.md) | PCIe slot A/B — slot penalty (−2.9%) is smaller than slot noise (13.9%) |
| 5 | [`docs/test-rig.md`](docs/test-rig.md) | Test platform spec and what must be recorded |
| 6 | [`docs/strata-b50-linux-prep.md`](docs/strata-b50-linux-prep.md) | Reproducing B50 on Ubuntu — disk / kernel / RAM blockers |
| 7 | [`docs/comfyui-capability.md`](docs/comfyui-capability.md) | **Capability matrix**: how big a model fits, video, image — three questions, one page |
| 8 | [`docs/comfyui-h3.md`](docs/comfyui-h3.md) | H3 video: resolution × duration matrix, 32 GB vs 16 GB |
| 9 | [`docs/comfyui-image.md`](docs/comfyui-image.md) | Qwen-Image 2.1 / Krea-2 / Music 3, including the kernel-variant A/B |
| 10 | [`docs/comfyui-power.md`](docs/comfyui-power.md) | **Power and energy** — watts, joules per job, cost and cooling |
| 11 | [`docs/pitfalls.md`](docs/pitfalls.md) | **926 lines of pits**: symptom → root cause → fix |
| 12 | [`docs/test-registry.md`](docs/test-registry.md) | **Test registry** — every test item: status, data location, reproduction entry, predictions vs. actuals |
| 13 | [`bench/README.md`](bench/README.md) | **Measurement definitions** — what makes two numbers comparable |
| 14 | [`bench/logs/`](bench/logs/) | 33 raw `llama-server` logs (path-scrubbed, otherwise byte-identical) |
| 15 | [`bench/data/`](bench/data/) | 207 machine-readable JSON records |
| 16 | [`CONTRIBUTING.md`](CONTRIBUTING.md) | Format required for submitting measurements |

### Most useful single pages, if you only read three

- **"Can this card run X?"** → [`docs/comfyui-capability.md`](docs/comfyui-capability.md)
- **"Why is my server slow?"** → [`docs/pitfalls.md`](docs/pitfalls.md) and [`docs/server-config.md`](docs/server-config.md)
- **"Is this number trustworthy?"** → [`docs/test-registry.md`](docs/test-registry.md)

---

## What was NOT tested

We state the boundary instead of extrapolating into it.

| Not tested | Why |
|---|---|
| **B60 (24 GB) / B65 (32 GB)** | Cards not available — not a single measurement |
| **Dual-card concurrency** | Not run |
| **2560×1440 and above** | Cost too high; video stops at 1920×1088 |
| **Sustained load (> 1 h)** | Single-task peaks only |
| **Vulkan / Strata backends** | SYCL only |

Two historical gaps are annotated rather than back-filled: one B50 864×480 record lost its log to a
later batch (record exists, timing breakdown permanently missing), and the 2026-10-14 B70 image batch
was captured on a **pre-kernel-swap** stack — **do not compare it side by side** with anything after 10-17
(see [`docs/comfyui-image.md`](docs/comfyui-image.md) §0).

---

## Reproducing

```bash
python bench/harness/registry_audit.py        # count / schema / evidence coverage, one command
ls bench/harness/                             # 24 collectors, matchers, and migrators
```

Every record carries `log_evidence` with `status ∈ {annotated, missing, pending}` — so you can tell,
per record, whether its timing breakdown was backed by a log, lost, or never attempted.

Measurement philosophy, in one line: **the number has to be measured on your own machine, and the
negative results get recorded too.**

---

## License

MIT — see [LICENSE](LICENSE). Text may be reproduced freely with attribution.

Author: 林永刚 (Yonggang Lin)
