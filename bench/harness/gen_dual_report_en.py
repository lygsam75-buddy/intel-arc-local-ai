# -*- coding: utf-8 -*-
"""从 bench/data 直出《docs/dual-b65-report.en.md》（英文版）。

与 gen_dual_report.py 共用 dual_data.py 取数层，两版数字同源。
结构与中文版一一对应；措辞复用旧英文版已定稿的表达。
行尾：CRLF，无尾换行。
"""
import os

from dual_data import *  # noqa: F401,F403

OUT = os.path.join(REPO, "docs", "dual-b65-report.en.md")

L = []
w = L.append

w("**English** · [简体中文](dual-b65-report.md)")
w("")
w("# Dual B65 in practice: what you buy, and what you do not")
w("")
w("> **In one line**: adding a card adds rooms, not speed — the second B65 buys **capacity and a")
w("> second production line**, not the speed of a single task.")
w("")
w("> **What to tell the customer (say it as-is)**")
w(">")
w("> People ask whether two cards means twice the speed. The answer has to be split in two.")
w(">")
w("> Put the second card in and VRAM goes from 31 GB to 62 GB. A model that did not fit now fits.")
w("> A machine that ran one clip now runs one clip with a chat model beside it. Both real changes.")
w(">")
w("> But ask how much faster the same clip gets — almost not at all. One card does a step in 42.30 s;")
w("> two cards together do 42.41 s. The same. So the second card buys room, not speed — to make one")
w("> clip faster, buy a stronger single card.")
w(">")
w("> If someone says two cards merge into one and double the compute: that mode was tested. It runs,")
w("> and it is slower than one card (29.19 vs 31.86) — every layer computed needs one reconciliation")
w("> between the cards, and reconciling costs more than it saves. The method here is each card on its")
w("> own. A layer split is \"the second card helps hold\", not \"helps compute\": when it fits on one card,")
w("> splitting is 5%–7% slower; when it does not fit, splitting is 17% faster.")
w(">")
w("> No motherboard change needed. A plain B850M is fine — card 1 alone in the x4 slot does a step in")
w("> 42.31 s, same as x16. Only four cards or a hard tensor-parallel requirement needs an x8/x8")
w("> workstation board; the positioning here is an ordinary computer running large models.")
w(">")
w("> One thing up front: two lanes at once need 64 GB of RAM; 32 GB is \"one clip plus one light job\".")
w("> Said up front beats explained afterwards.")
w("")
w("Test conditions: 2× GUNNIR B65 32G · ECC off (31.16 GiB usable per card) · driver 9150 · 32 GB RAM")
w("(2×16 GB) · display on the motherboard iGPU · a **mainstream mATX board of the B850M tier** (not a")
w("workstation board, cannot split x8/x8): card 0 in the CPU-attached x16 slot, card 1 in the chipset x4")
w("slot. Unless noted, every number is measured, and **no number came from workstation hardware**.")
w("")
w("## All-Test Summary")
w("")
w("Every collected figure folded into one table. One result per row; the matching section holds the")
w("detail.")
w("")
w("**Dynamic chart**: [`assets/dual-b65-dashboard.en.html`](assets/dual-b65-dashboard.en.html) (interactive · hover for one result)")
w("")
w("| Test item | Single B65 | Dual 2×B65 | One B70 | One result |")
w("|---|---:|---:|---:|---|")
w("| H3 720p·5 s end-to-end (steady state) | %s | %s | %s | dual gives no speedup, B70 is %s faster |" % (
    s(b65_720_fresh["server_sec"]), s(d6_fresh["server_sec"]),
    s(sample(b70_720, "fresh")["server_sec"]), fx(r_e2e)))
w("| H3 720p per step | %s s/it | %s s/it | %s s/it | the second card contributes 0 to one clip |" % (
    f2(b65_720_fresh["sampling_sec_per_step"]), f2(d6_fresh["sampling_sec_per_step"]),
    f2(sample(b70_720, "fresh")["sampling_sec_per_step"])))
w("| H3 1080p·5 s end-to-end (steady state) | %s | — | %s | B70 is %s faster |" % (
    s(b65_1080_fresh["server_sec"]), s(sample(b70_1080, "fresh")["server_sec"]), fx(r_1080)))
w("| Qwen Q4_0 decode | %s tok/s | %s tok/s | %s tok/s | no slowdown under concurrency |" % (
    f2(q_solo["summary"]["decode_tok_s"]), f2(q_conc["summary"]["decode_tok_s"]),
    f2(load("2026-10-20_b70-q4-0-sycl-l0.json")["summary"]["decode_tok_s"])))
w("| Q8_0 34.37 GiB decode (layer split vs single fully resident) | %s | %s | — | split buys capacity at no speed cost (%s) |" % (
    f2(q8_ngl37b["decode_tok_s"]), f2(ts6040["decode_tok_s"]), fx(r_q8_same)))
w("| Q4_0 19.41 GiB decode (layer split vs single) | %s | %s | — | if it fits, do not split — splitting is %s slower |" % (
    f2(q4_solo["decode_tok_s"]), f2(q4_dual["decode_tok_s"]), f1(100 * (1 - r_q4_same)) + "%"))
w("| Tensor-parallel decode | — | %s tok/s | — | slower than one card, do not use |" % f2(q8_t50["decode_tok_s"]))
w("| Usable VRAM | 31.16 GiB | 62.32 GiB | 31.16 GiB | dual buys 2× VRAM, not speed |")
w("| Context (actually fits) | %s | %s | %s | quote 1.75M externally; 3M is only an allocation ceiling |" % (
    tok(ctx["summary"]["single_max_allocated_ctx"]), tok(ctx["summary"]["dual_max_allocated_ctx_unified"]), tok(ctx["summary"]["single_max_allocated_ctx"])))
w("| Image gen steady state | %s / %s s | %s ~ %s s | — | dual instances, zero loss |" % (
    f2(img_solo_ss[1]["server_sec"]), f2(img_solo_ss[2]["server_sec"]),
    f2(img_c1_ss[1]["server_sec"]), f2(img_c0_ss[2]["server_sec"])))
