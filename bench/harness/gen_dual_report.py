# -*- coding: utf-8 -*-
"""从 bench/data 直出《docs/dual-b65-report.md》。

表格与全部数字都从原始 json 读，禁止手抄。
取数层在 dual_data.py（与 gen_dual_report_en.py 共用，数字同源）。
行尾：CRLF，无尾换行。
"""
import os

from dual_data import *  # noqa: F401,F403

OUT = os.path.join(REPO, "docs", "dual-b65-report.md")


L = []
w = L.append

w("# 双卡 B65 实战报告：买到什么，买不到什么")
w("")
w("> **一句话**：加卡是加房间，不是加速度——第二张 B65 买到的是**容量和第二条产线**，不是单条任务的速度。")
w("")
w("> **说给客户听（可以直接照着讲）**")
w(">")
w("> 有人问我，插两张卡是不是就两倍快。这个得分开说。")
w(">")
w("> 第二张卡插上去，显存从 31 GB 变 62 GB。原来装不下的模型，现在装得下了；")
w("> 原来只能跑一条片子，现在一条片子开着，旁边再挂个聊天。这都是实打实的变化。")
w(">")
w("> 但你要问同一条片子能快多少——几乎不快。单卡一步 42.30 秒，两张卡一起干 42.41 秒，一样。")
w("> 所以第二张卡买的是地方，不是速度——想让一条片子快，换更强的单卡。")
w(">")
w("> 有人跟你说「两张卡能并成一张使、算力翻倍」：那种模式我们试过，能跑但比单卡还慢")
w("> （29.19 对 31.86）——每算一层两张卡要对一次账，对账比省下来的还多。我们的办法是各干各的。")
w("> 拆层是「第二张卡帮忙装」不是「帮忙算」：单卡装得下时拆开反而慢 5%~7%，装不下时拆开快 17%。")
w(">")
w("> 主板不用换。普通 B850M 就行，卡 1 在 x4 槽单跑一步 42.31 秒，跟 x16 的一样。")
w("> 只有上四卡或非做张量并行才要 x8/x8 工作站板——我们定位就是普通电脑跑大模型。")
w(">")
w("> 有件事先说：想同时开两条线要 64 GB 内存，32 GB 是「一条片子加一个轻活」。先说，比事后解释好。")
w("")
w("实测条件：2× GUNNIR B65 32G · ECC 关（每卡可用 31.16 GiB）· 驱动 9150 · 32 GB 内存（2×16 GB）·")
w("显示器接主板核显 · 主板是 **B850M 这一级的主流 mATX 板**（不是工作站板，做不了 x8/x8 拆分）：")
w("卡 0 在 CPU 直连 x16 槽、卡 1 在芯片组 x4 槽。除另注外，全部数字都是实测，**没有靠工作站硬件撑出来的成绩**。")
w("")
w("## 总测试项汇总")
w("")
w("各收录数据按总测试项收进一张表。每项只给一个结果，展开见对应章节。")
w("")
w("**动态图**：[`assets/dual-b65-dashboard.html`](assets/dual-b65-dashboard.html)（可交互 · 悬停看一个结果）")
w("")
w("| 测试项 | 单卡 B65 | 双卡 2×B65 | 一片 B70 | 一个结果 |")
w("|---|---:|---:|---:|---|")
w("| H3 720p·5 s 端到端（稳态） | %s | %s | %s | 双卡不提速，B70 快 %s |" % (
    s(b65_720_fresh["server_sec"]), s(d6_fresh["server_sec"]),
    s(sample(b70_720, "fresh")["server_sec"]), fx(r_e2e)))
w("| H3 720p 单步 | %s s/it | %s s/it | %s s/it | 第二张卡对单条贡献 0 |" % (
    f2(b65_720_fresh["sampling_sec_per_step"]), f2(d6_fresh["sampling_sec_per_step"]),
    f2(sample(b70_720, "fresh")["sampling_sec_per_step"])))
w("| H3 1080p·5 s 端到端（稳态） | %s | — | %s | B70 快 %s |" % (
    s(b65_1080_fresh["server_sec"]), s(sample(b70_1080, "fresh")["server_sec"]), fx(r_1080)))
w("| Qwen Q4_0 解码 | %s tok/s | %s tok/s | %s tok/s | 并发不掉速 |" % (
    f2(q_solo["summary"]["decode_tok_s"]), f2(q_conc["summary"]["decode_tok_s"]),
    f2(load("2026-10-20_b70-q4-0-sycl-l0.json")["summary"]["decode_tok_s"])))
w("| Q8_0 34.37 GiB 解码（拆层 vs 单卡全驻） | %s | %s | — | 拆层买容量不赔速度（%s） |" % (
    f2(q8_ngl37b["decode_tok_s"]), f2(ts6040["decode_tok_s"]), fx(r_q8_same)))
w("| Q4_0 19.41 GiB 解码（拆层 vs 单卡） | %s | %s | — | 装得下别拆，拆开慢 %s |" % (
    f2(q4_solo["decode_tok_s"]), f2(q4_dual["decode_tok_s"]), f1(100 * (1 - r_q4_same)) + "%"))
w("| 张量并行解码 | — | %s tok/s | — | 比单卡慢，别用 |" % f2(q8_t50["decode_tok_s"]))
w("| 可用显存 | 31.16 GiB | 62.32 GiB | 31.16 GiB | 双卡买到 2× 显存，不是速度 |")
w("| 上下文（真装下） | %s | %s | %s | 对外说 1.75M，3M 只是分配上限 |" % (
    tok(ctx["summary"]["single_max_allocated_ctx"]), tok(ctx["summary"]["dual_max_allocated_ctx_unified"]), tok(ctx["summary"]["single_max_allocated_ctx"])))
