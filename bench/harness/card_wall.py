"""认出当前在位的 Intel Arc 卡是哪一块板 —— 型号 + 显存 + 功耗墙。

为什么需要：同一个型号名底下的 AIB SKU 可以有**完全不同的功耗墙**（B60 TF 200 W / B60 BS 120 W），
而跑测脚本只能看到 torch 报的型号名，两者一模一样。功耗墙是区分它们最硬的一位数。

🔴 它读的是 `zesPowerGetProperties.defaultLimit` = **出厂默认值**，在 IGS「调优」里把限制拉高**不会改它**
（B60 BS 拉到 144 W 时这里照样报 120000）。**判「拉高有没有生效」只能看实测功率**：
关掉调优时 BS 的 P90 约 111–125 W，拉到 144 W 后 P90 到 143–144 W、峰值过 150 W。

判据（本机已确认）：
  B70 = 290000 mW · B65 = 200000 mW · B60 TF = 200000 mW · B50 = 70000 mW
  B60 BS = 120000 mW（预期，未实测）

用法：
  python card_wall.py            # 打印型号 / 显存 / 功耗墙，人读
  python card_wall.py --wall     # 只打印整卡域功耗墙（mW），给 shell 判断用
  python card_wall.py --is-bs    # 是 B60 BS 返回 0，否则返回 1

退出码：0 = 读成功 / 命中判据；1 = 读失败或不命中。
"""
import os
import sys

# sycl8.dll 在 Library\bin 下，不加 PATH 会 0xC0000135 —— 看着像模型问题
os.environ.setdefault('ZES_ENABLE_SYSMAN', '1')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def wall_mw():
    """整卡电源域的 defaultLimit（mW）。读不到返回 None。"""
    try:
        from power_sampler import enumerate_domains
    except Exception as e:
        print(f"[card_wall] import power_sampler 失败: {e}", file=sys.stderr)
        return None
    ze, handles, meta = enumerate_domains()
    if not meta or not meta.get('domains'):
        return None
    card = meta.get('card')
    for d in meta['domains']:
        if d['i'] == card:
            return d.get('default_limit_mw')
    return None


def device_name():
    try:
        import torch
        if not torch.xpu.is_available():
            return None, None
        p = torch.xpu.get_device_properties(0)
        return p.name, round(p.total_memory / 1024 ** 3, 2)
    except Exception as e:
        print(f"[card_wall] torch 读取失败: {e}", file=sys.stderr)
        return None, None


def main():
    args = sys.argv[1:]
    w = wall_mw()

    if '--wall' in args:
        print(w if w is not None else -1)
        return 0 if w is not None else 1

    name, vram = device_name()

    if '--is-bs' in args:
        hit = bool(name and 'B60' in name and w == 120000)
        print(f"{name} | {vram} GiB | wall={w} mW | is_bs={hit}")
        return 0 if hit else 1

    print(f"型号     : {name}")
    print(f"显存     : {vram} GiB")
    print(f"功耗墙   : {w} mW" if w is not None else "功耗墙   : 读取失败")
    if w is not None:
        guess = {290000: 'B70', 200000: 'B65 或 B60 TF', 120000: 'B60 BS（推断）',
                 70000: 'B50'}.get(w, '未知板')
        print(f"功耗墙判板: {guess}")
    return 0 if w is not None else 1


if __name__ == '__main__':
    sys.exit(main())
