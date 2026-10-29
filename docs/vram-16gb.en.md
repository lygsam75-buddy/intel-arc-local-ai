**English** · [简体中文](vram-16gb.md)

# The 16 GB tier (Arc Pro B50): parameter tuning

> **This is the volume tier.** 16 GB is the first stop for users moving up from 8 GB, and it ships in the largest numbers.

---

## Why 16 GB is the battleground that matters

| Tier | Position | Value of tuning |
|---|---|---|
| 8 GB | where users are today | barely runs a modern model; nothing to tune |
| **16 GB** | **first upgrade stop** | ★★★★★ **highest volume; tuning moves the delivery numbers directly** |
| 24 GB | step up | ★★★ |
| 32 GB | one and done | ★★★ but high unit price, low volume |

**Conclusion**: effort spent finding the optimal parameters for the 16 GB tier is worth more than experiments on 32 GB.

---

## Hardware reference

| Model | VRAM | Bandwidth | Position |
|---|---:|---:|---|
| **Arc Pro B50** | 16 GB | 224 GB/s | single-slot half-height, 70 W, no auxiliary power |

**A counter-intuitive hypothesis, now confirmed on this machine**:

> For MoE, **VRAM capacity affects speed more than VRAM bandwidth does** — capacity decides whether the weights
> can be fully resident; bandwidth only matters once they are.

**Measured support** (2026-10-15, details in section B): shrinking the weights from 19.41 GiB to 10.73 GiB and
moving all of it into VRAM moved decode only from 37.74 to **45.99 (+22%)**. On a fully resident MoE the same card
uses just **19%** of its bandwidth; on a dense model it uses **68%** — **bandwidth has plenty of headroom, and
"does it fit" is the dividing line.**

**Corroboration elsewhere (not this machine; community measurements in Strata's `docs/INTEL_ARC.md`)**:

| Card | Quant | Decode |
|---|---|---:|
| Arc Pro B50 16 GB | Coder IQ1_M | ≈23 tok/s |
| Arc Pro B50 16 GB | IQ2_XS | 25 to 27 tok/s |

> ⚠️ These numbers come from **someone else's machine and were not reproduced here** (different model / version /
> parameters, **not comparable side by side with our numbers**). They move into the main table once reproduced here.

---

## Which 32 GB lessons do not carry over to 16 GB

| Lesson from 32 GB | Basis (B70 measured) | B50 measured | Carries over? |
|---|---|---|---|
| H3 gets much slower on B50 | the DiT does not fit in 15.51 GiB, offload is forced | end-to-end **399 s** (4 rounds); the same stack on B70 is 318 s (**+26%**) | ✅ **holds, but the effect is far smaller than expected** |
| Step-count tuning is equally useless on B50 | on B70 fixed overhead is 95% | ❌ **does not hold** — B50 fixed overhead falls to 59% (234.5/399), sampling takes 41%, **so step tuning works again** (6→2 steps, projected 88 s saved / −22%); but the first step still costs 54 s of fixed time, so whether that step can be removed has to be settled first | ❌ does not hold |
| The OmniXPU provider must be on | 7% slower with it off | not tested on its own on B50; but B50 runs the `generic-bmg` generic fallback and the vendor marks `performance_claim=false` | 🟡 unverified |

**Conclusion: tighten capacity and the bottleneck moves from "moving bytes off disk / RAM" to "VRAM and compute",
so the whole tuning priority flips.** The 32 GB lesson — "loading dominates, step count is useless" — does not
scale down with capacity. Details in the seventh section of [`comfyui-h3.md`](comfyui-h3.en.md).

---

## Per-item measurements

### A. Model × quant: does it run

Not "does it load" but **steady-state usable, no crash**.

| Model | Quant | Weight size | VRAM enough? | RAM enough (32 GB)? | Steady-state tok/s |
|---|---|---:|---|---|---:|
| Qwen3.6-35B-A3B | Q4_0 | 19.41 GiB | ✗ needs offload | ✓ runs | **37.74** (`-ncmoe 8`) |
| Qwen3.6-35B-A3B | Q3_K_S | 14.30 GiB | ✓ **fully resident** (1.21 GiB left) | ✓ | **37.99** (`-ncmoe 0`) |
| Qwen3.6-35B-A3B | IQ2_M | 10.73 GiB | ✓ fully resident (4.78 GiB left) | ✓ | **45.99** (`-ncmoe 0`) |
| Qwen3-VL-4B | Q4_0 | 2.21 GiB | ✓ fully resident | ✓ | **63.99** |

