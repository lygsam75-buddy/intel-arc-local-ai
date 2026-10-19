# 上线作业单（GitHub 首发）

> **触发**：2026-10-20 上线（已定）。**不等 B60/B65** —— 卡没到，首版就不包含它们，
> 在仓库里按「未测」明示，而不是留空让人猜。
>
> 逐项打勾再推。标 ☑️ 的是发布当天要确认的，标 ✅ 的是已经做过的。

---

## 0. 上线内容清单

六个板块。**顺序就是读者进来的顺序**：先看结论 → 再看自己那类负载 → 再查坑 → 最后才看原始数据。

| # | 板块 | 具体文件 | 规模 | 一句话定位（读者为什么要看） |
|---|---|---|---:|---|
| 1 | **门面** | `README.md` | 386 行 | 硬件口径 + 全部实测数字汇总 + 目录。**别人只看这一页也要能拿到结论** |
| 2 | **推理侧（llama.cpp）** | `docs/vram-16gb.md`<br>`docs/server-config.md`<br>`docs/slot-comparison.md`<br>`docs/test-rig.md`<br>`docs/strata-b50-linux-prep.md`<br>`bench/README.md` | 442 / 325 / 235 / 267 / 441 / 433 行 | 主力档位参数优化、可直接交付的 server 配置、槽位到底有没有损失、平台规格、在 Ubuntu 上复现的卡点。**`bench/README.md` 是「什么才算一条可比的数字」的口径定义** |
| 3 | **ComfyUI 侧** | `docs/comfyui-capability.md`<br>`docs/comfyui-h3.md`<br>`docs/comfyui-image.md`<br>`docs/comfyui-power.md` | 399 / 679 / 850 / 322 行 | 能力总表（能装多大 / 出视频 / 出图三问一页答完）→ 视频分辨率 × 时长全矩阵 → 出图与出音乐（含内核变体配对）→ 功耗与电费。**这是全库最有对客价值的一组** |
| 4 | **坑清单** | `docs/pitfalls.md` | 926 行 | 每个坑的现象 → 根因 → 修法。**含 TDR 2 秒、TIME_WAIT 端口耗尽、XPU 锁页内存、int8 门禁这几条最贵的** |
| 5 | **测试项台账** | `docs/test-registry.md`<br>`CONTRIBUTING.md` | 441 / 72 行 | 所有测试项的编号 / 状态 / 数据位置 / 复现入口，含**「预判 vs 实测」**和**更正台账**。**这是「数据可信」的唯一凭据** |
| 6 | **数据与工具** | `bench/data/` 207 个 JSON（2.4 MB）<br>`bench/logs/` 33 份 `llama-server` 原始日志（18 MB）<br>`bench/harness/` 24 个脚本 + 2 个 shell<br>`bench/logs/README.md` | 见左 | machine-readable 原始数据 + 采集脚本 + **日志↔记录对照**。审计入口：`python bench/harness/registry_audit.py` |

**全库合计**：Markdown 16 份 · 6,475 行；数据 207 条；日志 33 份；脚本 26 个。**约 21 MB**（日志占 18 MB）。

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
| 4 | `README.md`：硬件表、口径 A/B/C 各表、ComfyUI 各节、目录行 | ☑️ 发布当天通读一遍（重点：目录链接是否全部可达） |
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
| `.gitignore` | ✅ 覆盖 `__pycache__/`、`*.py[cod]`、`.venv/`、`*.gguf`、`*.bin`、`*.exe`、`*.zip`、`*.log`、`local.env`。**`*.log` 有例外**：`!bench/logs/*.log` 放行原始证据 |
| **孤儿 / 空壳文件** | ✅ 已删 `bench/results.md`（只有 1 行，内容已被 README 口径 A 表覆盖，且无任何引用） |
| `__pycache__` | ✅ 已物理删除（`.gitignore` 也盖住了） |
| LICENSE | ⚠️ MIT，copyright **`lygsam75-buddy`** —— **发布前确认这就是要挂的名字** |
| git 状态 | ☑️ 首次提交待做（见 §5） |

