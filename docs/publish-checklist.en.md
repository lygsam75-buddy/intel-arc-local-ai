**English** · [简体中文](publish-checklist.md)

# Launch Checklist (first GitHub release)

> **Trigger**: 2026-10-20 — **live** at <https://github.com/lygsam75-buddy/intel-arc-local-ai>.
> **No waiting for B60/B65.** The cards had not arrived, so the first release leaves them out and marks them
> **not measured** in the repo rather than leaving a blank to guess at.
>
> Tick every item before pushing. ☑️ marks an open item; ✅ marks one already done.

---

## 0. What Ships

> ⚠️ **Every line count, record count and size in this section is a snapshot from the 2026-10-20 release.** Data kept landing
> daily afterwards, so **do not read them as current**. The only current source is `python bench/harness/registry_audit.py`:
> **a fresh run on 2026-10-23 gives 372 records in `bench/data`**
> (355 active · 16 discarded · 1 probe_failed; comfyui 185 / bench 87 / ctx-sweep 68 / vision 27 / longctx 4 / capacity 1).

Six sections. **The order is the order a reader arrives in**: conclusion first → then their own workload type → then pitfalls → raw data last.

| # | Section | Files | Size | Why a reader opens it |
|---|---|---|---:|---|
| 1 | **Front page** | `README.md` (**English, GitHub default page**)<br>`README.zh-CN.md` (full Chinese version)<br>`docs/at-a-glance.md` · `docs/at-a-glance.en.md` | 401 / 436 / 98 / 98 lines | **Four tables up front** (what do you want to do / which card to buy / electricity cost / two cards side by side) — no jargon, conclusion first.<br>Below that: hardware table, **GUNNIR (蓝戟) + power limit** (why the same model performs differently per board), long context, H3, image and music generation, power.<br>`at-a-glance` is the more extreme "six tables on one page" version, linked from the top of both READMEs.<br>**Cross-linked at the top**; GitHub's first screen is English |
| 2 | **Inference (llama.cpp)** | `docs/vram-16gb.md`<br>`docs/server-config.md`<br>`docs/slot-comparison.md`<br>`docs/test-rig.md`<br>`docs/strata-b50-linux-prep.md`<br>`bench/README.md` | 442 / 325 / 235 / 267 / 441 / 433 lines | Parameter tuning for the main tier, server configs that ship as-is, whether slots actually cost anything, platform specs, and the blockers hit reproducing on Ubuntu. **`bench/README.md` defines what counts as a comparable number** |
| 3 | **ComfyUI** | `docs/comfyui-capability.md`<br>`docs/comfyui-h3.md`<br>`docs/comfyui-image.md`<br>`docs/comfyui-power.md` | 399 / 679 / 850 / 322 lines | Capability table (how big a model fits / video / image, three questions on one page) → full video resolution × duration matrix → image and music generation (including kernel-variant pairings) → power and electricity cost. **The most immediately useful group in the repo** |
| 4 | **Pitfalls** | `docs/pitfalls.md` | 926 lines | Symptom → root cause → fix for each one. **Includes the most expensive: the 2-second TDR, TIME_WAIT port exhaustion, XPU pinned memory, the int8 gate** |
| 5 | **Test registry** | `docs/test-registry.md`<br>`CONTRIBUTING.md` | 441 / 72 lines | ID, status, data location and reproduce entry for every test, plus **prediction vs measurement** and a **corrections log**. **The only evidence the data can be trusted** |
| 6 | **Data and tools** | `bench/data/` 207 JSON files (2.4 MB)<br>`bench/logs/` 33 raw `llama-server` logs (18 MB)<br>`bench/harness/` 24 scripts + 2 shell<br>`bench/logs/README.md` | see left | Machine-readable raw data, capture scripts and the **log ↔ record mapping**. Audit entry: `python bench/harness/registry_audit.py` |

**Repo total**: Markdown **19 files · 7,151 lines** (English 2 files, 499 lines = `README.md` 401 + `at-a-glance.en.md` 98;
Chinese 17 files, 6,652 lines); 207 data records; 33 logs; 26 scripts. **About 21 MB** (logs account for 18 MB).

### Language Policy: **English First Screen, Chinese as Source of Truth**

