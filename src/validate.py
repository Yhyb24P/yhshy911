"""验证体系（model.md §14）。

1. Q1 温度场 Bessel 半解析基准（常 T_a）+ Duhamel 时变参考解（§14.1）；
2. Q3/Q4 的网格收敛与时间步收敛（§14.2）；
3. 输入单位、物性正性和场分布软检查（§14.3）；
4. 长时热场拟稳态后验检查（§14.4）。
"""
import os

import numpy as np
from scipy.optimize import brentq
from scipy.special import j0, j1

from props import DryingRoom, Radius, R0, T0, HT, k1, theta
from solver import FVMSolver, integrate_to_event, map_to_physical, surface_from_state
from utils import atomic_json_dump, input_signature

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALPHA1 = k1(0.0) / (820.0 * 2600.0)   # Q1 热扩散系数 ≈1.69e-7 m²/s


def _signature(settings):
    return input_signature([
        __file__, os.path.join(ROOT, "src/solver.py"),
        os.path.join(ROOT, "src/props.py"),
        os.path.join(ROOT, "data/附件1.xlsx"), os.path.join(ROOT, "data/附件2.xlsx"),
    ], settings=settings)


class ConstRoom:
    """常温度环境（半解析基准用）。"""

    def __init__(self, Ta=50.0, Ca=0.05):
        self._Ta, self._Ca = Ta, Ca

    def Ta(self, t):
        return self._Ta

    def Ca(self, t):
        return self._Ca


class PlatformMoistureRoom(DryingRoom):
    """仅替换 4 h 后水分势的平台值，温度输入保持不变。"""

    def __init__(self, path, Ca_after):
        super().__init__(path)
        self.Ca_after = float(Ca_after)

    def Ca(self, t):
        a = np.asarray(t, dtype=float)
        measured = np.interp(a, self.times, self.Ca_data)
        out = np.where(a <= self.times[-1], measured, self.Ca_after)
        return float(out) if out.ndim == 0 else out


def eigenvalues(Bi, n_modes):
    """Robin 圆柱特征值：λJ_1(λ) = Bi·J_0(λ)（model.md §14.1）。"""
    f = lambda L: L * j1(L) - Bi * j0(L)
    grid = np.linspace(1e-4, np.pi * (n_modes + 2), 20000)
    fv = f(grid)
    roots, prev = [], fv[0]
    for i in range(1, len(grid)):
        if fv[i] * prev < 0:
            roots.append(brentq(f, grid[i - 1], grid[i]))
        prev = fv[i]
        if len(roots) == n_modes:
            break
    return np.array(roots)


def bessel_T_const(Ta, t, r, n_modes=300):
    """Q1 常温度 T_a 的半解析解（§14.1）。

    T(r,t) = Ta + Σ_n A_n J_0(λ_n r/R0) e^{−α λ_n² t/R0²}，
    A_n = 2(T0−Ta)J_1(λ_n)/[λ_n(J_0(λ_n)²+J_1(λ_n)²)]（Robin 归一化）。
    """
    Bi = HT * R0 / k1(0.0)
    lam = eigenvalues(Bi, n_modes)
    C = 2.0 * (T0 - Ta) * j1(lam) / (lam * (j0(lam)**2 + j1(lam)**2))
    r = np.atleast_1d(np.asarray(r, dtype=float))
    J = j0(np.outer(lam, r / R0))          # (n_modes, n_r)
    decay = np.exp(-ALPHA1 * lam**2 * t / R0**2)
    return Ta + J.T @ (C * decay)