> The Q4_0 row was measured on 2026-10-15: 19.41 GiB of weights **does not fit in 15.51 GiB of VRAM**, but with
> 32 GB of physical RAM plus a page file (64/128 GB) it **runs at steady state** without crashing.
> "Does not fit in VRAM" ≠ "does not run" — that is exactly why the 16 GB tier exists.

**Criterion**: with 32 GB of RAM, do weights + KV + runtime overhead fit? If not, it goes to SSD / page file and speed drops sharply.

---

### B. Expert offload split point — **done; the knee takes two shapes, set by whether the weights fit**

The key parameter for an MoE model is **how many layers of experts are offloaded to the CPU**:

```bash
# llama.cpp expert offload (-ncmoe: experts of the first N layers go to the CPU)
llama-cli -m <model>.gguf -ngl 999 -ncmoe <N> -c <ctx>
```

#### Measured (2026-10-15 · B50 16G main slot · Qwen3.6-35B-A3B · `-ngl 999 -fa on -ctk q8_0 -ctv q8_0 -p 512 -n 128 -r 1`)

**Three quant levels compared** (B50 usable VRAM 15.51 GiB):

| Quant | Size | Fits VRAM? | Best `-ncmoe` | **decode** | prompt |
|---|---:|---|---:|---:|---:|
| IQ2_M | 10.73 GiB | ✓ 4.78 GiB left | **0** | **45.99** | 551.95 |
| Q3_K_S | 14.30 GiB | ✓ 1.21 GiB left | **0** | **37.99** | 589.57 |
| Q4_0 | 19.41 GiB | ✗ | **8** | **37.74** | 412.53 |

**Full curves**

IQ2_M — fits, **gentle slope**:

| `-ncmoe` | 0 | 2 | 4 | 8 | 16 | 32 |
|---|---:|---:|---:|---:|---:|---:|
| decode | **45.99** | 45.31 | 44.46 | 41.93 | 39.28 | 32.45 |

Q3_K_S — 14.30 GiB just fits, also a **gentle slope**:

| `-ncmoe` | 0 | 2 | 4 | 8 |
|---|---:|---:|---:|---:|
| decode | **37.99** | 37.48 | 36.83 | 34.84 |

Q4_0 — does not fit, **cliff**:

| `-ncmoe` | 0 | 4 | 5 | 6 | 7 | **8** | 12 | 16 | 20 | 24 | 32 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| decode | 4.14 | 14.87 | 19.07 | 21.00 | 24.83 | **37.74** | 36.49 | 33.02 | 32.49 | 30.62 | 29.22 |

**Conclusions**:

1. **The knee is set by "does it fit", not by the model**:
   - **fits → `-ncmoe 0` is optimal**; offloading only slows it down, by at most −29% across the range
   - **does not fit → cliff**. Q4_0 at `-ncmoe 0` collapses to **4.14**; it takes offload 8 to get back to 37.74, **a 9× gap**.
2. **🔴 A smaller quant does not buy speed.** The best decode for all three levels sits in a narrow **37.7 to 46.0** band:
   shrinking the weights from 19.41 GiB all the way to 10.73 GiB and moving them fully into VRAM buys only **+22%** (37.74 → 45.99).
   **Cause: at this size the B50 is compute-bound, not bandwidth-bound.**
   Fully resident IQ2_M uses only **19%** of 224 GB/s, while the same card on dense Qwen3-VL-4B uses **68%**.
   81% of the bandwidth is still spare; moving more weights in will not make it faster.
   > Corollary: **on the 16 GB tier, picking a quant is picking quality and VRAM headroom, not speed.**
3. **`-ncmoe 0` on Q4_0 is not "slightly slow", it is a disaster** (4.14 vs 37.74).
   That is what a bare `-ngl 999` gets you — llama.cpp silently degrades to whole-layer offload.
4. The curve turns at **the moment the size exceeds usable VRAM**: 10.73 and 14.30 GiB stay flat,
   19.41 GiB falls off a cliff. So check the weight size against 15.51 GiB before shipping parameters.

#### Choosing a tier

