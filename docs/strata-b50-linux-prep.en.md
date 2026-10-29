**English** · [简体中文](strata-b50-linux-prep.md)

# Reproducing B50 Strata on Ubuntu: preparation checklist

> Goal: reproduce the community-reported **Coder IQ1_M ≈23 tok/s / IQ2_XS ≈25-27 tok/s**
> on this machine (Arc Pro B50 16G + Ryzen 5 9600X + 32 GB RAM).
> Bottom line first: **one hard blocker (disk) has to be cleared first. The other one (RAM)
> will put any reproduction below the community numbers by construction.**

---

## 0. Bottom line: three premises, one red, one yellow, one green

| # | Premise | Current state | Verdict |
|---|---|---|---|
| 1 | **≥ 150 GB for the Linux side, on an internal NVMe** (official minimum 80 GB) | Ubuntu partition **53.57 GB** (a USB drive is worse — see §2.1) | 🔴 **Hard blocker. Must be expanded** |
| 2 | **32 GB RAM is the official floor, and the same doc says 64 GB is the real recommendation** | 31.1 GB | 🟡 **It runs, but it is not a clean reproduction** |
| 3 | CPU has AVX-512 (experts are computed on the CPU) | Ryzen 5 9600X has it | 🟢 Meets the bar |
| 4 | **Kernel ≥ 6.14** (the full B50 support line) | To be confirmed | ⚪ **Check `uname -r` first — see §4.1** |
| 5 | **B50 in the primary slot** (Strata is a PCIe-sensitive load) | Currently in the secondary slot | 🟡 **See §3 — move it back before testing** |

---

## 1. 🔴 Disk: the Ubuntu partition is 53.57 GB — 3x too small

### Why it needs this much disk

Strata's official figures: **about 80 GB of disk to start, past 150 GB for the larger tiers.** Itemized:

| Item | Size | Note |
|---|---:|---|
| Model (the `--model` tier for Strata) | **≈70 GB** | installer says "about 70 GB" |
| Docker image `strata-sycl-dev` | **13 GB** | `sycl/setup_intel.py` runs inside this image |
| Intel oneAPI (DPC++ + oneMKL) | ≈5 GB | docs say "About 5 GB" (not needed with Docker, but the image already has it) |
| Build artifacts + JIT cache | 3 to 5 GB | |
| Ubuntu itself | 15 to 25 GB | |
| **swap (mandatory with 32 GB RAM)** | **64 GB+** | a 35 to 55 GB working set does not fit in 31 GB of RAM; swap covers it |

→ **≈170 to 180 GB total.** The official 80 GB minimum only holds for a 64 GB machine that runs no swap. This box has 32 GB, so **swap has to be generous**, which puts the real bar at **150 to 200 GB**.

### Current state

```
disk 0 (WD 500GB, NVMe)
  ├─ Partition 1  System      0.29 GB
  ├─ Partition 2  Reserved    0.02 GB
  ├─ Partition 3  <data disk> NTFS   411.88 GB   (used 89.4 GB, free 322.5 GB)
  └─ Partition 4  ext4       53.57 GB  ← Ubuntu lives here (UEFI entry present, boots)
```

**Key constraint: ext4 is the last partition on disk 0, and <data disk> sits in front of it.**
Shrinking <data disk> frees the gap between F's tail and ext4's head → **ext4 cannot grow to the right.**

### 2.1 Disk measurements: do not run this on a USB drive

Measured with `bench/harness/disk_probe.py` (raw sector reads, same method):

| Drive | Interface | Sequential read | **Random 4K latency** | Random 4K IOPS |
|---|---|---:|---:|---:|
| **ORICO CN300 500G** | **USB 3.0 (UASP)** | 414.6 MB/s | **215.1 µs** | 4,642 |
| WDS500G3XHC (current Ubuntu drive) | internal NVMe | 998.4 MB/s | **32.1 µs** | **30,940** |
| WD_BLACK SN750 SE 1TB | internal NVMe | 1703.8 MB/s | 165.6 µs ⚠️ | 6,027 |

