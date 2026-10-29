**English** · [简体中文](comfyui-power.md)

# GPU Power and Energy (ComfyUI measurements)

> **This page answers three questions**: how much power the card draws on these workloads, how hot it runs, and what a job costs in electricity.
> The first question is "will it run", the second "how long", the third "how big a PSU, how much cooling, what is the power bill" —
> **the TBP label cannot answer the third**, because it describes neither idle nor full load.

---

## 0. Conclusions first

**B70 at full load is 290 W, idle 51 W. Power does not track the workload; what changes is how much of the time the card is really working.**
**B60 is different: its wall is 200 W, and H3 only reaches 77% of it — at 24 GB, H3 is partially resident, so the card spends its time moving weights instead of computing (§3b).**

| Question | Answer in one line | Measured | Details |
|---|---|---|---|
| Idle watts? | **51.0 W**, swing < 0.3 W | 60 s sample, p50 = P90 = mean | §2 |
| Full-load watts? | **290 W** — matches the TBP label digit for digit | **13 of 14** cases land at P90 **290.1 to 291.6 W** (the one exception is in §5.2) | §2/§3/§4/§5 |
| Does it exceed TBP? | **Not sustained**; transients reach the **325 W** class | 1 s window peaks 291.5 to 327.1 W (range ceiling 348 W) | §3/§5 |
| Does resolution change it? | **No.** Duty cycle changes | 31.5% at 864×480 → 86.5% at 1920×1088 | §3 |
| Does duration change it? | **No.** Duty cycle climbs | 56.4% at 5 s → **89.8%** at 15 s | §4 |
| Does the model change it? | **No.** But the set of configurations that does not fit differs | Krea-2 bf16 P90 is only **93.1 W** | §5.2 |
| Does int8 save power? | **It saves time, not watts** | Same 290 W; energy gain ≈ time gain (difference < 1 pt) | §5.1 |
| B60 (24 GB)? | **P90 151 to 154 W, 75 to 77% of its 200 W wall** | H3 at three resolutions + three models, peak ≤168.9 W | §3b |
| B65 (32 GB)? | **P90 200.8 to 203.7 W, on the 200 W wall and a shade over it** | H3 at three resolutions, nine rounds, peak ≤223.5 W | §3c |
| Is electricity expensive? | **No. It is not a cost line** | 720p · 15 s = 0.099 kWh ≈ **¥0.069** | §6 |

> **What this page is for: choosing a PSU and a cooler.** Design for 290 W sustained plus 325 W transient.
> Electricity is negligible against total cost (a 15-second 720p video costs less than a tenth of a yuan).

---

## 1. How the readings are taken

| Item | Value |
|---|---|
| Source | Level Zero Sysman `zesPowerGetEnergyCounter` (hardware energy counter, µJ) |
| Average power | ΔE / Δt, numerator and denominator both from hardware; independent of the sampling interval, directly comparable across batches |
| Peak | **1 s window** peak, not an oscilloscope instantaneous peak |
| Idle | no job, no ComfyUI compute, sampled for 60 s |
| Whole round | submit prompt → finish, the same window as `server_sec` (includes loading / offload / VAE decode) |
| Whole-card domain | Sysman reports 4 domains; take the one with the largest `defaultLimit`; **domain 0 is the compute domain, about 92 W below the whole card** |

| Card | Whole-card `defaultLimit` | Measured P90 |
|---|---:|---:|
| B70 32G | 290,000 mW | 290.3 to 291.6 W |
| B65 32G | 200,000 mW | 200.8 to 203.7 W |
| B60 24G | 200,000 mW | 150.5 to 154.3 W |
| B50 16G | 70,000 mW (**unreadable**: the card is installed, Sysman reports `defaultLimit = -1 mW`) | — |

- **The average (`avg_w`) includes the loading segment** and gets diluted. Use **P90 / duty cycle** to see whether the card is pinned, and `loads == 0` to see whether anything was really resident.
- Not collected is recorded as `null`; **`null` ≠ 0 W**.

