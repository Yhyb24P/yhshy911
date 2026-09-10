def final_status(lines: list[str]) -> str:
    return "FAIL" if any(line.startswith("FAIL") for line in lines) else ("CONDITIONAL_PASS" if any(line.startswith(("WARN", "MANUAL_CHECK")) for line in lines) else "PASS")