> ⚠️ The SN750 SE random numbers are **contaminated**: `llama-server` was running during
> collection (14.3 GB resident, only 1 GB of system RAM free) and the model file on that drive
> was being read the whole time. Its real numbers should land near the blue drive in the row above.

**Why random latency decides this:**

Official docs state that on machines short of RAM, **experts are read from disk** through the system file cache.
This box has **32 GB of RAM < the model size (≈70 GB) → that path is guaranteed.**
So every token can pay a random disk read:

- internal NVMe: **32.1 µs**
- USB: **215.1 µs** → **6.7x worse**

This is a **continuous** cost, not a one-time load cost. **The problem with USB is not that it is slow. It is that it makes the conclusion wrong.**

**Sequential bandwidth is secondary**: 415 MB/s loads a 70 GB model in about 169 s, once, which is fine.
So a USB drive works as a **model store/backup**, not as a **runtime drive**.

**Two more USB-specific risks:**
- Install Ubuntu on it and **system I/O, swap and model reads all squeeze onto one USB 3.0 link**
  (415 MB/s is already the ceiling: UASP, straight into a USB 3.0 root hub — another port will not be faster);
- USB storage dropping off under sustained full load is a known risk, and a drop mid-run voids the whole test.

### 2.2 Plan: move no partitions

Three routes. **B+** is the recommendation:

| Option | What to do | Cost | Risk |
|---|---|---|---|
| A. Grow the existing Ubuntu | shrink <data disk> → in GParted **move** ext4 left against <data disk> → grow right to ≈330 GB | move a 53.57 GB partition, 20 to 40 min | medium. Moving partitions is routine, but this is the only Linux partition you have |
| **B+ (recommended)** | shrink <data disk> to ≈120 GB (≈292 GB freed) → **delete the old ext4** → create one **≈345 GB ext4** over "the 292 GB freed + the old 53.57 GB" → install Ubuntu 24.04.3 | reinstall + rebuild the environment | **low. No partition is moved** (the gap freed by shrinking F sits exactly in front of ext4), existing data untouched |
| C. USB drive | install Ubuntu on the CN300 | least effort | **high. 6.7x random latency, three I/O streams on one USB link, drop-off risk** |

**The full case for B+** (against the measured numbers):

1. Ubuntu, the model and swap all land on the **internal NVMe (32.1 µs random)**, not USB (215.1 µs);
2. **No partition is moved** — ext4 sits right behind F, so the space freed by shrinking F is already in the right place;
3. It also gets you kernel 6.14 (the full B50 support line, see §4.1).

**Before you start, confirm there is nothing to keep in the old Ubuntu (53.57 GB).**
It looks freshly installed with no environment built (otherwise it would not be 53.57 GB), but confirm it yourself.
Back up the 89.4 GB on <data disk> first as well.

> **The only good use for the CN300**: a zero-risk check that the link works at all,
> or as a transport/backup drive for model files. **But its speed numbers are not usable** —
> the drive skews the result and produces a wrong read on what B50 can really do.

---

## 2.3 B+ step by step

### Version: the ISO already on this machine is 26.04 — use it

The local `<Ubuntu ISO file>` (6.07 GB) **passes checksum**:

| | SHA256 |
|---|---|
| Local file | `487f87faaf547ea30e0aba4d5b53346292571256b25333a978db1692bcee9dd2` |
| Canonical | `487f87faaf547ea30e0aba4d5b53346292571256b25333a978db1692bcee9dd2` ✅ |

**Why 26.04 and not 24.04.3:**

| | Ubuntu 24.04.3 | **Ubuntu 26.04 LTS** |
|---|---|---|
| Kernel | 6.14 (HWE) | **Linux 7.0** |
| B50 (needs ≥6.14) | ✅ | ✅ |
| **B70 (needs ≥6.17)** | ❌ **not enough** | ✅ |
| Support window | 2029 / 2039 | **2031 / 2041** |

→ **26.04 covers both B50 and B70 on one disk.** With 24.04.3 you would install the OS again to test B70 Strata later.
(The ISO library also has a `26.04.1` refresh; either works, both are kernel 7.0.x.)

