# B50 上的两个负结果（2026-10-22）

两项都是**全失败**，数据记录标 `discarded`、`ok=0`，**不构成性能证据**——但结论本身要留：
一项改写「16 GB 档能不能跑 Krea-2 的 bf16」，一项给出**分辨率天花板的位置**。

采集环境：B50 16G（E212 / 25221EF7）· 驱动 32.0.101.9150 · ECC 关 · CPU 直连槽 ·
`--reserve-vram 4` · 端口 8189 · 本机同时在位核显与用户常驻的 8188 实例（未动）。

---

## 1. Krea-2 Turbo bf16 · 1024×1024 · 8 步 → **OOM**

| | |
|---|---|
| 权重 | `krea2_turbo_bf16.safetensors` **24.48 GiB** + `qwen3vl_4b_bf16` |
| 装载（服务端日志） | `loaded partially; 10966.68 MB usable, 10774.68 MB loaded, 13675.01 MB offloaded, 192.00 MB buffer reserved` |
| 首轮 | 墙钟 196.9 s（服务端 `Prompt executed in 193.69 seconds`）后失败 |
| 之后三轮 | 每轮 6.0 s 即失败，`loads=0` |
| 服务端错误 | `!!! Exception during processing !!! level_zero backend failed with error: 39 (UR_RESULT_ERROR_OUT_OF_DEVICE_MEMORY)` / `RuntimeError: level_zero backend failed with error: 39 (UR_RESULT_ERROR_OUT_OF_DEVICE_MEMORY)` |
| 记录文件 | `bench/data/2026-10-22_b50-16g_krea-2-turbo-bf16-k2bf16-comfyui.json`（`status=discarded`） |

**判读**：DiT 24.48 GiB 在 15.51 GiB 上卸掉 **13.68 GB** 之后仍然 OOM。
**这张卡上 Krea-2 的 bf16 档跑不了**，不是「慢」，是「装不下且卸不开」。

⚠️ **采集器的 `oom` 标记是 `false`**（它扫的关键字没覆盖 `UR_RESULT_ERROR_OUT_OF_DEVICE_MEMORY`），
所以 `discard_reason` 里写的是「失败类型需查服务端日志区分」。**服务端日志才是这一格的判据。**

⚠️ 同卡早先两次（`2026-10-16_b50-16g_krea-2-turbo-bf16-k2bf16-comfyui.json` 88.31 s、
`2026-10-17_...-k2bf16retry...` 102.78 s）也是失败，但当时**没留服务端日志**，
失败类型只能推。三次结论一致：**这一档在 16 GB 上不成立**。

---

## 2. H3 · 2560×1440 · 6 步 · 5 s → **OOM（分辨率天花板就在这里）**

| | |
|---|---|
| DiT / TE | `minimax_h3_fl2va_pruned_int8_convrot` / `qwen3vl_32b_minimax_h3_nvfp4_awq` |
| 装载（服务端日志） | `loaded partially; 10966.68 MB usable, 10396.37 MB loaded, 4563.29 MB offloaded`<br>`loaded partially; 6352.75 MB usable, 5911.64 MB loaded, 14084.50 MB offloaded` |
| 失败点 | 首轮 cold，墙钟 21.1 s（装载后即炸，`vram_post=10.86 GiB`） |
| 服务端错误 | `XPU out of memory. Tried to allocate 5.35 GiB. GPU 0 has a total capacity of 15.51 GiB of which 3.09 GiB is free.` |
| 记录文件 | `bench/data/2026-10-22_h3_2560x1440_b50ceil.json`（`status=discarded`） |

**判读**：2560×1440 下第二件的 `usable` 只剩 **6,352.75 MB**（卸载 **14,084.50 MB**），
随后一次分配要 **5.35 GiB**、当时只剩 3.09 GiB → **OOM**。

对照同卡已跑通的最高档（`2026-10-17_h3_1920x1088_b50scan.json`：cold **2,259.86 s**、末步 337.02 s/it）：

> **这张卡的视频天花板 = 1920×1088 能跑、2560×1440 装不下，卡在这两档之间。**

---

## 3. 顺手记下的一件事：B50 的功耗域没识别出来

三次采集的 `power` 字段都写着 `card_limit_mw: -1`（Sysman 的 `defaultLimit` 读不到），
而 B50 的 TBP 是 **70 W**，采出来的 `peak_w` 却报 **198.1 W**、`avg_w` 78.7 W ——
**明显不是整卡域，是别的域或整机域**。

→ **B50 的瓦特数一个都不要引用**（这也是 B50 那一列一直空着的原因）。
判据：`card_limit_mw` 必须等于规格 TBP，读不到就不报。
