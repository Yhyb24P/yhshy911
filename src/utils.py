"""通用工具：统一绘图风格 + 固定结果路径。

用法:
    from utils import setup_plot, FIG_DIR, save_fig
    setup_plot()
    ax.plot(x, y)
    save_fig(ax.figure, "fig1")   # -> results/figures/fig1.png
"""
import hashlib
import json
import os
import tempfile
import matplotlib
import matplotlib.pyplot as plt

# 结果目录（相对项目根）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(ROOT, "results", "figures")
TAB_DIR = os.path.join(ROOT, "results", "tables")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TAB_DIR, exist_ok=True)


def input_signature(paths, settings=None):
    """返回代码、附件与关键设置的位置无关内容指纹。

    路径只按共同根目录下的相对名称参与哈希，使仓库移动或克隆后仍能复用
    内容完全相同的长计算结果；文件内容或关键设置变化仍会使缓存失效。
    """
    h = hashlib.sha256()
    abs_paths = [os.path.abspath(p) for p in paths]
    common = os.path.commonpath(abs_paths)
    if os.path.isfile(common):
        common = os.path.dirname(common)
    for path in sorted(abs_paths, key=lambda p: os.path.relpath(p, common)):
        relative = os.path.relpath(path, common).replace(os.sep, "/")
        h.update(relative.encode("utf-8"))
        h.update(b"\0")
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    if settings is not None:
        h.update(repr(settings).encode("utf-8"))
    return h.hexdigest()


def staged_path(path):
    """在目标目录创建临时路径，供完成后用 os.replace 原子替换。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.",
                               suffix=".tmp", dir=os.path.dirname(os.path.abspath(path)))
    os.close(fd)
    return tmp


def atomic_json_dump(data, path):
    """原子写入 JSON，避免中断留下半个元数据文件。"""
    tmp = staged_path(path)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

# 统一风格：中文字体 + 300dpi + 简洁网格
plt.rcParams.update({
    "font.sans-serif": ["DejaVu Sans"],  # 中文环境可改为 ["SimHei", "Arial Unicode MS"]
    "axes.unicode_minus": False,
    "figure.dpi": 100,
    "savefig.dpi": 300,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "figure.figsize": [6.4, 4.8],
})


def setup_plot():
    """重置一张新图的默认风格。"""
    plt.style.use("default")
    plt.rcParams.update({
        "figure.dpi": 100,
        "savefig.dpi": 300,
        "axes.grid": True,
        "grid.alpha": 0.3,
    })


def save_fig(fig, name, ext="png"):
    """保存图到 results/figures/，返回路径。"""
    path = os.path.join(FIG_DIR, f"{name}.{ext}")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