**The one risk**: the community-verified Strata path is **24.04 + oneAPI 2026.1.1 + NEO 26.09**.
26.04 is a newer release with newer Mesa / NEO / Level Zero — probably better, but it is not that verified combination.
The Docker path sidesteps the host oneAPI version (the image ships its own).

### Steps

#### Phase one: boot media and BIOS

1. **Copy the ISO to the Ventoy drive (<USB drive>)** — no boot media to create. <USB drive> is the CN300,
   already running Ventoy (label `Ventoy`, exFAT, currently 456.8 GB free).
2. **Turn off Secure Boot in BIOS.** ⚠️ Ventoy will not boot directly with Secure Boot on
   (it needs MOK keys enrolled). Turning it off is the least painful path before a Linux install.
3. **Turn off Windows Fast Startup, then shut down fully** (not restart):
   ```powershell
   powercfg /h off
   ```
   > A full shutdown is required. If NTFS is left hibernated, any resize can corrupt the filesystem.

4. **Confirm there is nothing irreplaceable on <data disk>.** Current contents (89.4 GB used):
   `ARC PRO系列图`, `BaiduNetdiskDownload`, `ComfyUI-Intel`, `LLM`, `MyDrivers`, `oneMKL_pkg`
   → shrinking **loses no data** (it only frees the tail), but the resize moves data,
   so **copy anything important elsewhere** before you touch it.
5. **Confirm there is nothing to keep in the old Ubuntu (53.57 GB ext4).** It looks freshly installed with no environment built.

#### Phase two: partitioning — all of it in Live GParted

> **Why not Windows "Shrink Volume"**: <data disk> has 322.5 GB free,
> but Windows will only give up **10.76 GB** (measured with `Get-PartitionSupportedSize`).
> Shadow copies are ruled out (<data disk> usage 0 bytes), and so is the page file (it lives on <non-system disk>).
> The real cause is **fragmentation**: **15,445** fragmented files on <data disk>, free space broken into **3,665** extents
> (largest contiguous 184.09 GB), with files sitting at ≈401 GB —
> **Windows does not move files, so it can only shrink up to the last one.**
> GParted's `ntfsresize` moves files and does it in one pass, and you have to be in Live to delete/create partitions anyway.

6. Boot from Ventoy → pick **Try Ubuntu** (go to the Live desktop, do not install yet)
7. Open **GParted** and work in this order (apply each step with ✓):

   | Step | Action | Result |
   |---|---|---|
   | a | shrink `<data disk>` (ntfs) **to 200 GB** | `[<data disk> 200][free 212][ext4 53.57]` |
   | b | delete the old `ext4` partition | `[<data disk> 200][free ≈265]` becomes one block |
   | c | create **ext4** in the free space (future `/`), about **200 GB** | — |
   | d | create **linux-swap**, **64 GB** | 32 GB of RAM cannot hold a 35 to 55 GB working set; swap is mandatory |
   | e | apply | — |

   > **Why 200 GB is enough**: model 70 + Docker image 13 + oneAPI 5 + build/cache 5 +
   > system 20 + swap 64 ≈ **177 GB**. The less you shrink, the less data moves and the shorter it takes.

   > ⚠️ **Cost of skipping step a**: a moves data; on a 412 GB disk expect 10 to 40 min.
   > **Never cut power mid-way.** That is why you back up first.

8. Close GParted, run the installer → choose **"Manual partitioning / Something else"**
   - set the new ext4 as **`/`**, **do not tick format** (it is already ext4)
   - set the swap partition as swap
   - **reuse the existing 0.29 GB ESP (EFI system partition)**; ⚠️ **do not format it**
   - for "device for boot loader installation" pick **disk 0** (the WD 500G)

   > **Never pick "Erase disk and install"** — that wipes Windows too.

#### Phase three: verify right after install

```bash
uname -r                                          # expect 7.0.x
lspci -nn | grep -i 8086                          # expect [8086:e212] Arc Pro B50
ls /sys/class/drm/                                # the card is visible to setup_intel.py
free -h && swapon --show                          # confirm swap is active
lscpu | grep -o 'avx512[a-z_]*' | sort -u         # confirm AVX-512 is there
```

