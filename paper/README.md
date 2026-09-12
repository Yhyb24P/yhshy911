# 2026 高教社杯全国大学生数学建模竞赛 A 题《药材的烘干问题》论文（LaTeX）

本仓库为论文 LaTeX 工作区，基于国赛官方模板 `cumcmthesis.cls`，使用 XeLaTeX 编译。

## 文件

- `main.tex` — 论文全文
- `main.pdf` — 最近一次编译产物（37 页）
- `cumcmthesis.cls` — 官方 LaTeX 模板类（国赛官网或 Overleaf 官方模板同源）
- `tables/t1.tex` … `t6.tex` — 表 1–6，由 `build_tables.py` 自动生成
- `tables.tex` — 六张表的合并版（备用）
- `figures/` — 论文引用图件（PDF + PNG）
- `build_tables.py` — 从冻结结果 CSV 重新生成表格
- `check_paper.py` — 编译前一致性检查（图件存在性、括号/环境平衡、论文数字与
  `results/tables/*.json` 及 `results/validate.log` 交叉核对、表编号唯一性）
- `fix_sections.py` — 章节编号辅助脚本

## 编译

```bash
xelatex main.tex && xelatex main.tex
```

## 提交前 TODO

- [ ] 填写报名号 `\baominghao{...}`、学校 `\schoolname{...}`、
      三名队员 `\membera/b/c{...}`、指导教师 `\supervisor{...}`
- [ ] 承诺书按组委会要求单独处理（当前 `withoutpreface` 选项跳过）
- [ ] 若需重新同步表格：`python build_tables.py`
- [ ] 若 `check_paper.py` 报 `results/validate.log` 缺失，先运行
      `conda run -n cumcm-a python src/validate.py --skip-grid --skip-time`
- [ ] 最终一致性检查：`python check_paper.py`

## 数据说明

论文中全部数字均与冻结结果（`results/tables/*.json`，见建模项目主仓库）
一致，表格与冻结 CSV 同源，不手工誊抄。
