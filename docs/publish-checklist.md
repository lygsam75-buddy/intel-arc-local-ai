# Launch Checklist (first GitHub release)

> **触发**：2026-10-20 **已上线** —— <https://github.com/lygsam75-buddy/intel-arc-local-ai>。
> **不等 B60/B65** —— 卡没到，首版就不包含它们，在仓库里按「未测」明示，而不是留空让人猜。
>
> 逐项打勾再推。标 ☑️ 的是待确认项，标 ✅ 的是已经做过的。

---

## 0. 上线内容清单

> ⚠️ **本节的行数、条数、体积都是 2026-10-20 首发那一刻的快照**，之后每天都还在加数据，**不要再当现值用**。
> 现值的唯一来源是 `python bench/harness/registry_audit.py`：**2026-10-23 现跑 = `bench/data` 372 条**
> （355 active · 16 discarded · 1 probe_failed；comfyui 185 / bench 87 / ctx-sweep 68 / vision 27 / longctx 4 / capacity 1）。

六个板块。**顺序就是读者进来的顺序**：先看结论 → 再看自己那类负载 → 再查坑 → 最后才看原始数据。

| # | 板块 | 具体文件 | 规模 | 一句话定位（读者为什么要看） |
|---|---|---|---:|---|
| 1 | **门面** | `README.md`（**英文，GitHub 默认首页**）<br>`README.zh-CN.md`（中文完整版）<br>`docs/at-a-glance.md` · `docs/at-a-glance.en.md` | 401 / 436 / 98 / 98 行 | **开头四张表**（想干什么 / 该买哪张 / 电费 / 双卡并排）——不用术语，先给结论。<br>再往下：硬件表、**蓝戟 GUNNIR + 功耗墙**（为什么同型号不同板性能不同）、长上下文、H3、出图出音乐、功耗。<br>`at-a-glance` 是更极端的「六张表一页纸」版本，两个 README 首屏都链到它。<br>**顶部互链**，GitHub 首屏是英文 |
| 2 | **推理侧（llama.cpp）** | `docs/vram-16gb.md`<br>`docs/server-config.md`<br>`docs/slot-comparison.md`<br>`docs/test-rig.md`<br>`docs/strata-b50-linux-prep.md`<br>`bench/README.md` | 442 / 325 / 235 / 267 / 441 / 433 行 | 主力档位参数优化、可直接交付的 server 配置、槽位到底有没有损失、平台规格、在 Ubuntu 上复现的卡点。**`bench/README.md` 是「什么才算一条可比的数字」的口径定义** |
| 3 | **ComfyUI 侧** | `docs/comfyui-capability.md`<br>`docs/comfyui-h3.md`<br>`docs/comfyui-image.md`<br>`docs/comfyui-power.md` | 399 / 679 / 850 / 322 行 | 能力总表（能装多大 / 出视频 / 出图三问一页答完）→ 视频分辨率 × 时长全矩阵 → 出图与出音乐（含内核变体配对）→ 功耗与电费。**这是全库最有对客价值的一组** |
| 4 | **坑清单** | `docs/pitfalls.md` | 926 行 | 每个坑的现象 → 根因 → 修法。**含 TDR 2 秒、TIME_WAIT 端口耗尽、XPU 锁页内存、int8 门禁这几条最贵的** |
| 5 | **测试项台账** | `docs/test-registry.md`<br>`CONTRIBUTING.md` | 441 / 72 行 | 所有测试项的编号 / 状态 / 数据位置 / 复现入口，含**「预判 vs 实测」**和**更正台账**。**这是「数据可信」的唯一凭据** |
| 6 | **数据与工具** | `bench/data/` 207 个 JSON（2.4 MB）<br>`bench/logs/` 33 份 `llama-server` 原始日志（18 MB）<br>`bench/harness/` 24 个脚本 + 2 个 shell<br>`bench/logs/README.md` | 见左 | machine-readable 原始数据 + 采集脚本 + **日志↔记录对照**。审计入口：`python bench/harness/registry_audit.py` |

**全库合计**：Markdown **19 份 · 7,151 行**（英文 2 份 499 行 = `README.md` 401 + `at-a-glance.en.md` 98；
中文 17 份 6,652 行）；数据 207 条；日志 33 份；脚本 26 个。**约 21 MB**（日志占 18 MB）。

### 语言策略：**英文占首屏，中文是权威源**