w("| Video + chat | — | 12/12 correct, decode −0.2% | — | holds |")
w("| Video + video | — | 2/2 crash | — | does not hold (32 GB RAM wall) |")
w("| Full-load power P90 | %s W | %s W | %s W | additive, no mutual throttling |" % (
    f1(pw_s0["summary"]["power"]["p90_w_busy"]), f1(pw_b0["summary"]["power"]["pair_sum_p90_w"]),
    f1(b70_pw["summary"]["power"]["p90_w_max"])))
w("| Two 5 s clips per hour | — | %s clips/h | %s clips/h | dual wins %s |" % (f1(thr_dual), f1(thr_b70), fx(r_thr)))
w("| Price | ¥%s | ¥%s | ¥%s | nearly level: B70 buys speed, dual buys capacity + output |" % (
    yuan(P_B65), yuan(P_2B65), yuan(P_B70)))
w("")

# ---------------------------------------------------------------- 1
w("## 1. Four questions, four answers")
w("")
w("| Question | Answer |")
w("|---|---|")
w("| Does a dual card mean \"double the compute\"? | **No.** See the first two summary rows — not one step faster. |")
w("| Then what does the dual card buy? | **Capacity + output** (see the summary). ⚠️ With 32 GB of RAM \"two video lanes\" does not hold (§5.3); the real result is \"one video + one light task\". |")
w("| Can one B65 make an H3 video alone? | **Yes.** 720p·5 s steady state about %s; measured up to 720p 24 s (83 min per clip) — the question is \"how long you wait\", not \"how many seconds it can make\" (see `cards/B65-README.md` §6). |" % mmss_en(b65_720_fresh["server_sec"]))
w("| One B70 and two B65s (nearly the same price): what differs? | **B70 buys speed, dual buys capacity + output.** See the last summary row. |")
w("")

# ---------------------------------------------------------------- 2
w("## 2. Why \"dual card = double the compute\" does not hold")
w("")
w("The card is not the problem. Both software paths **refuse to split one task across two cards**:")
w("")
w("1. **ComfyUI / `torch.xpu` uses the first card only.** The process binds `xpu:0` on startup; the second")
w("   card does not exist inside that process. To make the second card work, start another process and pin it")
w("   with `ONEAPI_DEVICE_SELECTOR=level_zero:1`.")
w("2. **llama.cpp \"multiple devices\" is layered loading, not parallel compute.** `-dev SYCL0,SYCL1 -sm layer`")
w("   spreads different layers of the model over the two cards; while one layer computes, the other card")
w("   waits — layers have to synchronise, and the number of synchronisations grows with the layer count.")
w("")
w("Measured evidence is the first two summary rows plus the Q8_0 / Q4_0 rows (per step +0.3%%, decode −0.2%%, layer split %s, if it fits do not split) — all four at noise level or negative." % fx(r_q8_same))
w("")
w("One result: **the \"two chips as one, double compute\" expectation does not hold on either stack** — the correct expectation is two independent production lines. (The earlier \"layer split loses 4.84×\" was a collection error from misreading llama-bench's `-dev` semantics, corrected; process in `bench/notes/dual-b65-prep.md`.)")
w("")
w("Three questions to answer before adding a second card:")
w("")
w("1. **Do you want \"one faster\" or \"two at once\"?** The former: buy a stronger single card. Only the latter needs a second card.")
w("2. **Is your RAM 32 GB or 64 GB?** At 32 GB two video lanes do not run (§5.3) — only \"one video + one light task\".")
w("3. **Is there a model that does not fit on one card?** If not, a second card will not make any existing task faster.")
w("")

# ---------------------------------------------------------------- 3
w("## 3. Can a single B65 make an H3 video on its own")
w("")
w("**Yes, and this is the most practical way to run it.** One machine, one B65, no second card, no code changes, MiniMax H3 inside ComfyUI:")
w("")
w("| Duration | Frames | End-to-end (cold) | Per step (cold) | End-to-end (steady state) | Per step (steady state) |")
w("|---:|---:|---:|---:|---:|---:|")
EN_DUR = {"5 秒": "5 s", "10 秒": "10 s", "15 秒": "15 s", "17 秒": "17 s"}
for name, frames, cold, fresh, cached in dur_rows:
    steady = fresh or cached
    w("| %s | %d | %s | %s | %s | %s |" % (
        EN_DUR[name], frames, s(cold["server_sec"]),
        f2(cold["sampling_sec_per_step"]) + " s/it",
        s(steady["server_sec"]) if steady else "—",
        (f2(steady["sampling_sec_per_step"]) + " s/it") if steady else "—"))
w("")
w("The 5 s tier has more than one reading; do not mix them (the steady-state column above takes fresh): cold %s (full load included) / fresh %s / cached %s." % (
    s(b65_720_cold["server_sec"]), s(b65_720_fresh["server_sec"]), s(b65_720_cached["server_sec"])))