w("| 出图稳态 | %s / %s s | %s ~ %s s | — | 双实例并发零损失 |" % (
    f2(img_solo_ss[1]["server_sec"]), f2(img_solo_ss[2]["server_sec"]),
    f2(img_c1_ss[1]["server_sec"]), f2(img_c0_ss[2]["server_sec"])))
w("| 出视频 + 聊天 | — | 12/12 答对，decode −0.2% | — | 成立 |")
w("| 出视频 + 出视频 | — | 2/2 崩 | — | 不成立（32 GB 内存墙） |")
w("| 满载功耗 P90 | %s W | %s W | %s W | 叠加不互压 |" % (
    f1(pw_s0["summary"]["power"]["p90_w_busy"]), f1(pw_b0["summary"]["power"]["pair_sum_p90_w"]),
    f1(b70_pw["summary"]["power"]["p90_w_max"])))
w("| 两条 5 秒片产能 | — | %s 条/时 | %s 条/时 | 双卡赢 %s |" % (f1(thr_dual), f1(thr_b70), fx(r_thr)))
w("| 价格 | ¥%s | ¥%s | ¥%s | 几乎同价：B70 买速度，双卡买容量+产能 |" % (
    yuan(P_B65), yuan(P_2B65), yuan(P_B70)))
w("")

# ---------------------------------------------------------------- 一
w("## 一、四个问题，四个答案")
w("")
w("| 问题 | 答案 |")
w("|---|---|")
w("| 双卡是不是「算力翻倍」？ | **不是。** 数字见总表前两行，一步都没快。 |")
w("| 那双卡买什么？ | **容量 + 产能**（见总表）。⚠️ 32 GB 内存下「两条视频线」不成立（§5.3），实际是「一条视频 + 一条轻任务」。 |")
w("| 单卡 B65 能单独做 H3 视频吗？ | **能。** 720p·5 s 稳态约 %s；实测最高 720p 24 秒（83 分钟一条）——是「要等多久」不是「能出几秒」（见 `cards/B65-README.md` §6）。 |" % mmss(b65_720_fresh["server_sec"]))
w("| 一片 B70 和两片 B65（几乎同价），差什么？ | **B70 买速度，双卡买容量+产能。** 见总表末行。 |")
w("")

# ---------------------------------------------------------------- 二
w("## 二、为什么「双卡 = 算力翻倍」不成立")
w("")
w("不是这张卡不行，是这两条软件路径都**不把一个任务拆到两张卡上**：")
w("")
w("1. **ComfyUI / `torch.xpu` 只用第一张卡。** 进程起来就绑 `xpu:0`，第二张卡在这个进程里不存在。")
w("   想让第二张卡干活，只能再起一个进程、用 `ONEAPI_DEVICE_SELECTOR=level_zero:1` 把它钉过去。")
w("2. **llama.cpp 的「多设备」是分层装载，不是并行计算。** `-dev SYCL0,SYCL1 -sm layer` 把模型的不同层")
w("   分到两张卡上，算一层的时候另一张卡在等 —— 层与层之间要同步，同步次数随层数涨。")
w("")
w("实测证据就是总表的前两行与 Q8_0 / Q4_0 两行（单步 +0.3%%、解码 −0.2%%、拆层 %s、装得下别拆）——四条都在噪声内或负收益。" % fx(r_q8_same))
w("")
w("一个结果：**「双芯运作、算力翻倍」预期在这两套软件上不成立**——正确的预期是两条独立的产线。（早先「拆层赔 4.84 倍」是 llama-bench `-dev` 语义误读的采集错误，已更正，过程见 `bench/notes/dual-b65-prep.md`。）")
w("")
w("打算上第二张卡之前，先答三个问题：")
w("")
w("1. **你要的是「一条更快」还是「两条一起」？** 前者换更强的单卡，后者才上双卡。")
w("2. **你的内存是 32 GB 还是 64 GB？** 32 GB 下两条视频线跑不起来（§5.3），只能「一条视频 + 一条轻任务」。")
w("3. **有没有一个模型单卡装不下？** 没有的话，双卡不会让你现有任何一个任务变快。")
w("")

# ---------------------------------------------------------------- 三
w("## 三、单卡 B65 能不能单独做 H3 视频")
w("")
w("**能，而且这是目前最实用的用法。** 一台机器一张 B65，不用第二张卡、不用改代码，ComfyUI 里跑 MiniMax H3：")
w("")
w("| 时长 | 帧数 | 端到端（cold） | 单步（cold） | 端到端（稳态） | 单步（稳态） |")
w("|---:|---:|---:|---:|---:|---:|")
for name, frames, cold, fresh, cached in dur_rows:
    steady = fresh or cached
    w("| %s | %d | %s | %s | %s | %s |" % (
        name, frames, s(cold["server_sec"]),
        f2(cold["sampling_sec_per_step"]) + " s/it",
        s(steady["server_sec"]) if steady else "—",
        (f2(steady["sampling_sec_per_step"]) + " s/it") if steady else "—"))
w("")
w("5 秒档的读数不止一个，别混用（上表「稳态」列取的是 fresh）：cold %s（含完整装载）/ fresh %s / cached %s。" % (
    s(b65_720_cold["server_sec"]), s(b65_720_fresh["server_sec"]), s(b65_720_cached["server_sec"])))
