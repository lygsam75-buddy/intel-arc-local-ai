# `bench/logs/` —— 结论的原始证据

这里放的是 **`llama-server` 的原始运行日志**（stdout 重定向），不是整理过的摘要。

**为什么占 17 MB 还要入库**：`docs/` 里的若干结论是**断崖 / 撤回 / 口径修正**的直接产物，
判据就藏在这些日志里。留摘要不留原件，等于把「为什么这么下结论」丢掉。

---

## 路径已归一化（重要）

入库前做了一次**本机绝对路径归一化**，把机器相关的路径串换成占位符：

| 日志里原本的 | 现在写作 |
|---|---|
| `D:\LLM\models\…`、`D:/LLM/models/…` | `<模型目录>/…` |
| `F:\LLM\llama.cpp\build\bin\…` | `<llama.cpp>/build/bin\…` |
| `D:\WorkBuddy\…\intel-arc-ai-cookbook\bench\data` | `bench/data` |
| `D:\WorkBuddy\…\intel-arc-ai-cookbook\bench\logs` | `bench/logs` |

> 表里那个仓库目录名是**归一化当时**的目录名 —— 这一列记录的是「日志原文里出现过的字符串」，
> 与当前仓库名（`intel-arc-local-ai`）无关。

**归一化只动了路径字符串，其余字节逐字节未变** —— 包括：

- 行尾符（仍是 `\r\n`，未做任何换行转换）；
- 时间戳、`offloaded N/N layers`、`SYCL0 model buffer size`、`KV buffer size`；
- `Prompt executed in X seconds`、报错行、`abort` 行。

> 验证方式：把同一套替换规则**重新施加到归一化前的原件**上，结果与入库文件逐字节相等
> （33/33 通过）。归一化前的原件**不随仓库分发**。

**所以：日志的行内容可引用，路径不可引用。**（引用路径时用 `docs/` 里的占位符写法。）

---

## 命名

```
<日期>_<卡><显存>_<用途>-<参数>.log
例：2026-10-16_deliver-c16384-mmproj.log
```

`<用途>` 的取值：`deliver`（交付配置）、`asdelivered`（现场等价）、`ctx` / `ctx2`（上下文扫描）、
`f16kv`（f16 KV 边界）、`q8kv-slope`（KV 斜率）、`longctx`（真实深度曲线）、
`vision`（多模态）、`repeat` / `first` / `second`（复现）。

另有 3 个**独立驱动日志**（无对应数据记录）：`_authtest.log`（鉴权试错）、
`ctx-ceiling-run.log`、`longctx-v2-run.log`（驱动脚本自身的 stdout）。

---

## 日志 ↔ 数据记录对照

每条 `bench/data/*.json` 的 `source` / `log_evidence` / `timing_breakdown.source` 字段
指向这里的文件。反向索引：