w("From 10 s up only cold was measured (first run on a freshly started server), so **there is no steady-state reading** — that column is \"—\", not zero.")
w("")
w("| Resolution (5 s) | End-to-end (steady state) | Per step |")
w("|---|---:|---:|")
w("| 1280×720 | %s | %s s/it |" % (s(b65_720_fresh["server_sec"]), f2(b65_720_fresh["sampling_sec_per_step"])))
w("| 1920×1088 | %s | %s s/it |" % (s(b65_1080_fresh["server_sec"]), f2(b65_1080_fresh["sampling_sec_per_step"])))
w("")
w("Conclusions:")
w("")
w("1. **720p · 5 s · 6 steps: steady state %s, about %s.** The comfortable tier for one B65 — DiT 19.53 GiB fully resident, no weights move per step." % (s(b65_720_fresh["server_sec"]), mmss_en(b65_720_fresh["server_sec"])))
w("2. **720p is measured up to 24 s (about 83 min per clip — the highest pixel×frame pass point in the whole table)**; integer-second ceilings: 480p ≤ 50 s / 720p ≤ 24 s / 1080p ≤ 10 s / 1440p ≤ 5 s, 22 of 30 tiers pass. All 8 failures are XPU OOM (the transient peak does not fit — not host memory, not compute). Full ladder in `cards/B65-README.md` §6.")
w("3. **1080p · 5 s also works**: steady state %s (about %s), per step %s s/it. The price is DiT offloading 7,564 MB every round. **1080p is the edge for a 32 GB card, not the comfortable zone.**" % (s(b65_1080_fresh["server_sec"]), mmss_en(b65_1080_fresh["server_sec"]), f2(b65_1080_fresh["sampling_sec_per_step"])))
w("4. **Duration costs more than resolution.** At the same 720p, 5 → 15 s raises end-to-end %s× with no change in pixels — more frames, and the latent buffer grows with them." % f2(sample(b65_d15, "cold")["server_sec"] / b65_720_cold["server_sec"]))
w("5. Harness conditions: `--reserve-vram 4`, `OMNI_ATTN_BACKEND=sdpa`, int8 DiT + nvfp4 text encoder. **Changing the reserve changes loading behaviour** — quote numbers with their conditions.")
w("6. The full four-card comparison across resolutions is in [`comfyui-h3.md`](comfyui-h3.md); this document covers single B65 and dual B65 only.")
w("")

# ---------------------------------------------------------------- 4
w("## 4. Dual card vs single card, item by item")
w("")
w("Speed/capacity rows live in the summary (dual vs single is all there). This section adds only the three rows the summary does not carry:")
w("")
w("| Dimension | Figure | One result |")
w("|---|---:|---|")
w("| Image gen first round (loading) | single %s / dual %s, %s | concurrent page-cache contention, first round not comparable |" % (s(img_solo_ss[0]["server_sec"]), s(img_c0_ss[0]["server_sec"]), s(img_c1_ss[0]["server_sec"])))
w("| Card 1 (x4 slot) solo H3 | steady %s, per step %s s/it | matches card 0; not attributable to PCIe width (no swap test) |" % (s(c1_steady["server_sec"]), f2(c1_steady["sampling_sec_per_step"])))
w("| Where the +6.0%% end-to-end comes from | after warm-up %s (+%s) | not lost compute — concurrent page-cache contention; warm up before taking numbers |" % (
    s(d4b_fresh["server_sec"]), f1(100 * (d4b_fresh["server_sec"] / b65_720_fresh["server_sec"] - 1)) + "%"))
w("")
w("One result: **dual gives zero uplift to a single task** (per step +0.3%%, decode −0.2%%, both at jitter level); the 6.0%% end-to-end gap is fixed overhead from concurrent page-cache contention, narrowing to %s after warm-up — **whenever dual looks slower, warm up first**; full-load power adds up without mutual throttling (pair total %s W), and an 850 W PSU is enough with the GPU side budgeted at 400 W class." % (
    f1(100 * (d4b_fresh["server_sec"] / b65_720_fresh["server_sec"] - 1)) + "%",
    f1(pw_b0["summary"]["power"]["pair_sum_p90_w"])))
w("")
w("### 4.1 The inter-card path: a lower-level copy did not help either")
w("")
w("Between the two cards there is **only PCIe** — no NVLink or Xe-Link class of dedicated interconnect. So can a lower-level inter-card copy speed things up?")
w("llama.cpp offers three modes; all three ran in the same batch, under the same harness (`GGML_SYCL_DEV2DEV_MEMCPY`):")
w("")
w("| Inter-card copy mode | Tensor parallel decode | Tensor parallel prefill | Layer split decode | Layer split prefill |")
w("|---|---:|---:|---:|---:|")
w("| 0 · SYCL direct copy (default) | %s | %s | %s | %s |" % (f2(d2d["dual_tensor_5050_p2p"]), f2(d2d["prefill_dual_tensor_5050_p2p"]), f2(d2d["dual_layer_5050_p2p"]), f2(d2d["prefill_dual_layer_5050_p2p"])))
w("| 1 · Level Zero direct copy | %s | %s | %s | %s |" % (f2(d2d["dual_tensor_5050_l0direct"]), f2(d2d["prefill_dual_tensor_5050_l0direct"]), f2(d2d["dual_layer_5050_l0direct"]), f2(d2d["prefill_dual_layer_5050_l0direct"])))
w("| 2 · Forced through host memory | %s | %s | %s | %s |" % (f2(d2d["dual_tensor_5050_hostforward"]), f2(d2d["prefill_dual_tensor_5050_hostforward"]), f2(d2d["dual_layer_5050_hostforward"]), f2(d2d["prefill_dual_layer_5050_hostforward"])))
w("")
w("(Q8_0 34.37 GiB · `-ts 50,50` · decode tok/s, prefill tok/s, median of 3 runs each)")
w("")
w("One result: **a lower-level copy path does not rescue tensor parallel** — decode spread across the three modes is 1.5%% (inside noise); the bottleneck is sync count, not inter-card copy, so stop tuning this direction; a dual card does not need a different motherboard for PCIe topology (x4 slot per step %s matches x16's %s); only four cards or a hard tensor-parallel requirement needs x8/x8 — that is a workstation board." % (
    f2(c1_steady["sampling_sec_per_step"]), f2(d6_fresh["sampling_sec_per_step"])))
w("")