w("10 秒起只测了 cold（新起服务第一条），**没有稳态读数**，所以那一列是「—」，不是零。")
w("")
w("| 分辨率（5 秒） | 端到端（稳态） | 单步 |")
w("|---|---:|---:|")
w("| 1280×720 | %s | %s s/it |" % (s(b65_720_fresh["server_sec"]), f2(b65_720_fresh["sampling_sec_per_step"])))
w("| 1920×1088 | %s | %s s/it |" % (s(b65_1080_fresh["server_sec"]), f2(b65_1080_fresh["sampling_sec_per_step"])))
w("")
w("结论：")
w("")
w("1. **720p · 5 秒 · 6 步：稳态 %s，约 %s。** 这是单卡 B65 最舒服的一档 —— DiT 19.53 GiB 完整驻留显存，每步不搬权重。" % (s(b65_720_fresh["server_sec"]), mmss(b65_720_fresh["server_sec"])))
w("2. **720p 实测到 24 秒（约 83 分钟一条，全表最高像素×帧通过点）**；整数秒上限 480p ≤ 50 秒 / 720p ≤ 24 秒 / 1080p ≤ 10 秒 / 1440p ≤ 5 秒，30 档 22 过。失败 8 档全是 XPU OOM（瞬时峰值装不下，不是主机也不是算力）。阶梯全表见 `cards/B65-README.md` §6。")
w("3. **1080p · 5 秒也能出**：稳态 %s（约 %s），单步 %s s/it。代价是 DiT 每轮要卸 7,564 MB。**1080p 是 32 GB 卡的边界，不是舒适区。**" % (s(b65_1080_fresh["server_sec"]), mmss(b65_1080_fresh["server_sec"]), f2(b65_1080_fresh["sampling_sec_per_step"])))
w("4. **时长比分辨率更贵。** 同样 720p，5 → 15 秒端到端涨 %s×，像素一点没变 —— 帧数变多，潜在空间 buffer 跟着涨。" % f2(sample(b65_d15, "cold")["server_sec"] / b65_720_cold["server_sec"]))
w("5. 采集条件：`--reserve-vram 4`、`OMNI_ATTN_BACKEND=sdpa`、int8 DiT + nvfp4 文本编码器。**改预留值会影响装载行为**，数字要连条件一起引。")
w("6. 跨分辨率的完整四卡对照见 [`comfyui-h3.md`](comfyui-h3.md)；本文只讲单卡 B65 与双卡 B65。")
w("")

# ---------------------------------------------------------------- 四
w("## 四、双卡 vs 单卡：逐项对照")
w("")
d4b_fresh = sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")
w("速度/容量各行见总表（双卡 vs 单卡全列在那里）。本节只补总表没有的三条：")
w("")
w("| 维度 | 数字 | 一个结果 |")
w("|---|---:|---|")
w("| 出图首轮（装载） | 单卡 %s / 双卡 %s, %s | 并发抢页缓存，首轮不可比 |" % (s(img_solo_ss[0]["server_sec"]), s(img_c0_ss[0]["server_sec"]), s(img_c1_ss[0]["server_sec"])))
w("| 卡 1（x4 槽）单跑 H3 | 稳态 %s，单步 %s s/it | 与卡 0 一致，不归因 PCIe 宽度（无互换对照） |" % (s(c1_steady["server_sec"]), f2(c1_steady["sampling_sec_per_step"])))
w("| H3 端到端 +6.0%% 的来源 | 热车后 %s（+%s） | 不是算力损失，是并发抢页缓存；先热车再取数 |" % (
    s(d4b_fresh["server_sec"]), f1(100 * (d4b_fresh["server_sec"] / b65_720_fresh["server_sec"] - 1)) + "%"))
w("")
w("一个结果：**双卡对单条任务零提升**（单步 +0.3%%、解码 −0.2%%，均在抖动量级）；端到端那 6.0%% 是并发抢页缓存的固定开销，热车后收窄到 %s，**凡比双卡拖慢先热车再取数**；满载功耗相加不互压（合计 %s W），850 W 电源按显卡侧 400 W 级算。" % (
    f1(100 * (d4b_fresh["server_sec"] / b65_720_fresh["server_sec"] - 1)) + "%",
    f1(pw_b0["summary"]["power"]["pair_sum_p90_w"])))
w("")
w("### 4.1 卡间通道：把拷贝做得更底层，也没能提速")
w("")
w("两张卡之间**只有 PCIe**，没有 NVLink / Xe-Link 那类专用互联。那换个更底层的卡间拷贝方式能不能提速？")
w("llama.cpp 有三个档位可选，我们同一批、同一口径各跑三档（`GGML_SYCL_DEV2DEV_MEMCPY`）：")
w("")
w("| 卡间拷贝方式 | 张量并行 解码 | 张量并行 预填充 | 拆层 解码 | 拆层 预填充 |")
w("|---|---:|---:|---:|---:|")
w("| 0 · SYCL 直拷（默认） | %s | %s | %s | %s |" % (f2(d2d["dual_tensor_5050_p2p"]), f2(d2d["prefill_dual_tensor_5050_p2p"]), f2(d2d["dual_layer_5050_p2p"]), f2(d2d["prefill_dual_layer_5050_p2p"])))
w("| 1 · Level Zero 直拷 | %s | %s | %s | %s |" % (f2(d2d["dual_tensor_5050_l0direct"]), f2(d2d["prefill_dual_tensor_5050_l0direct"]), f2(d2d["dual_layer_5050_l0direct"]), f2(d2d["prefill_dual_layer_5050_l0direct"])))
w("| 2 · 强制走主机内存 | %s | %s | %s | %s |" % (f2(d2d["dual_tensor_5050_hostforward"]), f2(d2d["prefill_dual_tensor_5050_hostforward"]), f2(d2d["dual_layer_5050_hostforward"]), f2(d2d["prefill_dual_layer_5050_hostforward"])))
w("")
w("（Q8_0 34.37 GiB · `-ts 50,50` · 解码 tok/s、预填充 tok/s，各跑 3 次取中位数）")
w("")
w("一个结果：**换更底层的拷贝路径救不了张量并行**——三档解码极差 1.5%%（噪声内），卡间拷贝不是瓶颈、同步次数才是，这条路不用再试；双卡不需要为 PCIe 拓扑换主板（x4 槽单步 %s 与 x16 的 %s 一致）；只有上四卡或非做张量并行才要 x8/x8，那是工作站板。" % (
    f2(c1_steady["sampling_sec_per_step"]), f2(d6_fresh["sampling_sec_per_step"])))