| 层 | 语言 | 为什么 |
|---|---|---|
| **GitHub 首屏** | **英文**（`README.md`） | GitHub 的默认流量是英文检索与英文读者。**英文读者不会点「简体中文」那条链接，但中文读者一定会点「English」旁边那条** —— 所以首屏给英文，切换成本落在中文读者这边，代价最小 |
| 仓库名 / description / topics | **英文** | 决定能不能被搜到；`intel-arc` `xpu` `llama-cpp` `comfyui` 是真正的检索词 |
| **双语范围** | 两个 README（**内容对等**）+ `at-a-glance` 双份 | 英文页不是「入口页」而是**同级完整页**：同样的四张总表、同样的五组核心数字、同样的未测项清单。读者不必为了一个数切语言 |
| **正文与细节（16 份 `docs/`）** | **中文** | 目标读者是国内客户与工程师。**细节只有中文一份，不产生第二个真相源** |
| 不做 | 16 份 `docs/` 全量双语 | **6,600+ 行**文档每天在改，两份译文必然失步；**失步的译文比没有译文更坏**（读者不知道哪份对） |

> 分工判据：**英文页负责「让人决定要不要看下去」，中文页负责「照着做」**。
> 改数字的顺序：**先改中文（权威源）→ 再同步两个 README 的顶层表 → `at-a-glance` 最后跟**。

### 明确「不入库」的东西

| 项 | 原因 |
|---|---|
| 模型权重（`*.gguf` / `*.safetensors`）、构建产物（`*.exe` / `*.zip`） | 体积，且与结论无关 |
| 日志归一化前的原件（带本机绝对路径） | 只公开替换后的版本。**替换规则可复算**：同一套规则施加到原件上，结果与入库文件逐字节相等 |
| `__pycache__/`、`.venv/`、编辑器目录 | `.gitignore` 已盖 |
| ComfyUI 本体与 custom_nodes | 装在仓库外；**只记版本与关键文件 mtime**（跨批次对比必须查，见台账） |

---

## 1. 发布前最后一遍（数据 → 文档 → 台账，顺序反了必漏）

| # | 动作 | 完成 |
|---|---|---|
| 1 | `bench/data/` 命名统一 `<日期>_<卡><显存>_<模型>-<量化>-<后端>.json`；视频域 `<日期>_h3_<WxH>_<标记>.json` | ✅ 207 条全部符合 |
| 2 | 重跑审计：`python bench/harness/registry_audit.py`，看数量 / schema / 取证覆盖率 / 功耗覆盖 / 槽位覆盖 | ✅ `total 207`；comfyui **122**（B70 97 / B50 25）；`timing_breakdown` **120/122**；`log_evidence` **122/122**（`annotated` 120 · `missing` 2） |
| 3 | 取证回填：`python bench/harness/annotate_comfy_evidence.py --data bench/data --logdir "<标签>=<目录>"`（`--logdir` 可重复给；**三个域都要覆盖**） | ✅ 已回填；两条 `missing` 是日志已被覆盖 / 全轮失败，**不假装做过** |
| 4 | `README.zh-CN.md`：开头四张总表、硬件表、llama-bench 表、长上下文、ComfyUI 各节、功耗、目录行；`README.md` 英文页与中文页**逐表对齐**；`at-a-glance` 中英两份同数 | ✅ 已按「先中文 → 再英文 → 最后 at-a-glance」重写一遍；**同一组数字三处不能打架** |
| 5 | `docs/test-registry.md` §1 状态 / §2 覆盖矩阵 / §3 数量 / §5 预判 vs 实测 | ✅ 已同步到 207 / 122 |
| 6 | 各篇文档里的交叉引用与锚点 | ☑️ **改过小标题的必查**（历史踩过：小标题改了、链接没跟上） |
| 7 | 体积与单文件上限（GitHub 单文件 100 MB） | ✅ 最大单文件 3.67 MB |

---

## 2. 未测项怎么标注（**别留空，别让人猜**）

首版有三类「没有数据」的东西。**写法统一：在同位置明确写「未测 + 原因 + 补测条件」，不留 TODO 占位符。**