| What you want | Which tier | Cost / measured basis |
|---|---|---|
| Highest model quality | Q4_0 · 19.41 GiB | must offload experts, uses more RAM; 37.74 tok/s |
| Quality and speed balanced (**context ≤ 64K**) | Q3_K_S · 14.30 GiB | 37.99 tok/s (almost no loss); `-c 65536` still at full speed 37.13 |
| **Long context (agent loads at the 190,000-token level)** | **IQ2_M · 10.73 GiB** | lowest quality, but 22% faster, and `-c 262144` **does not spill** |

> **Do not choose a tier on the logic that "more VRAM saved means a longer context"**: IQ2_M already reaches the
> model's native 262144, and the 5 GiB Q3_K_S saves is **required to avoid spilling, not headroom**. Basis in
> [section D.4](#d4-this-fixes-the-tier-advice-in-section-b).

**Two boundaries of this section**:
- **CPU generation**: this machine is a Ryzen 5 9600X (**with AVX-512**). **Machines without AVX-512 are not measured**:
  CPU-side expert compute is slower there, so the knee for models that **do not fit** may shift right (more layers must be offloaded).
- **Q4_0 at full context**: 19.41 GiB, offload-dependent; it is the **only tier where `-c` costs speed**,
  with the knee between 32K and 64K — see **section D.5**.

> ⚠️ **Two measurement setups must not be mixed**: the `-ncmoe 0` in this section's table (`llama-bench`,
> `load_mode = auto`) = **4.14 tok/s**, which differs by **2.6×** from the `llama-server` figure with `-lm dio`
> (**10.71 tok/s**). The difference is **not attributed**. When quoting "how bad `-ncmoe 0` is", give both numbers.

Slot comparison (second slot x4 vs main slot x8) in [`docs/slot-comparison.md`](slot-comparison.en.md).

---

### C. KV cache quantization trade-offs — **done**

| Parameter | VRAM saved | Quality impact | 16 GB tier advice |
|---|---|---|---|
| `-ctk f16 -ctv f16` | baseline | none | **not recommended**: spills at full context, −26% |
| `-ctk q8_0 -ctv q8_0` | **measured about 35%** (20.8 → 13.5 KiB/token) | very small | **recommended starting point** |
| `-ctk q4_0 -ctv q4_0` | about 3/4 in theory, **not measured here** | to be assessed | quality loss needs measuring |

#### First measurement: the KV dtype does not change speed (2026-10-15 · B50 main slot · IQ2_M fully resident)

| KV dtype | `-c` | VRAM | Shared (spill) | decode | prompt |
|---|---:|---:|---:|---:|---:|
| q8_0 | 16384 | 11,365 MB | 44 MB | **45.21** | 44.35 |
| **f16** | 32768 | 11,753 MB | 60 MB | **45.28** | 42.22 |
| **f16** | 131072 | 13,751 MB | 156 MB | **45.23** | 42.97 |
| q8_0 | 131072 | 12,791 MB | 156 MB | **44.80** | 43.38 |

**Conclusion: as long as nothing spills into host memory, the KV dtype has no effect on speed (45.2 ± 0.5, all noise).**
So the right statement is:

> "KV quantization is not a speed switch. It only decides **whether the context length you want fits**.
> If it fits, use q8_0. If it does not, dropping to q4_0 buys **a longer context**, not a faster one."

> q4_0 on the **Q4_0 weights** model (19.41 GiB, `-ncmoe 8`): decode **37.52** vs q8_0's 37.43 / 37.74 — again no
> difference. But VRAM was not recorded for that run, so **how much VRAM q4_0 actually saves is still unmeasured here**.

#### Second measurement: how many bytes KV really takes (read the perf counters, not the log)

On SYCL with fit enabled, the llama-server log prints `KV buffer size` as **`0.00 MiB` once up front**
(a dry pass); the real value comes on the **next** pass (see `pitfalls.md` 4.5). So this measurement reads process
VRAM directly with `bench/harness/xpu_vram.py` and derives the figure from the delta between two `-c` values:

| Model | KV dtype | Points | Per-token delta |
|---|---|---|---:|
| IQ2_M | **f16** | 32768 → 131072 | **20.8 KiB/token** |
| IQ2_M | **q8_0** | 4096 → 65536 / 131072 | **13.5 KiB/token** |

Converting with `(n_embd_k_gqa + n_embd_v_gqa) × 10 layers = 10240 values/token`:

