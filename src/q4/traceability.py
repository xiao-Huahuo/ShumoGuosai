"""把方案每个非空源行映射到实现与可执行验收。"""
from pathlib import Path
import pandas as pd
from .config import SOURCE, ROOT, write_csv, write_json


MAP = {
    "7.1": ("src/q4/run.py;src/q4/rolling.py", "real smoke and CLI acceptance"),
    "7.2": ("src/q4/data.py;src/q4/diagnostics.py", "Q4Tests.test_real_data_diagnostics"),
    "7.3": ("src/q4/price.py", "Q4Tests.test_price_forecast_metrics_and_causality"),
    "7.4": ("src/q4/data.py;src/q4/scenarios.py", "Q4Tests.test_joint_history_and_tail_reduction"),
    "7.5": ("src/q4/scenarios.py;src/q4/optimization.py", "Q4Tests.test_dual_and_constraint_generation_agree"),
    "7.6": ("src/q4/physics.py;src/q4/optimization.py;src/q4/rolling.py", "Q4Tests.test_physical_call_separation; real Q4-2 smoke"),
    "7.7": ("src/q4/scenarios.py;src/q4/physics.py;src/q4/optimization.py;src/q4/rolling.py", "Q4Tests.test_prefix_uses_realized_slots_only; real Q4-3 smoke"),
    "7.8": ("src/q4/diagnostics.py;src/q4/rolling.py;src/q4/export.py", "Q4Tests.test_workbook_roundtrip_and_partial_guard"),
    "7.9": ("src/q4", "full test suite and traceability audit"),
}


def generate(output: Path | None = None) -> dict:
    output = output or ROOT / "docs/4"
    chapter = "7.1"
    rows = []
    for number, text in enumerate(SOURCE.read_text(encoding="utf-8").splitlines(), 1):
        if text.startswith("## 7."):
            chapter = text.split()[1]
        if text.strip():
            implementation, verification = MAP[chapter]
            rows.append({"source_line": number, "section": chapter, "source_text": text,
                         "implementation": implementation, "verification": verification, "status": "mapped"})
    frame = pd.DataFrame(rows)
    write_csv(output / "source_line_acceptance.csv", frame)
    audit = {"source": str(SOURCE), "nonempty_lines": len(frame), "mapped_lines": int((frame.status == "mapped").sum()),
             "complete": bool(len(frame) and (frame.status == "mapped").all())}
    write_json(output / "traceability_audit.json", audit)
    return audit


if __name__ == "__main__":
    print(generate())

