#!/usr/bin/env bash
# ============================================================
#  B60 24G 的 llama-server 口径 B：交付配置 + -c 天花板 + 视觉塔代价
#  Intel Arc Pro B60 24G (23.33 GiB 可用) · Qwen3.6-35B-A3B Q4_0 · SYCL · CPU 直连槽
#
#  为什么补这一轮：
#    B60 此前只有 llama-bench（口径 A：xpu_bench.py）与 ctx 分配扫描（H-04）。
#    **口径 B 是 ⛔** —— 真起 llama-server、打 /completion 量的数一条都没有。
#    而「客户照着抄就能跑出来的配置上量到的速度」才是对客口径
#    （见 docs/server-config.md §4.2 的纪律：对外报的速度必须是交付配置上量出来的，
#    不是 llama-bench 的峰值）。B50 那一侧已有 8 组交付配置 / 32 个采样，
#    B60 补齐才谈得上跨卡并排。
#
#  与 B50 的差异（按容量改判，不是照抄）：
#    B50 16G 装不下 Q4_0（19.41 GiB > 15.51 GiB 可见）→ 必须 -ncmoe 8 卸专家，
#    交付配置写在 docs/server-config.md §3。
#    B60 24G 装得下（19.41 < 23.33）→ ncmoe=0 全驻留，且 llama-bench 已实测
#    ncmoe=0 比 8 快 15%（52.43 vs 44.40 tok/s）。
#    → **B60 的交付配置 = B50 的「as-delivered」档**，这一轮就是要把这句话在
#      真 server 上确认一遍。
#
#  为什么要 --server-verbose：
#    默认 verbosity=3 时日志只有 58 行，**不含 KV / compute / model buffer 分配行**
#    （B60 ctx 那 4 条实测踩过：grep 全日志 0 命中）。没有那几行就答不出
#    「为什么慢 / 装不装得下」，--sample-vram 的性能计数器读数也没有对照物。
#    B50 的 8 组交付配置记录同样是 -v 下采的（其日志 verbosity = 2147483647）。
#
#  预测（写下来等着被打脸）：
#    c16384  KV(q8_0) ≈ 170 MiB（同模型同档 → 与 B50 同值）
#                    → 独显 ≈ 19.41 GiB + 0.17 GiB ≈ 19.6 GiB，装得下
#    c262144 KV(q8_0) ≈ 2.66 GiB → 独显 ≈ 22.1 GiB，仍 < 23.33 GiB
#                    → 预期 256K **也能加载**，但 decode 随 KV 变大往下掉
#    decode：B60 456 GB/s vs B50 224 GB/s（约 2×），同为全驻留 / 部分驻留，
#           预期 B60 交付配置 decode 落在 B50（35.55~37.55）与 B70（39.8~45.1）之间偏上。
#
#  跑之前先清场：确认 8188（用户常驻 ComfyUI）**没抢没杀**，本队列走 8099。
# ============================================================
set -u

# 路径全部走环境变量；仓库根目录直接从本脚本位置推出来，不手填。
REPO="${ARC_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MODELS="${ARC_MODELS:?请先设置 ARC_MODELS=<GGUF 所在目录>}"
BIN="${ARC_LLAMA_BIN:?请先设置 ARC_LLAMA_BIN=<llama.cpp 的 build/bin>}"
PY="${ARC_PYTHON:-python}"
SYCL="${ARC_SYCL_PATH:-}"
OUT="$REPO/bench/data"
LOGS="$REPO/bench/logs"

export ONEAPI_DEVICE_SELECTOR="${ONEAPI_DEVICE_SELECTOR:-opencl:0}"

MODEL="$MODELS/Qwen_Qwen3.6-35B-A3B-Q4_0.gguf"
MMPROJ="$MODELS/mmproj-Qwen3.6-35B-A3B-Q8_0.gguf"