- **f16 = 2.08 B per value** — **matches** f16's 2 B per value, which confirms the structural claim that only 10 layers carry KV.
- **q8_0 = 1.35 B per value** — **24% above** the textbook 1.0625 B per value for q8_0.
  **Not explained, recorded as measured**: on this backend the q8_0 KV layout costs about a quarter more than theory,
  and the mechanism was not traced. **Budget VRAM with the measured 13.5 KiB/token, not with the textbook figure.**

**Quick conversion (q8_0 · 13.5 KiB per token)**:

| `-c` | KV size |
|---:|---:|
| 32768 | 0.42 GiB |
| 65536 | 0.84 GiB |
| 131072 | 1.69 GiB |
| **262144** | **3.38 GiB** |

> Cross-check against the measured total: IQ2_M weights 10.73 GiB + KV 3.38 GiB = 14.11 GiB, but `-c 262144`
> measures **15,540 MB = 15.17 GiB** in total — **1.06 GiB** more. That remainder is recurrent state + compute
> buffers + output buffers, **and one part of it grows with context** (the fitted coefficient is higher than
> 13.5 KiB/token at small context). **Not traced, no explanation.**

#### Third measurement: `-ctk f16` on 16 GB does **not** OOM, it spills

**Does `-ctk f16` OOM outright? No.** Windows allows VRAM oversubscription: crossing the line raises no error, the
driver pages to host memory, and **the cost is speed**:

| Config | VRAM | Shared (spill) | decode | Relative loss |
|---|---:|---:|---:|---:|
| IQ2_M · f16 · `-c 131072` | 13,751 MB | 156 MB (no spill) | **45.23** | baseline |
| IQ2_M · f16 · `-c 262144` | 16,184 MB | **540 MB** | **33.52** | **−26%** |
| Q3_K_S · q8_0 · `-c 131072` | 16,130 MB | 412 MB | **30.25** | **−18%** |
| Q3_K_S · q8_0 · `-c 262144` | 16,086 MB | **2,332 MB** | **15.74** | **−58%** |

> The card's usable capacity is **15.51 GiB ≈ 15,882 MB**. The three rows above that figure are **all spilling**.

**This gives a harder criterion** (and backs the mechanism in section 1.7):

These runs used a probe **prompt of only about 50 tokens**, so attention cost is negligible, yet **prefill dropped too**
(Q3_K_S `-c 262144`: prompt from ≈44 to **18.39**). Prefill is pure compute and barely touches PCIe — it can only drop
because **the weights are not being fed**. → **"prefill and decode falling together" = VRAM spill, not a bandwidth
problem.** That criterion now has direct evidence.

👉 So **the default KV dtype on the 16 GB tier is q8_0**:
not because it is faster, but because **f16 spills at full context and costs 26%**.

Slot comparison (second slot x4 vs main slot x8) in [`docs/slot-comparison.md`](slot-comparison.en.md).

---

### D. Context ceiling — **"where the ceiling sits" depends on whether the weights fit**

**Two preconditions before reading this section**: D.1 to D.4 all assume **weights fully resident**.
On tiers where the weights do not fit and `-ncmoe` offload is required (Q4_0), `-c` **costs** —
the knee is between 32K and 64K, see **section D.5**.

"How long a context 16 GB can open" is **two questions pointing in opposite directions**; mix them and you get no answer.

#### D.1 Allocating context is **free**

`llama-server` + a short prompt (about 50 tokens), same model, same parameters, only `-c` changed:

| `-c` | 4096 | 16384 | 32768 | 65536 | 131072 | **262144** |
|---|---:|---:|---:|---:|---:|---:|
| decode tok/s | 45.21 | 45.07 | 45.07 | 44.47 | 44.75 | **44.93** |
| prompt tok/s | 43.24 | 44.63 | 42.88 | 41.91 | 42.51 | 43.78 |
| Load time | 13.1 s | 10.5 s | 11.1 s | 12.5 s | 10.5 s | **10.5 s** |

(IQ2_M · 10.73 GiB fully resident · `-ncmoe 0` · `-fa on -ctk q8_0 -ctv q8_0`)

