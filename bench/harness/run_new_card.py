#!/usr/bin/env python
"""新卡到手：一条命令跑完整条队列（体检 → llama.cpp → ComfyUI）。

为什么要有这个驱动脚本
----------------------
B60 / B65 到手后要跑的东西与 B50 / B70 是同一套，但**顺序不能错、跑完一项要立刻落盘**，
中间任何一项挂了都不能拖死后面。手工一条条敲的问题不是慢，是三件具体的事：

1. **静默跑错卡**：双卡在机时索引会变，标签写 B65、实际跑在 B70 上 —— 整批数据作废。
   → 每个阶段开跑前都过 `card_guard.pin_and_verify()`，型号不符直接停。
2. **口径漂移没人记**：驱动、ECC、TDR、显存可见量一变，历史数字就不能并排比。
   → 体检阶段先把这些**打印并落盘**，跑测时再写进每条记录。
3. **跑一半断了不知道跑到哪**：队列按 item 记账（`.new_card_state.json`），
   重跑自动跳过已完成项，失败项记 `fail` 但**不中断队列**。

刻意不做的事
------------
**不自动跑 `migrate_*.py`。** 那几个迁移器重跑会覆盖 `annotate` 回填的取证字段，
纪律是「绝不整目录重跑」。所以队列只跑到「原始 jsonl / server 日志落到采集目录」为止，
归档由 `--stages D` 打印出**逐条要人看的命令清单**，人确认后再执行。

用法
----
    export ARC_MODELS=<GGUF 目录>
    export ARC_LLAMA_BIN=<llama.cpp 的 build/bin>
    export ARC_BENCH_DIR=<采集脚本目录：card_guard.py / bench_f_h3.py / sweep.py 所在>
    export ARC_PYTHON=<跑测用的解释器>
    export ARC_SYCL_PATH="<SYCL 运行时目录>;<oneMKL 目录>"

    python bench/harness/run_new_card.py --card b65 --dry-run     # 先看计划
    python bench/harness/run_new_card.py --card b65               # 真跑
    python bench/harness/run_new_card.py --card b65 --stages C    # 只补跑 ComfyUI
"""
from __future__ import annotations

import argparse
import json
import os

import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / ".new_card_state.json"

# 每张卡的体检预期。vram 只做**告警**不做拦截（ECC / 驱动差异会让可见量浮动）。
CARDS = {
    "b50": dict(needle="B50", vram=(15.0, 16.2), toks=170, bw=224, tbp=70,
                quants=[("IQ2_M", "Qwen3.6-35B-A3B-UD-IQ2_M.gguf", "10.73"),
                        ("Q3_K_S", "Qwen3.6-35B-A3B-UD-Q3_K_S.gguf", "14.30"),
                        ("Q4_0", "Qwen_Qwen3.6-35B-A3B-Q4_0.gguf", "19.41")]),
    "b60": dict(needle="B60", vram=(23.0, 24.2), toks=197, bw=456, tbp=200,
                quants=[("IQ2_M", "Qwen3.6-35B-A3B-UD-IQ2_M.gguf", "10.73"),
                        ("Q3_K_S", "Qwen3.6-35B-A3B-UD-Q3_K_S.gguf", "14.30"),
                        ("Q4_0", "Qwen_Qwen3.6-35B-A3B-Q4_0.gguf", "19.41")]),
    "b65": dict(needle="B65", vram=(30.0, 32.2), toks=197, bw=608, tbp=200,
                quants=[("IQ2_M", "Qwen3.6-35B-A3B-UD-IQ2_M.gguf", "10.73"),
                        ("Q3_K_S", "Qwen3.6-35B-A3B-UD-Q3_K_S.gguf", "14.30"),
                        ("Q4_0", "Qwen_Qwen3.6-35B-A3B-Q4_0.gguf", "19.41")]),
    "b70": dict(needle="B70", vram=(30.0, 32.2), toks=367, bw=608, tbp=290,
                quants=[("IQ2_M", "Qwen3.6-35B-A3B-UD-IQ2_M.gguf", "10.73"),
                        ("Q3_K_S", "Qwen3.6-35B-A3B-UD-Q3_K_S.gguf", "14.30"),
                        ("Q4_0", "Qwen_Qwen3.6-35B-A3B-Q4_0.gguf", "19.41")]),
}