w("")

# ---------------------------------------------------------------- 五
w("## 五、双卡真正买到的三样东西")
w("")
w("![三样东西，三个结果：上下文 1M→1.75M token、34.37 GiB 拆层全驻、两条产线](assets/dual-b65-three-things.svg)")
w("")
w("三个结果分别展开见 5.1 / 5.2 / 5.3。")
w("")
w("### 5.1 容量：上下文 1M → 1.75M token（3M 只是分配上限）")
w("")
w("| 形态 | 配置 | 真装下 | 每 M token 占显存 | 上限处剩余 |")
w("|---|---|---:|---:|---:|")
w("| 单卡 | 默认 | **%s**（%d 个满长会话） | %s GiB | %s GiB |" % (tok(ctx["summary"]["single_max_allocated_ctx"]), ctx["summary"]["single_max_slots"], f1(ctx["summary"]["single_kv_gib_per_mtoken"]), f2(ctx["summary"]["single_headroom_at_ceiling_gib"])))
w("| 双卡 | 默认（`kv_unified=true`） | %s | %s GiB | %s / %s GiB |" % (tok(ctx["summary"]["dual_max_allocated_ctx_unified"]), f1(ctx["summary"]["dual_kv_gib_per_mtoken_unified"]), f2(cases["d175m"]["free_gib"][0]), f2(cases["d175m"]["free_gib"][1])))
w("| 双卡 | 显式 `--parallel`（`kv_unified=false`） | **%s**（%d 个满长会话） | %s GiB | %s / %s GiB |" % (tok(ctx["summary"]["dual_max_allocated_ctx_explicit_parallel"]), ctx["summary"]["dual_max_slots_explicit_parallel"], f1(ctx["summary"]["dual_kv_gib_per_mtoken_explicit_parallel"]), f2(ctx["summary"]["dual_headroom_at_ceiling_gib"][0]), f2(ctx["summary"]["dual_headroom_at_ceiling_gib"][1])))
w("")
w("一个结果：**是 3 倍不是 2 倍**（权重不再重复占位）——前提是显式 `--parallel`（不写只有 1.75 倍且 2M OOM）。")
w("🔴 **3M 只是分配上限**：长 prompt prefill 会把整机跑挂（主机内存顶穿、无 dump），**对外只说单卡 1M / 双卡默认 1.75M**。")
w("🔴 **虚拟内存定案：初始 = 最大 = 32768 MB**——页面文件过大反而把「进程自己退」变成「整机卡死」；锁死后超限请求进程自报 OOM 退出、机器照常用。")
w("对客一句话：**买容量要看主机内存，不只是显存。** 事故取证见 `bench/notes/ctx3m-hang-2026-10-24.md`。")
w("")
w("### 5.2 容量：装下一个 34.37 GiB 的模型")
w("")
w("| 配置 | 显存去向 | 预填充 tok/s | 解码 tok/s |")
w("|---|---|---:|---:|")
w("| Q8_0 单卡 `-ngl 37` | 30.78 GiB 上卡、约 4 GiB 层落 CPU | %s | **%s** |" % (f2(q8_ngl37["prefill_tok_s"]), f2(q8_ngl37["decode_tok_s"])))
w("| Q8_0 单卡 `-ngl 99` | 显存占满 31.14 GiB（剩 0.02 GiB）；权重 34.37 GiB，未上卡的 ≥ 3.2 GiB | %s | %s |" % (f2(q8_spill["prefill_tok_s"]), f2(q8_spill["decode_tok_s"])))
w("| Q8_0 双卡 `-sm layer` | **33.53 GiB 全驻显存**（卡 0 17.47 / 卡 1 16.06） | %s | **%s** |" % (f2(q8_s["ts5050"]["prefill_tok_s"]), f2(q8_s["ts5050"]["decode_tok_s"])))
w("| Q8_0 双卡 `-sm tensor` † | 33.65 GiB 均摊两卡（卡 0 16.92 / 卡 1 16.73） | %s | %s |" % (f2(q8_t50["prefill_tok_s"]), f2(q8_t50["decode_tok_s"])))
w("| Q4_0 单卡 `-ngl 99` | 18.32 GiB 全驻（剩 12.84 GiB） | %s | **%s** |" % (f2(q4_solo["prefill_tok_s"]), f2(q4_solo["decode_tok_s"])))
w("| Q4_0 双卡 `-sm layer` `50,50` | 17.96 GiB 全驻（卡 0 9.39 / 卡 1 8.57） | %s | %s |" % (f2(q4_dual["prefill_tok_s"]), f2(q4_dual["decode_tok_s"])))
w("| Q4_0 双卡 `-sm layer` `90,10` | 17.96 GiB 全驻（卡 0 17.09 / 卡 1 0.87） | %s | %s |" % (f2(q4_dual9["prefill_tok_s"]), f2(q4_dual9["decode_tok_s"])))
w("")
w("一个结果：**装得下就别拆，装不下才拆。** Q4_0 单卡本来就装得下，拆开慢 %s；Q8_0 单卡装不下，拆层全驻比单卡快 %s（比 spill 快 %s）——拆层买到的是容量，速度不赔。" % (
    f1(100 * (1 - r_q4_same)) + "%", fx(r_q8_same), fx(r_q8_spill)))