| 日志 | 对应数据记录 `bench/data/` |
|---|---|
| `2026-10-15_b50-16g-iq2m-longctx-v2.log` | `2026-10-15_b50-16g-iq2m-longctx-v2.json` |
| `2026-10-15_b50-16g-iq2m-longctx.log` | `2026-10-15_b50-16g-iq2m-longctx.json` |
| `2026-10-15_c131072-f16.log` | `2026-10-15_b50-16g-iq2m-f16kv_c131072-f16.json` |
| `2026-10-15_c131072-faON-q8.log` | `2026-10-15_b50-16g-iq2m-ctx2_c131072-faON-q8.json` |
| `2026-10-15_c131072-q8.log` | `…iq2m-q8kv-slope_c131072-q8.json` / `…q3ks-ctx_c131072-q8.json` |
| `2026-10-15_c16384-default.log` | `2026-10-15_b50-16g-iq2m-ctx_c16384-default.json` |
| `2026-10-15_c16384-faON-q8.log` | `2026-10-15_b50-16g-iq2m-ctx_c16384-faON-q8.json` |
| `2026-10-15_c16384-q8.log` | `2026-10-15_b50-16g-iq2m-q8kv-slope_c16384-q8.json` |
| `2026-10-15_c262144-f16.log` | `2026-10-15_b50-16g-iq2m-f16kv_c262144-f16.json` |
| `2026-10-15_c262144-faON-q8.log` | `2026-10-15_b50-16g-iq2m-ctx2_c262144-faON-q8.json` |
| `2026-10-15_c262144-q8.log` | `2026-10-15_b50-16g-q3ks-ctx_c262144-q8.json` |
| `2026-10-15_c32768-f16.log` | `2026-10-15_b50-16g-iq2m-f16kv_c32768-f16.json` |
| `2026-10-15_c32768-faON-q8.log` | `2026-10-15_b50-16g-iq2m-ctx2_c32768-faON-q8.json` |
| `2026-10-15_c4096-default.log` | `2026-10-15_b50-16g-iq2m-ctx_c4096-default.json` |
| `2026-10-15_c4096-faON-q8.log` | `2026-10-15_b50-16g-iq2m-ctx_c4096-faON-q8.json` |
| `2026-10-15_c4096-q8.log` | `…iq2m-f16kv_c4096-q8.json` / `…q3ks-ctx_c4096-q8.json` |
| `2026-10-15_c65536-faON-q8.log` | `2026-10-15_b50-16g-iq2m-ctx2_c65536-faON-q8.json` |
| `2026-10-15_c65536-q8.log` | `…iq2m-q8kv-slope_c65536-q8.json` / `…q3ks-ctx_c65536-q8.json` |
| `2026-10-16_asdelivered-c16384-mmproj.log` | `2026-10-16_b50-16g-q4_0-asdelivered-ncmoe0_asdelivered-c16384-mmproj.json` |
| `2026-10-16_asdelivered-c262144-mmproj.log` | `2026-10-16_b50-16g-q4_0-asdelivered-ncmoe0_asdelivered-c262144-mmproj.json` |
| `2026-10-16_b50-16g-q4_0-vision-nothink.log` | `2026-10-16_b50-16g-q4_0-vision-nothink.json` |
| `2026-10-16_b50-16g-q4_0-vision.log` | `2026-10-16_b50-16g-q4_0-vision.json`（`status: discarded`，留作反例） |
| `2026-10-16_deliver-c16384-mmproj.log` | `2026-10-16_b50-16g-q4_0-servercfg_deliver-c16384-mmproj.json` |
| `2026-10-16_deliver-c16384.log` | `2026-10-16_b50-16g-q4_0-servercfg_deliver-c16384.json` |
| `2026-10-16_deliver-c262144-mmproj.log` | `2026-10-16_b50-16g-q4_0-servercfg_deliver-c262144-mmproj.json` |
| `2026-10-16_deliver-c262144.log` | `2026-10-16_b50-16g-q4_0-servercfg_deliver-c262144.json` |
| `2026-10-16_deliver-c32768.log` | `2026-10-16_b50-16g-q4_0-servercfg_deliver-c32768.json` |
| `2026-10-16_deliver-c65536.log` | `2026-10-16_b50-16g-q4_0-servercfg_deliver-c65536.json` |
| `2026-10-16_first-c16384.log` | `2026-10-16_b50-16g-q4_0-c16384-repeat_first-c16384.json` |
| `2026-10-16_second-c16384.log` | `2026-10-16_b50-16g-q4_0-c16384-repeat_second-c16384.json` |
| `_authtest.log` | —（鉴权试错，见 `docs/server-config.md` §4.2） |
| `ctx-ceiling-run.log` / `longctx-v2-run.log` | —（驱动脚本 stdout） |

---

## 在日志里找什么

| 要找 | 搜什么 | 看哪份文档 |
|---|---|---|
| 真实显存账 | `SYCL0 model buffer size` / `KV buffer size` —— **fit 默认开时打两遍，认后一遍** | `docs/pitfalls.md` 4.5、`bench/README.md` |
| 层是否上了 GPU | `offloaded N/N layers to GPU` | `docs/pitfalls.md` 1.3 |
| fit 是否在跑 | `common_fit_params: successfully fit params to free device memory` | `docs/pitfalls.md` 4.5 / 4.6 |
| 只看 kv cache 的是哪几层 | `llama_kv_cache: layer … dev = SYCL0` | `docs/pitfalls.md` 4.5 |
| server 单次请求真实耗时 | `Prompt executed in X seconds` | `docs/server-config.md` §4.2 |
| 卡型号取证 | `Device: xpu:0 Intel(R) Arc(TM) Pro B…` | `docs/test-rig.md`、`docs/test-registry.md` T-20 |

---

## 提交新日志时

1. 归一化本机绝对路径（用与上面同一套规则，别只改一部分）；
2. 确认**没有**密钥、用户名、邮箱（提交前扫一遍）；
3. 命名按上面的规范；
4. 在 `bench/data/*.json` 的 `log_evidence` / `timing_breakdown.source` 里指向它，
   并写明「日志的 `Prompt executed` 与样本 `server_sec` 对得上」的配对依据。