---

## 2. Idle and full load

Conditions: B70 32G (ECC off) · desktop idle, no runs from this repo (a separate always-on ComfyUI idles on this machine and is included)

| State | Whole card | Compute domain | vs idle | Stability |
|---|---:|---:|---:|---|
| **Idle** (no job, 60 s sample) | **51.0 W** | 26.9 W | 1.0× | p50 = P90 = mean = 51.0 W, **swing < 0.3 W** |
| **Full load** (H3 sampling, 1 s window P90) | **290.3 to 291.1 W** | 200.0 W | **5.7×** | 1 s window instantaneous peak **291.5 to 325.6 W** |

- **Sustained power sits on PL1**: five configurations give P90 = **290.3 / 290.3 / 290.4 / 290.5 / 291.1 W**, matching `defaultLimit = 290000 mW` digit for digit. **The answer to "how many watts does B70 draw running AI" is 290 W.**
- **Transients reach ≈325 W**: 1 s window peaks span **291.5 to 325.6 W** across the five configurations (whole-card domain range ceiling 348 W). **Design cooling for 290 W and keep transient headroom to the 325 W class.**
- **The 51 W idle figure is the boot floor**: a 720p · 5-second clip takes 270.81 s; charging the entire run at idle would still be only 13.8 kJ (≈0.0038 kWh). **Energy is decided by how long the full-load segment runs.**
- At full load the compute domain is only **69%** of the whole card (200 W / 290 W); the remaining 92 W goes to VRAM, fans and VRM.

---

## 3. H3 video: resolution dimension

Configuration: B70 · 6 steps · duration 5.0 s (124 frames) · `reserve-vram 4` · `--enable-dynamic-vram` ·
SDPA · text encoder `qwen3vl_32b_minimax_h3_nvfp4_awq` (14.61 GiB).
Every power column comes from the **fresh** round (new prompt, genuinely recomputed).

| Resolution | Pixels | fresh end-to-end | Per step | Round avg | **Median** | **P90** | Peak | Duty cycle | Energy | Energy/MP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 864×480 | 414,720 | 161.86 s | 6.68 s/it | 142.8 W | 79.7 W | **290.3 W** | 299.7 W | 32% | **23.6 kJ** | 56.9 kJ |
| 1024×576 | 589,824 | 178.62 s | 11.47 s/it | 172.1 W | 90.1 W | **290.3 W** | 291.5 W | 44% | **31.2 kJ** | 52.9 kJ |
| 1280×720 | 921,600 | 270.81 s | 25.36 s/it | 212.9 W | 289.8 W | **290.4 W** | 312.8 W | 63% | **58.0 kJ** | 62.9 kJ |
| 1536×864 | 1,327,104 | 440.30 s | 48.68 s/it | 232.6 W | 289.8 W | **290.5 W** | 314.0 W | 73% | **103.1 kJ** | 77.7 kJ |
| 1920×1088 | 2,088,960 | 833.14 s | 113.21 s/it | 261.8 W | 289.9 W | **291.1 W** | 319.6 W | 86% | **218.6 kJ** | 104.6 kJ |

| Column | What it says |
|---|---|
| **P90** | Flat at **290.1 to 291.1 W** throughout (1 W spread over five rows) — full-load power is independent of resolution and of task type |
| **Median / duty cycle** | Median 79.7 → 289.9 W, duty cycle 32% → 86%: at low resolution the card spends more than half the time loading |
| **Round avg** | The climb from 142.8 to 261.8 W comes from the load structure (the card spends less time waiting), not from the card getting faster |
| **Energy** | 23.6 → 218.6 kJ (**9.26×**) while pixels grow only 5.04×; energy/MP 56.9 → 104.6 kJ (1.84×) |
| **1 s peak** | 291.5 to 325.6 W, never above the 348 W range ceiling. Spikes almost all land in cold rounds (864×480 cold 319.8 W vs fresh 299.7 W) → **this column records what a given round did, not the resolution** |