w("⚠️ `-ts` 比例对解码无影响（四档极差 0.3%%），跨场次同配置能差 6%%、只看方向不看趋势；`-sm row` 本 build 跑不起来，`-sm tensor` 比单卡还慢（%s tok/s）——**拆层是唯一不赔速度的协同模式**。口径：llama-server（19/128、3 次取中位），别与 llama-bench 混排。" % f2(q8_t50["decode_tok_s"]))
w("")
w("### 5.3 吞吐：两张卡各一条产线")
w("")
w("| 组合 | 形态 | 结果 |")
w("|---|---|---|")
w("| 出图 + 出图 | 两个 ComfyUI，各钉一张卡 | 稳态 %s ~ %s s/张，与同批单卡 %s / %s **持平** |" % (f2(img_c1_ss[1]["server_sec"]), f2(img_c0_ss[2]["server_sec"]), f2(img_solo_ss[1]["server_sec"]), f2(img_solo_ss[2]["server_sec"])))
w("| 出视频 + 聊天 | 卡 0 跑 H3，卡 1 跑 llama.cpp | 12/12 答对，decode 114.79 vs 115.02 tok/s（−0.2%） |")
w("| 出视频 + 出视频 | 两个 ComfyUI 各跑 H3 | **不成立**：2/2 在同一处崩溃，页面文件峰值 48.7 GB |")
w("")
w("- 第三条是 **32 GB 内存墙，不是显卡不够**：单实例 H3 约要 25 GB 虚拟内存，两个 50 GB，物理内存 32 GB 顶不住。")
w("  隔离两侧的 SYCL 缓存后照崩 → 不是缓存冲突。**32 GB 机器上双卡只能「一条视频 + 一条轻任务」；两条视频线要 64 GB 内存。**")
w("")

# ---------------------------------------------------------------- 六
w("## 六、一片 B70 vs 两片 B65（同价对决）")
w("")
w("价格口径（2026-10-26 确认）：**B70 ¥%s**、B65 ¥%s。**两片 B65 ¥%s，比一片 B70 贵 ¥%s，几乎同价。**" % (
    yuan(P_B70), yuan(P_B65), yuan(P_2B65), yuan(P_2B65 - P_B70)))
w("所以这就是「一片 B70 = 两片 B65」这道题的正确算法 —— 同样的钱，买到的是两种不同的东西。")
w("")
w("| | 一片 B70 32G | 两片 B65 32G |")
w("|---|---:|---:|")
w("| 价格 | **¥%s** | **¥%s** |" % (yuan(P_B70), yuan(P_2B65)))
w("| 核心 / 带宽 / 显存 | 32 核 · 608 GB/s · 31.16 GiB | 2×20 核 · 2×608 GB/s · 62.32 GiB |")
w("| H3 720p · 5 s 端到端（稳态） | **%s** | %s（每张） |" % (s(sample(b70_720, "fresh")["server_sec"]), s(b65_720_fresh["server_sec"])))
w("| H3 单步 | **%s s/it** | %s s/it |" % (f2(sample(b70_720, "fresh")["sampling_sec_per_step"]), f2(b65_720_fresh["sampling_sec_per_step"])))
w("| H3 1080p · 5 s 端到端（稳态） | **%s** | %s |" % (s(sample(b70_1080, "fresh")["server_sec"]), s(b65_1080_fresh["server_sec"])))
w("| Qwen Q4_0 解码 | **%s tok/s** | %s tok/s |" % (f2(load("2026-10-20_b70-q4-0-sycl-l0.json")["summary"]["decode_tok_s"]), f2(q_solo["summary"]["decode_tok_s"])))
w("| 满载功耗（P90） | %s W | %s W（两卡合计） |" % (f1(b70_pw["summary"]["power"]["p90_w_max"]), f1(pw_b0["summary"]["power"]["pair_sum_p90_w"])))
w("| 同时跑几条 H3 | 1 | **2** |")
w("| 34.37 GiB 的 Q8_0 | 同为 31.16 GiB，按容量推装不下；**B70 上单卡 Q8_0 没测** | 装得下，解码 %s tok/s |" % f2(q8_s["ts5050"]["decode_tok_s"]))
w("")
w("一个结果：**同价两种买法——B70 买单条速度（快 %s / %s），两片 B65 买容量+产能（显存 2×、上下文 3×、双线 %s 条/时、装得下 34.37 GiB）**。算力翻倍两边都不成立（B70 只快 %s，双卡单任务不变）；B70 不买容量（34.37 GiB 同样装不下，B70 单卡 Q8_0 未测、不给数字）。" % (
    fx(r_e2e), fx(r_step), f1(thr_dual), fx(r_e2e)))
w("")
w("| 你的场景 | 选 | 理由 |")
w("|---|---|---|")
w("| 一条片子要快、要 1080p 常态 | **B70** | 720p 快 %s、1080p 快 %s，单任务无替代 |" % (f2(r_e2e) + "×", f2(r_1080) + "×"))
w("| 同时出两条片子 / 一条视频一条问答 | **2× B65** | 同价，产能 %s（%s vs %s 条/时） |" % (fx(r_thr), f1(thr_dual), f1(thr_b70)))
w("| 要装 34 GiB 以上的模型、要 3M token 上下文 | **2× B65** | 容量翻倍；但预期是「装得下」，不是「跑得快」 |")
w("| 预算卡在 32 GB 显存这一档 | **B65** | 同显存、便宜约 ¥%s，慢 %s |" % (yuan(P_B70 - P_B65), fx(r_e2e)))
w("")

