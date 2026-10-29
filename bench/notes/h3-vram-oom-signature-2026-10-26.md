# H3 出视频那六个「挂」档，真正的原因是显存 OOM（2026-10-26 第三次归因翻案）

前两轮的结论都不对。第一轮说「像素 × 帧数有硬天花板 381 至 394 M」——错，那是跑测器 `BENCH_STALL_SEC=420` 的静默阈值。
第二轮说「墙在主机侧装载，卡没问题」——也不对。**第三轮把服务端日志翻出来，六个失败档全部是 `torch.OutOfMemoryError: XPU out of memory`，是显存。**

本轮没有跑任何新档：证据一直在 `_bench_f/server_<tag>.log` 里，之前只看了 `run_*.log`（跑测器视角，只记 rc）和功耗 CSV（只记瓦数），**没人翻服务端的 traceback**。

## 一、六个失败档的原始签名

| 档 | 分辨率·秒 | 帧 | 像素·帧 | 撞线的 op | 单次请求 | 当时空闲 | 已分配 | 保留未分配 | 执行时长 |
|---|---|--:|--:|---|--:|--:|--:|--:|--:|
| 578.6 M | 1080p·11 | 277 | 578.6 | `attention_pytorch` → `scaled_dot_product_attention` | **2.25 GiB** | 1.79 | 23.14 | 5.59 | 16:13（1,022.2 s 墙钟）|
| 582.5 M | 1440p·6 | 158 | 582.5 | `attention_pytorch` → `scaled_dot_product_attention` | **2.27 GiB** | 1.54 | 23.24 | 5.64 | 16:16（1,028.6 s）|
| 614.2 M | 1080p·12 | 294 | 614.2 | `attention_pytorch` → `scaled_dot_product_attention` | **2.38 GiB** | 0.20 | 23.81 | 6.49 | 18:12 / 17:49（1,150.3 / 1,119.1 s）|
| 685.2 M | 1080p·13 | 328 | 685.2 | `omni_xpu_kernel/int8` → `_tile_int8_linear` → `torch.empty` | **10.63 GiB** | 8.94 | 18.95 | 2.73 | 116 s |
| 720.7 M | 1080p·14 | 345 | 720.7 | `omni_xpu_kernel/int8` → `_tile_int8_linear` → `torch.empty` | **11.18 GiB** | 8.91 | 19.30 | 2.84 | 119 s |
| 756.2 M | 1080p·15 | 362 | 756.2 | `omni_xpu_kernel/int8` → `_tile_int8_linear` → `torch.empty` | **2.93 GiB** | 2.90 | 26.24 | 2.22 | 115 s |

六条统一形如：

```
torch.OutOfMemoryError: XPU out of memory. Tried to allocate N GiB.
GPU 0 has a total capacity of 31.16 GiB of which M GiB is free. 30.85 GiB allowed;
Of the allocated memory A GiB is allocated by PyTorch, and R GiB is reserved by PyTorch but unallocated.
```

## 二、两个撞线点，不是一条墙

- **578 至 614 M（1080p·11/12、1440p·6）**：死在 `comfy/ldm/modules/attention.py:600 attention_pytorch` 里的
  `scaled_dot_product_attention`，请求只有 **2.25 至 2.38 GiB** —— 但当时空闲只剩 1.79 / 1.54 / **0.20** GiB。
  这三档都跑够了 16 至 18 分钟才死，也就是**注意力矩阵随帧数长大，长到某一步分配不下**。
- **685 M 以上（1080p·13/14/15）**：死在 `omni_xpu_kernel/int8/__init__.py:187 _tile_int8_linear` 的
  `torch.empty((rows, output_features), ...)`，也就是 **int8 线性的输出缓冲**。
  13 / 14 秒档一口气要 **10.63 / 11.18 GiB**，而空闲 8.94 / 8.91 → 第 1 步（进度条仍是 `0/6`）就死，116 至 119 s 结束。
  15 秒档只请求 2.93 GiB，但那时已分配 26.24 GiB、只剩 2.90 —— **先撞线的 op 换了，请求大小并不单调**。