**Across a 64× span of context (16,384 → 262,144) the full span is only 1.6%. `-c 262144` (the model's native full context, `n_ctx_train = 262144`)
needs only 10.5 s to load and runs.** Default parameters (no `-fa`, no `-ctk/-ctv`) at `-c 16384` give **45.30** as well —
the parameter difference is not the cause either.

> ⚠️ **Do not extrapolate this**: the "free" here assumes IQ2_M fully resident (4.78 GiB spare).
> On Q4_0 (does not fit, needs offload) the same `-c` span costs **72%** of decode. See D.5.

**Why it is so cheap**: the model uses **hybrid attention**, `full_attention_interval = 4` — **only 10 of 40 layers
carry a KV cache**; the other 30 run on linear-attention (recurrent) state. Log evidence (`llama-server -v`):

```
llama_kv_cache: layer   0/1/2: filtered                  ← linear attention layer, no KV
llama_kv_cache: layer   3/7/11/15/19/23/27/31/35/39: dev = SYCL0   ← exactly 10 layers
llama_memory_recurrent: layer 3/7/11/.../39: skipped
load_tensors: offloaded 41/41 layers to GPU
llama_context: flash_attn = enabled
```

> Extrapolating with the measured q8_0 coefficient from section C (13.5 KiB/token): **if all 40 layers carried KV,
> 262144 would need about 13.5 GiB of KV** — impossible on a 15.51 GiB card. With only 10 layers it drops to
> **3.38 GiB**. **Hybrid attention is why long context runs on 16 GB.**
> (Note: this is a proportional extrapolation from the measured coefficient, not a measurement of a full-attention model.)

#### D.2 The real cost is **actual depth** (attention cost)

The D.1 probe had only about 50 tokens, **so depth never rose**. The cost only shows when KV is really filled to N
tokens and then generated (`cache_prompt: false` must be set explicitly, otherwise only the delta is counted and
prefill is badly overestimated):

| Measured depth | prefill tok/s | **decode tok/s** |
|---:|---:|---:|
| 508 | 414.91 | **44.35** |
| 31,323 | 427.53 | **30.82** |
| 59,918 | 385.95 | **24.26** |
| 119,902 | 330.04 | **17.02** |
| 181,454 | 285.82 | **13.01** |
| 244,098 | 254.76 | **10.48** |

**Fit (max residual 2.4%)**:

```
decode time (ms) ≈ 22.95 + 0.000298 × context depth
```

| Term | Meaning |
|---|---|
| Fixed term 22.95 ms | hard floor from reading the weights → a ceiling of **about 43.6 tok/s** (consistent with 45.2 at `-c 4096`) |
| Slope 0.298 ms / thousand tokens | **attention cost**, proportional to depth |

**Predict, then verify**: the 5-point fit predicts **12.29 tok/s** at depth 189,673; the v2 run at depth 181,454
measured **13.01** (fit 13.00 at the same depth, residual +0.1%). **The model holds.**

**What this means**:

> "A full context costs nothing in VRAM; it costs **attention**. At 190,000 tokens deep, decode is about
> **12 to 13 tok/s**; at 260,000, about **10 tok/s**. That is inherent cost, not a weak card.
> And this model has KV in only 1/4 of its layers — a full-attention model of the same size would make that line
> **about 4× steeper** (**scaled by layer count, not measured**)."

#### D.3 What hits the wall first: not `-c`, but **whether the weights still fit**

Opening `-c` all the way to 262144, the limit is not KV — it is **KV pushing total usage past 15.88 GiB, after which
spilling starts**:

| Config | `-c` | VRAM | Shared (spill) | decode | Full speed? |
|---|---:|---:|---:|---:|---|
| IQ2_M 10.73 GiB | 262144 | 15,540 MB | 284 MB | 44.93 | ✅ 97.8% occupancy, **just short of spilling** |
| **Q3_K_S** 14.30 GiB | 65536 | 15,513 MB | 92 MB | 37.13 | ✅ just fits |
| **Q3_K_S** | 131072 | 16,130 MB | 412 MB | 30.25 | ❌ −18% |
| **Q3_K_S** | 262144 | 16,086 MB | **2,332 MB** | 15.74 | ❌ **−58%** |
| IQ2_M + **f16 KV** | 262144 | 16,184 MB | 540 MB | 33.52 | ❌ −26% |

#### D.4 This fixes the tier advice in section B

**"Q3_K_S saves 5 GiB of VRAM → longer context" does not hold**:

- **IQ2_M (10.73 GiB) already reaches the model's native 262144**, and does not spill even at full context.
- **The 5 GiB Q3_K_S (14.30 GiB) saves is not headroom, it is a necessity**:
  it holds full speed only up to `-c 65536`; at `-c 262144` it spills 2.3 GB and decode drops 58%.

**Conclusion**:

| What you want | Which tier | Measured basis |
|---|---|---|
| Highest quality, **context ≤ 64K** | Q4_0 or Q3_K_S | Q3_K_S `-c 65536` = 37.13 at full speed |
| **Long context (agent loads at the 190,000-token level)** | **IQ2_M** | no spill at 262144; 13.01 at depth 180,000 |
| Short context, high error tolerance | IQ2_M or Q3_K_S | both sit in the 37 to 46 band |

> **In one line**: on the 16 GB tier, **long context means IQ2_M, not Q3_K_S.**
> The VRAM it saves does not buy "a longer context"; it buys "no spill when the context is long".

#### D.5 `Q4_0` (offload-dependent): here `-c` **costs** (measured)

D.1's "allocating context is free" **holds only for tiers that fit**.
Q4_0 (19.41 GiB, needs `-ncmoe 8` offload) is the counter-example — the part that stays on the card already sits at
the 15.9 GiB edge, so every step up in `-c` turns straight into spill.

**Measured (2026-10-16 · B50 main slot · Q4_0 + `-ncmoe 8` · text only · 1 warm-up + 4 samples)**:

| `-c` | KV buffer | VRAM | Shared | **True spill** (minus 3808.81 MiB host buffer) | decode | prefill |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16384 | 170 MiB | 15,945 MB | 3,848 MB | **≈39 MB** | 37.45 / 37.55 | 46.5 |
| 32768 | 340 MiB | 16,132 MB | 3,864 MB | **≈55 MB** | **37.57** | 46.51 |
| 65536 | 680 MiB | 16,194 MB | 4,206 MB | **≈397 MB** | **26.62 (−29%)** | 26.84 |
| 262144 | 2,720 MiB | 16,030 MB | 7,160 MB | **≈3,351 MB** | **10.35 (−72%)** | 24.01 |

**Side by side with IQ2_M (D.1)**, same move, "`-c` from 16K to 256K":

| Tier | Weights | VRAM headroom | Cost of going to 262144 |
| --- | ---: | ---: | --- |
| **IQ2_M** | 10.73 GiB | 4.78 GiB spare | **−0.6%** (45.21 → 44.93), free |
| **Q4_0 + `-ncmoe 8`** | 19.41 GiB (partially offloaded) | ≈ 0 | **−72%** (37.55 → 10.35), plus 3.35 GB of spill |

→ **"`-c` is free" is a conclusion for "the weights fit" and does not transfer to tiers that only run by offloading.**
Both statements are true; the preconditions differ.

**The context ceiling for this tier is around 32K** (decode drops 29% from 64K).

> **Reading note**: the "Shared" column above **is not spill**. `-ncmoe 8` deliberately places 3808.81 MiB of expert
> weights in `SYCL_Host`; that is counted in `vram_shared_mb` but is not spill (see `docs/pitfalls.md`). The "Shared"
> numbers in the D.1 to D.3 tables come close to true spill only because those runs used `-ncmoe 0`.
> **Before reading any `vram_shared_mb`, confirm what `-ncmoe` is.**



---

### E. Page file with 32 GB of RAM

**The page file is the only expandable "memory" and it is a hard delivery item.**

#### Current state on this machine (measured 2026-10-15)

| Item | Value |
|---|---|
| Physical RAM | 2×16 GB DDR5-6400 dual channel, system reports **31.1 GB** |
| Slots | **2, both populated** (B850M FORCE WIFI6E, max 128 GB / 4 devices) |
| Page file | **E: drive · initial 64 GB · max 128 GB · manually set (not system managed)** |
| Virtual memory ceiling | 31.1 + 128 ≈ **159 GB** |

> Only 2 slots, both taken — **"add RAM" on this machine means "replace RAM"**
> (2×16 → 2×24/32), not adding one more stick.

#### The question to answer

With a B50 16G on 32 GB of physical RAM running `<model>`, how large does the page file need to be to be safe?
(too small → loading fails; too large → wasted disk)

#### Why the page file is a hard delivery item

32 GB is the configuration of 90% of target users, and many machines already have both slots full — **"add RAM" is
not an option for users**. The page file is the only knob they can turn, so the recommended value has to go into the
SOP; parameters tuned on a 48 / 64 GB machine do not apply to a 32 GB user.

---

## Target output

One table, ready to hand over:

| Model | Quant | RAM needed | Page file | Launch parameters | Measured tok/s |
|---|---|---|---|---|---|
| … | … | 32 GB | … | … | … |

**This table is the 16 GB tier's deliverable.**