MODEL_35B = "Qwen_Qwen3.6-35B-A3B-Q4_0.gguf"


# --------------------------------------------------------------------- 小工具

def env(name, default=""):
    return os.environ.get(name, default)


def need_env(*names):
    missing = [n for n in names if not env(n)]
    if missing:
        sys.exit("缺少环境变量：%s（见本文件顶部「用法」）" % ", ".join(missing))


def sycl_candidates():
    """扫本机 oneAPI 安装布局，返回含 `sycl8.dll` 的 bin 目录。

    只作**诊断提示**用（自检失败时列给用户看），不作为默认值写死——
    全库不出现本机绝对路径的纪律对脚本一样有效。
    """
    import glob as _g
    roots = ["D:/oneAPI", "D:/oneapi-*", "C:/Program Files (x86)/Intel/oneAPI"]
    out = []
    for r in roots:
        for d in _g.glob(r + "/*/*/bin") + _g.glob(r + "/Library/bin"):
            if os.path.isfile(os.path.join(d, "sycl8.dll")):
                out.append(d)
    return sorted(set(out))


def ctx_bad_files(card):
    """当前 status 不是 ok 的 ctx 产出文件集合。

    ⚠️ 只按**文件名**去重、不看内容：调用方拿它当基线，跑完后重新算一次，
    差集就是本次新产生的废档。已标 discarded 的历史负结果会进基线，不会误报。
    """
    out = set()
    for p in (REPO / "bench" / "data").glob("*%s-ctx*.json" % card):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("status") != "ok":
            out.add(p.name)
    return out


def sycl_check(bin_, sycl):
    """跑 `llama-bench --version` 验证 SYCL 运行时可达，不可达就退出。

    🔴 为什么必须有这道：llama-bench 加载不到运行时 DLL 时**不打印任何错误**，
    只给退出码 3221225781（`0xC0000135` = STATUS_DLL_NOT_FOUND）。B60 首轮
    4 项 ctx 全挂在这，而且日志 0 行，只能靠退出码反推。

    判据：`ARC_SYCL_PATH` 指向的目录必须同时含
      - `sycl8.dll`（⚠️ **不是** `sycl8-preview.dll`，旧安装里只有 preview 版）
      - `mkl_sycl_blas.5.dll`
    """
    exe = os.path.join(bin_, "llama-bench.exe")
    if not os.path.isfile(exe):
        sys.exit("找不到 %s" % exe)
    chk = dict(os.environ)
    if sycl:
        chk["PATH"] = sycl + os.pathsep + chk.get("PATH", "")
    try:
        r = subprocess.run([exe, "--version"], capture_output=True,
                           timeout=120, env=chk)
    except OSError as e:
        sys.exit("llama-bench 起不来：%s" % e)
    if r.returncode != 0:
        msg = [
            "llama-bench 自检失败（rc=%d）。" % r.returncode,
            "  最常见原因：ARC_SYCL_PATH 指错目录。判据——该目录必须同时含",
            "    sycl8.dll（⚠️ 不是 sycl8-preview.dll）和 mkl_sycl_blas.5.dll。",
            "  当前 ARC_SYCL_PATH=%r" % sycl,
        ]
        cands = sycl_candidates()
        if cands:
            msg.append("  本机含 sycl8.dll 的目录（可直接用作 ARC_SYCL_PATH）：")
            msg += ["    " + c for c in cands]
        else:
            msg.append("  本机没扫到含 sycl8.dll 的目录，先装/修 oneAPI 基础工具包。")
        sys.exit("\n".join(msg))
    print("[自检] llama-bench 可启动，SYCL 运行时可达（ARC_SYCL_PATH=%s）"
          % (sycl or "<未设，走 PATH>"))


