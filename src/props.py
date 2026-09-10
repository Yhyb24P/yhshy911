"""物性模型与环境/几何输入（model.md §2、§5、§7、§8、§10）。

约定（model.md 附录 B）：
- T 以 °C 保存，仅代入 Arrhenius 指数时转 Θ = T + 273.15 K；
- X 始终为药材干基含水率（kg/kg）；
- 附件 1 的水分变量只作为 C_a / χ_a 有效边界势使用。
"""
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

# ---- 题设常数（附录 2）----
R0 = 0.02          # m，初始圆柱半径
T0 = 28.0          # °C，初始温度
X0 = 2.55          # kg/kg，初始干基含水率
HT = 25.0          # W/(m²·K)，对流换热系数
HM = 8e-7          # m/s，等效传质系数

# ---- Q4 半径平台（附件 2 复核）----
T_RPLAT = 241200.0   # s，自该时刻起连续 11 个实测点均为 1.198 cm
R_PLAT = 0.01198     # m


def theta(T):
    """°C → K（仅用于 Arrhenius 指数）。"""
    return T + 273.15


def _x(X):
    """X 下限截断，防止 exp(-a/X) 除零。"""
    return np.clip(np.asarray(X, dtype=float), 1e-12, None)


# ---- 附录 2：Q1 常物性 + 含水率依赖扩散系数 ----
def rho1(X):
    return 820.0


def cp1(X):
    return 2600.0


def k1(X):
    return 0.36


def D1(X, Th):
    return 7e-9 * np.exp(-0.89 / _x(X))


# ---- 附录 3：Q2/Q3 变物性经验公式 ----
def rho3(X):
    return 650.0 + 128.0 * X


def cp3(X):
    return 1450.0 + 2736.0 * X / (X + 1.0)


def k3(X):
    return 0.21 + 0.38 * X / (X + 1.0)


def D3(X, Th):
    return 2.4e-3 * np.exp(-0.45 / _x(X)) * np.exp(-3850.0 / Th)


# ---- 附录 4：Q4 变物性经验公式 ----
def rho4(X):
    return 760.0 + 90.0 * X


def cp4(X):
    return 1850.0 + 2150.0 * X / (X + 1.0)


def k4(X):
    return 0.12 + 0.20 * X / (X + 1.0)


def D4(X, Th):
    return 4.2e-4 * np.exp(-0.30 / _x(X)) * np.exp(-3850.0 / Th)


PROPS = {
    1: dict(rho=rho1, cp=cp1, k=k1, D=D1),
    2: dict(rho=rho3, cp=cp3, k=k3, D=D3),
    3: dict(rho=rho3, cp=cp3, k=k3, D=D3),
    4: dict(rho=rho4, cp=cp4, k=k4, D=D4),
}


class DryingRoom:
    """烘房环境输入（附件 1）：观测区间内分段线性插值，4 h 后末端平台值常值延拓。"""

    def __init__(self, path="data/附件1.xlsx"):
        df = pd.read_excel(path)
        self.times = df["时间"].to_numpy(dtype=float)
        self.Ta_data = df["温度"].to_numpy(dtype=float)
        self.Ca_data = df["水分浓度"].to_numpy(dtype=float)
        self.Ta_end, self.Ca_end = float(self.Ta_data[-1]), float(self.Ca_data[-1])

    def Ta(self, t):
        return np.interp(t, self.times, self.Ta_data, right=self.Ta_end)

    def Ca(self, t):
        return np.interp(t, self.times, self.Ca_data, right=self.Ca_end)


class Radius:
    """实测半径 R(t)（附件 2，Q4 几何输入）。

    前段 [0, 241200 s) 用 PCHIP 保形单调插值；t ≥ 241200 s 直接钳制为实测
    末端平台 1.198 cm，避免三次样条在末端平台产生伪振荡（model.md §10.1）。
    """

    def __init__(self, path="data/附件2.xlsx"):
        df = pd.read_excel(path)
        t = df["时间"].to_numpy(dtype=float)
        # 附件 2 以 cm 给出半径；求解器中的所有长度统一使用 m。
        # 必须在构造插值器前换算，否则平台前会把 2 cm 当成 2 m，且在
        # T_RPLAT 处从约 1.198 m 非物理跳变到 0.01198 m。
        R = df["半径"].to_numpy(dtype=float) * 1e-2
        m = t <= T_RPLAT
        self._pchip = PchipInterpolator(t[m], R[m])
        self._R_end = float(R[~m].mean())
        if abs(self._R_end - R_PLAT) > 1e-6:
            raise ValueError(f"末端半径 {self._R_end} m 与复核值 {R_PLAT} m 不一致")

        # 在输入层阻断长度单位或附件内容错误，避免静默污染整个 Q4。
        if abs(float(self._pchip(0.0)) - R0) > 1e-10:
            raise ValueError("附件 2 初始半径换算后应为 0.02 m")
        if abs(float(self._pchip(T_RPLAT)) - self._R_end) > 1e-10:
            raise ValueError("半径插值与末端平台在 241200 s 处不连续")

    def __call__(self, t):
        t = np.asarray(t, dtype=float)
        return np.where(t < T_RPLAT, self._pchip(np.minimum(t, T_RPLAT)), self._R_end)