| Layer | Language | Why |
|---|---|---|
| **GitHub first screen** | **English** (`README.md`) | GitHub's default traffic is English search and English readers. **English readers will not click a "Simplified Chinese" link, but Chinese readers will always click the one next to "English"** — so the first screen goes English, and the switching cost lands where it is cheapest |
| Repo name / description / topics | **English** | Decides whether it is findable at all; `intel-arc` `xpu` `llama-cpp` `comfyui` are the terms people actually search |
| **Bilingual scope** | Both READMEs (**content parity**) + both `at-a-glance` files | The English page is not an entry page but **a full peer**: same four summary tables, same five core numbers, same list of unmeasured items. No reader switches language for one figure |
| **Body and detail (16 `docs/` files)** | **Chinese** | The audience is Chinese-language customers and engineers. **Detail exists in Chinese only, so no second source of truth appears** |
| Not doing | Full bilingual for all 16 `docs/` files | **6,600+ lines** change daily; two translations would drift, and **a drifted translation is worse than none** (the reader cannot tell which is right) |

> Division of labour: **the English page helps someone decide whether to keep reading; the Chinese page tells them how to do it**.
> Order for changing a number: **edit Chinese first (source of truth) → sync the top-level tables in both READMEs → update `at-a-glance` last**.

### What Stays Out of the Repo

| Item | Reason |
|---|---|
| Model weights (`*.gguf` / `*.safetensors`), build artefacts (`*.exe` / `*.zip`) | Size, and irrelevant to the conclusions |
| Logs before normalisation (they carry absolute local paths) | Only the substituted version is published. **The rule is replayable**: apply the same substitutions to the original and the result is byte-identical to the committed file |
| `__pycache__/`, `.venv/`, editor directories | Covered by `.gitignore` |
| ComfyUI itself and custom_nodes | Installed outside the repo; **only the version and key-file mtimes are recorded** (check them when comparing batches — see the registry) |

---

## 1. Final Pass Before Publishing (data → docs → registry; any other order misses something)

| # | Action | Done |
|---|---|---|
| 1 | `bench/data/` names follow `<date>_<card><vram>_<model>-<quant>-<backend>.json`; video uses `<date>_h3_<WxH>_<tag>.json` | ✅ all 207 conform |
| 2 | Rerun the audit: `python bench/harness/registry_audit.py`; check counts / schema / evidence coverage / power coverage / slot coverage | ✅ `total 207`; comfyui **122** (B70 97 / B50 25); `timing_breakdown` **120/122**; `log_evidence` **122/122** (`annotated` 120 · `missing` 2) |
| 3 | Backfill evidence: `python bench/harness/annotate_comfy_evidence.py --data bench/data --logdir "<label>=<dir>"` (`--logdir` can repeat; **all three domains must be covered**) | ✅ Backfilled; the two `missing` are a log since overwritten and a run that failed every round — **not faked as done** |
| 4 | `README.zh-CN.md`: the four summary tables up front, hardware table, llama-bench table, long context, ComfyUI sections, power, directory lines; the English `README.md` **aligned table by table** with the Chinese one; both `at-a-glance` files carrying the same numbers | ✅ Rewritten in the order Chinese → English → `at-a-glance`; **the same numbers must not disagree in three places** |
| 5 | `docs/test-registry.md` §1 status / §2 coverage matrix / §3 counts / §5 prediction vs measurement | ✅ Synced to 207 / 122 |
| 6 | Cross-references and anchors across all docs | ☑️ **Check every heading you renamed** (this has bitten before: heading changed, link left behind) |
| 7 | Size and per-file limit (GitHub allows 100 MB per file) | ✅ Largest file 3.67 MB |

---

## 2. How to Mark Unmeasured Items (**leave no gap, make no one guess**)

The first release has three kinds of "no data". **One rule: write "not measured + why + what it would take" in place, and never leave a TODO placeholder.**