def driver_version(model_hint):
    """按型号在显示类里找驱动版本。

    ⚠️ 两个坑：① 子键编号（`0000`/`0004`…）**不固定**，与插槽/枚举顺序相关，
    不能写死；② 一张卡一个子键，历史卡（已拔掉的 B50）会留着旧记录，
    所以必须按 `DriverDesc` 里的型号去配，不能取第一个。
    """
    try:
        import winreg
    except ImportError:
        return None
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return None
    hits = []
    with k:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(k, i)
            except OSError:
                break
            i += 1
            if not (len(sub) == 4 and sub.isdigit()):
                continue
            try:
                with winreg.OpenKey(k, sub) as sk:
                    desc, _ = winreg.QueryValueEx(sk, "DriverDesc")
                    ver, _ = winreg.QueryValueEx(sk, "DriverVersion")
            except OSError:
                continue
            if model_hint.upper() in str(desc).upper():
                hits.append((sub, str(desc), str(ver)))
    if not hits:
        return None
    if len({h[2] for h in hits}) > 1:
        print("  ⚠️ 同型号有多个驱动记录：%s" % "; ".join("%s=%s" % (h[0], h[2]) for h in hits))
    return hits[0][2]


def reg_value(path, name):
    """单值读取（TDR 这类固定位置用）；读不到返回 None。"""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            val, _ = winreg.QueryValueEx(k, name)
            return val
    except OSError:
        return None


def port_free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def time_wait():
    """本机 TIME_WAIT 条数。取不到返回 None —— 这是辅助信息，不该拖死队列。

    ⚠️ `netstat` 在本机是 GBK 输出，按 UTF-8 严格解码会抛
    `UnicodeDecodeError`（还是在线程里抛，看着像崩溃）→ 一律收字节再宽松解码。
    """
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, timeout=60)
    except Exception:
        return None
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    if not out:
        return None
    return len([l for l in out.splitlines() if "TIME_WAIT" in l])


def xpu_enum(py):
    code = ("import torch,json;"
            "print(json.dumps([{'name':torch.xpu.get_device_properties(i).name,"
            "'gib':round(torch.xpu.get_device_properties(i).total_memory/1073741824,2)}"
            " for i in range(torch.xpu.device_count())]))")
    r = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()[:300]
    try:
        return json.loads(r.stdout.strip().splitlines()[-1]), None
    except Exception as e:
        return None, "枚举输出解析失败：%s" % e


# --------------------------------------------------------------------- 队列