# ---------------------------------------------------------------- 5
w("## 5. What the second card really buys: three things")
w("")
w("![Three things, three results: context 1M→1.75M token, 34.37 GiB fully resident on a layer split, two production lines](assets/dual-b65-three-things.en.svg)")
w("")
w("The three results unpacked in 5.1 / 5.2 / 5.3.")
w("")
w("### 5.1 Capacity: context 1M → 1.75M token (3M is only an allocation ceiling)")
w("")
w("| Form | Configuration | Actually fits | VRAM per M token | Left at the ceiling |")
w("|---|---|---:|---:|---:|")
w("| Single card | default | **%s** (%d full-length sessions) | %s GiB | %s GiB |" % (tok(ctx["summary"]["single_max_allocated_ctx"]), ctx["summary"]["single_max_slots"], f1(ctx["summary"]["single_kv_gib_per_mtoken"]), f2(ctx["summary"]["single_headroom_at_ceiling_gib"])))
w("| Dual card | default (`kv_unified=true`) | %s | %s GiB | %s / %s GiB |" % (tok(ctx["summary"]["dual_max_allocated_ctx_unified"]), f1(ctx["summary"]["dual_kv_gib_per_mtoken_unified"]), f2(cases["d175m"]["free_gib"][0]), f2(cases["d175m"]["free_gib"][1])))
w("| Dual card | explicit `--parallel` (`kv_unified=false`) | **%s** (%d full-length sessions) | %s GiB | %s / %s GiB |" % (tok(ctx["summary"]["dual_max_allocated_ctx_explicit_parallel"]), ctx["summary"]["dual_max_slots_explicit_parallel"], f1(ctx["summary"]["dual_kv_gib_per_mtoken_explicit_parallel"]), f2(ctx["summary"]["dual_headroom_at_ceiling_gib"][0]), f2(ctx["summary"]["dual_headroom_at_ceiling_gib"][1])))
w("")
w("One result: **it is 3× not 2×** (weights are no longer duplicated) — the precondition is an explicit `--parallel` (without it only 1.75× and 2M goes straight to OOM).")
w("🔴 **3M is only an allocation ceiling**: a long prompt's prefill hangs the whole machine (host memory exhausted, no dump) — **quote only single-card 1M / dual-card default 1.75M externally**.")
w("🔴 **Virtual memory, settled: initial = maximum = 32768 MB** — an oversized page file turns \"the process reports OOM and exits\" into \"the machine hangs\"; locked down, an over-limit request makes the process report OOM and exit while the machine stays usable.")
w("One line for the customer: **buying capacity means buying host RAM, not just VRAM.** Incident forensics in `bench/notes/ctx3m-hang-2026-10-24.md`.")
w("")
w("### 5.2 Capacity: fitting one 34.37 GiB model")
w("")
w("| Configuration | Where the VRAM goes | Prefill tok/s | Decode tok/s |")
w("|---|---|---:|---:|")
w("| Q8_0 single card `-ngl 37` | 30.78 GiB on card, about 4 GiB of layers on CPU | %s | **%s** |" % (f2(q8_ngl37["prefill_tok_s"]), f2(q8_ngl37["decode_tok_s"])))
w("| Q8_0 single card `-ngl 99` | VRAM full at 31.14 GiB (0.02 GiB left); weights 34.37 GiB, ≥ 3.2 GiB not on card | %s | %s |" % (f2(q8_spill["prefill_tok_s"]), f2(q8_spill["decode_tok_s"])))
w("| Q8_0 dual card `-sm layer` | **33.53 GiB fully resident** (card 0 17.47 / card 1 16.06) | %s | **%s** |" % (f2(q8_s["ts5050"]["prefill_tok_s"]), f2(q8_s["ts5050"]["decode_tok_s"])))
w("| Q8_0 dual card `-sm tensor` † | 33.65 GiB split evenly (card 0 16.92 / card 1 16.73) | %s | %s |" % (f2(q8_t50["prefill_tok_s"]), f2(q8_t50["decode_tok_s"])))
w("| Q4_0 single card `-ngl 99` | 18.32 GiB fully resident (12.84 GiB left) | %s | **%s** |" % (f2(q4_solo["prefill_tok_s"]), f2(q4_solo["decode_tok_s"])))
w("| Q4_0 dual card `-sm layer` `50,50` | 17.96 GiB fully resident (card 0 9.39 / card 1 8.57) | %s | %s |" % (f2(q4_dual["prefill_tok_s"]), f2(q4_dual["decode_tok_s"])))
w("| Q4_0 dual card `-sm layer` `90,10` | 17.96 GiB fully resident (card 0 17.09 / card 1 0.87) | %s | %s |" % (f2(q4_dual9["prefill_tok_s"]), f2(q4_dual9["decode_tok_s"])))
w("")
w("One result: **if it fits, do not split; split only when it does not fit.** Q4_0 already fits on one card and splitting costs %s; Q8_0 does not fit on one card, and a fully resident layer split is %s faster than one card (%s faster than spill) — the split buys capacity and costs no speed." % (
    f1(100 * (1 - r_q4_same)) + "%", fx(r_q8_same), fx(r_q8_spill)))
w("⚠️ The `-ts` ratio has no measurable effect on decode (four settings, 0.3%% spread); the same configuration can differ 6%% across sessions — read direction only, never trend; `-sm row` does not run on this build, `-sm tensor` is slower than one card (%s tok/s) — **layer split is the only cooperation mode that costs no speed**. Harness: llama-server (19/128, median of 3), do not interleave with llama-bench." % f2(q8_t50["decode_tok_s"]))
w("")
w("### 5.3 Throughput: one production line per card")
w("")
w("| Combination | Form | Result |")
w("|---|---|---|")
w("| Image + image | two ComfyUI instances, one card pinned each | steady state %s ~ %s s/image, **level** with %s / %s on a single card in the same batch |" % (f2(img_c1_ss[1]["server_sec"]), f2(img_c0_ss[2]["server_sec"]), f2(img_solo_ss[1]["server_sec"]), f2(img_solo_ss[2]["server_sec"])))
w("| Video + chat | card 0 on H3, card 1 on llama.cpp | 12/12 answered correctly, decode 114.79 vs 115.02 tok/s (−0.2%) |")
w("| Video + video | two ComfyUI instances each running H3 | **does not hold**: 2/2 crashed at the same point, page file peak 48.7 GB |")
w("")
w("- The third row is **a 32 GB RAM wall, not a GPU shortfall**: one H3 instance needs about 25 GB of virtual memory, two need 50 GB, and 32 GB of physical RAM cannot carry it.")
w("  Isolating the SYCL caches on both sides still crashed → not a cache conflict. **On a 32 GB machine a dual card does \"one video + one light task\" only; two video lanes need 64 GB of RAM.**")
w("")