**所以「墙」不是某个固定 op 的固定上限，而是「31.16 GiB 装不下这一档的瞬时峰值」。**
峰值由三样一起构成：12,431.90 MB 部分驻留的 DiT + 激活 + 注意力矩阵 / int8 输出缓冲。
像素 × 帧数一变，这三样的配比就变，**哪一样先透支，报错就落在哪个 op 上**。

## 三、这解释了之前所有反常，也推翻了主机侧那条

| 之前记的现象 | 用显存 OOM 解释 |
|---|---|
| 685 M 起功耗只有 62 至 81 W、「连采样都没进」| 对，但原因不是装载失败：**装载是成功的**（`loaded partially` 那一行逐字节相同），是第 1 步的 int8 输出缓冲分配不下来，**一秒有效算力都没跑** |
| 578 / 614 M 进了采样、跑了 1,000 s+ 才死在第 2 步 | 对，是注意力矩阵涨到装不下 |
| 「提交内存爬到 111 GiB 就是墙」| **彻底作废**：三档提交 109.33 / 111.58 / 109.48 GiB，全在 127.11 GiB 上限以下 12 GiB 有余；真正撞线的是一次 GIU 级的 XPU 分配。**主机从来没顶到过** |
| 失败档 Job 峰值比通过档低（93.66 vs 100+ GiB）| 还是那句：**死得早，没跑到 VAE**，跟墙无关 |
| `--reserve-vram` 4→1 无效 | 一致的：它改不动「int8 输出缓冲要 10.63 GiB」这件事 |
| 卸载更多（7,564.24 MB）反而挂 | 一致的：卸载腾出来的是权重那 7.5 GB，但 13 秒档要的是**一次连续的 10.63 GiB**，碎片化之后仍然装不下 |

## 四、对外口径要改两处

1. **不是「这台机装不下」，是「这张卡（31.16 GiB）装不下这一档的瞬时峰值」。**
   机器的 32 GB 内存 + 96 GiB 页面文件**从来没有成为瓶颈**（提交峰值 111.58 / 127.11 GiB）。
2. **不是「卡跑不动」（算力不足），也不是「卡坏了」。**
   卡算得动 —— 同样的算力在 537.3 M（720p·24 秒）上跑完了 83 分钟。**缺的是显存容量，不是算力，也不是稳定性。**

## 五、这条证据打开了什么（下一步，未做）

既然瓶颈是**瞬态缓冲**而不是权重驻留，那它就不是一块铁板：

- **注意力侧**：`attention_pytorch` 走的是 `comfy/ops.py:63 scaled_dot_product_attention` 的 pytorch 实现。
  换后端（flash / 分块 attention，即 `OMNI_ATTN_BACKEND` 那类开关）有可能把「一次 2.4 GiB」变成「分块的小块」。
- **int8 侧**：`_tile_int8_linear` 名字里就带 tile，但要的是 10.63 GiB 一整块 —— **说明这个 tile 是按 rows 整块切的，没有按显存预算自适应**。
  这一条是内核侧问题，不是参数能解决的，但值得提给内核提供方。
- 若这两条能改成按预算分块，**天花板会往上挪**，而 537.3 M 这个对客数字只会变得保守、不会变得吹牛。

⚠️ **别再拿「功耗不到 150 W 所以没进采样」当「装载失败」的证据**：功耗判据只能区分「跑了很久」和「立刻死」，
**「立刻死」的原因必须去 `_bench_f/server_<tag>.log` 的 traceback 里看**。这条是本轮最大的方法论教训。

## 六、取证命令（可复现）

```bash
cd <ComfyUI 目录>/_bench_f
for t in 1920x1088-d11-hi 1920x1088-d12-hi 1920x1088-d13-hi \
         1920x1088-d14-hi 1920x1088-d15-hi 2560x1440-d6-hi; do
  echo "### $t"
  grep -E "OutOfMemoryError|Tried to allocate" "server_b65-h3-$t.log" | tail -1
  grep -E "Prompt executed in|loaded partially" "server_b65-h3-$t.log" | tail -2
done
```