class Queue:
    def __init__(self, card, dry):
        self.card = card
        self.dry = dry
        self.state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        self.state.setdefault(card, {})
        self.fails = []

    def done(self, item):
        return self.state[self.card].get(item, {}).get("status") == "ok"

    def run(self, item, argv, timeout, note="", verify=None):
        if self.done(item):
            print("[skip] %-34s 已完成（%s）" % (item, self.state[self.card][item].get("at", "?")))
            return True
        print("\n" + "=" * 78)
        print("[item] %s  %s" % (item, note))
        print("       " + " ".join(argv))
        if self.dry:
            return True
        t0 = time.time()
        try:
            rc = subprocess.run(argv, cwd=str(REPO), timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = -9
            print("[warn] 超时 %d s —— 记失败，继续下一项" % timeout)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            rc = -1
            print("[warn] 起不来：%s" % e)
        dt = time.time() - t0
        # 🔴 rc==0 不代表跑成了：ctx_sweep 内部各档 load_failed 也照样返回 0，
        # B60 首轮 4 条环境错误就是这样被记成 ok 并跳过的。所以 rc==0 后再查一遍产出。
        bad = None
        if rc == 0 and verify:
            try:
                bad = verify()
            except Exception as e:
                bad = "校验本身出错：%s" % e
        ok = (rc == 0) and not bad
        self.state[self.card][item] = {
            "status": "ok" if ok else "fail", "rc": rc,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"), "sec": round(dt, 1), "argv": argv,
        }
        if bad:
            self.state[self.card][item]["verify"] = bad
        STATE.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        if not ok:
            self.fails.append((item, rc, round(dt, 1)))
            print("[fail] %s%s（%0.0f s）—— 负结果也要落盘，不中断队列"
                  % (item, " rc=0 但产出校验不过：%s" % bad if bad else " rc=%d" % rc, dt))
        else:
            print("[ok]   %s  %0.0f s" % (item, dt))
        return ok

    def summary(self):
        print("\n" + "=" * 78)
        print("本次结果（%s）" % self.card)
        for item, rec in self.state[self.card].items():
            print("  %-34s %-4s rc=%-3s %s s  %s" % (
                item, rec.get("status"), rec.get("rc"), rec.get("sec"), rec.get("at")))
        if self.fails:
            print("\n失败项（负结果同样有诊断价值，别删）：")
            for f in self.fails:
                print("  %s  rc=%s  %s s" % f)
        else:
            print("\n全部通过。")
        print("\n下一步（归档，**必须人看**，不自动跑）：")
        print("  python bench/harness/run_new_card.py --card %s --stages D" % self.card)


# --------------------------------------------------------------------- 各阶段

def stage_a(q, card, cfg, py):
    """体检：不跑负载，只把「这批数据属于什么口径」定下来。"""
    print("\n" + "#" * 78)
    print("# A 体检 —— 以下每一项变了，历史数字就不能并排比")
    print("#" * 78)

    devs, err = xpu_enum(py)
    if devs is None:
        sys.exit("[A] 枚举 XPU 失败：%s\n     检查 ARC_PYTHON 是否指向真正跑测的解释器" % err)
    for i, d in enumerate(devs):
        print("  xpu:%-2d %-46s %6.2f GiB" % (i, d["name"], d["gib"]))
    hit = [d for d in devs if cfg["needle"].upper() in d["name"].upper()]
    if not hit:
        sys.exit("[A] ❌ 在位的卡里没有 %s（在位：%s）—— 先插卡，别往下跑"
                 % (cfg["needle"], ", ".join(d["name"] for d in devs)))
    target = hit[0]
    lo, hi = cfg["vram"]
    if not (lo <= target["gib"] <= hi):
        print("  ⚠️ 显存可见量 %.2f GiB 不在预期区间 %.1f~%.1f —— "
              "查 ECC 是否被打开（IGS → Graphics → ECC）" % (target["gib"], lo, hi))

    drv = driver_version(cfg["needle"])
    tdr = reg_value("SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers", "TdrDelay")
    tddi = reg_value("SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers", "TdrDdiDelay")
    print("\n  驱动版本      %s" % drv)
    print("  TdrDelay      %s %s" % (tdr, "" if str(tdr) == "60" else "⚠️ 不是 60 —— 长内核会被 2 s 看门狗杀掉"))
    print("  TdrDdiDelay   %s" % tddi)
    for port in (8188, 8189, 8099):
        print("  端口 %-5d    %s" % (port, "空闲" if port_free(port) else "被占用"))
    tw = time_wait()
    if tw is not None:
        print("  TIME_WAIT     %d %s" % (tw, "" if tw < 2000 else "⚠️ 偏高，查采集侧连接泄漏"))

    # ECC 与功耗墙（同一支脚本读，读不到不拦）
    sysman = REPO / "bench" / "harness" / "gpu_sysman.py"
    if sysman.exists() and not q.dry:
        r = subprocess.run([py, str(sysman)], capture_output=True, text=True, timeout=180)
        tail = [l for l in (r.stdout or "").splitlines() if l.strip()][:14]
        if tail:
            print("\n  ── gpu_sysman ──")
            for l in tail:
                print("  " + l)

    if not q.dry:
        rec = {"card": q.card, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "device": target["name"], "vram_gib": target["gib"],
               "driver": drv, "tdr_delay": tdr, "tdr_ddi_delay": tddi,
               "devices_in_machine": devs}
        out = REPO / "bench" / "logs" / ("preflight_%s_%s.json"
                                         % (q.card, time.strftime("%Y%m%d")))
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n  → 体检记录：%s" % out.relative_to(REPO))
    return target, drv


def stage_b(q, card, cfg, py):
    """llama.cpp：基线 → 量化档 → -ncmoe 拐点 → 上下文。"""
    need_env("ARC_MODELS", "ARC_LLAMA_BIN")
    models, bin_ = env("ARC_MODELS"), env("ARC_LLAMA_BIN")
    sycl = env("ARC_SYCL_PATH")
    gpu = {"b50": "Intel Arc Pro B50 LP 16G", "b60": "Intel Arc Pro B60 24G",
           "b65": "Intel Arc Pro B65 32G", "b70": "Intel Arc Pro B70 32G"}[card]
    drv = env("ARC_DRIVER") or (driver_version(cfg["needle"]) or "")
    sel = env("ONEAPI_DEVICE_SELECTOR", "opencl:0")
    # 🔴 先自检再开跑：运行时 DLL 缺失时 llama 全家都是「0 行日志 + rc=3221225781」，
    # 不先拦一下就会像 B60 首轮那样白跑 4 项才发现全挂。
    sycl_check(bin_, sycl)
    out = str(REPO / "bench" / "data")
    xb = str(REPO / "bench" / "harness" / "xpu_bench.py")
    scan = str(REPO / "bench" / "harness" / "scan_ncmoe.py")
    ctx = str(REPO / "bench" / "harness" / "ctx_sweep.py")

    common = ["--bin", bin_, "--gpu", gpu, "--driver", drv, "--ecc", "off",
              "--device-selector", sel, "--sycl-path", sycl, "--outdir", out]

    def bench(tag, model, quant, ncmoe, reps, est):
        argv = [py, "-u", xb, "--model", os.path.join(models, model), "--tag", tag,
                "--backend", "SYCL", "--quant", quant, "--reps", str(reps),
                "--pp", "512", "--tg", "128"] + common + \
               ["--", "-ngl", "999", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0",
                "-ncmoe", str(ncmoe)]
        return q.run(tag, argv, timeout=est, note="%s · ncmoe=%d · r=%d" % (quant, ncmoe, reps))

    # B1 头条基线：Q4_0 全驻留。B60 装得下是核心假设；B65/B70 之间这才是同条件对比
    bench("%s-q4-0-base" % card, MODEL_35B, "Q4_0", 0, 3, 2400)
    # B2 拐点：装得下时 0 应该最优，扫一遍确认（B60 的形态预期与 B50 相反）
    bench("%s-q4-0-ncmoe8" % card, MODEL_35B, "Q4_0", 8, 1, 1800)
    # B3 小档全驻留：给「换小模型不提速」这条曲线补端点
    for quant, fn, gib in cfg["quants"]:
        if quant == "Q4_0":
            continue
        bench("%s-%s-base" % (card, quant.lower().replace("_", "")), fn, quant, 0, 1, 1800)
    # B4 上下文天花板：分配不花钱、填满才花钱
    if Path(os.path.join(models, MODEL_35B)).exists():
        logs = REPO / "bench" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        # 基线差集：跑前就已是废档的文件（含已标 discarded 的历史负结果）不算，
        # 跑完后**新出现**的废档才算本次失败。ctx_sweep 内部各档 load_failed 也
        # 照样返回 0，不查这一下就会把环境错误记成 ok 并跳过（B60 首轮实测踩过）。
        pre_bad = ctx_bad_files(card)

        def _verify():
            new = sorted(ctx_bad_files(card) - pre_bad)
            return ("产出 %d 条非 ok：%s" % (len(new), ", ".join(new[:4]))) if new else None

        q.run("%s-ctx" % card,
              [py, "-u", ctx, "--bin", bin_, "--model", os.path.join(models, MODEL_35B),
               "--quant", "Q4_0", "--gpu", gpu, "--driver", drv, "--ecc", "off",
               "--device-selector", sel, "--sycl-path", sycl, "--ncmoe", "0",
               "--outdir", out, "--logdir", str(logs), "--tag", "%s-ctx" % card,
               # 平台身份（T-20 必填）：这些值必须来自实测，不能照规格表编
               "--slot", "CPU 直连槽",
               "--chip", env("ARC_CHIP", ""), "--subsys", env("ARC_SUBSYS", ""),
               "--vbios", env("ARC_VBIOS", ""), "--vram-gib", env("ARC_VRAM_GIB", "")],
              timeout=7200, note="上下文档位扫描", verify=_verify)


def stage_c(q, card, cfg):
    """ComfyUI：视频 / 出图 / 出音乐。**时间最长**，一项一项来。"""
    need_env("ARC_BENCH_DIR", "ARC_PYTHON")
    bd, py = env("ARC_BENCH_DIR"), env("ARC_PYTHON")
    # 用户的 ComfyUI 常驻 8188：**不许抢、不许杀**。两个采集脚本都读 COMFY_PORT
    # （sweep.py 是 import bench_f_h3 拿 PORT 的），所以在这里统一设一次就够。
    os.environ.setdefault("COMFY_PORT", "8189")
    # 功耗采样器：power_lib 的解析顺序是 ARC_POWER_SAMPLER → 本目录副本 →
    # ARC_REPO/bench/harness/... 。采集目录里**没有**副本，不显式指过去就降级成
    # 「本次不记功耗」——B60 首轮 6 项全丢，而功耗墙是对客核心论据，不能省。
    os.environ.setdefault("ARC_POWER_SAMPLER",
                          str(REPO / "bench" / "harness" / "power_sampler.py"))
    h3 = os.path.join(bd, "bench_f_h3.py")
    sw = os.path.join(bd, "sweep.py")
    needle = cfg["needle"]

    def h3run(tag, w, h, dur, steps, fresh, cached, est):
        q.run(tag, [py, "-u", h3, "--tag", tag, "--expect-card", needle,
                    "--width", str(w), "--height", str(h), "--duration", str(dur),
                    "--steps", str(steps), "--fresh", str(fresh), "--cached", str(cached)],
              timeout=est, note="H3 %dx%d · %ss · %d 步" % (w, h, dur, steps))

    # C1 固定工作负载：864×480 · 5 s · 6 步 —— 与 B50/B70 那批同条件
    h3run("%s-h3-864x480" % card, 864, 480, 5.0, 6, 1, 1, 3600)
    # C2 分辨率抽测：容量更大的卡看上限，B65 预期与 B70 一致
    h3run("%s-h3-1280x720" % card, 1280, 720, 5.0, 6, 1, 1, 7200)
    if card in ("b60", "b65"):
        h3run("%s-h3-1920x1088" % card, 1920, 1088, 5.0, 6, 1, 1, 14400)

    # C3 出图：Qwen-Image 2.1 int8（三卡都有对照），Krea-2 int8
    q.run("%s-img-q21-int8" % card,
          [py, "-u", sw, "--only", "q21", "--quant", "int8_convrot",
           "--expect-card", needle, "--suffix", card, "--resolution", "1280x720"],
          timeout=7200, note="Qwen-Image 2.1 int8 · 1280x720")
    q.run("%s-img-krea2-int8" % card,
          [py, "-u", sw, "--only", "krea2", "--quant", "int8_convrot",
           "--expect-card", needle, "--suffix", card],
          timeout=7200, note="Krea-2 Turbo int8 · 1024x1024")
    # C4 出音乐：TE 档位看容量（≥31 GiB 可用 bf16 TE，24 GB 档要 int8）
    te = "bf16" if cfg["vram"][1] > 31 else "int8_convrot"
    q.run("%s-audio-music3" % card,
          [py, "-u", sw, "--only", "music3", "--quant", "int8_convrot",
           "--music-te", te, "--expect-card", needle, "--suffix", card],
          timeout=7200, note="Music 3 · 120 s · TE=%s" % te)


def stage_d(q, card):
    """归档：只打印，不执行。迁移器重跑会覆盖取证字段，必须人看。"""
    print("\n" + "#" * 78)
    print("# D 归档清单（**不自动执行**）")
    print("#" * 78)
    print("""
0) 🔴 **先把这张卡的身份登记进迁移器，再迁数据**（不登记 → 迁移时硬失败，
   这是设计上的保护，但也意味着白跑一遍）：
     ① `python bench/harness/gpu_identity.py` 读**真实的** chip DEV / SUBSYS / VBIOS
     ② `migrate_comfy_media.py` 的 `CARDS`（按型号加一项，chip/subsys/device_id 照抄实测值）
     ③ `SUFFIX_CARD` / `MARK_STACK`（若 tag 用组合后缀）
     ④ `annotate_comfy_evidence.py` 的 `CARD_LOG_KEYS`（卡型 → 日志文件名）
   ⚠️ **不许照规格表编 DEV/SUBSYS** —— 猜错会让整批记录带上别人的身份。

1) 先把源 jsonl / server 日志的位置对清楚（采集目录：%s）
     ls <采集目录>/_bench_f/*%s*  <采集目录>/_bench_f/server_*%s*.log

2) 迁移器**一次只迁这一批的新文件**，别整目录重跑：
     ls bench/data/*.json | wc -l          # 先记下当前条数
     python bench/harness/migrate_comfy.py --help
     python bench/harness/migrate_comfy_media.py --help
   ⚠️ 重跑会抹掉 annotate 回填的 timing_breakdown / log_evidence / env.env_evidence
      → 迁移前先整目录备份 bench/data。

3) 取证回填（三个域都要给 `--logdir`）：
     python bench/harness/annotate_comfy_evidence.py --data bench/data \\
         --logdir "b70=<B70 日志目录>" --logdir "%s=<%s 日志目录>"

4) 审计 + 台账：
     python bench/harness/registry_audit.py
     更新 docs/test-registry.md §1 状态 / §2 矩阵 / §3 数量，再改 README 的表。

5) 发布：docs/publish-checklist.md
""" % (env("ARC_BENCH_DIR", "<ARC_BENCH_DIR>"), card, card, card, card.upper()))


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="新卡到手后的整条跑测队列")
    ap.add_argument("--card", required=True, choices=sorted(CARDS))
    ap.add_argument("--stages", default="A,B,C,D",
                    help="逗号分隔：A 体检 / B llama.cpp / C ComfyUI / D 归档清单")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不执行、不记状态")
    ap.add_argument("--force", action="store_true", help="忽略已完成标记，全部重跑")
    a = ap.parse_args()

    card = a.card
    cfg = CARDS[card]
    stages = [s.strip().upper() for s in a.stages.split(",") if s.strip()]

    if a.force and STATE.exists() and not a.dry_run:
        st = json.loads(STATE.read_text(encoding="utf-8"))
        st.pop(card, None)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[force] 已清掉 %s 的完成标记" % card)

    py = env("ARC_PYTHON") or sys.executable
    print("卡：%s（%s）  解释器：%s  模式：%s"
          % (card.upper(), cfg["needle"], py, "dry-run" if a.dry_run else "真跑"))
    print("显卡规格：%d GB/s · %d INT8 TOPS · TBP %d W" % (cfg["bw"], cfg["toks"], cfg["tbp"]))

    q = Queue(card, a.dry_run)

    if "A" in stages:
        stage_a(q, card, cfg, py)
    if "B" in stages:
        stage_a_light(q, card, cfg, py)
        stage_b(q, card, cfg, py)
    if "C" in stages:
        stage_c(q, card, cfg)
    if "D" in stages:
        stage_d(q, card)

    q.summary()


