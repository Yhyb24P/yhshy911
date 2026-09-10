"""冻结 PDE 结果的圆柱面积加权品质指标。

cell-centered FVM 场优先使用控制体面积权重；只有读取已归档的物理半径
剖面时才使用圆柱坐标梯形积分。所有函数均为分析层纯函数，不修改求解器。
"""
import numpy as np
from scipy.integrate import trapezoid

from props import HM


def radial_volume_weights(n):
    """返回 n 个等宽 cell-centered 圆环的归一化截面积权重。"""
    if int(n) != n or n < 1:
        raise ValueError("n 必须是正整数")
    i = np.arange(1, int(n) + 1, dtype=float)
    weights = 2.0 * i - 1.0
    return weights / weights.sum()


def weighted_mean_X(X, weights=None):
    """计算圆柱横截面的面积加权平均含水率。"""
    X = np.asarray(X, dtype=float)
    weights = radial_volume_weights(X.shape[-1]) if weights is None else np.asarray(weights)
    return np.sum(X * weights, axis=-1) / np.sum(weights)


def weighted_std_X(X, weights=None):
    """计算面积加权径向标准差，而非等半径采样点的普通标准差。"""
    X = np.asarray(X, dtype=float)
    weights = radial_volume_weights(X.shape[-1]) if weights is None else np.asarray(weights)
    mean = weighted_mean_X(X, weights)
    variance = np.sum((X - np.expand_dims(mean, -1)) ** 2 * weights, axis=-1) / np.sum(weights)
    return np.sqrt(np.maximum(variance, 0.0))


def moisture_range(X):
    """返回 X_max-X_min。"""
    X = np.asarray(X, dtype=float)
    return np.max(X, axis=-1) - np.min(X, axis=-1)


def drying_rate_from_flux(X_surface, C_ambient, radius, h_m=HM):
    """由 Robin 表面通量计算模型平均干燥速率 -d X_bar/dt。"""
    radius = np.asarray(radius, dtype=float)
    if np.any(radius <= 0):
        raise ValueError("radius 必须为正")
    return 2.0 * float(h_m) / radius * (
        np.asarray(X_surface, dtype=float) - np.asarray(C_ambient, dtype=float)
    )


def profile_moments(X, radii, radius):
    """从含中心和表面的物理半径剖面做圆柱面积积分。

    用于只保存了 0.1 cm 物理采样的冻结轨迹。优化与事件品质指标仍使用
    ``weighted_mean_X``/``weighted_std_X`` 对 FVM cell 场直接计算。
    """
    X = np.asarray(X, dtype=float)
    radii = np.asarray(radii, dtype=float)
    radius = float(radius)
    if X.shape[-1] != radii.size or radii.ndim != 1:
        raise ValueError("X 最后一维必须与 radii 对齐")
    if abs(radii[0]) > 1e-12 or abs(radii[-1] - radius) > 1e-10:
        raise ValueError("剖面必须包含中心 r=0 和表面 r=R")
    denominator = 0.5 * radius ** 2
    mean = trapezoid(X * radii, radii, axis=-1) / denominator
    variance = trapezoid((X - np.expand_dims(mean, -1)) ** 2 * radii,
                         radii, axis=-1) / denominator
    return mean, np.sqrt(np.maximum(variance, 0.0))