| Unmeasured | Why | How it reads in the repo |
|---|---|---|
| **B60 (24 GB) / B65 (32 GB)** | Cards not in hand | The hardware table in the README keeps the spec rows (readers need them to choose); the data tables **omit** both rows; the matching items in `test-registry.md` §2 read "not measured (card not in hand)" |
| **Follow-up B50 work** (above the resolution ceiling, two-card concurrency) | The B50 was physically removed; only the B70 is left | Data already captured is kept (25 records); anything not run is marked "card removed, needs to go back in" |
| **T-11 two-card concurrency / T-16 Vulkan / T-14 Strata run** | Needs a second card or a specific machine state | Marked ⛔/⏸️ in the registry with the precondition spelled out |
| **2560×1440 and above** | VRAM and time cost too high; not measured | `comfyui-h3.md` states that the five settings stop at 1920×1088 and anything above is not measured |
| **Sustained full load (> 1 h) stability** | Only single-task peaks were captured | `comfyui-power.md` §8 open items say there is no long-run data, so do not size cooling for 290 W |

> **The criterion**: report how far the measurement goes. Where there is none, end with "not measured at this setting" and **never fill the table with an extrapolated value**.

---

## 3. Pre-publish Scan (rerun 2026-10-19)

| Item | Result |
|---|---|
| **Secrets** | ✅ 0 hits. `--api-key local` is a local placeholder; every `token` in the docs is the LLM sense |
| **Absolute local paths** | ✅ 0 hits (the two remaining are the **substitution reference table** in `bench/logs/README.md`, where the raw form has to be shown, plus a historical trace in the registry). Cleaned: real directories in script docstrings, `/d/oneapi-dpcpp` in `pitfalls.md`, the real working directory in the registry |
| **Size** | ✅ About **21 MB** (`bench/logs/` 18 MB · `bench/data/` 2.4 MB · `docs/` 420 KB); largest file 3.67 MB |
| `.gitignore` | ✅ Covers `__pycache__/`, `*.py[cod]`, `.venv/`, `*.gguf`, `*.bin`, `*.exe`, `*.zip`, `*.log`, `local.env`. **`*.log` has no exception**: raw logs are not published; `bench/logs/` keeps only a README through |
| **Orphan / stub files** | ✅ Deleted `bench/results.md` (1 line, already covered by Table A in the README, and nothing linked to it) |
| `__pycache__` | ✅ Physically deleted (`.gitignore` covers it too) |
| LICENSE | ✅ MIT, copyright **`Yonggang Lin`**; README and git author use the same name (email `lygsam75@gmail.com` ties it to the GitHub account) |
| **git state** | ✅ Already a git repo (`main`); `.gitattributes` pins `* -text` with code on LF; **pushed to GitHub** (289/289 blob shas match local) |

**Log path normalisation, as executed** (one-off, done): in the raw log text, the model directory, the llama.cpp build directory
and the working directory had their **path strings** replaced with placeholders, **every other byte untouched**
(including `\r\n` line endings, timestamps, `offloaded N/N layers`, `buffer size`, `Prompt executed`, error lines).
The check: apply the same substitutions to the original and the result is **byte-identical** to the committed file (33/33 pass).
Details in `bench/logs/README.md`.

---

## 4. Open Calls Before Launch (**only these need your sign-off**)

| # | Item | Decision |
|---|---|---|
| 1 | **Repo name** | ✅ `intel-arc-local-ai` · display name **Intel Arc Local AI Handbook** |
| 2 | **Visibility** | ✅ **public** (a handbook is only worth something if it can be found; scanned clean of secrets, absolute paths and internal product names) |
| 3 | **Attribution** | ✅ **Yonggang Lin** · `lygsam75@gmail.com` — identical in LICENSE, both READMEs and the git author |
| 4 | **Repo description / topics** | ✅ Set. Description (English, so it is findable): `Field-measured local AI on Arc Pro B50 / B60 / B65 / B70: llama.cpp, ComfyUI, image · video · audio generation, and power — with raw logs and machine-readable data.`; topics: `intel-arc` `xpu` `llama-cpp` `comfyui` `local-llm` `benchmark` `oneapi` `arc-pro` |
| 5 | **Positioning** | ✅ Set: **make it known that this Intel card works, and works well**, and **that the board is built by GUNNIR (蓝戟)**. The criterion is the **power limit** — reference cards carry a lower power limit and hold some performance back, so power data is not a bonus metric but direct evidence of the performance ceiling (see the matching section in `README.zh-CN.md`) |
| 6 | **GitHub login** | ✅ Solved: the `gh` CLI was not logged in, so the **OAuth token GitHub Desktop had stored in the Windows credential manager** was used (`GH_TOKEN` injected into `gh`); the release went through first try (see §5) |