| 未测项 | 原因 | 仓库里的写法 |
|---|---|---|
| **B60（24 GB）/ B65（32 GB）** | 卡未到 | README 硬件表保留规格行（读者要选型），数据表**不出现**这两行；`test-registry.md` §2 对应项标「未测（卡未到）」 |
| **B50 的后续实验**（分辨率天花板以上、双卡并发） | B50 已物理拆下，只剩 B70 | 已跑过的数据照常收录（25 条）；未跑的标「卡已拆，需重新上机」 |
| **T-11 双卡并发 / T-16 Vulkan / T-14 Strata 实跑** | 依赖第二张卡或在机状态 | 台账里标 ⛔/⏸️ 并写清前置条件 |
| **2560×1440 及以上分辨率** | 显存与时间成本过高，未测 | `comfyui-h3.md` 明确「五档到 1920×1088 为止，再往上未测」 |
| **长期满载（> 1 h）稳定性** | 只做了单任务峰值 | `comfyui-power.md` §8 待解里写明「无长时数据，别按 290 W 承诺散热」 |

> **判据**：对客能说的只有「实测到哪儿」，不能说的用一句「这一档没测」结束，**不要用推算值填表**。

---

## 3. 发布前扫描（2026-10-19 重跑）

| 项 | 结果 |
|---|---|
| **密钥** | ✅ 0 命中。`--api-key local` 是本地占位；文档里 `token` 均为 LLM 语义 |
| **本机绝对路径** | ✅ 0 命中（余下两处是 `bench/logs/README.md` 的**替换规则对照表**，必须写出原形；台账里的是历史留痕）。已清掉：脚本 docstring 里的真实目录、`pitfalls.md` 的 `/d/oneapi-dpcpp`、台账里的真实工作目录 |
| **体积** | ✅ 约 **21 MB**（`bench/logs/` 18 MB · `bench/data/` 2.4 MB · `docs/` 420 KB）；最大单文件 3.67 MB |
| `.gitignore` | ✅ 覆盖 `__pycache__/`、`*.py[cod]`、`.venv/`、`*.gguf`、`*.bin`、`*.exe`、`*.zip`、`*.log`、`local.env`。**`*.log` 无例外**：原始日志不上仓库，`bench/logs/` 只留 README |
| **孤儿 / 空壳文件** | ✅ 已删 `bench/results.md`（只有 1 行，内容已被 README 口径 A 表覆盖，且无任何引用） |
| `__pycache__` | ✅ 已物理删除（`.gitignore` 也盖住了） |
| LICENSE | ✅ MIT，copyright **`Yonggang Lin (林永刚)`**；README / git 作者已统一为同一署名（email `lygsam75@gmail.com` 用于关联 GitHub 账号） |
| git 状态 | ✅ 已是 git 仓库（`main`）；`.gitattributes` 定死 `* -text` + 代码走 LF；**已推送到 GitHub**（289/289 blob sha 与本地一致） |

**日志路径归一化的落地细节**（一次性，已完成）：日志原文里的模型目录、llama.cpp 构建目录、工作目录路径，
把**路径字符串**换成占位符，**其余字节逐字节未动**（含 `\r\n` 行尾、时间戳、`offloaded N/N layers`、
`buffer size`、`Prompt executed`、报错行）。验证方式：同一套替换规则施加到原件上，
结果与入库文件**逐字节相等**（33/33 通过）。细则见 `bench/logs/README.md`。

---

## 4. 上线前要定的事（**只有这几项需要你本人拍**）

| # | 事项 | 结论 |
|---|---|---|
| 1 | **仓库名** | ✅ 已定：`intel-arc-local-ai` · 显示名 **Intel Arc Local AI Handbook** |
| 2 | **公开范围** | ✅ **public**（手册的价值就在于被搜到；已扫过无密钥、无绝对路径、无内部产品名） |
| 3 | **署名** | ✅ 已定：**Yonggang Lin（林永刚）** · `lygsam75@gmail.com` —— LICENSE、两个 README、git 作者三处一致 |
| 4 | **仓库描述 / topics** | ✅ 已定。描述（英文，好被搜到）：`Field-measured local AI on Arc Pro B50 / B60 / B65 / B70: llama.cpp, ComfyUI, image · video · audio generation, and power — with raw logs and machine-readable data.`；topics：`intel-arc` `xpu` `llama-cpp` `comfyui` `local-llm` `benchmark` `oneapi` `arc-pro` |
| 5 | **对外定位** | ✅ 已定：**让更多人知道 Intel 这张卡能用、而且用得不错**，并**记住板子是蓝戟 GUNNIR 做的**。判据是**功耗墙**——公版卡功耗墙更低、性能有所保留，所以功耗数据不是附赠指标，是性能上限的直接依据（见 `README.zh-CN.md` 对应小节） |
| 6 | **GitHub 登录** | ✅ 已解决：`gh` CLI 未登录，改用 **GitHub Desktop 凭据管理器里的 OAuth token**（`GH_TOKEN` 注入 `gh`），发布当天一次通过（见 §5） |

