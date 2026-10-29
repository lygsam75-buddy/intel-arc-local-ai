# Dual Intel Arc Pro B65 on a Consumer Motherboard: What You Actually Get

**Summary:** We ran a full benchmark suite on two Intel Arc Pro B65 32 GB cards in a mainstream B850M mATX motherboard — no workstation board, no x8/x8 bifurcation. The honest answer: the second card buys capacity and throughput, not single-task speed. Here are the numbers.

**Full data, methodology, and reproducible harness:** [github.com/lygsam75-buddy/intel-arc-local-ai](https://github.com/lygsam75-buddy/intel-arc-local-ai)

---

## The Question Everyone Asks

"If I add a second GPU, does everything get 2× faster?"

No. And the reason is more interesting than you'd think.

We tested two GUNNIR Intel Arc Pro B65 32 GB cards (ECC off, 31.16 GiB usable each) on a **B850M mATX board** — the same class of motherboard most builders already own. Card 0 sits in the CPU-attached x16 slot; card 1 in the chipset x4 slot. No workstation hardware was used to produce any of these results.

**Setup:** 2× Arc Pro B65 · driver 9150 · 32 GB (2×16 GB) system RAM · display on integrated graphics · MiniMax H3 video generation + LLM inference workloads. Full test conditions in the [repository's dual-card report](../dual-b65-report.md).

---

## Finding 1: The Second Card Is a Room, Not a Speed Boost

| Workload | Single B65 | 2× B65 | What It Means |
|---|---:|---:|---|
| H3 720p 5 s video (end-to-end) | 394.06 s | 417.78 s | Not faster. Period. |
| H3 720p per-step sampling | 42.30 s/it | 42.41 s/it | Second card contributes 0 to single-task speed |
| LLM Q4_0 decode (both cards active) | 50.56 tok/s | 50.47 tok/s | Concurrent workloads don't slow each other |
| Available VRAM | 31.16 GiB | 62.32 GiB | **2× memory — this is what you're buying** |
| Two parallel 5 s video clips | — | 18.3 clips/hr | vs single B65 13.0 clips/hr: **1.40× throughput** |
| Price | ¥9,999 | ¥19,998 | vs one B70 at ¥18,999 |

The headline: **one B70 buys speed; two B65s buy capacity + throughput at nearly the same price.**

Full benchmark table with 13 more workloads: [dual-b65-report.md](../dual-b65-report.md)

---

## Finding 2: Don't Bother with Tensor Parallelism (For Now)

We tried running a single workload across both cards via tensor parallelism. The result: **28.65 tok/s vs 50.56 tok/s on a single card**. Every layer boundary forces the two cards to synchronize, and the synchronization overhead eats more than the parallelism saves.

The working model is **independent lanes**: each card runs its own task. The second card is a second production line, not a booster for the first.

> **Note:** The official multi-GPU stack (vLLM + oneCCL) targets Ubuntu/Docker. On Windows, our independent-lane approach is the practical path. Details in [§7 of the report](../dual-b65-report.md).

---

## Finding 3: Layer Offloading Works — But Only When You Must

For models that don't fit on one card (e.g., a 34.37 GiB Q8_0 model vs 31.16 GiB VRAM), splitting layers across two cards works:

- **When it doesn't fit:** offloading to card 2 gives you **1.17× speedup** vs system memory offload (31.86 → 37.35 tok/s)
- **When it fits on one card:** splitting is **slower** than running on a single card (53.63 → 49.80 tok/s, −7.1%)

**Rule:** offloading buys capacity at near-zero speed cost — but only cross the bridge when you need to.

---

## Finding 4: The Board Matters Less Than You'd Think

On a B850M (no PCIe bifurcation), the second card in the x4 chipset slot runs a single H3 step at **42.31 s/it** — identical to the x16 slot. For workloads where the model is resident in VRAM, the PCIe link width doesn't matter.

It matters only when weights must cross the bus every step (heavily offloaded models). Then the x4 link becomes a bottleneck.

**Practical implication:** for the independent-lane use case, a consumer B850M is sufficient. You only need an x8/x8 workstation board for 4-card setups or sustained tensor parallelism.

---

## Finding 5: The Memory Wall Is Real

With 32 GB system RAM (the configuration we tested):

- ✅ **One video + one chat/LLM task:** works (12/12 correct, decode −0.2%)
- ❌ **Two simultaneous video renders:** crashes (2/2 runs, out of system memory)

For two parallel video pipelines, **64 GB system RAM is required**. Better to know before building.

---

## Reproducibility

All benchmarks in this article come from a **fully open-source harness** — same scripts, same data files, same analysis:

📦 **Repository:** [github.com/lygsam75-buddy/intel-arc-local-ai](https://github.com/lygsam75-buddy/intel-arc-local-ai)

Key documents:
- [Dual-card full report](../dual-b65-report.md) — all 15 test items with raw numbers
- [B65 single-card deep dive](../cards/B65-README.md) — 30-tier H3 duration ladder, VRAM analysis
- [LLM server tuning](../server-config.md) — Vulkan vs SYCL, context allocation, quantization
- [ComfyUI + MiniMax H3 on Arc](../comfyui-h3.md) — video generation benchmarks across 4 cards
- [Pitfalls & troubleshooting](../pitfalls.md) — every gotcha we hit, with fixes

Every chart is generated from raw `bench/data/*.json` files. No hand-typed numbers.

---

## TL;DR for Evaluating Dual Arc Pro B65

| Your goal | Recommendation |
|---|---|
| Run bigger models (34 GB+ weights) | ✅ Two B65s give you 62 GiB VRAM at near-zero speed cost |
| Run two independent workloads | ✅ Full throughput, zero interference |
| Make one video faster | ❌ Buy a B70 instead (1.42× faster at similar price) |
| Tensor parallelism across both cards | ⚠️ Currently slower than single card on Windows |
| Two parallel video renders | ⚠️ Needs 64 GB system RAM |

**The second B65 buys you a second room, not a faster room.** Plan accordingly.

---

*This article is based on proprietary benchmark data collected in October 2026. All raw data, analysis scripts, and documentation are open-source at [github.com/lygsam75-buddy/intel-arc-local-ai](https://github.com/lygsam75-buddy/intel-arc-local-ai). The same harness covers Intel Arc Pro B50/B60/B65/B70 with full cross-card comparisons.*

*Tags: Intel Arc, Intel Arc Pro B65, dual GPU, LLM inference, video generation, MiniMax H3, ComfyUI, llama.cpp, Vulkan, SYCL, PCIe, workstation*
