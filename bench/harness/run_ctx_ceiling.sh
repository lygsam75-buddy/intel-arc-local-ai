#!/usr/bin/env bash
# ============================================================
#  16 GB 档：上下文天花板 + KV 量化的真实显存账
#  B50 16G (15.51 GiB 可用) · Qwen3.6-35B-A3B · SYCL · 主槽
#
#  为什么补这一轮：
#    D 节原来只问了「-c 能开到多少」，但实测发现**分配几乎不花钱**
#    （IQ2_M 从 -c 4096 到 262144 只掉 1.6%）。真正的问题变成了两个：
#
#    1. **哪个量化档还能开到 262144？**
#       IQ2_M (10.73 GiB) 余 4.78 GiB —— 已实测能开满。
#       Q3_K_S (14.30 GiB) 只余 1.21 GiB —— 强压缩档位，这里就是要找它的边界。
#       这直接决定 B 节「Q3_K_S 省 5 GiB 换更长上下文」这句话**对不对**。
#
#    2. **KV 到底占多少字节？**
#       llama-server 的日志在 SYCL 上报 `SYCL0 KV buffer size = 0.00 MiB`，
#       是**假数**（见 docs/pitfalls.md 4.5）。所以只能：
#         a) 用 `-ctk f16` 把 KV 体积翻一倍，看 OOM 边界往哪移 —— 间接验证；
#         b) 直接用 Windows 性能计数器读**真实**显存（xpu_vram.py）—— 直接量。
#       两条路互为交叉验证。
#
#  预测（写下来等着被打脸）：
#    KV 每 token = (n_embd_k_gqa + n_embd_v_gqa) × 10 层
#                = 1024 值 × 10 层 = 10240 值/token
#      q8_0 ≈ 1.0625 B/值 → 10.9 KiB/token → -c 262144 约 2.66 GiB
#      f16  = 2 B/值       → 20.0 KiB/token → -c 262144 约 5.00 GiB
#    推论：
#      IQ2_M + q8_0  @262144 = 10.73 + 2.66 ≈ 13.4 GiB → 装得下（实测已确认）
#      IQ2_M + f16   @262144 = 10.73 + 5.00 ≈ 15.7 GiB → **超过 15.51，应 OOM**
#      IQ2_M + f16   @131072 = 10.73 + 2.50 ≈ 13.2 GiB → 装得下
#      Q3_K_S + q8_0 @262144 = 14.30 + 2.66 ≈ 17.0 GiB → **应 OOM**
#      Q3_K_S + q8_0 @65536  = 14.30 + 0.66 ≈ 15.0 GiB → 临界，可能刚好过
#
#  跑之前先清场：<部署目录>\stop_model.ps1（见 pitfalls 3.4）
# ============================================================
set -u

# 路径全部走环境变量；仓库根目录直接从本脚本位置推出来，不用手填。
REPO="${ARC_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MODELS="${ARC_MODELS:?请先设置 ARC_MODELS=<GGUF 所在目录>}"
BIN="${ARC_LLAMA_BIN:?请先设置 ARC_LLAMA_BIN=<llama.cpp 的 build/bin>}"
OUT="$REPO/bench/data"
LOGS="$REPO/bench/logs"
SYCL="${ARC_SYCL_PATH:-}"
PY="${ARC_PYTHON:-python}"

export ONEAPI_DEVICE_SELECTOR=opencl:0

COMMON=( --bin "$BIN"
         --gpu "Intel Arc Pro B50 LP 16G" --driver "32.0.101.8976" --ecc off
         --device-selector opencl:0 --sycl-path "$SYCL"
         --port 8099 --ncmoe 0 --n-predict 128 --reps 2 --timeout 300
         --load-timeout 240 --sample-vram
         --outdir "$OUT" --logdir "$LOGS" )

# ---- Run B：Q3_K_S 的上下文天花板（q8_0 KV）----
echo "########## Run B: Q3_K_S 上下文天花板 ##########"
"$PY" -u "$REPO/bench/harness/ctx_sweep.py" \
  --model "$MODELS/Qwen3.6-35B-A3B-UD-Q3_K_S.gguf" --quant "Q3_K_S" \
  --tag "b50-16g-q3ks-ctx" \
  "${COMMON[@]}" \
  --configs "c4096-q8|-c 4096 -fa on -ctk q8_0 -ctv q8_0;c65536-q8|-c 65536 -fa on -ctk q8_0 -ctv q8_0;c131072-q8|-c 131072 -fa on -ctk q8_0 -ctv q8_0;c262144-q8|-c 262144 -fa on -ctk q8_0 -ctv q8_0"

# ---- Run C：IQ2_M 的 f16 KV（体积翻倍 → 找 OOM 边界）----
echo "########## Run C: IQ2_M f16 KV 边界 ##########"
"$PY" -u "$REPO/bench/harness/ctx_sweep.py" \
  --model "$MODELS/Qwen3.6-35B-A3B-UD-IQ2_M.gguf" --quant "IQ2_M" \
  --tag "b50-16g-iq2m-f16kv" \
  "${COMMON[@]}" \
  --configs "c4096-q8|-c 4096 -fa on -ctk q8_0 -ctv q8_0;c32768-f16|-c 32768 -fa on -ctk f16 -ctv f16;c131072-f16|-c 131072 -fa on -ctk f16 -ctv f16;c262144-f16|-c 262144 -fa on -ctk f16 -ctv f16"

echo
echo "全部完成。数据在 $OUT，日志在 $LOGS"