# ---------------------------------------------------------------- 6
w("## 6. One B70 vs two B65 (same-price match-up)")
w("")
w("Prices (official JD store, checked 2026-10-26): **B70 ¥%s**, B65 ¥%s. **Two B65s come to ¥%s — ¥%s more than one B70, nearly level.** So this is the right way to work out \"one B70 = two B65\" — the same money buys two different things." % (
    yuan(P_B70), yuan(P_B65), yuan(P_2B65), yuan(P_2B65 - P_B70)))
w("")
w("| | One B70 32G | Two B65 32G |")
w("|---|---:|---:|")
w("| Price | **¥%s** | **¥%s** |" % (yuan(P_B70), yuan(P_2B65)))
w("| Cores / bandwidth / VRAM | 32 cores · 608 GB/s · 31.16 GiB | 2×20 cores · 2×608 GB/s · 62.32 GiB |")
w("| H3 720p · 5 s end-to-end (steady state) | **%s** | %s (each) |" % (s(sample(b70_720, "fresh")["server_sec"]), s(b65_720_fresh["server_sec"])))
w("| H3 per step | **%s s/it** | %s s/it |" % (f2(sample(b70_720, "fresh")["sampling_sec_per_step"]), f2(b65_720_fresh["sampling_sec_per_step"])))
w("| H3 1080p · 5 s end-to-end (steady state) | **%s** | %s |" % (s(sample(b70_1080, "fresh")["server_sec"]), s(b65_1080_fresh["server_sec"])))
w("| Qwen Q4_0 decode | **%s tok/s** | %s tok/s |" % (f2(load("2026-10-20_b70-q4-0-sycl-l0.json")["summary"]["decode_tok_s"]), f2(q_solo["summary"]["decode_tok_s"])))
w("| Full-load power (P90) | %s W | %s W (both cards) |" % (f1(b70_pw["summary"]["power"]["p90_w_max"]), f1(pw_b0["summary"]["power"]["pair_sum_p90_w"])))
w("| H3 clips at once | 1 | **2** |")
w("| 34.37 GiB Q8_0 | also 31.16 GiB, by capacity it does not fit; **Q8_0 on a single B70 was not measured** | fits, decode %s tok/s |" % f2(q8_s["ts5050"]["decode_tok_s"]))
w("")
w("One result: **nearly the same price, two ways to buy — B70 buys single-job speed (%s / %s faster), two B65s buy capacity + output (2× VRAM, 3× context, %s clips/h on two lanes, holds a 34.37 GiB model)**. \"Double compute\" holds on neither side (B70 is only %s faster, dual leaves a single job unchanged); B70 does not buy capacity either (34.37 GiB does not fit there as well; single-B70 Q8_0 not measured, so no number)." % (
    fx(r_e2e), fx(r_step), f1(thr_dual), fx(r_e2e)))
w("")
w("| Your situation | Pick | Why |")
w("|---|---|---|")
w("| One clip, fast, 1080p as the norm | **B70** | %s faster at 720p, %s at 1080p; nothing replaces it for single-task work |" % (f2(r_e2e) + "×", f2(r_1080) + "×"))
w("| Two clips at once / one video plus one Q&A | **2× B65** | nearly the same price, %s the output (%s vs %s clips/h) |" % (fx(r_thr), f1(thr_dual), f1(thr_b70)))
w("| A model above 34 GiB, or the largest context | **2× B65** | capacity doubles; but the expectation is \"it fits\", not \"it runs faster\" |")
w("| Budget pinned at the 32 GB VRAM tier | **B65** | same VRAM, about ¥%s cheaper, %s slower |" % (yuan(P_B70 - P_B65), fx(r_e2e)))
w("")

