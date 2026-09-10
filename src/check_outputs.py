"""审计四个正式 Excel 产物是否满足 model.md §17。

本脚本只读文件，不运行 PDE。大工作簿使用 XML 流式扫描时间列，避免把
result2.xlsx 的数百万个单元格全部载入内存。
"""
import json
import math
import os
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from openpyxl import load_workbook

import model2
import model4
from xlsx_io import HEADER, Q4_R_COLS, R_COLS


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "附件3"
TABLES = ROOT / "results" / "tables"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _sheet_xml_paths(path):
    """按工作簿顺序返回工作表 XML 路径。"""
    with ZipFile(path) as zf:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {
        rel.attrib["Id"]: rel.attrib["Target"].lstrip("/") for rel in rels
    }
    paths = []
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for sheet in root.find(f"{NS}sheets"):
        target = rid_to_target[sheet.attrib[rel_ns]]
        paths.append(target if target.startswith("xl/") else "xl/" + target)
    return paths


def _time_axis(path, sheet_xml):
    """流式读取 A 列，返回数据行数、首末时刻和步长一致性。"""
    count = 0
    first = last = previous = None
    step = None
    regular = True
    with ZipFile(path) as zf, zf.open(sheet_xml) as stream:
        for _event, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag != f"{NS}row":
                continue
            row_number = int(elem.attrib["r"])
            if row_number >= 2:
                cell = elem.find(f"{NS}c")
                _assert(cell is not None and cell.attrib.get("r", "").startswith("A"),
                        f"{path.name}: 第 {row_number} 行缺少时间")
                value = cell.find(f"{NS}v")
                _assert(value is not None, f"{path.name}: 第 {row_number} 行时间为空")
                t = float(value.text)
                if first is None:
                    first = t
                if previous is not None:
                    delta = t - previous
                    if step is None:
                        step = delta
                    regular &= abs(delta - step) < 1e-9
                previous = last = t
                count += 1
            elem.clear()
    return count, first, last, step, regular


def _check_layout(path, sheet_names, headers):
    wb = load_workbook(path, read_only=True, data_only=False)
    _assert(wb.sheetnames == sheet_names,
            f"{path.name}: 工作表应为 {sheet_names}，实际为 {wb.sheetnames}")
    for ws in wb.worksheets:
        row1 = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        _assert(list(row1) == [HEADER] + list(headers), f"{path.name}/{ws.title}: 表头错误")
        row2 = next(ws.iter_rows(min_row=2, max_row=2, values_only=False))
        _assert(row2[0].number_format == "0", f"{path.name}/{ws.title}: 时间格式应为整数")
        _assert(all(c.value is None or c.number_format == "0.0000" for c in row2[1:]),
                f"{path.name}/{ws.title}: 数值格式应为四位小数")
    wb.close()


def _check_book(name, sheet_names, headers, expected_rows, first, last, step):
    path = DATA / name
    _assert(path.exists(), f"缺少 {path}")
    _check_layout(path, sheet_names, headers)
    axes = [_time_axis(path, xml) for xml in _sheet_xml_paths(path)]
    for got in axes:
        n, t0, t1, dt, regular = got
        _assert(n == expected_rows, f"{name}: 数据行应为 {expected_rows}，实际为 {n}")
        _assert(t0 == first and t1 == last, f"{name}: 时间范围应为 {first}..{last}，实际为 {t0}..{t1}")
        if expected_rows > 1:
            _assert(regular and dt == step, f"{name}: 时间步长并非恒定 {step} s")
    _assert(len(set(axes)) == 1, f"{name}: 各工作表时间轴不一致")
    print(f"[通过] {name}: {expected_rows} 行，t={first:g}..{last:g} s，步长 {step:g} s")


def _load_meta(name):
    with open(TABLES / name, encoding="utf-8") as f:
        return json.load(f)


def _check_event(meta, label):
    _assert(meta["t_dry"] > 0, f"{label}: 终止时间无效")
    xmax = max(meta["X_event"])
    _assert(abs(xmax - 0.15) <= 2e-8,
            f"{label}: 事件场 max(X)={xmax:.12g} 未定位到 0.15")


def run():
    q2 = _load_meta("q2_meta.json")
    q4 = _load_meta("q4_meta.json")
    _assert(q2.get("N") == 321, f"Q2/Q3 正式结果应使用 N=321，实际 N={q2.get('N')}")
    _assert(q4.get("N") == 321, f"Q4 正式结果应使用 N=321，实际 N={q4.get('N')}")
    _assert(q2.get("signature") == model2._signature(321), "Q2 缓存指纹已过期")
    _assert(q4.get("signature") == model4._signature(321), "Q4 缓存指纹已过期")
    _check_event(q2, "Q3")
    _check_event(q4, "Q4")

    q3_rows = math.floor(q2["t_dry"] / 60.0)
    q4_rows = math.floor(q4["t_dry"] / 60.0)
    _check_book("result1.xlsx", ["温度", "水分浓度"], R_COLS,
                1800, 1, 1800, 1)
    _check_book("result2.xlsx", ["温度", "水分浓度"], R_COLS,
                q2["n_rows"], 1, q2["n_rows"], 1)
    _check_book("result3.xlsx", ["Sheet1"], R_COLS,
                q3_rows, 60, q3_rows * 60, 60)
    _check_book("result4.xlsx", ["Sheet1"], Q4_R_COLS + ["药材表面"],
                q4_rows, 60, q4_rows * 60, 60)
    print(f"[通过] 连续事件：Q3={q2['t_dry']:.4f} s，Q4={q4['t_dry']:.4f} s")


if __name__ == "__main__":
    run()