def duhamel_T(room, t_eval, r, n_modes=300):
    """Q1 时变 T_a(t) 的 Duhamel 叠加参考解（§14.1）。

    w = T − T_a(t) 满足 w_t = α∇²w − T_a'(t)，Robin 齐次边界；
    均匀源项的分段常数斜率解析卷积。
    """
    Bi = HT * R0 / k1(0.0)
    lam = eigenvalues(Bi, n_modes)
    beta = ALPHA1 * lam**2 / R0**2
    # Robin 归一化：均匀初值/均匀源项投影系数 2J_1(λ_n)/[λ_n(J_0²+J_1²)]
    norm = j0(lam)**2 + j1(lam)**2
    C0 = 2.0 * (T0 - room.Ta(0.0)) * j1(lam) / (lam * norm)
    A = 2.0 * j1(lam) / (lam * norm)
    r = np.atleast_1d(np.asarray(r, dtype=float))
    J = j0(np.outer(lam, r / R0))
    seg_t, seg_Ta = room.times, room.Ta_data
    slopes = np.diff(seg_Ta) / np.diff(seg_t)
    out = np.empty((len(np.atleast_1d(t_eval)), len(r)))
    for i, t in enumerate(np.atleast_1d(t_eval)):
        t = float(t)
        term0 = J.T @ (C0 * np.exp(-beta * t))
        tau_end = np.minimum(seg_t[1:], t)
        dtau = np.clip(tau_end - seg_t[:-1], 0.0, None)
        # 分段常数斜率的解析卷积：w[n, j] 为模态 n 在第 j 段的贡献
        w = np.where(dtau[None, :] > 0,
                     (-slopes[None, :])
                     * np.exp(-beta[:, None] * (t - tau_end[None, :]))
                     * (1 - np.exp(-beta[:, None] * dtau[None, :]))
                     / beta[:, None],
                     0.0)
        out[i] = room.Ta(t) + term0 + J.T @ (A * w.sum(axis=1))
    return out


def check_bessel(N=81):
    print("== §14.1 Q1 温度场半解析基准 ==")
    r = np.array([0.0, 0.005, 0.01, 0.015, 0.02])
    s = FVMSolver(1, ConstRoom(50.0), N=N)
    for t_chk in (60.0, 300.0, 1800.0):
        s.advance_to(t_chk)
        T_num, _, _ = s.sample(r)
        err = np.abs(T_num - bessel_T_const(50.0, t_chk, r)).max()
        print(f"  常 T_a=50:  t={t_chk:>6.0f} s   max|T_num−T_ref| = {err:.3e} °C")

    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    s2 = FVMSolver(1, room, N=N)
    for t_chk in (60.0, 300.0, 1800.0):
        s2.advance_to(t_chk)
        T_num, _, _ = s2.sample(r)
        err = np.abs(T_num - duhamel_T(room, np.array([t_chk]), r)[0]).max()
        print(f"  时变 T_a:   t={t_chk:>6.0f} s   max|T_num−T_Duhamel| = {err:.3e} °C")


def _event_run(q, N=81, dt_cap=60.0, quasi_steady_T=False,
               event_interval=None):
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    radius = Radius(os.path.join(ROOT, "data/附件2.xlsx")) if q == 4 else None
    s = FVMSolver(q, room, N=N, radius=radius, dt_cap=dt_cap,
                  quasi_steady_T=quasi_steady_T)
    if event_interval is None:
        return integrate_to_event(s, 60.0, log_every_s=0.0)

    # 正式 Q2 每 1 s 调用一次 advance_to 并随即检查事件。验证时复现完全
    # 相同的时间线，但只在 60 s 时刻保留场，避免保存约 20 万个状态。
    if 60 % event_interval != 0:
        raise ValueError("60 s 输出间隔必须是事件检查间隔的整数倍")
    times, Ts, Xs = [], [], []
    k = 0
    while True:
        k += 1
        t_next = event_interval * k
        lo_solver = s.clone()
        s.advance_to(t_next)
        if s.g() <= 0.0:
            t_dry, T_ev, X_ev = s.refine_event(lo_solver, t_next)
            return times, Ts, Xs, t_dry, T_ev, X_ev
        if abs(t_next / 60.0 - round(t_next / 60.0)) < 1e-10:
            times.append(t_next)
            Ts.append(s.T.copy())
            Xs.append(s.X.copy())