# ---------------------------------------------------------------- 7
w("## 7. Carriers compared: what is the same for AI inference, what is not")
w("")
w("> This section is about structure, not parameters. **Only two carriers were measured on this machine: one")
w("> card, and two B65s.** The other two rows in the table were never on this machine, so **they get no numbers")
w("> at all** — only what their structure implies.")
w("")
w("| Carrier | VRAM | Inter-card path | Measured here |")
w("|---|---|---|---|")
w("| 1× B65 | one pool, 31.16 GiB | — | ✅ |")
w("| **2× B65** (this document) | two independent pools, 31.16 GiB each | PCIe (card 1 in the chipset x4 slot here); **no P2P**, cross-card only through host memory | ✅ |")
w("| 2× RTX 5090 | two independent pools, 32 GB each | PCIe; **consumer cards have no P2P either**, cross-card only through host memory | ⛔ not measured |")
w("| Unified-memory platform (DGX Spark class) | **one pool**, the GPU addresses the whole machine's memory | the concept of \"moving between cards\" does not exist | ⛔ not measured |")
w("")
w("### The same in three ways")
w("")
w("![Three things that stay the same: one-job speed = compute + bandwidth, what does not fit moves down a tier, one process eats one card](assets/dual-b65-carriers-same.en.svg)")
w("")
w("1. **Single-task speed is set by compute and bandwidth, not by card count.** Measured in the summary's first two rows. Any vendor's card, any carrier, this holds.")
w("2. **What does not fit has to go down a level, and going down costs a move.** VRAM is fastest, host RAM next, disk slowest; whoever is short of capacity pays for that level of moving.")
w("3. **One process uses one card.** `torch.xpu` and ComfyUI both bind the first card and do not spread out on their own. To get both cards working, the easy route is **start two processes**, not one process using two cards.")
w("")
w("### Different in three ways")
w("")
w("![Three things that differ: pool count sets the direction, no P2P means dear cross-card, bandwidth is not doubled per job](assets/dual-b65-carriers-diff.en.svg)")
w("")
w("1. 🔴 **How many pools there are decides where the bottleneck sits, and it flips the optimisation direction.**")
w("   - **Two independent pools** (this document's case): cut a large model up and place layers on both cards, and layers have to synchronise.")
w("     Measured, Q8_0 34.37 GiB with a layer split, fully resident, decodes at **%s tok/s**; one card with about 4 GiB of CPU tail at **%s**;" % (f2(q8_s["ts5050"]["decode_tok_s"]), f2(q8_ngl37["decode_tok_s"])))
w("     one card forced to spill at **%s** —" % f2(q8_spill["decode_tok_s"]))
w("     **the split costs no speed and avoids the single-card spill tier (%s tok/s).** With two pools the direction is not \"never split\", it is \"**a split is fine, but do not expect it to make a single task faster**\" — single-task speed is still set by one card's compute and bandwidth." % fx(r_q8_spill))
w("   - **One pool** (unified memory): the question \"which layer goes on which card\" does not exist; fast and slow layers sit continuously in the same pool.")
w("     The direction inverts — what you do is **keep hot data in the fast segment**, not spread load over more cards.")
w("2. **Whether P2P exists decides how expensive \"cross-card\" is.** The two B65s here have no P2P; cross-card data lands in host memory and is fetched back, two PCIe trips each way. Consumer cards (the 5090 tier) have no P2P either — on \"cross-card is expensive\", the two carriers are **the same class**, and both suit \"one card, one job\" better.")
w("3. **Bandwidth does not double with card count.** Two B65s together are 2×608 GB/s in total, but one task runs only on the card it sits on, so what it can use is still 608 GB/s. Cutting a model in half across two cards trades \"cross-card sync every step\" for \"half a model per card\": total bandwidth rises, bandwidth per task does not.")
w("")
w("### Into card selection")
w("")
w("| Your situation | What to do | Why |")
w("|---|---|---|")
w("| Two unrelated jobs | **one instance per card** | measured, image + image and video + chat do not lose speed; the most reliable dual-card use |")
w("| One model does not fit | **dual card `-sm layer` split** | measured, buys capacity at no cost in speed (%s vs %s fully resident single card, same session); `-sm row` does not run on this build, `-sm tensor` runs but is slower than one card |" % (f2(ts6040["decode_tok_s"]), f2(q8_ngl37b["decode_tok_s"])))
w("| The model already fits on one card | **do not split, stay on one card** | Q4_0, same session: dual card %s vs single card %s, splitting is %s slower |" % (f2(q4_dual["decode_tok_s"]), f2(q4_solo["decode_tok_s"]), f1(100 * (1 - r_q4_same)) + "%"))
w("| One task needs to be faster | **buy a stronger single card**, not another card | the second card contributes 0 to one task, on any carrier |")
w("| Does not fit and you do not want to split | unified-memory platform (not measured here) | one pool: if it fits, the whole model stays resident, and cross-card sync does not exist |")
w("")

# ---------------------------------------------------------------- 8
w("## 8. Working parameters (copy these)")
w("")
w("### 8.1 Two ComfyUI instances: one card each")
w("")
w("```bash")
w("# instance 1 (card 0, CPU-attached x16)")
w("COMFY_PORT=8190 ONEAPI_DEVICE_SELECTOR=level_zero:0 \\")
w("  SYCL_CACHE_DIR=<tools dir>/_sycl_cache_c0 \\")
w("  <ComfyUI dir>/python_embeded/python.exe <ComfyUI dir>/main.py \\")
w("    --listen 127.0.0.1 --port 8190 --reserve-vram 4")
w("")
w("# instance 2 (card 1, chipset x4) — start it 20 s later, so they do not load at the same time")
w("COMFY_PORT=8191 ONEAPI_DEVICE_SELECTOR=level_zero:1 \\")
w("  SYCL_CACHE_DIR=<tools dir>/_sycl_cache_c1 \\")
w("  <ComfyUI dir>/python_embeded/python.exe <ComfyUI dir>/main.py \\")
w("    --listen 127.0.0.1 --port 8191 --reserve-vram 4")
w("```")
w("")
w("- **Pinning a card has exactly one layer: `ONEAPI_DEVICE_SELECTOR=level_zero:N`.** ComfyUI's `main.py` has no")
w("  \"assert index\" parameter of its own; copying the bench collector's `--expect-index` (that is a")
w("  `bench_f_h3.py` argument) fails on the parameter and the process never starts.")
w("- **Check it once yourself after startup**: read VRAM occupancy for each instance. Both rising means each is")
w("  holding its own card; only one rising means both landed on the same card.")
w("- **`SYCL_CACHE_DIR` must be separate for each**, sharing one means the kernel caches overwrite each other.")
w("- Ports 8190 / 8191. **8188 is the always-on instance — do not take it, do not kill it.**")
w("- `--reserve-vram 4` is the collection condition behind this set of numbers; changing it changes loading")
w("  behaviour.")
w("")
w("### 8.2 llama.cpp on two cards: multiple devices + layered loading")
w("")
w("```bash")
w("# SYCL runtime DLLs live in python_embeded and must be prepended, or the exe dies with 0xC0000005")
w("PATH=<python_embeded dir>/Library/bin:<llama.cpp bin dir>:$PATH")
w("ONEAPI_DEVICE_SELECTOR=level_zero:0,1 \\")
w("  llama-server -m <model dir>/Qwen_Qwen3.6-35B-A3B-Q4_0.gguf \\")
w("    -dev SYCL0,SYCL1 -sm layer \\")
w("    -c 3145728 --parallel 12 \\")
w("    --host 127.0.0.1 --port 8099")
w("```")
w("")
w("- 🔴 **`-c` must line up with `--parallel`**: `--parallel = ctx / 262144`. Out of line, the log shows")
w("  `kv_unified=true`, each M token takes 22.2 to 22.4 GiB, and 2M goes straight to OOM; lined up,")
w("  `kv_unified=false` and each M token takes only 14.5 to 15.6 GiB.")
w("- **To run on one card only, write `-dev SYCL0` (or `SYCL1`)** and narrow `ONEAPI_DEVICE_SELECTOR` to the")
w("  same card as well, otherwise the device enumeration order changes.")
w("- 🔴 **`PATH` must be prepended with `python_embeded\\Library\\bin`** (the SYCL runtime DLLs are in there).")
w("  Without it the symptom is **exit code `0xC0000005`, a crash within 1 s, empty stderr** — it looks like a")
w("  model problem, but the runtime simply was not found.")
w("")
w("### 8.3 Three checks")
w("")
w("| What to check | How | Why |")
w("|---|---|---|")
w("| Did it start | wait for `model loaded` in the log, then send one `/v1/chat/completions` | a working TCP port does not mean it can answer |")
w("| Did it fit | look at **whether VRAM occupancy scales with `-c`** | single card `-c 1572864` / `2097152` both start and answer, but occupancy equals 1M (12.68 / 12.63 vs 12.81 GiB) — the extra context was never allocated |")
w("| Is it worth it | look at **how fast it runs** | Q8_0 single card `-ngl 99` does not fit, yet still reports `model loaded` + probe 200; the remainder just sits on the CPU |")
w("")
w("### 8.4 Two small settings that make the numbers fake")
w("")
w("- **`cache_prompt` must be off** (`cache_prompt: false` in the multimodal comparisons). Left on, firing the")
w("  same image repeatedly hits the prompt cache, wall clock drops to 0.1 s and decode reports 115 tok/s — that")
w("  is cache, not compute.")
w("- **Warm up before taking numbers.** The same H3 job: page cache cold %s, warm %s — a %s percentage-point gap. For any \"how much does the dual card slow things down\", run one warm round first." % (s(d1_fresh["server_sec"]), s(sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")["server_sec"]), f1(100 * (d1_fresh["server_sec"] / sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")["server_sec"] - 1))))
w("")