## 3b. B60 (24 GB) on the same workload: **the wall is 200 W, and H3 reaches only 77% of it**

Configuration: B60 24G (23.33 GiB visible) · 6 steps · duration 5.0 s (124 frames) · `reserve-vram 4` · port 8189 ·
driver 9150. Whole-card domain `defaultLimit = 200000 mW` (B60's spec TBP).

| Resolution | End-to-end (4/3 rounds) | Per step | Round avg | **P90** | Peak | Energy |
|---|---:|---:|---:|---:|---:|---:|
| 864×480 | 203 to 261 s | 11.8 to 12.2 s/it | 86.0 to 91.1 W | **153.7 to 154.3 W** | 166.0 W | ≤19.2 kJ |
| 1280×720 | 427 to 437 s | 45.5 to 46.4 s/it | 114.6 to 116.7 W | **150.5 to 151.1 W** | 167.5 W | ≤50.6 kJ |
| 1920×1088 | 1328 to 1347 s | 190.7 to 191.9 s/it | 134.2 to 136.1 W | **151.4 to 152.2 W** | 168.9 W | ≤181.0 kJ |

1. **B60's P90 is only 75 to 77% of its wall**: H3 runs partially resident (3,728 MB offloaded at 864×480 → 10,769 MB at 1920×1088), each step carries weight movement, and the card never reaches 200 W. B70 on the same workload is fully resident with P90 flat at 290 W — **"full load pinned to the wall" is itself a side effect of "it fits"**.
2. **P90 barely moves with resolution** (153.7 → 151.4 W, in fact slightly down); what climbs is the round average (86.0 → 134.2 W), the same direction as B70.
3. **None of the three generation models hit the wall either**: Qwen-Image 2.1 P90 148.4 to 150.0 W (peak 150.4), Krea-2 71.3 to 147.3 W (peak 148.4), Music 3 137.8 to 139.3 W (peak 163.2).
4. **A 200 W PSU per spec is enough** (measured peak ≤168.9 W, headroom >15%); compute electricity from measured P90, not from TBP.

---

## 3c. B65 (32 GB) on the same workload: **against the 200 W wall at all three resolutions**

Configuration: B65 32G (31.16 GiB visible) · 6 steps · duration 5.0 s (124 frames) · `reserve-vram 4 --enable-dynamic-vram` ·
port 8189 · driver 9150. Whole-card domain `defaultLimit = 200000 mW` (B65's spec TBP).

| Resolution | End-to-end (cold / fresh / cached) | Per step | Round avg | **P90** | Peak | Duty cycle | Energy |
|---|---:|---:|---:|---:|---:|---:|---:|
| 864×480 | 227.71 / 198.12 / 198.53 s | 10.65 s/it | 113.9 to 121.6 W | **200.8 W** | 221.6 to 222.7 W | 36 to 42% | 24.4 to 26.3 kJ |
| 1280×720 | 437.11 / 394.06 / 382.92 s | 42.30 s/it | 151.8 to 165.9 W | **202.0 to 202.8 W** | 216.8 to 222.2 W | 65 to 74% | 64.0 to 67.6 kJ |
| 1920×1088 | 1,338.33 / 1,326.17 / 1,314.04 s | 188.64 s/it | 179.4 to 181.8 W | **203.3 to 203.7 W** | 221.1 to 223.5 W | 89 to 91% | 239.4 to 240.4 kJ |

> ✅ **Re-checked 2026-10-25: the attribution in this table holds.** With both cards installed, sampling was redone per PCI bus (`power_probe_multi.py`, delivery configuration):
> P90 **200.3 / 201.8 / 204.3 W**, 1 s peak **222.4 / 215.1 / 219.0 W** — within **0.2 to 2%** of this table, row by row.
> Only per-run energy moved (480p 24.4 to 26.3 → **35.1 kJ**, 720p 64.0 to 67.6 → **70.7**, 1080p 239.4 to 240.4 → **250.0**),
> and the cause is entirely **longer loading**; per-step times did not move (11.03 / 42.53 / 191.53 s/it). See `cards/B65-README.md` §7.

**Three cards, three shapes on one workload** (864×480):

| | B60 24G (200 W wall) | **B65 32G (200 W wall)** | B70 32G (290 W wall) |
|---|---|---|---|
| P90 | **153.7 to 154.3 W (77%)** | **200.8 W (100%)** | 290.1 to 291.6 W (100%) |
| Fully resident? | No (3,728 MB offloaded per round) | No (2 offloads per round) | **Yes (0 offloads)** |
| Per step | 11.8 to 12.2 s/it | **10.65 s/it** | 6.64 s/it |

1. **Same 200 W wall, same 20 Xe2 cores: B65 sits on the wall, B60 reaches only 77%.** Neither card fits H3; both move weights. So "pinned to the wall or not" can no longer be explained by "it fits". 🔴 **No controlled test was run, no cause given** — only two measurable differences exist: per step 10.65 vs 11.8 to 12.2 s/it, bandwidth 608 vs 456 GB/s.
2. **P90 can sit slightly above the nominal wall** (203.3 to 203.7 against 200.0, 1.7 to 1.9% over) → **design cooling for 200 W sustained plus 224 W transient**; "on the wall" does not mean "never over it".
3. **Resolution changes only the duty cycle** (36 to 42% → 65 to 74% → 89 to 91%), never P90.


**Duration dimension (1280×720 · 6 steps · duration only; all three points are `cold`)**

| Duration | End-to-end | Round avg | **P90** | Peak | Duty cycle | Energy |
|---:|---:|---:|---:|---:|---:|---:|
| 5 s | 437.11 s | 151.8 to 165.9 W | 202.0 to 202.8 W | 216.8 to 222.2 W | 65 to 74% | 64.0 to 67.6 kJ |
| 10 s | 1,166.44 s | 170.9 W | **204.1 W** | 222.3 W | **81.9%** | **199.6 kJ** |
| 15 s | 2,149.75 s | 183.1 W | **203.7 W** | 223.1 W | **92.0%** | **394.1 kJ** |

> **Duration behaves like resolution: duty cycle only, P90 unchanged** (202.0 → 204.1 → 203.7 W, all a shade over the 200 W wall).
> A 15-second clip: **394 kJ ≈ ¥0.077** (0.7 yuan per kWh) — estimate a long clip as "seconds × power" and it holds; estimate by "number of clips" and you are off by an order of magnitude.

4. **⭐ B65 draws more energy than B70**: on the same 1080p · 5 s job, B65 **240 kJ ≈ ¥0.047**, B70 218.6 kJ ≈ ¥0.043, B60 181 kJ ≈ ¥0.035. Power is 30% lower but the card is 58% slower, and the product is 11% more energy → **billing per job, "the lower-power card is cheaper to run" does not hold; only billing per hour makes it true.**

---

## 3d. B65 image and music generation: about 3.3 kJ per image, about 25 kJ per 120 s track

Configuration as in §3c (B65 32G · driver 9150 · port 8189 · whole-card domain `defaultLimit = 200000 mW`).
**Only steady-state rounds with `loads=0` are used** (the first round includes loading, so its power and energy do not represent steady state); the two music rounds are `loads=1`, see item 4 below.

| Workload | Steady-state time | Round avg | **P90** | Peak | Duty cycle | Energy per round |
|---|---:|---:|---:|---:|---:|---:|
| Qwen-Image 2.1 int8 · 1280×720 · 25 steps | **16.13 / 16.19 s** | 185.2 to 185.7 W | **204.2 to 205.7 W** | 207.0 W | 83 to 88% | **3,336.7 / 3,345.0 J** |
| Krea-2 Turbo int8 · 1280×720 · 8 steps | **8.74 / 8.73 s** | 191.9 to 196.8 W | **207.0 to 208.2 W** | 208.3 W | 89% | **1,729.1 / 1,733.5 / 1,772.8 J** |
| Music 3 · 120 s · 30 steps · `reserve 2` | **180.85 / 180.21 s** | 138.4 / 139.2 W | **195.4 / 195.6 W** | 219.0 W | 49% | **25,108.6 / 25,381.9 J** |

1. **Image generation also sits on the wall** (P90 204 to 208 W, the same band as video's 200.8 to 203.7 W), duty cycle 83 to 89%; the rest is loading and pre/post-processing.
2. **Electricity per image is negligible**: 3,340 J ≈ **¥0.00065**; the Krea-2 image ≈ **¥0.00034**. Image generation is not a reason to pick a card; what separates them is the wall (290 vs 200 W) and the time.
3. **Music generation is the most energy-hungry thing this card does**: a 120 s track **25.1 to 25.4 kJ ≈ ¥0.0049**, **7.5×** a single image.
4. ⚠️ **The `reserve 4` group cannot go in the table**: every round reloads all three components (`loads=3`) and the four rounds are still falling (310 → 301 → 237 → 225 s), so repeated loading is mixed into the 30.9 to 37.8 kJ → **same card, same model, a different reserve setting moves energy by 20 to 50%**.
5. ⚠️ Qwen-Image round 4 has `counter_resets=1` → energy uses only the first two steady-state rounds; that round's P90 is still usable.

---

## 3e. Both cards at full load: combined P90 400.8 W, no cross-card clock drop (2026-10-23)

Conditions: 2× B65 · one ComfyUI instance per card, generating simultaneously (Qwen-Image 2.1 int8 · 1280×720 · 25 steps) ·
**each card's own whole-card power domain**, 1 s sampling

| Case | Card 0 (bus 3 · CPU-attached x16) | Card 1 (bus 16 · chipset x4) | Combined |
|---|---|---|---|
| Card 0 only | avg 195.6 / P90 205.5 / peak 208.0 W | idle 44.9 W | — |
| Card 1 only | idle 51.3 W | avg 185.7 / P90 200.0 / peak 201.9 W | — |
| **Both at once** | avg 196.1 / P90 **206.0** / peak 208.4 W | avg 190.3 / P90 **201.3** / peak 203.3 W | **P90 400.8 / peak 406.5 W** |

- **No mutual throttling**: with both cards at full load, each P90 matches its solo run (card 0 206.0 vs 205.5, card 1 201.3 vs 200.0),
  and generation time does not move either (16.17 / 16.25 s vs 16.18 / 16.18 s solo).
- **Sizing the PSU**: GPU side peak **406.5 W** + CPU (R5 9600X at full load roughly 90 to 140 W) + board / memory / drives ≈ **550 to 600 W**.
  The machine's 850 W unit (ATX 3.0 / PCIe 5.0) is enough; the combined P90 of 400.8 W already includes the stretch where both cards peak at once.
- ⚠️ **Sampling trap**: `power_sampler.py` only samples Sysman's **device 0**, so with two cards it always reads the same card
  (on this machine Sysman dev0 = bus 16 = card 1), and Sysman order ≠ `level_zero:N`.
  Two-card power must come from `power_probe_multi.py`, attributed by PCI bus.
  **Measured directly on 2026-10-25**: at the same instant the idle card (bus 16) read **44.8 W** and the working card (bus 3) **156.3 W**,
  while the probe built into `bench_f_h3.py` reported 43 W avg / 45 W peak for that round — that was the idle card.
  So **with two cards installed, `samples[].power` is never trustworthy**; power figures come only from the `power_probe_multi.py` CSV.
  To check for yourself, see whether P90 sits on the card's `defaultLimit` (B65 = 200 W, B70 = 290 W); only a real load pins the wall.

---

## 4. H3 video: duration dimension → energy per video second

Configuration: B70 · 1280×720 · 6 steps · `reserve-vram 4` · `--enable-dynamic-vram` ·
text encoder `qwen3vl_32b_minimax_h3_nvfp4_awq` (nvfp4 tier, 14.61 GiB).

**All three points are single cold rounds** (`--fresh 0 --cached 0`, all genuinely recomputed), so they compare directly within this section.
⚠️ **Do not compare this section's 5 s against §3's 720p row**: the §3 table is **fresh** rounds; the same configuration in a fresh round runs
270.81 s / 58.0 kJ end-to-end, while cold here is 301.73 s / 60.4 kJ — **the 4% gap is one extra load, not measurement noise.**

| Duration | Frames | cold end-to-end | Per step | Round avg | **P90** | Duty cycle | Energy | **Energy per video second** | Energy per frame |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **5 s** | 124 | 301.73 s | 25.42 s/it | 197.8 W | **290.3 W** | 56.4% | **60.40 kJ** | 12.08 kJ/s | 487 J |
| **10 s** | 243 | 719.02 s | 91.30 s/it | 248.6 W | **291.6 W** | 80.4% | **179.45 kJ** | 17.94 kJ/s | 738 J |
| **15 s** | 362 | 1,323.84 s | 188.19 s/it | 267.8 W | **290.6 W** | 89.8% | **355.05 kJ** | 23.67 kJ/s | 981 J |

1. **P90 holds at 290.3 to 291.6 W** (1.3 W spread), consistent with the resolution dimension: **compute longer or compute larger, full load is still 290 W**.
2. **Time scales as p ≈ 1.87, energy as p ≈ 1.65**: duty cycle 56.4% → 89.8%; the longer the video, the smaller the loading segment's share of one end-to-end run → **the same electrons buy more on long clips**.
3. **Energy per video second 12.08 → 23.67 kJ/s (1.96×)**, not a constant; energy per frame 487 → 981 J (2.01×).
4. **The 15 s case reaches 89.8% duty cycle**, the fullest in the whole set (above 1920×1088's 86.5%) → **to keep B70 pinned at full load, stretch duration rather than resolution**.

---

## 5. Image and music generation: three models × two quantization tiers

B70 · 1280×720 · `reserve-vram 4` · single generation · **steady-state average over three rounds** (`resident`×2 + the new-prompt round).
`loads` = number of model reloads in that round; **it is the key to reading this table**.

| Model | Quantization | Steady-state end-to-end | loads | Steady energy per run | Avg power | **P90** | Duty cycle |
|---|---|---:|---:|---:|---:|---:|---:|
| **Qwen-Image 2.1** | bf16 | 14.05 s | **0** | 4.14 kJ | 269.4 W | **291.0 W** | 89.2% |
| **Qwen-Image 2.1** | int8 | 10.80 s | **0** | 3.20 kJ | 266.6 W | **291.1 W** | 86.1% |
| **Krea-2** | bf16 | **127.74 s** | **3** | **10.82 kJ** | **82.4 W** | **93.1 W** ⚠️ | **5.6%** |
| **Krea-2** | int8 | **6.08 s** | **0** | **1.93 kJ** | 214.7 W | **291.4 W** | 55.6% |
| **Music 3** | bf16-TE | 232.95 s | 3 | 39.16 kJ | 165.7 W | **290.1 W** | 30.9% |
| **Music 3** | int8-TE | 193.73 s | 3 | 32.74 kJ | 167.5 W | **290.2 W** | 29.7% |

> The steady state for the two Music 3 rows uses only rounds with `loads == 3`: one bf16-TE `resident` round reloads just 1 time
> (158.53 s / 30,156 J), 1.5× away from the 237.02 s / 39,940 J of the 3-reload rounds.
> **Rounds with different `loads` under the same role name cannot share an average** — otherwise "int8 is 17% faster" becomes "30% faster".

### 5.1 ⭐ Quantization does not change power, only time — so the energy gain ≈ the time gain

| Model | Time gain (int8 vs bf16) | **Energy gain** | Gap between them |
|---|---:|---:|---:|
| Qwen-Image 2.1 | −23.1% | **−22.5%** | 0.6 pt |
| Music 3 | −16.8% | **−16.4%** | 0.4 pt |
| Krea-2 | −95.2% | **−82.1%** | 13.1 pt |

The first two rows agree within 1 percentage point — **because int8 and bf16 both hold P90 at 290 W: identical watts**.
Every joule saved comes from finishing sooner: `E ≈ P90 × time`.
**So "int8 saves power" is wrong. The correct statement is "int8 computes faster, so each run spends less energy".**

### 5.2 ⭐⭐ Krea-2 bf16 is the only counterexample, and it writes "does not fit" in power draw

Krea-2 bf16 totals **32,916 MB > 31,907 MB whole card** → it reloads every round (`loads = 3`),
which produces a shape no other tier shows:

- **P90 only 93.1 W**, duty cycle **5.6%** — the card spends 94% of its time waiting on disk and never gets pinned.
  This is the only tier in the repo with P90 far below 290 W; **seeing it means the configuration does not fit, no need to dig through the size accounting**.
- **Time 21.0×, energy only 5.6×** — because the loading segment draws little power (around 82 W, roughly 1.6× the 51 W idle).
  **The cost of "does not fit" lands on time, not on the bill**: losing 20× the time in a day far outweighs those few kWh.
- **Do not describe it as "bf16 is power-hungry"** — bf16 steady state is 10.82 kJ per image, int8 is 1.93 kJ;
  most of the 8.9 kJ difference is **the extra loading**, not compute. **This is a capacity problem, not a quantization problem.**

### 5.3 How Music 3 differs from image and video: higher peaks

**6** of Music 3's eight rounds have a 1 s peak ≥ **318 W** (max **327.1 W**), a touch above H3's 325.6 W.
The audio VAE decode segment is short and dense, so **boost stacks onto full load more easily**. Cooling is still designed for 290 W, but **music workloads need generous transient headroom**.

> **Electricity across the three load types** (at ¥0.7/kWh — **China Southern Power Grid residential reference rate**; use your local bill):
> one image (Qwen-Image 2.1 bf16 steady state) 4.14 kJ ≈ **¥0.0008**; Krea-2 int8 1.93 kJ ≈ ¥0.0004;
> one 5-second music track (Music 3 bf16-TE) 39.16 kJ ≈ **¥0.0076**; one 720p · 15 s video 355 kJ ≈ ¥0.069.
> **The magnitudes are far apart**: images draw almost nothing; video is what the PSU and cooling design must target.

---

## 6. One-line conclusion

### 6.1 The one-line version

> **B70 on these workloads: full load is 290 W — the same as the TBP label; idle is 51 W.**
> **Power does not change with how big or how long the job is; what changes is how much of the time the card is really working.**

### 6.2 The four most-asked questions

| Question | Answer | Basis |
|---|---|---|
| **How big a PSU?** | Size a single card at **290 W sustained + 325 W transient**; then add CPU and system headroom | §2, §3 |
| **What wattage should cooling be designed for?** | **290 W**. The 1 s window peaks at up to 325 W, but the sustained state never parks at 325 W | §2, §3 |
| **Does full load exceed the label?** | **No.** H3 covers **13 rounds** (five resolutions each cold/fresh, plus three durations); P90 stays within 290.3 to 291.6 W and never touches the 348 W whole-card range ceiling | §3, §4 |
| **What does electricity cost?** | 720p · 5 s ≈ **0.017 kWh**; 1080p · 5 s ≈ **0.061 kWh**; 720p · 15 s ≈ **0.099 kWh** | §3, §4 |

### 6.3 Common misconceptions

| Misconception | Reality |
|---|---|
| "B70 is a 290 W card, so it draws 290 W running AI" | True only at **full load**. At 864×480 the duty cycle is 31.5% and the round average is **142.8 W** — a meter reading 143 W **does not mean the spec is inflated** — the card is waiting on disk |
| "Lowering resolution saves power" | It saves **time**, not watts. The full-load segment is always 290 W |
| "Use the compute-domain reading as whole-card power" | The compute domain (domain 0) reports only **200 W** at full load, about 92 W below the whole card (VRAM / fans / VRM). **Always report the whole-card domain** |

---

## 7. Reproduce

```bash
# Standalone sampling (runs alongside any job, independent of this project's harness)
python bench/harness/power_sampler.py --out p.csv --interval 1.0   # touch p.stop when you are done
python bench/harness/power_sampler.py --out p.csv --duration 60    # fixed length, measures the idle baseline

# Automatic sampling during benchmark runs (on by default since 2026-10-19, disable with --no-power)
python bench_f_h3.py --tag <tag> --expect-card B70 --steps 6 --duration 5.0 \
       --width 1280 --height 720 --reserve-vram 4
python sweep.py --suffix b70pw --expect-card B70 --reserve-vram 4
```

This produces `p.csv` (`t,iso,dom,w,e_uj,dt_sec`, flushed every row) and `p.meta.json` (power-domain list plus the whole-card domain index).
At startup the harness prints the whole-card domain it found and its `defaultLimit`; if it finds none it degrades automatically and the run is not interrupted.
⚠️ `bench_f_h3.py` / `sweep.py` must use the interpreter bundled with that ComfyUI; `power_sampler.py` depends only on `ze_loader`, so any python can run it.

---

## 8. Not measured yet

| # | Gap |
|---|---|
| 1 | **B50 (16 GB tier) is unreadable**: the card has been installed since 2026-10-22, the whole-card `defaultLimit` reports **-1 mW**, and the watts it yields (peak 198 to 206 W) clearly contradict the 70 W spec, so none of it is quoted. **B60 is measured** (P90 150 to 154 W, wall not reached). **B65 is measured (2026-10-21)**: wall `200000 mW`, H3 at two resolutions P90 **200.8 to 202.8 W** (on the wall), 1 s peak 216.8 to 222.7 W, duty cycle 36 to 74% — ⚠️ **B60 and B65 share a 200 W TBP, yet one pins the wall and the other does not**; the difference is "does it fit" (B60 at 24 GB cannot hold DiT+TE and swaps constantly) |
| 2 | **2560×1440 and above are untested** (the resolution dimension has not reached there either); **there is no "larger" tier above 1920×1088**, so whether power keeps climbing with pixels cannot be answered yet |
| 3 | The whole-card vs compute-domain difference (≈90 W) **has not been broken down**: how much goes to VRAM / fans / VRM is not reported per-domain by Sysman |
| 4 | Whole-card power under **multi-card concurrency** was unmeasured — **measured 2026-10-23** (2× B65, see §3e: combined P90 400.8 W / peak 406.5 W, no cross-card clock drop). Still missing: power for video + video at the same time (that shape does not fit in 32 GB of memory, see `slot-comparison.md` §6.5) |
| 5 | **No long-run full-load stability data**: every case is a single round of ≤22 minutes. **Whether clocks drop after 1 hour or more at continuous full load** (thermal wall / VRM headroom) was not tested — the one question left unanswered by "can it run 7×24" |
| 6 | The sampling interval is fixed at 1 s. **Sub-second transients** (millisecond current spikes) are invisible; whether the 1 s peak is a conservative lower or upper bound for transient-based PSU sizing is unverified |