> If `lspci` shows the card but `/sys/class/drm` is empty, add `xe.force_probe=e212` per §4.1.

#### Fallback: a quick check without touching partitions

To confirm the link works at all with zero risk, **leave the partitions alone**:
install Ubuntu on the CN300 (USB), run it once, and only ask for "boots, sees the card, installs Strata, emits tokens".
**Its speed numbers are void** (see §2.1: 6.7x random latency).

---

## 2. 🟡 RAM: 32 GB is the official floor, not the recommendation

Official text (`docs/INTEL_ARC.md` + project docs):

> VRAM: the port keeps the experts on the card (`--stream-experts`).
> **A 32 GB card holds the Coder IQ1_M or IQ2_XS. Smaller cards mirror part of the experts in RAM and are slower.**

> RAM: **32 GB is the minimum; 64 GB is the real recommendation, the point where every model tier runs.**
> Strata **loads 35 to 55 GB into RAM** and pins part of it for the GPU.

**B50 is a 16 GB card → it must take the "mirror part of the experts into RAM" path → RAM is the bottleneck, not VRAM.**

Against the closest community data (JR-Strata / Arc Pro B60 24 GB, IQ3_XXS, 128K context):

| Tier | Experts | Footprint |
|---|---:|---:|
| B60 VRAM | 10,617 | ≈17.22 GiB |
| **System RAM (pinned)** | 13,959 | **≈22.75 GiB** |

→ A 24 GB card still needs **22.75 GiB of RAM** for experts. B50 has 16 GB of VRAM,
so **more experts have to be mirrored into RAM**, not fewer. From 31.1 GB of total memory, subtract 3 to 4 GB for the system and KV,
plus file cache for the n-gram table — headroom is very thin.

**What this means for the reproduction:** the community figure of ≈23 to 27 tok/s for B50 16 GB
most likely came from a **64 GB** machine. Numbers from this 32 GB box are **lower by construction**,
and the gap is RAM, not the card. **That is why this run is worth doing to answer "does 32 GB work at all",
not "can it match 23 tok/s" — the first question is the one that matters.**

---

## 3. 🟢 Move it back to the primary slot: Strata is a PCIe-sensitive load

**This runs opposite to the llama.cpp conclusion with the parameters set right. Do not mix the two up — both are true.**

| Engine | What crosses PCIe per token | Does the slot matter |
|---|---|---|
| llama.cpp + `-ncmoe 8` | activations only (tens of KB) | **no** (measured 2.9% difference, below the 13.9% noise of the secondary slot itself) |
| llama.cpp + `-ncmoe 4–7` | **whole layers/expert weights shuttle back and forth** | **yes** (secondary slot measured a 41%–59% throughput loss) |
| **Strata (Intel SYCL port)** | **expert weights** (`--stream-experts`, streamed from RAM/pinned memory to the GPU) | **critically** |

JR-Strata lists "H2D bandwidth ≈6.8 GB/s (PCIe 4.0 x4 via OCuLink)" as a key metric,
precisely because experts stream from the host side into the GPU.

→ One rule covers both: **if weights cross PCIe continuously, the slot is the bottleneck; if only activations cross, the slot does not matter.**
llama.cpp `-ncmoe 4–7` (weights move) and Strata (weights stream) fall on the same side;
`-ncmoe ≥ 8` (nothing moves) falls on the other.

→ **Before testing Strata, move B50 back to the primary slot PCIE1 (x8).** The secondary x4 slot loses badly under this load,
and it makes "can it reach 23 tok/s" a meaningless question.

---

## 4. Software checklist

### 4.1 OS: the kernel version is the easiest way to waste this whole project

Intel's official support table (look up by PCI ID; **cards of the same generation differ**; the table **covers this product line only**):

| PCI ID | Model | Architecture | Initial support (experimental) | **Full support (on by default)** |
|---|---|---|---|---|
| **E212** | **Arc Pro B50** | Xe2 Battlemage | **kernel 6.11** | **Ubuntu 24.04+ (kernel 6.14)** |
| E211 | Arc Pro B60 | Xe2 | not available | Ubuntu 24.04+ (kernel 6.15) |
| E223 | Arc Pro B70 | Xe2 | not available | Ubuntu 25.10+ (kernel 6.17) |