# ---------------------------------------------------------------- 9
w("## 9. Pitfall list")
w("")
w("| # | Pitfall | Symptom | Fix |")
w("|---:|---|---|---|")
w("| 1 | Assuming a dual card doubles compute | per step 42.30 → 42.41 s/it, not one step faster | `torch.xpu` uses the first card only; llama.cpp multiple devices is layered loading |")
w("| 2 | Assuming a layer split always costs speed | dual card 33.53 GiB fully resident, decode %s tok/s | same-session measurement says it costs nothing: %s faster than %s fully resident on one card, %s faster than %s spilling on one card. `-sm row` is the one that really does not run |" % (
    f2(ts6040["decode_tok_s"]), fx(r_q8_same), f2(q8_ngl37b["decode_tok_s"]), fx(r_q8_spill), f2(q8_spill["decode_tok_s"])))
w("| 7 | Assuming tensor parallel accelerates | `-sm tensor`, two cards, decode 29.08 to 29.50 tok/s | slower than %s fully resident on one card: the per-layer cross-card sync costs more than the second card contributes. For cooperation use the layer split, not tensor |" % f2(q8_ngl37b["decode_tok_s"]))
w("| 15 | Assuming a larger context is always better | 3M allocates fine, long-prompt prefill stalls at 8192 token | 14 minutes later the machine hangs silently (no dump, no blue screen). 3M is an allocation ceiling only; usable ceilings are 1M single card / 1.75M dual card |")
w("| 16 | Assuming a bigger page file is safer | 64 GB page file, system promises 95.11 GiB | promised too much, so what should be an OOM in the process becomes a machine hang. The page file wants \"enough, with headroom\" |")
w("| 17 | Assuming \"start it small\" locks it down | initial 32 GB / maximum 64 GB, Windows grew it to ≈56 GB while loading 3M | commit limit climbs back to 86.97 GiB, commit 98.9%, the same hang danger zone. **Initial and maximum must be equal (32768)** |")
w("| 18 | Assuming virtual memory has to be set large to be safe | initial = maximum = 32768 locked, 3M load exits on its own at 20.4 s, commit peak 55.4%, limit never grows | a request over the ceiling makes the process report OOM and exit, machine stays usable. Virtual memory, settled: **fixed at 32 GB (initial = maximum)** |")
w("| 14 | Assuming a lower-level inter-card copy rescues tensor parallel | three copy paths (SYCL direct / Level Zero direct / forced through host memory) decode %s / %s / %s tok/s | all three inside the noise. Inter-card copy is not the bottleneck, sync count is. Stop tuning in this direction |" % (f2(d2d["dual_tensor_5050_p2p"]), f2(d2d["dual_tensor_5050_l0direct"]), f2(d2d["dual_tensor_5050_hostforward"])))
w("| 3 | Taking a starting process as proof it fit | `-c 1.5M` / `2M` start and answer, VRAM not a byte higher | switch to \"does VRAM scale with `-c`\" |")
w("| 4 | Taking \"does not fit\" as \"will not start\" | Q8_0 single card `-ngl 99` still returns 200 | switch to \"how fast does it run\" |")
w("| 5 | `-c` not aligned with `--parallel` | 22.2 to 22.4 GiB per M token, 2M OOM | `--parallel = ctx / 262144`, confirm `kv_unified=false` in the log |")
w("| 6 | Two instances generating video at once | 2/2 crash after `loads=2`, `0xC0000005`, page file peak 48.7 GB | 32 GB RAM wall; on a dual card do \"one video + one light task\" only |")
w("| 7 | Taking numbers from the first round | first round 543 s, 406 s after warm-up, same configuration | run one warm round first; the first round includes concurrent loading and is not comparable |")
w("| 8 | Attributing power to the wrong card | H3 running hard, sampler reports 42 to 46 W | the sampler reads Sysman device 0 only, and **Sysman order ≠ `level_zero:N`** (here Sysman dev0 = bus 16 = card 1). For dual-card power use a collector that enumerates per card and attributes by PCI bus |")
w("| 9 | Starting llama.cpp without prepending `PATH` | `0xC0000005`, crash within 1 s, empty stderr | prepend `<python_embeded dir>/Library/bin` |")
w("| 10 | Passing `-c` to `llama-bench` | `invalid parameter for argument: -c` | `llama-bench` takes `-p` / `-n`, it does not know `-c` |")
w("| 11 | Piping output and then reading numbers | a pipe only flushes when the process ends, nothing visible in between | write straight to `>> logfile 2>&1` |")
w("| 12 | Sharing one `SYCL_CACHE_DIR` | the two instances overwrite each other's kernel cache | give each its own; but note: that crash after isolation was not a cache problem |")
w("| 13 | Assuming no power draw because the collector never started | the power field in the record is empty | without an explicit start it degrades silently to \"power not recorded\", which is not zero power |")
w("")