**日志路径归一化的落地细节**（一次性，已完成）：日志原文里的模型目录、llama.cpp 构建目录、工作目录路径，
把**路径字符串**换成占位符，**其余字节逐字节未动**（含 `\r\n` 行尾、时间戳、`offloaded N/N layers`、
`buffer size`、`Prompt executed`、报错行）。验证方式：同一套替换规则施加到原件上，
结果与入库文件**逐字节相等**（33/33 通过）。细则见 `bench/logs/README.md`。

---

## 4. 上线前要定的事（**只有这几项需要你本人拍**）

| # | 事项 | 建议默认 |
|---|---|---|
| 1 | **仓库名** | `intel-arc-ai-cookbook` |
| 2 | **公开范围** | **public**（手册的价值就在于被搜到；已扫过无密钥、无绝对路径、无内部产品名） |
| 3 | **署名** | `lygsam75-buddy`（LICENSE 已写死，与 git 全局身份一致） |
| 4 | **仓库描述 / topics** | 描述：`Intel Arc Pro B50/B70 本地 AI 实测手册：llama.cpp · ComfyUI · 出图/视频/功耗`；topics：`intel-arc` `xpu` `llama-cpp` `comfyui` `oneapi` `benchmark` `local-llm` |
| 5 | **GitHub 登录** | `gh` 当前**未登录** → 需要一次浏览器授权（见 §5），之后长期有效 |

---

## 5. 首次发布步骤

```bash
cd <仓库根目录>

git init -b main
git add -A
git status --short --untracked-files=all   # 核对：无 .workbuddy/、无 *.gguf、无 __pycache__、无仓库外日志
git commit -m "initial: Intel Arc 本地 AI 实战手册（B50/B70 实测 + 测试项备案）"

# 建库并推送（需先 gh auth login）
gh auth login                              # 浏览器授权，只需一次
gh repo create intel-arc-ai-cookbook --public --source . --push \
  --description "Intel Arc Pro B50/B70 本地 AI 实测手册：llama.cpp · ComfyUI · 出图/视频/功耗"

# 补 topics
gh repo edit --add-topic intel-arc,xpu,llama-cpp,comfyui,oneapi,benchmark,local-llm
```

**commit message 规范**（之后每次提交都按这个来）：

```
data(b60):  新卡数据
docs:       文档更新
fix(data):  补录/修正历史记录（写清依据）
chore:      工具与基建
```

---

## 6. 发布后当天

- ☑️ `README.md` 顶部「GitHub（待发布）」改成实际链接
- ☑️ `docs/test-registry.md` §0 登记发布日期与首个 commit
- ☑️ 对客材料可以开始引用仓库链接（「性能档案」落地）
- ☑️ 核对 GitHub 页面上 `bench/logs/` 是否真的可见（`.gitignore` 的 `!` 例外只对已跟踪文件生效，`git add` 时要确认 33 份都在）
- ☑️ 可选：给 README 加一张仓库首页截图 / 一张功耗曲线，提升第一眼可信度

---

## 7. 首版**不能**承诺的东西（对客口径）

| 不能这么说 | 因为 | 应该说 |
|---|---|---|
| 「B70 满载 290 W，按 290 W 配散热」 | 只有单任务峰值，**没有 >1 h 长时数据** | 「单任务 P90 稳定在 290 W，长时未测」 |
| 「INT8 让能耗降 30%」 | 量化**不改功率、只改耗时**，能量收益 ≈ 时间收益 | 「INT8 算得快，所以每次少花电」 |
| 「B60/B65 也差不多」 | **卡没到，一条没测** | 「B60/B65 未测」 |
| 「双卡并发能翻倍」 | T-11 未测（第二张卡已在机但未做并发） | 「双卡并发未测」 |
| 拿 `server_sec` 比两批数据 | 装不下时会重载，端到端秒数不可比 | 「跨批次只比 `it/s`，`loads == 0` 时端到端才可比」 |