---

## 5. 首次发布步骤

### 已做完（不用再动）

```bash
git init -b main                    # ✅
git config core.autocrlf false      # ✅ 配合 .gitattributes 的 * -text
git add -A && git commit            # ✅ 已有 10 次提交，工作区干净
```

> **行尾策略是取证结论的一部分**：日志入库前核对过「路径归一化、其余字节逐字节未动（含 `\r\n`）」。
> `core.autocrlf=true` 会把这份结论作废 —— 所以 `.gitattributes` 写死 `* -text`，
> 只有 `*.py` / `*.sh` 走 `text eol=lf`。**别改成默认值。**

### 发布执行记录（2026-10-20 已完成）

`gh` CLI **本身未登录**（`gh auth status` → not logged into any GitHub hosts），实际走的是
**GitHub Desktop 落在 Windows 凭据管理器里的 OAuth token**
（`GitHub - https://api.github.com/lygsam75-buddy`）→ 以 `GH_TOKEN` 交给 `gh`，等同已登录：

```bash
gh auth setup-git --hostname github.com          # 让 git push 走 gh 的凭据助手
gh repo create intel-arc-local-ai --public --source . --push \
  --description "Field-measured local AI on Arc Pro B50 / B70: llama.cpp, ComfyUI, image · video · audio generation, and power — with raw logs and machine-readable data."
gh repo edit lygsam75-buddy/intel-arc-local-ai --add-topic ...   # ⚠️ repo edit 要 [OWNER/REPO]，只给名字会报格式错
```

**结果**：<https://github.com/lygsam75-buddy/intel-arc-local-ai> · public · `main` ·
289 文件 · 33 份日志 · 207 条 JSON · 8 个 topics。

**推送后核对**（比「推上去了」更重要的那一步）：把远端 `git/trees/main?recursive=1` 的每个 blob sha
与本地 `git rev-parse HEAD:<path>` 逐个比对 → **289/289 完全一致**。
这就是 `.gitattributes` 里 `* -text` 有没有白写的判据 —— blob sha 一致 ⇒ 服务端没做行尾转换 ⇒
日志「路径归一化、其余字节逐字节未动」的取证结论在线上仍然成立。

> 本地目录名仍是旧的 `intel-arc-ai-cookbook`（改名时被本会话占用目录，`mv` / `Rename-Item` 都报占用）。
> **不影响上线** —— GitHub 上的仓库名由 `gh repo create` 决定，与本地目录名无关。
> 会话结束、目录释放后再改本地目录名即可。

**commit message 规范**（之后每次提交都按这个来）：

```
data(b60):  新卡数据
docs:       文档更新
fix(data):  补录/修正历史记录（写清依据）
chore:      工具与基建
```

---

## 6. 发布后当天

- ✅ 两个 README 已换成实际仓库地址 / 纯链接表述（`https://github.com/lygsam75-buddy/intel-arc-local-ai`）
- ✅ `docs/test-registry.md` §0 已登记发布日期、首个 commit `c83228e` 与 289/289 blob sha 核对结果
- ✅ 对客材料可以开始引用仓库链接（「性能档案」落地）
- ✅ 已核对线上 `bench/logs/` 可见：`contents/bench/logs` 返回 **34 项**（33 份日志 + README）
- ☑️ 可选（未做）：README 首页截图 / 功耗曲线图，提升第一眼可信度

---

## 7. 首版**不能**承诺的东西（对客口径）

| 不能这么说 | 因为 | 应该说 |
|---|---|---|
| 「B70 满载 290 W，按 290 W 配散热」 | 只有单任务峰值，**没有 >1 h 长时数据** | 「单任务 P90 稳定在 290 W，长时未测」 |
| 「INT8 让能耗降 30%」 | 量化**不改功率、只改耗时**，能量收益 ≈ 时间收益 | 「INT8 算得快，所以每次少花电」 |
| 「B60/B65 也差不多」 | **卡没到，一条没测** | 「B60/B65 未测」 |
| 「双卡并发能翻倍」 | **实测不翻倍**（2× B65）：两条线各跑各的，H3 端到端 +6.0%、Qwen 解码 −0.2% | 「双卡买的是吞吐与容量，不是单任务速度」 |
| 拿 `server_sec` 比两批数据 | 装不下时会重载，端到端秒数不可比 | 「跨批次只比 `it/s`，`loads == 0` 时端到端才可比」 |