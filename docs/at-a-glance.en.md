**English** · [简体中文](at-a-glance.md)

# At a glance: what these two cards can actually do

Skip the long docs. **Six tables below tell you which card to buy and what it can run.**

Every number was measured on our own machines. Raw data lives in [`../bench/data/`](../bench/data/).

---

## 1. The four questions everyone asks

| What you want to do | B50 (¥3,499 · 16 GB) | B60 (¥6,099 · 24 GB) | B65 (¥9,499 · 32 GB) | B70 (¥18,999 · 32 GB) | Verdict |
|---|---|---|---|---|---|
| Chat with a 35B model | **37.6 tok/s** | **52.4 tok/s** | **53.1 tok/s** | **75.9 tok/s** | All four fine, pick by budget |
| Generate a 1280×720 image | **52 s** | **18 s** | **16 s** | **11 s** | B60 / B65 are close to B70 |
| Generate a 5-second 480p video | **6.6 min** | **3.7 min** | **3.3 min** | **2.5 min** | All four can do it |
| Generate a 5-second 1080p video | **38 min** | **22 min** | **22 min** | **14 min** | All four can, just slowly |

> **What is tok/s?** How many "word chunks" the model spits out per second. Bigger is faster.
> 37 is already faster than most people read; 75 is double that.

> **B65 column:** chat **53.1 tok/s**, image **16 s**, music (120 s) **3 min**, 480p **3.3 min**,
> 720p **6.6 min**, 1080p **22.1 min** (all warm runs). It sits next to B60 for a reason —
> both have **20 Xe2 cores**, so the extra money buys VRAM, not speed.

---

## 2. Electricity: cheaper than you think

| | B50 16 GB | B60 24 GB | B65 32 GB | B70 32 GB |
|---|---|---|---|---|
| Idle | not measured | not measured | not measured | **51 W** (like a light bulb) |
| Full load | 70 W (spec sheet, not measured) | **151–154 W** (P90, TBP 200 W) | **201–204 W** (P90, pinned to the 200 W wall) | **290 W** (measured, holds steady) |
| One hour at full load | about **¥0.05** | about **¥0.10** | about **¥0.14** | about **¥0.20** |
| One 5-second 720p video | not measured | about **¥0.01** (50 kJ) | about **¥0.01** (65 kJ) | about **¥0.01** (58 kJ) |

At **¥0.7 per kWh**.

> **Electricity is not the problem — the PSU and cooling are.** For a 290 W card, use at least a 550 W PSU.

---

## 3. How big a model fits on B50 (16 GB)

| Model size | Fits in VRAM? | Chat speed |
|---|---|---|
| **10.7 GB** (IQ2_M) | Yes, fully resident | **46 tok/s** |
| **14.3 GB** (Q3_K_S) | Yes, fully resident | **38 tok/s** |
| **19.4 GB** (Q4_0) | No, part of it spills to RAM | **37.6 tok/s** |

> **Two counter-intuitive facts, both measured:**
>
> 1. **It still runs when it does not fit** — just slower. Windows moves the excess to RAM without an error.
> 2. **A smaller model is not faster.** Going from 19.4 GB to 10.7 GB only moves speed from 37.6 to 46.
>    **Pick the small quant to save VRAM, not to go faster.**

---

## 4. How long a video takes on B50 (5-second clip)

| Resolution | Wait time | In human terms |
|---|---|---|
| 480p (864×480) | 4.7 min | time for a coffee |
| 720p (1280×720) | 11 min | a quick errand |
| 1080p (1920×1088) | **37.7 min** | a proper meal |

> **The rule is simple: double the pixels, more than quadruple the time.**
>
> Note: this table comes from a separate run (cold single-shot). The 4.7 min for 480p is not the same run as
> the 6.6 min in table 1 — **read the trend, do not compare absolute numbers across tables**.

---

## 5. Which one to buy

| You are | Buy |
|---|---|
| On a ¥3,500 budget: chat + images + occasional 480p/720p video | **B50 16 GB** |
| On a ¥6,000 budget: noticeably faster chat, more VRAM headroom | **B60 24 GB** (measured: 52.4 tok/s) |
| Want 32 GB of VRAM for under ¥10,000 | **B65 32 GB** (¥9,499) — same die as B70 with 20 of 32 Xe2 cores, so **chat speed equals B60**; you pay for VRAM, not speed |
| Want 2–5× the speed, need 1080p, do not want to count VRAM | **B70 32 GB** (¥18,999 after the 2026-10-21 price rise) |
| Want two cards on one job | **Never tested. No answer.** |

> **Cheapest speed per tok/s** (chat only): B50 **¥93** · B60 **¥116** · B65 **¥179** · B70 **¥250**.
> After the price rise B70 has the highest cost per tok/s of the four — what it sells is the ceiling.

---

## 6. Three words and you are done

| Term | Plain English |
|---|---|
| **tok/s** | Word chunks per second. Bigger is faster — that is all you need |
| **Quantization** (Q4_0 / INT8 …) | Shrinking the model. More shrink = less VRAM, possibly dumber |
| **P90 / full load** | 90% of the time it stays under this wattage. Think "normal full load" |

---

## Two things we will not fake

**Not tested:** two cards on one job, above 1440p, sustained runs over one hour, music on B50, and the vision tower on B65.
**No guesses, no invented numbers.**

**Where to verify:** every number traces back to a file in [`../bench/data/`](../bench/data/). Status, data
location and reproduction steps for each test item are in [`test-registry.md`](test-registry.md).
