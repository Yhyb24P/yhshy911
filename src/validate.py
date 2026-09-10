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
from solver import FVMSolver, integrate_to_event, map_to_physical

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALPHA1 = k1(0.0) / (820.0 * 2600.0)   # Q1 热扩散系数 ≈1.69e-7 m²/s


class ConstRoom:
    """常温度环境（半解析基准用）。"""

    def __init__(self, Ta=50.0, Ca=0.05):
        self._Ta, self._Ca = Ta, Ca

    def Ta(self, t):
        return self._Ta

    def Ca(self, t):
        return self._Ca


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


def _event_run(q, N=81, dt_cap=60.0, quasi_steady_T=False):
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    radius = Radius(os.path.join(ROOT, "data/附件2.xlsx")) if q == 4 else None
    s = FVMSolver(q, room, N=N, radius=radius, dt_cap=dt_cap,
                  quasi_steady_T=quasi_steady_T)
    return integrate_to_event(s, 60.0, log_every_s=0.0)


CHECK_TIMES = (1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800)


def _sample_fields(times, Ts, Xs):
    """在共同时间和归一化半径上采样，供不同离散方案直接比较。"""
    by_time = {int(t): k for k, t in enumerate(times)}
    xi = np.linspace(0.0, 1.0, 21)
    Trows, Xrows = [], []
    for t in CHECK_TIMES:
        if t in by_time:
            k = by_time[t]
            Trows.append(map_to_physical(Ts[k], xi, 1.0))
            Xrows.append(map_to_physical(Xs[k], xi, 1.0))
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
        for N in Ns:
            times, Ts, Xs, t_dry, _Tev, _Xev = _event_run(q, N=N)
            res[q][N] = t_dry
            print(f"  Q{q} N={N:>3d}: t_dry={t_dry:12.2f} s = {t_dry/3600:8.3f} h")
            fields = _sample_fields(times, Ts, Xs)
            if previous is not None:
                dT = np.max(np.abs(fields[0] - previous[0]))
                dX = np.max(np.abs(fields[1] - previous[1]))
                print(f"       与上一网格公共场值差：max|ΔT|={dT:.3e} °C, max|ΔX|={dX:.3e}")
            previous = fields
    return res


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
            fields = _sample_fields(times, Ts, Xs)
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
        Xsurf = [1.5 * x[-1] - 0.5 * x[-2] for x in Xseq]
        Tsurf = [1.5 * T[-1] - 0.5 * T[-2] for T in Tseq]
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
    args = ap.parse_args()
    check_inputs()
    check_bessel()
    soft_checks()
    quasi_steady_check()
    if not args.skip_grid:
        grid_convergence()
    if not args.skip_time:
        time_convergence()