# 交付配置：与 docs/server-config.md §3 / §5.1 同一条命令行，只把 -ncmoe 由 8 改 0。
#   -fa on -ctk q8_0 -ctv q8_0   注意力与 KV 量化档**显式固定**（SYCL 后端在
#                                FA/KV 档不同时走不同注意力内核，交给默认值就无法归因）
#   -lm dio                      load_mode，与 B50 交付配置一致
#   --fit off                    `--fit` 默认开着会先跑一次试算加载，把日志里的
#                                buffer size 写成 0.00 的假数（pitfalls 4.5）
#   --jinja --api-key local --parallel 1   与 B50 交付配置逐字一致
# ⚠️ --api-key 要同时给 server 与 client：只给一边会 4 组全 401、速度字段全空，
#    而加载日志与显存读数一切正常 —— **看起来像跑通了**（pitfalls 记过这个坑）。
DELIVERY="-fa on -ctk q8_0 -ctv q8_0 -lm dio --fit off --jinja --api-key local --parallel 1"

# 平台身份（T-20 必填）：这些值来自 gpu_identity.py / gpu_sysman.py 实测，不照规格表编。
IDENT=( --gpu "Intel Arc Pro B60 24G"
       --driver "${ARC_DRIVER:-32.0.101.9150}" --ecc off
       --device-selector "$ONEAPI_DEVICE_SELECTOR" --sycl-path "$SYCL"
       --slot "CPU 直连槽" --chip E211 --subsys 25421EF7 --vbios 2304140000
       --vram-gib 23.33
       --port 8099 --n-predict 128 --reps 4 --timeout 300 --load-timeout 600
       --sample-vram --server-verbose --api-key local
       --outdir "$OUT" --logdir "$LOGS" )

echo "########## Run 1: B60 交付配置（ncmoe=0 全驻留）+ -c 天花板 + 视觉塔代价 ##########"
"$PY" -u "$REPO/bench/harness/ctx_sweep.py" \
  --bin "$BIN" --model "$MODEL" --quant Q4_0 --ncmoe 0 \
  --tag "b60-servercfg" \
  "${IDENT[@]}" \
  --extra-args "$DELIVERY" \
  --configs "b60-c16384|-c 16384;b60-c16384-mmproj|-c 16384 --mmproj $MMPROJ --image-min-tokens 1024;b60-c32768|-c 32768;b60-c65536|-c 65536;b60-c131072|-c 131072;b60-c262144|-c 262144"

echo
echo "########## Run 2: 同一条交付配置但卸专家（ncmoe=8）——确认方向在真 server 上也成立 ##########"
"$PY" -u "$REPO/bench/harness/ctx_sweep.py" \
  --bin "$BIN" --model "$MODEL" --quant Q4_0 --ncmoe 8 \
  --tag "b60-servercfg-ncmoe8" \
  "${IDENT[@]}" \
  --extra-args "$DELIVERY" \
  --configs "b60-c16384-ncmoe8|-c 16384"

# ------------------------------------------------------------
#  自检：**真的跑了吗**。rc=0 不代表跑成了 —— ctx_sweep 内部各档
#  load_failed / probe_failed 也照样返回 0，不数一下就会把环境错误记成 ok。
# ------------------------------------------------------------
echo
echo "########## 自检 ##########"
"$PY" -u - "$OUT" <<'PYEOF'
import glob, json, os, sys

out = sys.argv[1]
rows = []
for p in sorted(glob.glob(os.path.join(out, "*b60-servercfg*.json"))):
    try:
        d = json.loads(open(p, encoding="utf-8").read())
    except Exception as e:
        rows.append((os.path.basename(p), "PARSE_FAIL", str(e)[:60]))
        continue
    v = d.get("vram_after_probe") or d.get("vram") or {}
    rows.append((d.get("config_name"), d.get("status"),
                 d.get("decode_tok_s"), d.get("decode_n"),
                 d.get("spread_pct"), v.get("vram_dedicated_mb"),
                 v.get("vram_shared_mb")))
for r in rows:
    print("   %-24s %-13s decode=%-7s n=%-3s spread=%-5s vram=%s shared=%s" % r)
bad = [r for r in rows if r[1] not in ("active", "ok")]
print("共 %d 条；非 active %d 条" % (len(rows), len(bad)))
if not rows:
    sys.exit("[自检失败] 一条产出都没有 —— 队列没跑起来，别往下走")
if len(bad) == len(rows):
    sys.exit("[自检失败] 全部非 active —— 这是环境错误，不是负结果")
PYEOF

echo
echo "全部完成。数据在 $OUT，日志在 $LOGS"
