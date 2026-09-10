"""统一有限体积求解器（model.md §13、§19）。

空间：ξ∈[0,1] 上 cell-centered FVM（Q1–Q3 取 R≡R0，Q4 取实测半径 R(t)）。
时间：Backward Euler 启动 + BDF2 主积分 + 自适应时间步（强制落 60 s 数据节点）。
非线性：Picard 迭代（物性冻结在前一迭代），低含水率末段欠松弛。
终止事件：连续监测 g(t)=X_max−0.15，穿越区间内二分定位连续时刻（model.md §13.5）。

控制方程（model.md §19，q=1..4）：
    ρ_q(X)c_{p,q}(X) T_t = 1/(R_q(t)²ξ) ∂_ξ[ξ k_q(X) T_ξ]
    X_t                  = 1/(R_q(t)²ξ) ∂_ξ[ξ D_q(X,Θ) X_ξ]
边界：T_ξ(0)=X_ξ(0)=0；
    k_q/R_q · T_ξ(1) = h_T[T_a−T_s]， −D_q/R_q · X_ξ(1) = h_m[X_s−χ_a]，χ_a=C_a。
"""
import numpy as np
from scipy.linalg.lapack import dgtsv

from props import PROPS, R0, T0, X0, HT, HM, theta


def map_to_physical(vals, r_phys, R):
    """把 cell-centered 场值 (N,) 映射到物理半径 r_phys (m)。

    轴上取值用中心单元（零梯度对称），表面用二阶外推 1.5v_N−0.5v_{N−1}；
    位于药材之外（r>R）的位置返回 NaN（model.md §17.4）。
    """
    N = len(vals)
    xi = np.asarray(r_phys, dtype=float) / R
    inside = xi <= 1.0
    nodes = np.concatenate([[0.0], (np.arange(N) + 0.5) / N, [1.0]])
    vnodes = np.concatenate([[vals[0]], vals, [1.5 * vals[-1] - 0.5 * vals[-2]]])
    return np.where(inside, np.interp(np.clip(xi, 0.0, 1.0), nodes, vnodes), np.nan)


def robin_surface_value(cell_value, gamma_cell, ambient, h, R, N):
    """由最外层单元中心值重构 Robin 边界值。

    半单元扩散阻力 δ/Γ 与表面对流阻力 1/h 串联：
        Γ(u_N-u_s)/δ = h(u_s-u_a),  δ=R/(2N)。
    该重构与最后一个控制体中的隐式边界通量完全一致。
    """
    delta = float(R) / (2.0 * N)
    gamma_cell = float(gamma_cell)
    return (gamma_cell * float(cell_value) + h * delta * float(ambient)) / (
        gamma_cell + h * delta
    )


def surface_from_state(q, room, t, T, X, R, hT=HT, hM=HM):
    """从任意历史 cell 场重构与离散 Robin 通量一致的两个表面值。"""
    p = PROPS[q]
    k_last = np.asarray(p["k"](X), dtype=float)
    D_last = np.asarray(p["D"](X, theta(T)), dtype=float)
    k_last = float(k_last if k_last.ndim == 0 else k_last[-1])
    D_last = float(D_last if D_last.ndim == 0 else D_last[-1])
    N = len(X)
    Ts = robin_surface_value(T[-1], k_last, room.Ta(t), hT, R, N)
    Xs = robin_surface_value(X[-1], D_last, room.Ca(t), hM, R, N)
    return Ts, Xs


