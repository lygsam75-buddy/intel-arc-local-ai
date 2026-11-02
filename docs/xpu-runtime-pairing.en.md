# Same code, 3× slower: the SYCL pairing rule for XPU runtimes (measured)

> **Bottom line:** when building the ComfyUI Intel XPU runtime (comfy-aimdo) yourself, the **SYCL runtime the compiler links against must match the sycl DLL that ships with torch**. Same source, same B70, same parameters — only the linked SYCL runtime differs (sycl8 vs sycl9): a 5 s 480p Pika H3 Flex clip goes from **377 s to 104 s (3.6×)**. Version numbers are a distraction; pairing is what matters.

- Rig: Arc Pro B70 32G (ECC off) + Ryzen 5 9600X + 32 GB RAM + Windows, 2026-11-02
- Ready-to-install pack: **[Release: xpu-runtime-sycl9-20261102](https://github.com/lygsam75-buddy/intel-arc-local-ai/releases/tag/xpu-runtime-sycl9-20261102)**

## How it surfaced

A Pika H3 Flex benchmark ran at **111.8 s** per 5 s 480p clip in the morning on the integration-pack runtime, then **350–380 s** in the afternoon on a self-built runtime (AIMDO 0.6.0). Single variable: we installed oneAPI and compiled the XPU runtime ourselves.

Ruled out by single-variable reruns: code version (old commit rebuilt on the same toolchain = same speed as 0.6.0), init parameters (allocator mode, headroom), init timing, cache effects. **Confirmed:** rebuilding against oneAPI 2026.1 (sycl9) restored 112.1 s / 104.1 s.

## Mechanism

`aimdo_xpu.dll` links one SYCL runtime. torch 2.13/2.14+xpu ships **sycl9.dll** (`python_embeded\Library\bin`), tuned with its UR adapters; oneAPI 2025.x compilers link **sycl8.dll**. A sycl8-linked dll keeps the slower dispatch path even when torch's UR stack is nearby.

**Quick check:** look at `sycl*.dll` next to `aimdo_xpu.dll` in the `comfy_aimdo` package dir — it must match torch's `Library\bin` version (9).

## Measured (B70, seed 20261220, wall clock Queue → MP4)

| Workflow (5.2 s clip, with audio) | sycl8 build | sycl9 build | integration runtime |
|---|---|---|---|
| Pika 6-step 832×480 | 377 s | **104–112 s** | 111.8 s |
| Pika 6-step 1344×768 | 529–536 s | **336 s** | 316.7 s |
| Base 20-step 832×480 | 448–460 s | **224 s** | 250.3 s |
| Base 20-step 1344×768 | 1073–1088 s | **920 s** | 1130.5 s |

Six-step distillation speedup under sycl9: **2.0×** (480p) / **2.7×** (768p). Output stability: bit-identical on repeat runs at 480p six-step; <0.3% size drift elsewhere (normal GPU atomics jitter).

## Three rules

1. **SYCL pairing** — match the compiler's linked SYCL major version to torch's `syclN.dll` (sycl9 → oneAPI 2026.x).
2. **Never stack acceleration LoRAs** on distilled adapters (Pika H3 Flex's six steps are the trained schedule).
3. **32 GB RAM rigs** — use the nvfp4 text-encoder tier; pagefile is the only expandable "memory".

## Install the pack

`pika-h3-flex-xpu-runtime-sycl9-win64.zip` (5.8 MB) from the [release page](https://github.com/lygsam75-buddy/intel-arc-local-ai/releases/tag/xpu-runtime-sycl9-20261102): sycl9-linked `comfy-aimdo 0.6.0+xpu`, kitchen 0.2.40, the sycl9 runtime DLL set, and `install.ps1`.

Sources: [xiangyuT/comfy-aimdo-xpu](https://github.com/xiangyuT/comfy-aimdo-xpu) (AIMDO 0.6.0 + XPU port, incl. one `dxcore.lib` link fix) / [comfy-kitchen-xpu](https://github.com/xiangyuT/comfy-kitchen-xpu); sycl9/UR DLLs are Intel/torch redistributables.

See also: [Pika H3 Flex on B70](comfyui-pika-h3-flex.en.md).