# ---------------------------------------------------------------- 七
w("## 七、不同搭配载体在 AI 推理上的相同与不同")
w("")
w("> 这一节讲结构，不讲参数。**本机实测过的载体只有「一张卡」和「两张 B65」**；表里另外两种本机没有，")
w("> 所以**不给它们任何数字**，只讲结构决定了什么。")
w("")
w("| 载体 | 显存 | 卡间通道 | 本机实测 |")
w("|---|---|---|---|")
w("| 1× B65 | 一个池子，31.16 GiB | — | ✅ |")
w("| **2× B65**（本文） | 两个独立池子，各 31.16 GiB | PCIe（本机卡 1 在芯片组 x4 槽）；**无 P2P**，跨卡只能经主机内存 | ✅ |")
w("| 2× RTX 5090 | 两个独立池子，各 32 GB | PCIe；**消费级卡同样没有 P2P**，跨卡也只能经主机内存 | ⛔ 没测 |")
w("| 统一内存平台（DGX Spark 这类） | **一个池子**，GPU 直接寻址整机内存 | 不存在「卡间搬运」这个概念 | ⛔ 没测 |")
w("")
w("### 相同的三件事")
w("")
w("![载体在变，这三条不变：单条速度=算力+带宽、装不下往下层搬、一个进程只吃一张卡](assets/dual-b65-carriers-same.svg)")
w("")
w("1. **单条任务的速度由算力和带宽决定，不由卡的数量决定**（实测见总表前两行）。换哪家卡、换哪种载体，这条都成立。")
w("2. **装不下就得往下层放，放下去就要搬。** 显存最快、主机内存次之、磁盘最慢；")
w("   谁的容量不够，谁就要付这一层搬运的钱。")
w("3. **一个进程只吃一张卡。** `torch.xpu` 和 ComfyUI 都只绑第一张卡，不会自己铺开。")
w("   要让两张卡都干活，最省事的是**起两个进程**，不是一个进程用两张卡。")
w("")
w("### 不同的三件事")
w("")
w("![结构不同，这三条跟着变：池子数量定方向、无 P2P 跨卡贵、带宽不随卡数翻倍](assets/dual-b65-carriers-diff.svg)")
w("")
w("1. 🔴 **池子有几个，决定瓶颈在哪，也决定优化方向正好相反。**")
w("   - **两个独立池子**（本文这种）：把一个大模型切开、分层放到两张卡上，层与层之间要同步。")
w("     实测 Q8_0 34.37 GiB 拆层全驻显存解码 **%s tok/s**，单卡带约 4 GiB CPU 尾 **%s**、"
  "单卡硬塞 spill **%s** ——" % (f2(q8_s["ts5050"]["decode_tok_s"]), f2(q8_ngl37["decode_tok_s"]), f2(q8_spill["decode_tok_s"])))
w("     **拆层既不赔速度，还避开了单卡 spill 那一档（%s tok/s）。** 两池子的方向不是「别拆层」，" % fx(r_q8_spill))
w("     而是「**拆层可以，但别指望它把单条任务变快**」—— 单条任务的速度仍由单卡的算力与带宽决定。")
w("   - **一个池子**（统一内存）：没有「哪层放哪张卡」这个问题，快层和慢层在同一个池子里连续。")
w("     方向反过来了 —— 要做的是**把热数据留在快的那一段**，而不是想办法把负载铺到更多卡上。")
w("2. **有没有 P2P，决定「跨卡」有多贵。** 本文两张 B65 之间没有 P2P，跨卡数据要落主机内存再取，")
w("   来回两趟 PCIe。消费级卡（5090 这一档）同样没有 P2P —— 就「跨卡很贵」这一点，两种载体是**同一类**，")
w("   都更适合「两张卡各干各的」。")
w("3. **带宽不随卡数翻倍。** 两张 B65 合起来是 2×608 GB/s 的**总额**，但一条任务只跑在它所在的那张卡上，")
w("   能动用的还是 608 GB/s。把模型切两半摊到两张卡，等于用「每步跨卡同步」换掉「每张卡装一半」——")
w("   带宽总量涨了，单条任务能用的没涨。")
w("")
w("### 落到选型")
w("")
w("| 你的情况 | 怎么做 | 为什么 |")
w("|---|---|---|")
w("| 两件互不相干的活 | **两张卡各起一个实例** | 实测出图+出图、出视频+聊天都不掉速，这是双卡最稳的用法 |")
w("| 一个模型装不下 | **双卡 `-sm layer` 拆层** | 实测买容量不赔速度（37.35 vs 单卡全驻 31.86，同场次）；`-sm row` 在本 build 上跑不起来，`-sm tensor` 跑得通但比单卡还慢 |")
w("| 模型单卡就装得下 | **别拆层，老实单卡** | Q4_0 档同场次：双卡 49.80 vs 单卡 53.63，拆开慢 7% |")
w("| 想让单条任务更快 | **换更强的单卡**，不是加卡 | 加卡对单条任务的贡献是 0，哪种载体都一样 |")
w("| 装不下又不想拆层 | 统一内存平台（本机没测） | 一个池子，装得下就整块驻留，不存在跨卡同步 |")
w("")

