"""参数与边界假设的敏感性/情景分析（model.md §15）。

对烘干终止时刻 t_dry^(3) 计算弹性 S_p = (Δt_dry/t_dry)/(Δp/p)：
1. h_T：0.8 / 1.0 / 1.2 倍基准（§15.1）；
2. h_m：0.5 / 1.0 / 1.5 / 2.0 倍基准（§15.1）；
3. 4 h 后平台外拓：T_a 与 C_a 分别扰动，并给出冷湿/热干联合情景（§15.3）。

每个情景从 t=0 独立求解 Q2（附录 3，固定半径），用 60 s 采样积分到
X_max 首次低于 0.15 的连续事件时刻。结果写 results/tables/q_sens.json。
不预设哪个参数更敏感，由结果判断（§15）。
"""
import json
import os
import time as _time

from props import DryingRoom, Radius, HT, HM
from solver import FVMSolver, integrate_to_event

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results/tables/q_sens.json")
N = 81


def t_dry_for(hT, hM, room):
    s = FVMSolver(2, room, N=N, hT=hT, hM=hM)
    _, _, _, t_dry, _, _ = integrate_to_event(s, 60.0, log_every_s=0.0)
    return t_dry


def t_dry_q4(radius):
    """Q4（附录 4）终止时刻；radius=None 即 Q4-Fixed（R≡R0，§10.7 反事实）。"""
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    s = FVMSolver(4, room, N=N, radius=radius)
    _, _, _, t_dry, _, _ = integrate_to_event(s, 60.0, log_every_s=0.0)
    return t_dry


def elasticity(t_var, t_base, p_var, p_base):
    return (t_var - t_base) / t_base / ((p_var - p_base) / p_base)


def run():
    t0 = _time.time()
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))

    # 基准情景（h_T=HT, h_m=HM, 原平台值）
    t_base = t_dry_for(HT, HM, room)
    print(f"[sens] 基准 t_dry^(3) = {t_base:.1f} s = {t_base/3600:.2f} h")

    res = {"N": N, "t_base": t_base, "hT": {}, "hm": {}, "platform": {}}

    # 1. h_T 弹性（§15.1）
    for f in (0.8, 1.0, 1.2):
        t = t_base if f == 1.0 else t_dry_for(f * HT, HM, room)
        res["hT"][f] = t
        s = "基准" if f == 1.0 else f"S_hT={elasticity(t, t_base, f*HT, HT):+.3f}"
        print(f"  h_T x{f:.1f}: t_dry={t:.1f} s  {s}")

    # 2. h_m 弹性（§15.1）
    for f in (0.5, 1.0, 1.5, 2.0):
        t = t_base if f == 1.0 else t_dry_for(HT, f * HM, room)
        res["hm"][f] = t
        s = "基准" if f == 1.0 else f"S_hm={elasticity(t, t_base, f*HM, HM):+.3f}"
        print(f"  h_m x{f:.1f}: t_dry={t:.1f} s  {s}")

    # 3. 平台外拓情景（§15.3）。温度和水分势必须分别扰动；二者同倍
    # 缩放会把“升温加速”和“湿度升高减速”混在一起。摄氏温度也没有
    # 有意义的比例零点，因此温度采用 ±2 °C，而 C_a 采用 ±10%。
    for delta in (-2.0, 2.0):
        r2 = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
        r2.Ta_end += delta
        t = t_dry_for(HT, HM, r2)
        key = f"Ta_{delta:+.0f}C"
        res["platform"][key] = t
        print(f"  平台 T_a {delta:+.0f} °C: t_dry={t:.1f} s  Δt={(t-t_base)/3600:+.2f} h")
    for f in (0.9, 1.1):
        r2 = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
        r2.Ca_end *= f
        t = t_dry_for(HT, HM, r2)
        res["platform"][f"Ca_x{f:.1f}"] = t
        print(f"  平台 C_a x{f:.1f}: t_dry={t:.1f} s  S_Ca={elasticity(t, t_base, f, 1.0):+.3f}")

    for name, dT, fC in (("cool_humid", -2.0, 1.1), ("hot_dry", 2.0, 0.9)):
        r2 = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
        r2.Ta_end += dT
        r2.Ca_end *= fC
        t = t_dry_for(HT, HM, r2)
        res["platform"][name] = t
        print(f"  平台 {name}: t_dry={t:.1f} s  Δt={(t-t_base)/3600:+.2f} h")

    # 4. Q4-Fixed 反事实（§10.7）：附录 4 物性 + 固定半径 R0，隔离纯几何收缩效应
    rad = Radius(os.path.join(ROOT, "data/附件2.xlsx"))
    t_q4 = t_dry_q4(rad)          # 收缩移动域（= t_dry^(4)）
    t_q4_fixed = t_dry_q4(None)   # Q4-Fixed（R≡R0）
    res["q4"] = {"t_dry_shrink": t_q4, "t_dry_fixed": t_q4_fixed,
                 "delta_t_geom": t_q4_fixed - t_q4}
    print(f"  Q4 收缩: t_dry^(4)={t_q4:.1f} s；Q4-Fixed: {t_q4_fixed:.1f} s；"
          f"Δt_geom={t_q4_fixed - t_q4:+.1f} s（§10.7 纯几何收缩效应）")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1)
    print(f"[sens] 写入 {OUT}，耗时 {_time.time()-t0:.1f} s")
    return res


if __name__ == "__main__":
    run()