CHECK_TIMES = (1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800)


def _sample_fields(q, times, Ts, Xs):
    """在共同时间和归一化半径上采样，供不同离散方案直接比较。"""
    by_time = {int(t): k for k, t in enumerate(times)}
    xi = np.linspace(0.0, 1.0, 21)
    Trows, Xrows = [], []
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    radius = Radius(os.path.join(ROOT, "data/附件2.xlsx")) if q == 4 else None
    for t in CHECK_TIMES:
        if t in by_time:
            k = by_time[t]
            R = R0 if radius is None else float(radius(t))
            Trow = map_to_physical(Ts[k], xi * R, R)
            Xrow = map_to_physical(Xs[k], xi * R, R)
            Trow[-1], Xrow[-1] = surface_from_state(q, room, t, Ts[k], Xs[k], R)
            Trows.append(Trow)
            Xrows.append(Xrow)
    return np.asarray(Trows), np.asarray(Xrows)


def check_inputs():
    print("== 输入单位与半径连续性 ==")
    radius = Radius(os.path.join(ROOT, "data/附件2.xlsx"))
    t = np.linspace(0.0, 259200.0, 1001)
    R = radius(t)
    ok = abs(float(radius(0.0)) - 0.02) < 1e-12 and np.all(np.diff(R) <= 1e-12)
    print(f"  R(0)={float(radius(0.0)):.5f} m, R(72h)={float(radius(259200.0)):.5f} m, 单调连续={ok}")
    if not ok:
        raise AssertionError("附件 2 半径单位或插值不正确")


def grid_convergence(Ns=(81, 161, 321), questions=(3, 4)):
    print("== §14.2 网格收敛 ==")
    res = {}
    for q in questions:
        res[q] = {}
        previous = None
        previous_event = None
        for N in Ns:
            # Q3 正式结果由 model2 在默认 dt_cap=60 s 下逐秒调用
            # advance_to 并逐秒括区。验证复现同一配置，只把场输出抽稀。
            kwargs = {"event_interval": 1.0} if q == 3 else {}
            times, Ts, Xs, t_dry, _Tev, _Xev = _event_run(q, N=N, **kwargs)
            res[q][N] = t_dry
            print(f"  Q{q} N={N:>3d}: t_dry={t_dry:12.2f} s = {t_dry/3600:8.3f} h")
            fields = _sample_fields(q, times, Ts, Xs)
            if previous is not None:
                dT = np.max(np.abs(fields[0] - previous[0]))
                dX = np.max(np.abs(fields[1] - previous[1]))
                dt_event = t_dry - previous_event
                print(f"       与上一网格差：Δt_dry={dt_event:+.2f} s, "
                      f"max|ΔT|={dT:.3e} °C, max|ΔX|={dX:.3e}")
            previous = fields
            previous_event = t_dry
    return res