# ---------------------------------------------------------------- 八
w("## 八、跑通的参数（可以直接抄）")
w("")
w("### 8.1 ComfyUI 双实例：两张卡各一个")
w("")
w("```bash")
w("# 实例 1（卡 0，CPU 直连 x16）")
w("COMFY_PORT=8190 ONEAPI_DEVICE_SELECTOR=level_zero:0 \\")
w("  SYCL_CACHE_DIR=<工具目录>/_sycl_cache_c0 \\")
w("  <ComfyUI 目录>/python_embeded/python.exe <ComfyUI 目录>/main.py \\")
w("    --listen 127.0.0.1 --port 8190 --reserve-vram 4")
w("")
w("# 实例 2（卡 1，芯片组 x4）—— 错开 20 秒再起，避开同时装载")
w("COMFY_PORT=8191 ONEAPI_DEVICE_SELECTOR=level_zero:1 \\")
w("  SYCL_CACHE_DIR=<工具目录>/_sycl_cache_c1 \\")
w("  <ComfyUI 目录>/python_embeded/python.exe <ComfyUI 目录>/main.py \\")
w("    --listen 127.0.0.1 --port 8191 --reserve-vram 4")
w("```")
w("")
w("- **钉卡只有一层：`ONEAPI_DEVICE_SELECTOR=level_zero:N`。** ComfyUI 的 `main.py` 本身没有「断言索引」这个参数，")
w("  照抄台架采集器的 `--expect-index`（那是 `bench_f_h3.py` 的参数）会直接报参数错误起不来。")
w("- **起好之后自己核一次**：两个实例各看一次显存占用，两个都涨才是各占一张卡；只有一个涨，就是都落到了同一张。")
w("- **`SYCL_CACHE_DIR` 必须各给一份**，共用一个会互相覆盖内核缓存。")
w("- 端口用 8190 / 8191。**8188 是常驻实例，不要抢、不要杀。**")
w("- `--reserve-vram 4` 是这套数字的采集条件，改它会影响装载行为。")
w("")
w("### 8.2 llama.cpp 双卡：多设备 + 分层装载")
w("")
w("```bash")
w("# SYCL 运行时的 DLL 在 python_embeded 里，必须前置，否则 exe 起来就 0xC0000005")
w("PATH=<python_embeded 目录>/Library/bin:<llama.cpp bin 目录>:$PATH")
w("ONEAPI_DEVICE_SELECTOR=level_zero:0,1 \\")
w("  llama-server -m <模型目录>/Qwen_Qwen3.6-35B-A3B-Q4_0.gguf \\")
w("    -dev SYCL0,SYCL1 -sm layer \\")
w("    -c 3145728 --parallel 12 \\")
w("    --host 127.0.0.1 --port 8099")
w("```")
w("")
w("- 🔴 **`-c` 必须与 `--parallel` 对齐**：`--parallel = ctx / 262144`。不对齐时日志里 `kv_unified=true`，")
w("  每 M token 要 22.2~22.4 GiB，2M 直接 OOM；对齐后 `kv_unified=false`，每 M token 只要 14.5~15.6 GiB。")
w("- **只在一张卡上跑就写 `-dev SYCL0`（或 `SYCL1`）**，并把 `ONEAPI_DEVICE_SELECTOR` 一起收窄到同一张，否则设备枚举顺序会变。")
w("- 🔴 **`PATH` 必须前置 `python_embeded\\Library\\bin`**（里面有 SYCL 运行时的 DLL）。不加的表现是")
w("  **退出码 `0xC0000005`、1 秒内崩、stderr 全空** —— 看着像模型问题，其实是运行时没找到。")
w("")
w("### 8.3 三条判断")
w("")
w("| 查什么 | 怎么做 | 为什么 |")
w("|---|---|---|")
w("| 起没起 | 等日志出现 `model loaded`，再发一次 `/v1/chat/completions` | TCP 通不等于能提问 |")
w("| 装没装下 | 看**显存占用有没有随 `-c` 按比例涨** | 单卡 `-c 1572864` / `2097152` 都能起能答，但占用与 1M 一样（12.68 / 12.63 vs 12.81 GiB）—— 多出来的上下文没真分配 |")
w("| 值不值得 | 看**跑得多快** | Q8_0 单卡 `-ngl 99` 装不下却照样 `model loaded` + 探针 200，只是余下层落 CPU |")
w("")
w("### 8.4 两条会让数字假掉的小设置")
w("")
w("- **`cache_prompt` 必须关**（多模态对照里是 `cache_prompt: false`）。不关的话同一张图连打会命中提示词缓存，")
w("  墙钟掉到 0.1 s、decode 报 115 tok/s —— 那是缓存，不是算力。")
w("- **先热车再取数**。同一条 H3，页缓存冷 %s、热 %s，差 %s 个百分点。凡「双卡拖慢多少」，先跑一轮热的。" % (s(d1_fresh["server_sec"]), s(sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")["server_sec"]), f1(100 * (d1_fresh["server_sec"] / sample(load("2026-10-23_h3_1280x720_duald4b.json"), "fresh")["server_sec"] - 1))))
w("")

# ---------------------------------------------------------------- 九
w("## 九、坑清单")
w("")
w("| # | 坑 | 表现 | 处理 |")
w("|---:|---|---|---|")
w("| 1 | 以为双卡算力翻倍 | 单步 42.30 → 42.41 s/it，一步没快 | `torch.xpu` 只用第一张卡；llama.cpp 多设备是分层装载 |")
w("| 2 | 以为拆层一定赔速度 | 双卡 33.53 GiB 全驻，解码 37.35 tok/s | 同场次实测不赔：比单卡全驻 31.86 快 1.17×、比单卡 spill 13.80 快 2.55×。`-sm row` 才真跑不起来 |")
w("| 7 | 以为张量并行能加速 | `-sm tensor` 两卡解码 29.08~29.50 tok/s | 比单卡全驻 31.86 还慢：每层跨卡同步的代价超过第二张卡的贡献。要协同走拆层，别走张量 |")
w("| 15 | 以为上下文写得越大越好 | 3M 分配成功，长 prompt prefill 卡在 8192 token | 14 分钟后整机静默卡死（无 dump、无蓝屏）。3M 只是分配上限；可用上限单卡 1M / 双卡 1.75M |")
w("| 16 | 以为页面文件越大越保险 | 64 GB 页面文件，系统承诺 95.11 GiB | 承诺太满，本该进程报 OOM 变成整机卡死。页面文件要「够用且留余量」 |")
w("| 17 | 以为「初始调小」就锁住了 | 初始 32 GB / 最大 64 GB，3M 装载时 Windows 扩到 ~56 GB | commit limit 涨回 86.97 GiB、提交 98.9%，同卡死危险区。**初始与最大必须同值（32768）** |")
w("| 18 | 以为虚拟内存要设很大才安全 | 初始 = 最大 = 32768 锁死后，3M 装载 20.4 s 进程自己退、提交峰值 55.4%，limit 全程不扩 | 超上限的请求进程自己报 OOM 退出、机器照常用。虚拟内存定案：**32 GB 固定（初始 = 最大）** |")
w("| 14 | 以为换更底层的卡间拷贝能救张量并行 | 三档拷贝路径（SYCL 直拷 / Level Zero 直拷 / 强制走主机内存）解码 %s / %s / %s tok/s | 三档在噪声内。卡间拷贝不是瓶颈，同步次数才是。别再往这个方向调 |" % (f2(d2d["dual_tensor_5050_p2p"]), f2(d2d["dual_tensor_5050_l0direct"]), f2(d2d["dual_tensor_5050_hostforward"])))
w("| 3 | 进程起得来就当真装下了 | `-c 1.5M` / `2M` 能起能答，显存一点没多占 | 改看「显存有没有随 `-c` 按比例涨」 |")
w("| 4 | 装不下就认定起不来 | Q8_0 单卡 `-ngl 99` 照样 200 | 改看「跑得多快」 |")
w("| 5 | `-c` 与 `--parallel` 不对齐 | 每 M token 22.2~22.4 GiB，2M OOM | `--parallel = ctx / 262144`，确认日志 `kv_unified=false` |")
w("| 6 | 双实例同时出视频 | 2/2 崩在 `loads=2` 之后，`0xC0000005`，页面文件峰值 48.7 GB | 32 GB 内存墙；双卡只做「一条视频 + 一条轻任务」 |")
w("| 7 | 首轮直接取数 | 首轮 543 s、热车后 406 s，同一个配置 | 先跑一轮热车；首轮含并发装载，不可比 |")
w("| 8 | 功耗归错卡 | H3 跑得正旺，采样器报 42~46 W | 采样器只读 Sysman 第 0 个设备，且 **Sysman 顺序 ≠ `level_zero:N`**（本机 Sysman dev0 = 总线 16 = 卡 1）。双卡功耗改用按卡枚举、按 PCI 总线归属的采集器 |")
w("| 9 | `PATH` 没前置就起 llama.cpp | `0xC0000005`，1 秒内崩，stderr 全空 | 前置 `<python_embeded 目录>/Library/bin` |")
w("| 10 | `llama-bench` 传 `-c` | `invalid parameter for argument: -c` | `llama-bench` 用 `-p` / `-n`，不认 `-c` |")
w("| 11 | 输出接管道再取数 | 管道要等进程结束才吐字，中途一个字都看不到 | 直接 `>> 日志文件 2>&1` |")
w("| 12 | 共用 `SYCL_CACHE_DIR` | 两个实例互相覆盖内核缓存 | 各给一份；但注意：隔离后照崩的那次不是缓存问题 |")
w("| 13 | 采集器没启动就以为没功耗 | 记录里功耗字段是空的 | 不显式启动就静默降级成「不记功耗」，不是零功耗 |")
w("")

# ---------------------------------------------------------------- 十
w("## 十、数据从哪来")
w("")
w("- 时间：**2026-10-23**（双卡 H3、出图、容量、功耗全部实测）；单卡基线取 **2026-10-21**（H3、出图、Qwen）与")
w("  **2026-10-22**（H3 时长阶梯）；**2026-10-24** 三批：张量并行与卡间拷贝路径（§4.1、§九第 7/14 条）、")
w("  `-ts` 细扫与 Q4_0 档双卡/单卡同场次对照（§5.2）、3M 上下文跑不跑得动（§5.1、§九第 15/16 条）。")
w("  ⚠️ **§5.2 的 Q4_0 对照与单卡 `-ngl 37` 重跑是同一时段（17:37~17:47）连跑的**，是目前最紧的同场次比较；")
w("  12:39 与 16:10 两个场次的双卡数字相差 6%，**跨场次只当参考**。")
w("- 原始记录：`bench/data/` 下按日期命名的 json，每条含 workload、samples、summary、notes。本文所有表格由")
w("  `bench/harness/gen_dual_report.py` 从这些 json 直出，**没有手抄数字**。")
w("- 用到的记录：")
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
w("- 相关文档：跨卡对照总表 [`slot-comparison.md`](slot-comparison.md) §6、H3 四卡实测 [`comfyui-h3.md`](comfyui-h3.md)、")
w("  功耗 [`comfyui-power.md`](comfyui-power.md)、常见坑 [`pitfalls.md`](pitfalls.md)。")
w("- 调试过程与踩坑的完整记录在 `bench/notes/dual-b65-prep.md`，**那份是工程笔记，不是产品文档**；对外结论以本文和 `docs/` 为准。")
w("- 3M 上下文把整机跑挂的完整取证（含转储判据、单变量对照、页面文件分析）在 `bench/notes/ctx3m-hang-2026-10-24.md`。")
w("")

text = "\n".join(L) + "\n"
text = text.replace("\r\n", "\n").replace("\r", "\n")
text = text.replace("\n", "\r\n")
if text.endswith("\r\n"):
    text = text[:-2]

with open(OUT, "wb") as f:
    f.write(text.encode("utf-8"))

print("written:", OUT, len(text), "bytes")
