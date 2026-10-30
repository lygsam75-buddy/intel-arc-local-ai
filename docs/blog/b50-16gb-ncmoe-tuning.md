# A 9× cliff hidden in one flag: running a 35B MoE on a 16 GB Intel Arc B50

*Measured 2026-10-15 on Windows 11. Every number below comes from `llama-bench` / `llama-server` runs I made myself on hardware I own. Full data, harness and the rest of the card's benchmark set: [intel-arc-local-ai](https://github.com/lygsam75-buddy/intel-arc-local-ai).*

---

## TL;DR

On a 16 GB card, `-ncmoe` is not a gentle knob. Two distinct regimes:

| Weights fit in VRAM? | Best `-ncmoe` | Penalty for guessing wrong |
|---|---|---|
| **Yes** | **0** | up to **−29%** decode if you offload anyway |
| **No** | **the exact layer count that makes it fit** | **−89%** decode at `-ncmoe 0` |

The second row is the trap. `-ngl 999 -ncmoe 0` on a model that doesn't fit does not run "a bit slower" — it collapses. 4.14 tok/s vs 37.74 tok/s on the same model, same card, one flag apart.

And the second, more irritating finding: **shrinking the quantization to fit fully in VRAM buys you only +22%.** On this card at this model size you are compute-bound, not bandwidth-bound. Choosing a quant tier is a decision about *quality and headroom*, not about speed.

---

## Test setup

| | |
|---|---|
| GPU | Intel Arc Pro B50 16 GB — usable **15.51 GiB (15,882 MB)**, 224 GB/s, 70 W, single slot, no external power |
| CPU | Ryzen 5 9600X (has AVX-512 — this matters, see limitations) |
| RAM | 32 GB (2×16 GB DDR5-6400), page file 64/128 GB |
| OS | Windows 11, display on iGPU, whole card left to compute |
| Model | Qwen3.6-35B-A3B (MoE, 40 layers, hybrid attention) |
| Stack | llama.cpp SYCL backend, Intel driver 32.0.101.8976 |

Fixed bench command unless noted:

```
-ngl 999 -fa on -ctk q8_0 -ctv q8_0 -p 512 -n 128 -r 1
```

Note on that model: it is **not** a normal transformer. `full_attention_interval = 4`, so only 10 of 40 layers carry KV cache; the other 30 use a recurrent state. That is the single reason 262K context is possible on 16 GB at all — see the context section.

---

## Finding 1 — `-ncmoe` has two regimes, and the cliff is vertical

I swept `-ncmoe` on three quantization tiers of the same model. Same card, same flags, only the weight size differs.

**Q4_0 · 19.41 GiB · does not fit in 15.51 GiB**

| `-ncmoe` | 0 | 4 | 5 | 6 | 7 | **8** | 12 | 16 | 20 | 24 | 32 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| decode tok/s | **4.14** | 14.87 | 19.07 | 21.00 | 24.83 | **37.74** | 36.49 | 33.02 | 32.49 | 30.62 | 29.22 |

**IQ2_M · 10.73 GiB · fits (4.78 GiB spare)**

| `-ncmoe` | 0 | 2 | 4 | 8 | 16 | 32 |
|---|---:|---:|---:|---:|---:|---:|
| decode tok/s | **45.99** | 45.31 | 44.46 | 41.93 | 39.28 | 32.45 |

**Q3_K_S · 14.30 GiB · fits (1.21 GiB spare)**

| `-ncmoe` | 0 | 2 | 4 | 8 |
|---|---:|---:|---:|---:|
| decode tok/s | **37.99** | 37.48 | 36.83 | 34.84 |

Two things fall out of this:

1. **If it fits, `-ncmoe 0` is optimal.** Offloading only costs you — monotonically, up to −29%.
2. **If it doesn't fit, the curve is a cliff, and the bottom of the cliff is at `-ncmoe 0`.** Q4_0 at `-ncmoe 0` is 4.14 tok/s. At `-ncmoe 8` it is 37.74. That is **9.1×**, and the only thing that changed is how many MoE layers stay on the CPU.