def boundary_potential_check(Ns=(81, 161, 321), levels=(0.03, 0.05, 0.07)):
    """检查长期环境水分势变化时的场排序和终止时间（P0）。

    非线性 D(X,T) 可能形成低扩散率干燥表层，因此本检查同时报告全场与
    中心的交叉，不把预期单调性直接写成会掩盖现象的硬断言。
    """
    print("== P0 长期环境水分势排序诊断 ==")
    path = os.path.join(ROOT, "data/附件1.xlsx")
    result = {}
    for N in Ns:
        runs = {}
        for Ca in levels:
            room = PlatformMoistureRoom(path, Ca)
            s = FVMSolver(2, room, N=N)
            runs[Ca] = integrate_to_event(s, 60.0, log_every_s=0.0)
            print(f"  N={N:>3d}, C_a={Ca:.3f}: t_dry={runs[Ca][3]:.2f} s")
        pairs = {}
        for low, high in zip(levels[:-1], levels[1:]):
            lo, hi = runs[low], runs[high]
            n = min(len(lo[2]), len(hi[2]))
            diff = np.asarray(lo[2][:n]) - np.asarray(hi[2][:n])
            center = diff[:, 0]
            crossed = np.flatnonzero(center > 1e-10)
            key = f"{low:.3f}_vs_{high:.3f}"
            pairs[key] = {
                "max_low_minus_high": float(diff.max()),
                "max_center_low_minus_high": float(center.max()),
                "first_center_crossing_s": (None if not len(crossed)
                                             else float(lo[0][crossed[0]])),
            }
            print(f"       {low:.3f}≤{high:.3f}: max(X_low−X_high)={diff.max():.3e}, "
                  f"中心最大差={center.max():.3e}, "
                  f"中心首次交叉={pairs[key]['first_center_crossing_s']}")
        result[str(N)] = {
            "t_dry": {str(Ca): float(runs[Ca][3]) for Ca in levels},
            "pairs": pairs,
        }

    # 固定 D 的控制组用于核对 Robin 符号和离散矩阵。若控制组保持排序而
    # 非线性组发生交叉，交叉来自 D(X) 的干燥表层反馈，而非环境势方向写反。
    control_N, D0 = 41, 3.6e-9
    control_runs = {}
    for Ca in levels:
        room = PlatformMoistureRoom(path, Ca)
        s = FVMSolver(2, room, N=control_N, quasi_steady_T=True)
        s.p = dict(s.p)
        s.p["D"] = lambda X, Th, value=D0: np.zeros_like(
            np.asarray(X, dtype=float)) + value
        control_runs[Ca] = integrate_to_event(s, 60.0, log_every_s=0.0)
    control_pairs = {}
    for low, high in zip(levels[:-1], levels[1:]):
        lo, hi = control_runs[low], control_runs[high]
        n = min(len(lo[2]), len(hi[2]))
        max_diff = float((np.asarray(lo[2][:n]) - np.asarray(hi[2][:n])).max())
        control_pairs[f"{low:.3f}_vs_{high:.3f}"] = max_diff
    result["constant_D_control"] = {
        "N": control_N,
        "D": D0,
        "t_dry": {str(Ca): float(control_runs[Ca][3]) for Ca in levels},
        "max_low_minus_high": control_pairs,
    }
    print(f"  固定 D={D0:.2e} 控制组："
          + ", ".join(f"C_a={Ca:.3f}→{control_runs[Ca][3]:.2f}s" for Ca in levels))
    print("       排序最大违例：" + ", ".join(
        f"{pair}={value:.3e}" for pair, value in control_pairs.items()))
    return result


def _q1_surface_values(N, dt_cap, times=(1.0, 10.0, 100.0, 1800.0)):
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    s = FVMSolver(1, room, N=N, dt_cap=dt_cap)
    values = []
    for t in times:
        s.advance_to(t)
        values.append(s.surface()[1])
    return np.asarray(values)


def q1_surface_convergence(Ns=(161, 321, 641),
                           dt_caps=(1.0, 0.5, 0.25),
                           times=(1.0, 10.0, 100.0, 1800.0)):
    """Q1 初始水分边界层的表面值空间/时间收敛（P0）。"""
    print("== P0 Q1 水分表面收敛 ==")
    spatial = {N: _q1_surface_values(N, min(dt_caps), times) for N in Ns}
    temporal = {dt: _q1_surface_values(max(Ns), dt, times) for dt in dt_caps}
    for N, values in spatial.items():
        print(f"  空间 N={N:>3d}, Δt_max={min(dt_caps):g} s: "
              + ", ".join(f"X_s({t:g}s)={v:.8f}" for t, v in zip(times, values)))
    for left, right in zip(Ns[:-1], Ns[1:]):
        print(f"       N={left}→{right}: max|ΔX_s|="
              f"{np.max(np.abs(spatial[right]-spatial[left])):.3e}")
    for dt, values in temporal.items():
        print(f"  时间 N={max(Ns)}, Δt_max={dt:g} s: "
              + ", ".join(f"X_s({t:g}s)={v:.8f}" for t, v in zip(times, values)))
    for coarse, fine in zip(dt_caps[:-1], dt_caps[1:]):
        print(f"       Δt={coarse:g}→{fine:g} s: max|ΔX_s|="
              f"{np.max(np.abs(temporal[fine]-temporal[coarse])):.3e}")
    return {
        "times_s": list(times),
        "spatial": {str(N): values.tolist() for N, values in spatial.items()},
        "temporal": {str(dt): values.tolist() for dt, values in temporal.items()},
    }