**What this means here:**

1. **Ubuntu 24.04.3 (HWE kernel 6.14) is the bar for B50 on this machine**; `uname -r` must show `6.14.x`.
2. **Ubuntu 24.04.1 ships kernel 6.8 — unusable for B50. Not "slow": the card is not detected.**
   If that Ubuntu is 24.04.1, upgrade the HWE kernel first, or just reinstall 24.04.3.
3. **On 6.11 to 6.13 (24.04.2's 6.11) the card is "experimental, not enabled by default"**,
   and may need `xe.force_probe=e212` on the kernel command line before it is detected.
   → If `lspci` sees the card but `sycl-ls` / `/sys/class/drm` do not, **try this first**.
4. Also note: **full B70 support needs Ubuntu 25.10 (6.17).**
   So do not use 24.04 when you test B70 Strata later — the two need different systems.

After boot, run these three:

```bash
uname -r                                          # expect >= 6.14 (the full B50 support line)
lspci -nn | grep -i vga                           # should show Arc Pro B50 [8086:e212]
ls /sys/class/drm/                                # setup_intel.py finds the card through this
```

> If `lspci` shows the card but the last two come back empty → the kernel is too old or the card is not enabled. Try the kernel parameter:
> ```bash
> sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 xe.force_probe=e212"/' /etc/default/grub
> sudo update-grub && sudo reboot
> ```

### 4.2 GPU driver and runtime

```bash
sudo apt update
sudo apt install -y intel-opencl-icd libze1 libze-intel-gpu1
```

> If the Ubuntu-shipped version is too old (`xe` + Level Zero V2 needs a recent NEO),
> use Intel's client GPU repository: <https://dgpu-docs.intel.com/driver/client/overview.html>

**The step people trip on — group membership:**

```bash
sudo usermod -aG render $USER     # without this, sycl-ls lists CPU only, no Arc
sudo usermod -aG docker $USER
# then log in again (log out and back in; a new terminal is not enough)
```

Check: `sycl-ls` should list Arc. **If it lists CPU devices only, you are not in the `render` group.**

### 4.3 Build dependencies

Two paths. Start with Docker (the one `./setup.sh --backend sycl` uses):

```bash
sudo apt install -y docker.io git
git clone https://github.com/Niko1221/Strata
cd Strata
docker build -t strata-sycl-dev sycl/tools           # about 6 min, produces a 13 GB image
```

Only the native build (no Docker) needs oneAPI:

```bash
sudo apt install -y intel-oneapi-compiler-dpcpp-cpp intel-oneapi-mkl-devel ninja-build cmake git
```

> Official requirement: **DPC++ 2025.3 or newer** (testing used 2026.1).

### 4.4 AOT targets — **B50 is not on the official list; confirm it on site**

The official AOT targets (this product line only):

| Target | Card |
|---|---|
| `bmg-g31` | Arc Pro B70 32G |
| `bmg-g21` | **Arc Pro B60** |

**B50 (`e212`) does not appear in this table.** After boot, run:

```bash
sycl-ls
ocloc ids bmg-g21     # check whether the reported device id matches B50
```

Then decide between `-DSTRATA_SYCL_AOT=bmg-g21` and no AOT at all (JIT).
**Cost of no AOT: every kernel is JIT-compiled at first launch; the docs say about 47 s.** Slow, not broken.

### 4.5 Environment variables (`xe` cards only; skip them and you hit bugs)

| Variable | Value | Why |
|---|---|---|
| `SYCL_CACHE_PERSISTENT` | **`0`** | the persistent JIT cache **crashes on first compile on Xe2** |
| `ZES_ENABLE_SYSMAN` | `1` | needed by the native runtime |
| `STRATA_VERIFY_DEVICE_PLAN` | `1` | needed by the native runtime |
| `STRATA_VERIFY_NO_HOST` | **`1`** | **required on `xe` whenever any expert sits outside VRAM**, otherwise the output is NaN logits. B50 always hits this case |

> `strata-sycl.sh` sets `STRATA_VERIFY_NO_HOST=1` for you; with the native runtime you set it yourself.
> Also: `source /opt/intel/oneapi/setvars.sh` aborts in a shell with `set -u` on
> `OCL_ICD_FILENAMES: unbound variable` (known in oneAPI 2026.1.1) — run `set +u` first.

---

## 5. Model choice

Strata tiers: `Q2_0` / `IQ2_XS` / `IQ3_XXS` / `IQ3_S` / `Coder (IQ1_M)`.
The installer downloads **about 70 GB** by default.

**This machine (16 GB VRAM + 32 GB RAM) can only take the smallest tier.** Reference sizes:

| Tier | Must stay resident | Size |
|---|---:|---:|
| Q2_0 / IQ2_XS | weight shards | 35 to 40 GB |
| of which the n-gram table (mmap-able on SSD) | — | 28.8 GB |
| IQ3_XXS and up | — | larger; out of scope here |

> **One counter-intuitive point**: `Q2_0` is slightly smaller than `IQ2_XS`, yet **prompt throughput is 3.4x higher**.
> It avoids the quant format that depends on a large lookup table, and on this model the decode lookup table dominates.
> **Pick Q2_0 for speed, IQ2_XS for quality.** For a first run start with **Q2_0** — prove the link works and the speed looks sane,
> then switch to IQ2_XS for comparison.

**Check the disk before downloading**: 70 GB model + 13 GB image + swap, see §1.

---

## 6. Safety red line (official warning — do not cross it)

> **Do not ask for more VRAM than the card has.** On the `xe` driver, an allocation past
> VRAM can push buffers into RAM until the machine runs out of memory and stalls.
> **Leave about 1.5 GB free.**

In plain terms: on the `xe` driver, **when the configuration asks for more VRAM than the card has, the driver does not error — it pushes buffers into system memory until RAM is exhausted and the machine hangs.**

This box is a **16 GB card + 32 GB RAM**, the combination most likely to hit it. So:

- count B50's usable VRAM as **15.51 GiB** and ask for **≈14 GB at most** in the config;
- close everything that eats RAM before running (**nothing left in the background on the Windows side**; the two systems never run at once, but confirm before rebooting);
- when it breaks, read `dmesg` first instead of retrying.

---

## 7. Order of execution (suggested)

1. **Decide the disk plan** (recommended: the Live+GParted path in §2.3 — shrink <data disk> to 200 GB → delete the old ext4 →
   create ext4 200 GB + swap 64 GB → install 26.04, **all in one place, no existing partition moved**)
   → skip this and everything after it is wasted
2. Prepare Ubuntu 24.04.3, confirm kernel ≥ 6.12 and that `lspci` shows `e212`
3. Install the GPU driver + `render`/`docker` groups, **log in again**, `sycl-ls` shows Arc
4. **Move B50 back to the primary slot PCIE1** (§3)
5. Carve out ≥64 GB of swap
6. `git clone` Strata → `docker build` the 13 GB image
7. `./setup.sh --backend sycl --model Q2_0 --context 32768`
8. Once it runs, record: **does it start / does it fall back to SSD / decode / prefill / peak RAM and swap**
9. Then try IQ2_XS for comparison

---

## 8. What this reproduction means for customers (think it through before you start)

The community B50 16 GB table **does not state the test machine's RAM**. This box has 32 GB, the official floor;
the community run was most likely 64 GB. The two outcomes read very differently:

| Result | Reading | What it means |
|---|---|---|
| Runs on 32 GB, clearly below 23 tok/s | **most likely.** The gap is RAM, not the card | "B50 can run 125B, but 32 GB is the floor for it: smallest quant only, and expect SSD fallback" |
| Does not run on 32 GB | a valuable negative result all the same | "32 GB is not enough for a 125B-class model — do not commit to it" |

**Both are deliverable conclusions**, but **only with `ram_gb: 32` recorded next to them.**
Add RAM to 64 GB before testing and the numbers are invalid for 90% of customers —
same rule as before: **the test environment's `ram_gb` must be registered with the data.**