The turning point is not a model property. It is the exact moment weight volume crosses usable VRAM: 10.73 and 14.30 GiB are both flat; 19.41 GiB falls off. **Compute the weight size against your usable VRAM before you pick a flag**, not after.

### Caveat on the `-ncmoe 0` number

`4.14` is the `llama-bench` figure (`load_mode = auto`). The same config through `llama-server` (`-lm dio`) reads **10.71 tok/s**. That is a 2.6× gap I have not explained. Both numbers are real; quote both if you cite "how bad `-ncmoe 0` is". The *shape* of the cliff is not in doubt — only the absolute bottom.

---

## Finding 2 — Quantization tiers buy quality, not speed

Take the best `-ncmoe` for each tier and line them up:

| Quant | Weight size | Fits? | Best `-ncmoe` | decode tok/s |
|---|---:|---|---:|---:|
| Q4_0 | 19.41 GiB | ✗ | 8 | 37.74 |
| Q3_K_S | 14.30 GiB | ✓ | 0 | 37.99 |
| IQ2_M | 10.73 GiB | ✓ | 0 | **45.99** |

Shrinking 19.41 → 10.73 GiB (a 45% reduction) and moving everything on-die buys **+22%**.

The reason is measurable: at this model size the B50 uses **19% of its 224 GB/s**. The same card running a dense 4B model uses **68%**. There is 81% bandwidth headroom, so pushing more weights on-die does nothing. This is a compute-bound regime wearing a bandwidth-bound card's clothes.

> Practical consequence: on 16 GB, pick the quant tier for the model quality you need and the VRAM headroom you need for context. Do not expect speed to follow.

---

## Finding 3 — KV cache quantization is a capacity knob, not a speed knob

KV tier does not change decode speed as long as nothing spills:

| KV | `-c` | VRAM | Spilled | decode |
|---|---:|---:|---:|---:|
| q8_0 | 16384 | 11,365 MB | 44 MB | 45.21 |
| f16 | 32768 | 11,753 MB | 60 MB | 45.28 |
| f16 | 131072 | 13,751 MB | 156 MB | 45.23 |
| q8_0 | 131072 | 12,791 MB | 156 MB | 44.80 |

That's 45.2 ± 0.5 — noise. What KV quantization actually decides is **how much context you can hold without spilling**.

Measured bytes per token on this backend (read from the XPU VRAM counter, not from logs):

| KV | Measured | Theoretical |
|---|---:|---:|
| f16 | **20.8 KiB/token** | 20.0 (2.0 B/value × 10,240 values) |
| q8_0 | **13.5 KiB/token** | 10.9 (1.0625 B/value × 10,240 values) |

q8_0 comes out **24% above theoretical**. I could not explain it and am not going to guess — just don't budget with the textbook number. Use 13.5 KiB/token.

The cost of getting this wrong is not an OOM. **Windows allows VRAM oversubscription** — it silently pages to host memory and you pay in speed:

| Config | VRAM | Spilled | decode | Loss |
|---|---:|---:|---:|---:|
| IQ2_M · f16 · `-c 131072` | 13,751 MB | 156 MB | 45.23 | baseline |
| IQ2_M · f16 · `-c 262144` | 16,184 MB | 540 MB | 33.52 | **−26%** |
| Q3_K_S · q8_0 · `-c 131072` | 16,130 MB | 412 MB | 30.25 | **−18%** |
| Q3_K_S · q8_0 · `-c 262144` | 16,086 MB | **2,332 MB** | 15.74 | **−58%** |

Usable is 15,882 MB — every row above that line is spilling.

**So the default on 16 GB is `-ctk q8_0 -ctv q8_0`** — not because it is faster, but because f16 spills at full context and costs 26%.

A useful diagnostic falls out of this: in those spilling rows the **probe prompt is only ~50 tokens**, so attention cost is negligible, yet **prefill dropped too** (Q3_K_S at `-c 262144`: prompt 44 → 18.39 tok/s). Prefill is pure compute and barely touches PCIe. **Prefill and decode falling together = VRAM spill, not a bandwidth problem.**

---

## Finding 4 — Allocating context is free; filling it is not

Two different questions people merge into one.

**Allocation:** same model, same flags, only `-c` changes. Probe prompt ~50 tokens.