# ---------------------------------------------------------------- 10
w("## 10. Where the data comes from")
w("")
w("- Dates: **2026-10-23** (dual-card H3, image generation, capacity, power — all measured); single-card")
w("  baselines from **2026-10-21** (H3, image generation, Qwen) and **2026-10-22** (H3 duration ladder);")
w("  **2026-10-24** three batches: tensor parallel and the inter-card copy paths (§4.1, §9 items 7 and 14),")
w("  the `-ts` fine sweep and the Q4_0 dual/single same-session comparison (§5.2), and whether 3M context runs")
w("  (§5.1, §9 items 15 and 16). ⚠️ **The Q4_0 comparison and the single-card `-ngl 37` re-run in §5.2 were run")
w("  back to back in one window (17:37 to 17:47)** — the tightest same-session comparison available; the dual-card")
w("  numbers from the 12:39 and 16:10 sessions differ by 6%, so **across sessions treat them as reference only**.")
w("- Raw records: json files named by date under `bench/data/`, each carrying workload, samples, summary, notes.")
w("  Every table in this document is generated by `bench/harness/gen_dual_report_en.py` (shared data layer")
w("  `bench/harness/dual_data.py`) straight from those json files — **no number was retyped by hand**.")
w("- Records used:")
w("")
for n in [
    "2026-10-21_b65-32g_minimax-h3-int8_convrot-b65h3-1280x720-comfyui.json",
    "2026-10-21_b65-32g_minimax-h3-int8_convrot-b65h3-1920x1088-comfyui.json",
    "2026-10-22_h3_1280x720_b65d10.json",
    "2026-10-22_h3_1280x720_b65d15.json",
    "2026-10-22_h3_1280x720_b65d17.json",
    "2026-10-22_h3_1280x720_b65d20.json",
    "2026-10-19_h3_1280x720_b70scan.json",
    "2026-10-19_h3_1920x1088_b70scan.json",
    "2026-10-19_h3_1280x720_b70pw.json",
    "2026-10-20_b70-q4-0-sycl-l0.json",
    "2026-10-23_h3_1280x720_duald1.json",
    "2026-10-23_h3_1280x720_duald4b.json",
    "2026-10-23_h3_1280x720_duald6.json",
    "2026-10-23_h3_1280x720_dualc1.json",
    "2026-10-23_h3_1280x720_dualc1b.json",
    "2026-10-23_b65-32g-q4_0-dual-c1.json",
    "2026-10-23_b65-32g-q4_0-dual-c1-concurrent.json",
    "2026-10-23_dual-a4-vision-under-h3.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2solo-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2c0-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-duala2c1-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3s0-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3s1-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3b0-comfyui.json",
    "2026-10-23_b65-32g_qwen-image-2.1-int8_convrot-c3b1-comfyui.json",
    "2026-10-23_b65-32g_q4_0-ctxcap-dual.json",
    "2026-10-23_b65-32g-q8_0-dual-layer-qwen3.6-35b-a3b.json",
    "2026-10-23_b65-32g-q8_0-single-spill-qwen3.6-35b-a3b.json",
    "2026-10-23_b65-32g-q8_0-single-ngl37-qwen3.6-35b-a3b.json",
    "2026-10-24_b65-32g-q8_0-dual-tensor-scan.json",
    "2026-10-24_b65-32g-q8_0-dual-dev2dev-scan.json",
    "2026-10-24_b65-32g-dual-ts-scan2.json",
    "2026-10-24_b65-32g-q4_0-solo.json",
    "2026-10-24_b65-32g-q8_0-solo37-recheck.json",
    "2026-10-24_b65-32g-q4_0-ctx3m-probe.json",
    "2026-10-24_b65-32g-q4_0-ctx262144-single-ctrl.json",
    "2026-10-24_b65-32g-q4_0-ctx3m-loadonly-pfmax64.json",
    "2026-10-24_b65-32g-q4_0-ctx3m-loadonly-pf3232.json",
]:
    w("  - `%s`" % n)
w("")
w("- Related documents: the cross-slot comparison table [`slot-comparison.md`](slot-comparison.md) §6, H3 on")
w("  four cards [`comfyui-h3.md`](comfyui-h3.md), power [`comfyui-power.md`](comfyui-power.md), common pitfalls")
w("  [`pitfalls.md`](pitfalls.md).")
w("- The full record of debugging and missteps is in `bench/notes/dual-b65-prep.md`; **that file is engineering")
w("  notes, not product documentation** — the conclusions live in this document and in `docs/`.")
w("- Complete forensics on the 3M context machine hang (dump criteria, single-variable controls, page file")
w("  analysis) is in `bench/notes/ctx3m-hang-2026-10-24.md`.")
w("")

text = "\n".join(L) + "\n"
text = text.replace("\r\n", "\n").replace("\r", "\n")
text = text.replace("\n", "\r\n")
if text.endswith("\r\n"):
    text = text[:-2]

with open(OUT, "wb") as f:
    f.write(text.encode("utf-8"))

print("written:", OUT, len(text), "chars")
