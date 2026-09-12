"""论文编译前一致性检查：图件/输入文件、结构平衡、论文数字与冻结结果。"""
import hashlib
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "paper")
TABLES = os.path.join(ROOT, "results", "tables")

tex = open(os.path.join(PAPER, "main.tex"), encoding="utf-8").read()
failed = False

# 1. 图件引用
figs = re.findall(r"includegraphics\[[^\]]*\]\{([^}]+)\}", tex)
print("== figures ==")
for f in figs:
    matches = []
    for ext in (".pdf", ".png"):
        paper_path = os.path.join(PAPER, f + ext)
        if not os.path.exists(paper_path):
            continue
        # 论文图件必须是项目 results/figures 的同名实际产物，不能仅检查存在。
        source_path = os.path.join(ROOT, "results", f + ext)
        if not os.path.exists(source_path):
            matches.append(("SOURCE_MISS", ext))
            continue
        digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
        matches.append(("OK" if digest(paper_path) == digest(source_path) else "STALE", ext))
    status = "MISS" if not matches else ("OK" if all(x[0] == "OK" for x in matches)
                                      else "/".join(sorted(set(x[0] for x in matches))))
    print(f"{status:11} {f}", " ".join(x[1] for x in matches))
    failed |= status != "OK"

# 2. \input 文件
inputs = re.findall(r"\\input\{([^}]+)\}", tex)
print("== inputs ==")
for f in inputs:
    ok = os.path.exists(os.path.join(PAPER, f))
    print(("OK  " if ok else "MISS"), f)
    failed |= not ok

# 3. 括号与环境平衡
print("brace balance (should be 0):", tex.count("{") - tex.count("}"))
print("dollar odd count (should be 0):", tex.count("$") % 2)
for env in ["figure", "table", "equation", "minipage", "document",
            "abstract", "longtable", "thebibliography", "enumerate"]:
    b = len(re.findall(r"\\begin\{" + env + r"\}", tex))
    e = len(re.findall(r"\\end\{" + env + r"\}", tex))
    if b != e:
        print(f"ENV MISMATCH {env}: begin={b} end={e}")
print("env check done")


def _load(name):
    with open(os.path.join(TABLES, name), encoding="utf-8") as f:
        return json.load(f)


def _plain(lit):
    r"""去掉 LaTeX 指数写法，得到可解析的数字串。"""
    s = lit.replace(r"\times10^{", "e").replace(r"\times10^", "e")
    return s.replace("}", "").replace("\\", "").replace("^{", "")


def _literal_to_float(lit):
    try:
        return float(_plain(lit))
    except ValueError:
        return None


def _half_ulp(lit):
    """字面量末位数量级的一半，用于判定是否为正确舍入。"""
    m = re.fullmatch(r"([+-]?\d+(?:\.(\d+))?)(?:e([+-]?\d+))?", _plain(lit))
    if not m:
        return None
    decimals = len(m.group(2) or "")
    exp = int(m.group(3) or 0)
    return 0.5 * 10.0 ** (exp - decimals)


# 4. 论文数字与冻结结果交叉核对
q2, q4 = _load("q2_meta.json"), _load("q4_meta.json")
grid = _load("grid_convergence.json")["t_dry_s"]
tc = _load("time_convergence.json")["t_dry_s"]
flux = _load("flux_balance.json")["metrics"]
sens = _load("q_sens.json")
qgc = _load("quality_grid_convergence.json")
qrows = {(r["T_platform_C"], r["N"]): r for r in qgc["rows"]}

# (说明, 论文中应出现的字面量, 由冻结结果重算的值)
claims = [
    ("Q3 t_dry", "205885.5", q2["t_dry"]),
    ("Q4 t_dry", "182964.7", q4["t_dry"]),
    ("Q4-Fixed t_dry", "464785.2", sens["q4"]["t_dry_fixed"]),
    ("Q4-Fixed /h", "129.11", sens["q4"]["t_dry_fixed"] / 3600.0),
    ("grid q3 161>321", "-149.56", grid["3"]["321"] - grid["3"]["161"]),
    ("grid q3 321>641", "-52.59", grid["3"]["641"] - grid["3"]["321"]),
    ("grid q4 161>321", "-25.87", grid["4"]["321"] - grid["4"]["161"]),
    ("grid q4 321>641", "-7.54", grid["4"]["641"] - grid["4"]["321"]),
    ("time q3 60>15", "0.26", tc["3"]["15.0"] - tc["3"]["60.0"]),
    ("time q4 60>15", "0.12", tc["4"]["15.0"] - tc["4"]["60.0"]),
    ("flux q2 rel", r"1.191\times10^{-5}", flux["2"]["max_rel_to_12h_loss"]),
    ("flux q4 rel", r"1.298\times10^{-5}", flux["4"]["max_rel_to_12h_loss"]),
    ("sens baseline", "205885.2", sens["t_base"]),
    ("sens hm x0.5", "232696.6", sens["hm"]["0.5"]),
    ("platform +2C", "193390.3", sens["platform"]["Ta_+2C"]),
    ("quality 48C /h", "61.31", qrows[(48.0, 321)]["t_dry_s"] / 3600.0),
    ("quality 52C /h", "53.9942", qrows[(52.0, 321)]["t_dry_s"] / 3600.0),
    ("sigma base", "0.0194273", qrows[(50.165, 321)]["X_std_event"]),
    ("sigma 52C", "0.0194249", qrows[(52.0, 321)]["X_std_event"]),
    ("grid/signal ratio", "4.51", qgc["conclusion"]["grid_delta_to_signal_ratio"]),
]

print("== numbers ==")
for label, lit, value in claims:
    parsed, tol = _literal_to_float(lit), _half_ulp(lit)
    agree = (parsed is not None and tol is not None
             and abs(parsed - value) <= tol * (1 + 1e-9))
    ok = (lit in tex) and agree
    print(("OK  " if ok else "FAIL"),
          f"{label:20} tex={lit!r} recomputed={value!r}")
    failed |= not ok

# 5. 验证日志与论文数字（Bessel/Duhamel 基准、降阶对照）
vlog = os.path.join(ROOT, "results", "validate.log")
print("== validate.log ==")
if os.path.exists(vlog):
    log = open(vlog, encoding="utf-8").read()
    for lit in ("2.217e-02", "3.882e-02", "7.250e-03",
                "2.029e-04", "4.157e-03", "3.761e-03",
                "3.411e-13", "2.132e-13", "308.85", "283.24"):
        ok = lit in log
        print(("OK  " if ok else "FAIL"), lit)
        failed |= not ok
else:
    print("MISS results/validate.log"
          "（运行 python src/validate.py --skip-grid --skip-time）")
    failed = True

# 6. 表格编号唯一性（需已编译生成 main.aux）
aux = os.path.join(PAPER, "main.aux")
print("== table numbering ==")
if os.path.exists(aux):
    aux_text = open(aux, encoding="utf-8").read()
    by_num = {}
    for m in re.finditer(r"\\newlabel\{(tab:[^}]+)\}\{\{([^}]*)\}", aux_text):
        label, num = m.group(1), m.group(2)
        if "@cref" in label:          # hyperref 的伴随标签，编号格式不同
            continue
        by_num.setdefault(num, []).append(label)
    for num, labels in sorted(by_num.items(),
                              key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        dup = "" if len(labels) == 1 else "   <== DUPLICATE"
        print(f"表 {num}: {', '.join(labels)}{dup}")
        failed |= len(labels) > 1
else:
    print("main.aux 不存在，跳过（请先编译）")

if failed:
    raise SystemExit("论文资产未完全来自本地项目产物")