| `-c` | 4096 | 16384 | 32768 | 65536 | 131072 | **262144** |
|---|---:|---:|---:|---:|---:|---:|
| decode tok/s | 45.21 | 45.07 | 45.07 | 44.47 | 44.75 | **44.93** |

64× more context, 1.6% total spread. `-c 262144` is the model's native limit (`n_ctx_train = 262144`) and loads in 10.5 s. Allocation costs nothing — **as long as the weights are fully resident.**

**Depth:** fill the cache to N tokens and re-measure (`cache_prompt: false` is mandatory, otherwise you only measure increments).

| Depth | prefill tok/s | decode tok/s |
|---:|---:|---:|
| 508 | 414.91 | 44.35 |
| 31,323 | 427.53 | 30.82 |
| 59,918 | 385.95 | 24.26 |
| 119,902 | 330.04 | 17.02 |
| 181,454 | 285.82 | 13.01 |
| 244,098 | 254.76 | **10.48** |

Fit (max residual 2.4%):

```
decode_ms ≈ 22.95 + 0.000298 × depth_tokens
```

- Intercept 22.95 ms is the weight-read floor → ~43.6 tok/s ceiling, matching the 45.2 measured at `-c 4096`.
- Slope 0.298 ms per 1k tokens is the attention bill, linear in depth.

Held out one point: predicted 12.29 tok/s at depth 189,673; measured 13.01 at 181,454 (fit says 13.00 there). Model holds.

> With only 10 of 40 layers carrying KV, this line is unusually flat. A full-attention model of the same size would be roughly **4× steeper** — that extrapolation is arithmetic on layer count, not a measurement.

---

## The config table I actually ship

B50 16 GB, 32 GB RAM, Qwen3.6-35B-A3B:

| Goal | Quant | `-ncmoe` | `-c` | decode |
|---|---|---:|---:|---:|
| Best quality | Q4_0 · 19.41 GiB | **8** | ≤65536 | 37.74 |
| Balance (≤64K ctx) | Q3_K_S · 14.30 GiB | **0** | 65536 | 37.13 |
| Long context / agent | IQ2_M · 10.73 GiB | **0** | **262144** | 44.93 |

All with `-fa on -ctk q8_0 -ctv q8_0`.

One correction to a common assumption: **do not pick the smallest quant to "save VRAM for a longer context."** IQ2_M already reaches the model's native 262,144. The 5 GiB Q3_K_S appears to save is *the price of not spilling*, not spare headroom you can spend elsewhere.

---

## Reproduce

```bash
# the cliff
llama-bench -m Qwen3.6-35B-A3B-Q4_0.gguf -ngl 999 -ncmoe 0 \
  -fa 1 -ctk q8_0 -ctv q8_0 -p 512 -n 128 -r 1
llama-bench -m Qwen3.6-35B-A3B-Q4_0.gguf -ngl 999 -ncmoe 8 \
  -fa 1 -ctk q8_0 -ctv q8_0 -p 512 -n 128 -r 1

# allocation vs depth (needs a server)
llama-server -m Qwen3.6-35B-A3B-IQ2_M.gguf -ngl 999 -ncmoe 0 \
  -fa on -ctk q8_0 -ctv q8_0 -c 262144
# then POST with "cache_prompt": false to force real prefill
```

---

## Limitations

- **One card, one model family, one OS.** B50 16 GB on Windows 11. Nothing here is verified on B60/B65/B70 or on Linux.
- **AVX-512 CPU.** The 9600X has it. On a CPU without AVX-512, the CPU-side expert compute is slower, so the cliff position for "doesn't fit" models may move — you'd need to offload more. **Untested.**
- **The 2.6× spread on `-ncmoe 0`** between `llama-bench` and `llama-server` is unexplained. Treat absolute values at the cliff bottom as approximate; the shape is not.
- **The q8_0 KV overhead (+24% over theory)** is unexplained on this backend. Budget with the measured number.
- Single run per cell (`-r 1`). Run-to-run noise on this rig was within 1–3% on decode, larger on prefill.

If you have a non-AVX-512 box or a Linux box with a B50, I would genuinely like to see the `-ncmoe` sweep repeated there — that is the one number I cannot validate myself.