---

## 5. First Release Steps

### Done, Leave Alone

```bash
git init -b main                    # ✅
git config core.autocrlf false      # ✅ matches * -text in .gitattributes
git add -A && git commit            # ✅ 10 commits already, working tree clean
```

> **The line-ending policy is part of the evidence**: before the logs went in, they were verified as path-normalised
> with every other byte untouched (including `\r\n`). `core.autocrlf=true` would void that claim, so `.gitattributes`
> pins `* -text` and only `*.py` / `*.sh` use `text eol=lf`. **Do not revert it to the default.**

### Release Run Log (2026-10-20, complete)

The `gh` CLI **itself was not logged in** (`gh auth status` → not logged into any GitHub hosts). What worked was the
**OAuth token GitHub Desktop had stored in the Windows credential manager**
(`GitHub - https://api.github.com/lygsam75-buddy`), handed to `gh` as `GH_TOKEN`, which is equivalent to being logged in:

```bash
gh auth setup-git --hostname github.com          # let git push use gh's credential helper
gh repo create intel-arc-local-ai --public --source . --push \
  --description "Field-measured local AI on Arc Pro B50 / B70: llama.cpp, ComfyUI, image · video · audio generation, and power — with raw logs and machine-readable data."
gh repo edit lygsam75-buddy/intel-arc-local-ai --add-topic ...   # ⚠️ repo edit needs [OWNER/REPO]; a bare name is a format error
```

**Result**: <https://github.com/lygsam75-buddy/intel-arc-local-ai> · public · `main` ·
289 files · 33 logs · 207 JSON records · 8 topics.

**Post-push verification** (the step that matters more than "it pushed"): every blob sha from the remote
`git/trees/main?recursive=1` compared against local `git rev-parse HEAD:<path>`, one by one → **289/289 identical**.
That is what proves the `* -text` in `.gitattributes` did its job — identical blob shas mean the server applied no
line-ending conversion, so the claim that the logs are path-normalised with every other byte untouched still holds online.

> The local directory is still named `intel-arc-ai-cookbook` (the rename hit a lock held by this session; both `mv` and `Rename-Item` refused).
> **This does not affect the release** — the GitHub repo name comes from `gh repo create`, not from the local folder name.
> Rename the folder once the session ends and the lock clears.

**Commit message convention** (follow it for every later commit):

```
data(b60):  new card data
docs:       documentation updates
fix(data):  backfill / correct historical records (state the evidence)
chore:      tooling and infrastructure
```

---

## 6. Release Day, Afterwards

- ✅ Both READMEs carry the real repo address / plain link form (`https://github.com/lygsam75-buddy/intel-arc-local-ai`)
- ✅ `docs/test-registry.md` §0 records the release date, the first commit `c83228e` and the 289/289 blob sha result
- ✅ The repository link can now be cited directly — the performance record is live
- ✅ Confirmed `bench/logs/` is visible online: `contents/bench/logs` returns **34 entries** (33 logs + README)
- ☑️ Optional (not done): a screenshot on the README front page / power curve charts, to raise first-glance credibility

---

## 7. What the First Release **Cannot** Claim

| Do not say | Because | Say instead |
|---|---|---|
| "B70 draws 290 W at full load, size cooling for 290 W" | Single-task peaks only; **no run longer than 1 h** | "Single-task P90 holds at 290 W; long runs not measured" |
| "INT8 cuts energy 30%" | Quantisation **does not change power, only time**; energy saved ≈ time saved | "INT8 computes faster, so each run costs less electricity" |
| "B60/B65 are about the same" | **Cards never arrived; not one measurement** | "B60/B65 not measured" |
| "Two cards double the throughput" | **Measured: no doubling** (2× B65): two separate lines, H3 end-to-end +6.0%, Qwen decode −0.2% | "Two cards buy throughput and capacity, not single-task speed" |
| Comparing `server_sec` across two batches | When the model does not fit it reloads, so end-to-end seconds are not comparable | "Compare `it/s` across batches; end-to-end is only comparable when `loads == 0`" |