def q1_initial_surface_convergence(Ns=(641, 1281, 2561),
                                   dt_caps=(0.25, 0.125, 0.0625,
                                            0.03125, 0.015625)):
    """只针对 t=1 s 的深度加密，确定 Q1 正式生产离散。"""
    print("== P0 Q1 t=1 s 表面深度加密 ==")
    spatial = {N: float(_q1_surface_values(N, 0.03125, (1.0,))[0]) for N in Ns}
    temporal = {dt: float(_q1_surface_values(max(Ns), dt, (1.0,))[0])
                for dt in dt_caps}
    print("  空间：" + ", ".join(f"N={N}→{v:.8f}" for N, v in spatial.items()))
    print("  时间：" + ", ".join(f"Δt={dt:g}→{v:.8f}" for dt, v in temporal.items()))
    return {
        "time_s": 1.0,
        "spatial_dt_cap_s": 0.03125,
        "spatial": {str(k): v for k, v in spatial.items()},
        "temporal_N": max(Ns),
        "temporal": {str(k): v for k, v in temporal.items()},
    }


def p0_validation():
    result = {
        "signature": _signature(("p0", (81, 161, 321), (161, 321, 641),
                                  (641, 1281, 2561))),
        "boundary_potential": boundary_potential_check(),
        "q1_surface": q1_surface_convergence(),
        "q1_t1_deep": q1_initial_surface_convergence(),
    }
    path = os.path.join(ROOT, "results/tables/p0_validation.json")
    atomic_json_dump(result, path)
    print(f"[P0] 写入 {path}")
    return result


def time_convergence(dt_caps=(60.0, 30.0, 15.0), questions=(3, 4), N=81):
    print("== §14.2 时间步收敛 ==")
    res = {}
    for q in questions:
        res[q] = {}
        previous = None
        for dt_cap in dt_caps:
            times, Ts, Xs, t_dry, _Tev, _Xev = _event_run(q, N=N, dt_cap=dt_cap)
            res[q][dt_cap] = t_dry
            print(f"  Q{q} Δt_max={dt_cap:>4.0f} s: t_dry={t_dry:12.2f} s")
            fields = _sample_fields(q, times, Ts, Xs)
            if previous is not None:
                dT = np.max(np.abs(fields[0] - previous[0]))
                dX = np.max(np.abs(fields[1] - previous[1]))
                print(f"       与上一时间步公共场值差：max|ΔT|={dT:.3e} °C, max|ΔX|={dX:.3e}")
            previous = fields
    return res