def stage_a_light(q, card, cfg, py):
    """B/C 阶段开跑前的轻量守卫：只断言型号，不重复打印整张体检表。

    ⚠️ **绝不能在这里设 `ONEAPI_DEVICE_SELECTOR=opencl:0`**：ComfyUI 侧
    （`card_guard.pin_and_verify` → `torch.xpu`）走的是 **Level Zero**，
    而 `opencl:0` 会把 Level Zero 设备数清零 —— 实测现象就是
    `[卡型守卫] 没枚举到任何 XPU 设备`（llama.cpp 不受影响，因为它用的是
    OpenCL 后端，所以同一个环境变量下 B 阶段全过、C 阶段全挂）。
    llama.cpp 的 selector 由 `xpu_bench.py --device-selector` 单独传给
    llama-bench，不依赖进程环境。
    """
    devs, err = xpu_enum(py)
    if devs is None:
        sys.exit("[guard] 枚举失败：%s" % err)
    hit = [d for d in devs if cfg["needle"].upper() in d["name"].upper()]
    if not hit:
        sys.exit("[guard] ❌ 在位没有 %s（%s）—— 拒绝开跑"
                 % (cfg["needle"], ", ".join(d["name"] for d in devs)))
    if len(devs) > 1:
        idx = devs.index(hit[0])
        os.environ["ONEAPI_DEVICE_SELECTOR"] = "level_zero:%d" % idx
        print("[guard] 双卡在机 → ONEAPI_DEVICE_SELECTOR=level_zero:%d（%s）"
              % (idx, hit[0]["name"]))
    else:
        # 单卡：清掉可能污染 Level Zero 枚举的 OpenCL selector
        os.environ.pop("ONEAPI_DEVICE_SELECTOR", None)
    print("[guard] ✅ 型号核对通过：%s %.2f GiB" % (hit[0]["name"], hit[0]["gib"]))


if __name__ == "__main__":
    main()