class FVMSolver:
    def __init__(self, q, room, N=81, hT=HT, hM=HM, radius=None,
                 eps_T=1e-7, eps_X=1e-8, max_iter=100,
                 dt_init=0.5, dt_growth=1.4, dt_cap=60.0, dt_late=20.0,
                 relax_xmax=0.3, omega=0.5, quasi_steady_T=False):
        if q not in PROPS:
            raise ValueError(f"未知题号 q={q}")
        self.q, self.room, self.N = q, room, N
        self.hT, self.hM, self.radius = hT, hM, radius
        self.p = PROPS[q]
        self.eps_T, self.eps_X, self.max_iter = eps_T, eps_X, max_iter
        self.dt_max, self.dt_growth, self.dt_cap = min(dt_init, dt_cap), dt_growth, dt_cap
        self.dt_late = dt_late
        self.relax_xmax, self.omega = relax_xmax, omega
        self.quasi_steady_T = quasi_steady_T

        self.i = np.arange(1, N + 1, dtype=float)
        self.face_idx = np.arange(1, N, dtype=float)      # 面 f（单元 f−1 与 f 之间）
        self.V_coef = (2 * self.i - 1) / N ** 2            # V_i = πR²·V_coef

        self.T = np.full(N, T0)
        self.X = np.full(N, X0)
        self.t = 0.0
        self.hist = []                                    # BDF2 历史，保留最近两步

    # ---------- 几何 / 事件 ----------
    def R_at(self, t):
        return R0 if self.radius is None else self.radius(t)

    def g(self):
        """事件函数 g(t) = X_max(t) − 0.15（model.md §9、§10.6）。"""
        return max(float(self.X.max()), self.surface()[1]) - 0.15

    def surface(self):
        """当前时刻与 FVM Robin 通量一致的表面温度和含水率。"""
        return surface_from_state(self.q, self.room, self.t, self.T, self.X,
                                  self.R_at(self.t), self.hT, self.hM)

    def sample(self, r_phys):
        """当前时刻在物理半径 r_phys (m) 处采样 T、X；越材位置为 NaN。"""
        R = self.R_at(self.t)
        T = map_to_physical(self.T, r_phys, R)
        X = map_to_physical(self.X, r_phys, R)
        at_surface = np.isclose(np.asarray(r_phys, dtype=float), R, rtol=0.0, atol=1e-12)
        if np.any(at_surface):
            Ts, Xs = self.surface()
            T = np.where(at_surface, Ts, T)
            X = np.where(at_surface, Xs, X)
        return T, X, R

    # ---------- 单步隐式积分（Picard）----------
    def _vec(self, v):
        v = np.asarray(v, dtype=float)
        return v if v.shape == (self.N,) else np.full(self.N, float(v))

    def _step(self, dt):
        N = self.N
        t_new = self.t + dt
        R = self.R_at(t_new)
        Ta = self.room.Ta(t_new)
        Ca = self.room.Ca(t_new)
        p = self.p

        # 变步长 BDF2（model.md §13.2）：
        #   u_{n+1} = [(1+θ)²u^n − θ²u^{n−1}]/(2θ+1) + [θ(1+θ)Δt₋₁/(2θ+1)]·f(u_{n+1})
        # θ=Δt/Δt₋₁；前两步退化为 Backward Euler（model.md §13.2）。
        dt_eff = dt
        if len(self.hist) == 2:
            dt_prev = self.hist[-1][0] - self.hist[-2][0]
            th = dt / dt_prev
            denom = 2.0 * th + 1.0
            H_T = ((1 + th)**2 * self.hist[-1][1] - th**2 * self.hist[-2][1]) / denom
            H_X = ((1 + th)**2 * self.hist[-1][2] - th**2 * self.hist[-2][2]) / denom
            dt_eff = th * (1 + th) * dt_prev / denom
        elif len(self.hist) == 1:
            H_T, H_X = self.hist[-1][1], self.hist[-1][2]
        else:
            H_T, H_X = self.T.copy(), self.X.copy()

        V = np.pi * R * R * self.V_coef
        Tm, Xm = self.T.copy(), self.X.copy()
        if self.quasi_steady_T:
            Tm.fill(Ta)
        relax = float(Xm.max()) < self.relax_xmax   # 低含水率末段欠松弛（model.md §13.4）
        stall, best = 0, np.inf
        for _ in range(self.max_iter):
            Th = theta(Tm)
            rho = self._vec(p["rho"](Xm))
            cp = self._vec(p["cp"](Xm))
            k = self._vec(p["k"](Xm))
            D = self._vec(p["D"](Xm, Th))
            ki = self._harm(k[:-1], k[1:])
            Di = self._harm(D[:-1], D[1:])
            if self.quasi_steady_T:
                Tn = np.full(N, Ta)
            else:
                Tn = self._solve(Tm, H_T, ki, k[-1], rho * cp, V,
                                 dt_eff, Ta, self.hT, R)
            # 水分方程 X_t=(1/(R²ξ))∂ξ[ξD X_ξ] 无 ρc_p 容量项（model.md §6 式(2)、§19 式(35)），
            # 时间系数乘子取 1.0；误用 ρc_p 会把 X 扩散放慢 ~1e6 倍导致冻结。
            Xn = self._solve(Xm, H_X, Di, D[-1], 1.0, V,
                             dt_eff, Ca, self.hM, R)
            dT, dX = np.abs(Tn - Tm).max(), np.abs(Xn - Xm).max()
            if dT < self.eps_T and dX < self.eps_X:
                Tm, Xm = Tn, Xn
                break
            # 停滞检测：误差不再下降时启用欠松弛，保证固定点迭代前进
            if max(dT, dX) < 0.5 * best:
                stall, best = 0, max(dT, dX)
            else:
                stall += 1
            if relax or stall >= 4:
                Tm = self.omega * Tn + (1 - self.omega) * Tm
                Xm = self.omega * Xn + (1 - self.omega) * Xm
            else:
                Tm, Xm = Tn, Xn
        else:
            raise RuntimeError(f"Picard 未收敛 t={t_new:.3f} s (q={self.q}, N={self.N})")

        self.T, self.X, self.t = Tm, np.maximum(Xm, 1e-6), t_new   # 物理下界 X≥0
        self.hist.append((t_new, self.T.copy(), self.X.copy()))
        if len(self.hist) > 2:
            self.hist.pop(0)

    @staticmethod
    def _harm(a, b):
        """调和平均，双零界面取 0（防止 0/0 产生 NaN）。"""
        den = a + b
        return np.where(den > 0, 2 * a * b / np.where(den > 0, den, 1.0), 0.0)

    def _solve(self, u, H, G, G_boundary, rho_cp, V, dt, amb, h, R):
        """解单个场的隐式三对角系统（物性冻结，Thomas 算法）。

        u: 当前 Picard 迭代值；H: BDF2 历史组合；G: 界面系数 (N−1,)；
        G_boundary: 最外层单元物性；amb: 环境值（Ta 或 Ca）；h: hT 或 hM；
        R: 当前半径。
        离散依据：控制体 i 的能量平衡
            ρc_p V_i T_i' = 2πi·k_i(T_{i+1}−T_i) − 2π(i−1)k_{i−1}(T_i−T_{i−1})，
        中心面（ξ=0）面积为 0 自然零通量，表面面用 Robin 通量 2πR·h(us−amb)。
        """
        N = self.N
        fcoef = 2 * np.pi * self.face_idx * G
        a = np.zeros(N)
        c = np.zeros(N)
        c[:-1] = -fcoef
        a[1:] = -fcoef
        time_coeff = np.asarray(rho_cp, dtype=float) * V / dt
        b = time_coeff.copy()
        b[0] += fcoef[0]
        if N > 2:
            b[1:-1] += fcoef[:-1] + fcoef[1:]
        b[-1] += fcoef[-1]
        d = time_coeff * H
        # Robin 边界采用半单元扩散阻力与表面对流阻力串联，得到
        # h_eff=hΓ/(Γ+hR/(2N))。通量对 u_N 隐式处理，保持三对角矩阵的
        # M-矩阵结构，避免二阶外推中的负权重破坏离散比较性质。
        delta = R / (2.0 * N)
        h_eff = h * G_boundary / (G_boundary + h * delta)
        boundary_coeff = 2 * np.pi * R * h_eff
        b[-1] += boundary_coeff
        d[-1] += boundary_coeff * amb
        return self._thomas(a, b, c, d)

    @staticmethod
    def _thomas(a, b, c, d):
        """用编译 LAPACK ``dgtsv`` 解三对角系统。"""
        _du2, _diag, _du, x, info = dgtsv(
            np.array(a[1:], dtype=float, copy=True),
            np.array(b, dtype=float, copy=True),
            np.array(c[:-1], dtype=float, copy=True),
            np.array(d, dtype=float, copy=True),
            overwrite_dl=1, overwrite_d=1, overwrite_du=1, overwrite_b=1,
        )
        if info != 0:
            raise np.linalg.LinAlgError(f"LAPACK dgtsv 求解失败，info={info}")
        return x

    # ---------- 自适应推进 ----------
    def advance_to(self, t_target):
        """推进到 t_target：自适应步长，强制落在 60 s 数据节点上（model.md §13.3）。

        低含水率末段干燥锋变陡，收紧步长以解析锋面、抑制中心差分过冲（§13.3）。
        """
        while self.t < t_target - 1e-9:
            dt = min(self.dt_max, t_target - self.t)
            if self.X.max() < self.relax_xmax:
                dt = min(dt, self.dt_late)
            node = np.floor((self.t + dt) / 60.0) * 60.0
            if node > self.t + 1e-9:
                dt = node - self.t
            self._step(dt)
            self.dt_max = min(self.dt_cap, self.dt_max * self.dt_growth)

    # ---------- 事件定位 ----------
    def clone(self):
        """复制当前积分器的完整状态，包括 BDF2 历史和自适应步长。"""
        s = FVMSolver(self.q, self.room, N=self.N, hT=self.hT, hM=self.hM,
                      radius=self.radius, eps_T=self.eps_T, eps_X=self.eps_X,
                      max_iter=self.max_iter, dt_init=self.dt_max,
                      dt_growth=self.dt_growth, dt_cap=self.dt_cap,
                      dt_late=self.dt_late,
                      relax_xmax=self.relax_xmax, omega=self.omega,
                      quasi_steady_T=self.quasi_steady_T)
        s.t, s.T, s.X = self.t, self.T.copy(), self.X.copy()
        s.dt_max = self.dt_max
        s.hist = [(t, T.copy(), X.copy()) for t, T, X in self.hist]
        return s

    @staticmethod
    def refine_event(lo_solver, t_hi, tol=0.01, max_iter=40):
        """在 [t_lo, t_hi] 内二分定位 g=0 的连续时刻（model.md §13.5）。

        lo_solver 必须是穿越前时刻的完整快照，以保留 BDF2 历史。
        返回 (t_dry, T_event, X_event)。
        """
        lo, hi = float(lo_solver.t), float(t_hi)
        for _ in range(max_iter):
            mid = 0.5 * (lo + hi)
            s = lo_solver.clone()
            s.advance_to(mid)
            if s.g() > 0.0:
                lo = mid
            else:
                hi = mid
            if hi - lo < tol:
                break
        t_dry = 0.5 * (lo + hi)
        s = lo_solver.clone()
        s.advance_to(t_dry)
        return t_dry, s.T.copy(), s.X.copy()


def integrate_to_event(s, interval, log_every_s=3600.0):
    """从当前时刻推进到干燥终止事件，每 interval 秒采样一次。

    返回 (times, Ts, Xs, t_dry, T_event, X_event)：
    times 为输出时刻列表（不含事件行），Ts/Xs 为对应 cell 场值；
    t_dry 为二分定位的连续事件时刻；T_event/X_event 为事件时刻场值。
    """
    times, Ts, Xs = [], [], []
    k = 0
    while True:
        k += 1
        t_next = interval * k
        lo_solver = s.clone()
        s.advance_to(t_next)
        if s.g() <= 0.0:
            t_dry, T_ev, X_ev = s.refine_event(lo_solver, t_next)
            return times, Ts, Xs, t_dry, T_ev, X_ev
        # 只保存严格早于终止事件的规则网格行。原实现先保存穿越后的
        # t_next，再追加更早的精确事件行，导致结果末尾时间倒序。
        times.append(t_next)
        Ts.append(s.T.copy())
        Xs.append(s.X.copy())
        if log_every_s and t_next % log_every_s == 0:
            print(f"    t={t_next:>10.0f} s   X_max={s.X.max():.4f}", flush=True)
