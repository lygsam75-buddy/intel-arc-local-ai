#!/usr/bin/env bash
# ============================================================
#  16 GB 档：量化档 × -ncmoe 拐点扫描
#  B50 16G (15.51 GiB 可用) · Qwen3.6-35B-A3B · SYCL · 主槽
#
#  为什么单独做这一轮：
#    Q4_0 是 19.41 GiB，装不进 15.51 GiB 显存，所以必须先卸载专家
#    （拐点在 -ncmoe 8，37.6 tok/s）。但那只是"装不下的情况下怎么救"。
#    真正要回答的是相反的问题：**换小一档量化，把整模型塞进显存之后，
#    拐点去哪了？** 如果权重全驻留，-ncmoe 0 就该是最优，
#    而且速度路线从"CPU 算专家"换成"全 GPU"，量级会变。
#
#  两个档位是刻意选的，覆盖两个不同的问法：
#    IQ2_M  10.73 GiB  —— 舒适区。留 4.78 GiB 给 KV，验证"全驻留"这条路
#    Q3_K_S 14.30 GiB  —— 边界。只留 1.21 GiB，验证"最大能上到哪档还全驻留"
#    中间的 IQ2_XXS / Q2_K_XL / IQ3_* 按需补，规律出来再决定要不要铺满。
#
#  ------------------------------------------------------------
#  跑之前必须先清场（否则数字全是别人的）：
#    <部署目录>\stop_model.ps1
#  它同时清掉 llama-server / watchdog 的 cmd.exe / wscript launcher。
#  只杀 llama-server 会被 watchdog 在 15 秒内拉回来 —— 详见
#  docs/pitfalls.md 3.4。清完确认这三样都不在了再动手。
#
#  清场后还要等页面文件回写完（见 docs/pitfalls.md 1.7），
#  经验判据：空闲物理内存稳定、不再增长。
# ============================================================
set -u

# 路径全部走环境变量；仓库根目录直接从本脚本位置推出来，不用手填。
REPO="${ARC_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MODELS="${ARC_MODELS:?请先设置 ARC_MODELS=<GGUF 所在目录>}"
BIN="${ARC_LLAMA_BIN:?请先设置 ARC_LLAMA_BIN=<llama.cpp 的 build/bin>}"
OUT="$REPO/bench/data"
SYCL="${ARC_SYCL_PATH:-}"

GPU="Intel Arc Pro B50 LP 16G"
DRIVER="32.0.101.8976"

# 用 managed python，别用系统 python
PY="${ARC_PYTHON:-python}"

export ONEAPI_DEVICE_SELECTOR=opencl:0

# r=1：B50 场景下 decode 稳态与 reps 关系不大（实测 3.13 vs 3.06），
# 而每加一个点要多花几分钟，扫拐点用 r=1 足够，拐点确认后再补 r=3。
COMMON=(
  --bin "$BIN"
  --gpu "$GPU" --driver "$DRIVER" --ecc off
  --device-selector opencl:0
  --sycl-path "$SYCL"
  --reps 1 --pp 512 --tg 128
  --outdir "$OUT"
)

run_one () {   # $1=模型文件 $2=量化名 $3=tag  $4=ncmoe 列表
  local model="$MODELS/$1" quant="$2" tag="$3" pts="$4"
  [[ -f "$model" ]] || { echo "[SKIP] 模型不存在: $model"; return; }
  echo "=============================================================="
  echo "  $quant   $(stat -c %s "$model" | awk '{printf "%.2f GiB", $1/1073741824}')"
  echo "=============================================================="
  "$PY" -u "$REPO/bench/harness/scan_ncmoe.py" \
    --model "$model" \
    --quant "$quant" \
    --tag "$tag" \
    --ncmoe "$pts" \
    "${COMMON[@]}"
}

# 舒适区：预期 -ncmoe 0 就是最优，0 与 8 的差距就是"全驻留"值多少
run_one "Qwen3.6-35B-A3B-UD-IQ2_M.gguf" "IQ2_M" "b50-16g-iq2m-ncmoe-pcie5x8" "0,2,4,8,16,32"

# 边界：14.30 GiB，只留 1.21 GiB 给 KV 和计算缓冲
# 若 0 直接 OOM，那本身就是结论 —— 记下来，别跳过
run_one "Qwen3.6-35B-A3B-UD-Q3_K_S.gguf" "Q3_K_S" "b50-16g-q3ks-ncmoe-pcie5x8" "0,2,4,8"

echo
echo "全部完成。数据在 $OUT"
echo "对照组（已测）：Q4_0 19.41 GiB 装不进显存，拐点 -ncmoe 8 = 37.6 tok/s（主槽）"