def soft_checks(N=81, questions=(2, 4)):
    print("== §14.3 物理一致性软检查 ==")
    for q in questions:
        times, Ts, Xs, t_dry, Tev, Xev = _event_run(q, N=N)
        s_room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
        Xseq = Xs + [Xev]
        Tseq = Ts + [Tev]
        radius = Radius(os.path.join(ROOT, "data/附件2.xlsx")) if q == 4 else None
        sample_times = list(times) + [t_dry]
        surfaces = [surface_from_state(q, s_room, t, T, X,
                                       R0 if radius is None else float(radius(t)))
                    for t, T, X in zip(sample_times, Tseq, Xseq)]
        Tsurf = [v[0] for v in surfaces]
        Xsurf = [v[1] for v in surfaces]
        Xmin = min(min(float(x.min()) for x in Xseq), min(Xsurf))
        Tmin = min(min(float(x.min()) for x in Tseq), min(Tsurf))
        Tmax = max(max(float(x.max()) for x in Tseq), max(Tsurf))
        p = FVMSolver(q, s_room, N=N).p
        positive = all(np.all(p["k"](x) > 0) and np.all(p["D"](x, theta(T)) > 0)
                       for T, x in zip(Tseq[::50], Xseq[::50]))
        viol = sum(xs > X[-1] + 1e-9 or X[-1] > X[0] + 1e-9
                   or np.any(np.diff(X) > 1e-9)
                   for X, xs in zip(Xseq[::50], Xsurf[::50]))
        in_T_bounds = Tmin >= T0 - 1e-8 and Tmax <= max(s_room.Ta_data) + 1e-6
        print(f"  Q{q}: X_min={Xmin:.4f}, k/D>0={positive}, 温度范围=[{Tmin:.3f},{Tmax:.3f}] 合理={in_T_bounds}, 剖面违例={viol}")
        if Xmin < 0 or not positive or not in_T_bounds:
            raise AssertionError(f"Q{q} 物理一致性检查失败")


def quasi_steady_check(N=81, t_check=86400.0):
    print("== §14.4 长时热场拟稳态后验检查 ==")
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    for q in (2, 4):
        radius = Radius(os.path.join(ROOT, "data/附件2.xlsx")) if q == 4 else None
        s = FVMSolver(q, room, N=N, radius=radius)
        s.advance_to(t_check)
        err = float(np.max(np.abs(s.T - room.Ta(t_check))))
        spread = float(s.T.max() - s.T.min())
        print(f"  Q{q} t={t_check/3600:.0f} h: max|T−T_a|={err:.3e} °C, 径向极差={spread:.3e} °C")
        full = _event_run(q, N=N)
        reduced = _event_run(q, N=N, quasi_steady_T=True)
        dt_event = reduced[3] - full[3]
        common = min(len(full[0]), len(reduced[0]))
        dX = max(np.max(np.abs(full[2][k] - reduced[2][k]))
                 for k in range(0, common, 60))
        print(f"       T≈T_a 降阶对照：Δt_dry={dt_event:.2f} s, 抽样 max|ΔX|={dX:.3e}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-grid", action="store_true", help="跳过网格收敛（耗时较长）")
    ap.add_argument("--skip-time", action="store_true", help="跳过时间步收敛（耗时较长）")
    ap.add_argument("--include-641", action="store_true", help="网格收敛额外计算 N=641")
    ap.add_argument("--p0", action="store_true", help="追加水分势排序与 Q1 表面收敛诊断")
    ap.add_argument("--p0-only", action="store_true", help="只运行两项 P0 专项诊断")
    ap.add_argument("--grid-only", action="store_true", help="只运行事件时间空间收敛")
    ap.add_argument("--time-only", action="store_true", help="只运行事件时间步收敛")
    args = ap.parse_args()
    if args.p0_only:
        p0_validation()
    elif args.grid_only:
        Ns = (81, 161, 321, 641) if args.include_641 else (81, 161, 321)
        values = grid_convergence(Ns=Ns)
        path = os.path.join(ROOT, "results/tables/grid_convergence.json")
        atomic_json_dump({"signature": _signature(("grid", Ns)),
                          "t_dry_s": values}, path)
        print(f"[grid] 写入 {path}")
    elif args.time_only:
        values = time_convergence()
        path = os.path.join(ROOT, "results/tables/time_convergence.json")
        atomic_json_dump({"signature": _signature(("time", (60.0, 30.0, 15.0), 81)),
                          "t_dry_s": values}, path)
        print(f"[time] 写入 {path}")
    else:
        check_inputs()
        check_bessel()
        soft_checks()
        quasi_steady_check()
        if not args.skip_grid:
            grid_convergence(Ns=(81, 161, 321, 641) if args.include_641
                             else (81, 161, 321))
        if not args.skip_time:
            time_convergence()
        if args.p0:
            p0_validation()
