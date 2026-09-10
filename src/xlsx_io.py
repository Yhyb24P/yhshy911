"""结果输出：填充 data/附件3/resultN.xlsx 模板（model.md §17 输出契约）。

模板结构（附件 3）：
- result1/2：工作表「温度」「水分浓度」，时间首行 1 s，不写 t=0；
- result3/4：单工作表，时间首行 60 s，不写 t=0；result4 为 0–1.9 cm +「药材表面」；
- result1–3 径向列为 0, 0.1, …, 2.0 cm；
- 数值一律保留 4 位小数；越材位置（result4 中 r>R(t)）留空。
"""
import os

import numpy as np
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

from utils import staged_path

HEADER = "时间\\到药材中心的距离"
R_COLS = [round(0.1 * j, 1) for j in range(21)]   # 0, 0.1, …, 2.0 cm
Q4_R_COLS = R_COLS[:-1]                            # 0, 0.1, …, 1.9 cm + 表面


def _fmt_time(t):
    t = float(t)
    return int(t) if abs(t - round(t)) < 1e-9 else round(t, 4)


def _fmt_val(v):
    if v is None:
        return None
    v = float(v)
    return None if np.isnan(v) else round(v, 4)


def header_row(ws, cols):
    """创建结果表表头。"""
    return [HEADER] + list(cols)


def data_row(ws, t, values):
    """创建带明确小数格式的数据行；空值保持为空。"""
    tc = WriteOnlyCell(ws, value=_fmt_time(t))
    tc.number_format = "0" if isinstance(tc.value, int) else "0.0000"
    row = [tc]
    for value in values:
        value = _fmt_val(value)
        cell = WriteOnlyCell(ws, value=value)
        if value is not None:
            cell.number_format = "0.0000"
        row.append(cell)
    return row


def write_workbook(path, sheets):
    """sheets: [(工作表名, 列头序列, 时间序列, 数据 (nrows, ncols)), …]。"""
    tmp = staged_path(path)
    try:
        wb = Workbook(write_only=True)
        for title, cols, times, data in sheets:
            ws = wb.create_sheet(title)
            ws.append(header_row(ws, cols))
            for k, t in enumerate(times):
                ws.append(data_row(ws, t, data[k]))
        wb.save(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
