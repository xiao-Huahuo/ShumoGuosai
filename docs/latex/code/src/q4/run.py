"""问题四命令行入口。"""
import argparse
from pathlib import Path
import time
from .config import Config, ROOT
from .data import read_inputs
from .diagnostics import diagnostics, write_experiment_plan, write_window_policy, production_gates
from .export import export_workbook, write_tables
from .rolling import run_day_q42, run_day_q43, run_period


def settings(arguments: argparse.Namespace) -> Config:
    if arguments.command in ("q42", "q43") and arguments.allow_limited:
        raise ValueError("正式q42/q43禁止--allow-limited；仅供smoke/benchmark参数兼容")
    nodes = {"0": (0,), "06": (0, 6), "0612": (0, 6, 12), "all": (0, 6, 12, 18)}[arguments.nodes]
    return Config(scenarios=arguments.scenarios, residual_window=arguments.window,
                  bootstrap_repetitions=arguments.bootstrap, seconds=arguments.seconds,
                  gap=arguments.gap, solver_threads=arguments.threads, nodes=nodes, hard_timeout=arguments.hard_timeout,
                  allow_limited=arguments.allow_limited)


def main() -> None:
    parser = argparse.ArgumentParser(description="Q4 strict-causal volatile-price DRO dispatch")
    parser.add_argument("command", choices=("prepare", "diagnostics", "smoke", "benchmark", "q42", "q43"))
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/q4/raw/current")
    parser.add_argument("--end", type=int, default=365)
    parser.add_argument("--day", type=int, default=31)
    parser.add_argument("--scenarios", type=int, default=20)
    parser.add_argument("--window", type=int, default=56, choices=(56, 84, 112))
    parser.add_argument("--bootstrap", type=int, default=100)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--hard-timeout", type=float, default=30.0)
    parser.add_argument("--gap", type=float, default=0.03)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--nodes", choices=("0", "06", "0612", "all"), default="all")
    parser.add_argument("--smoke-mode", choices=("4-2", "4-3"), default="4-2")
    parser.add_argument("--allow-limited", action="store_true")
    parser.add_argument("--with-lightgbm", action="store_true")
    arguments = parser.parse_args()
    config = settings(arguments)
    processed = ROOT / "inputs/q4/rescue_processed"
    data = read_inputs(processed)
    if arguments.command == "prepare":
        print(data.price.audit)
        return
    if arguments.command == "diagnostics":
        print(diagnostics(data, arguments.output, with_lightgbm=arguments.with_lightgbm))
        write_experiment_plan(config, arguments.output)
        write_window_policy(arguments.output)
        return
    if arguments.command in ("smoke", "benchmark"):
        runner = run_day_q42 if arguments.command == "smoke" and arguments.smoke_mode == "4-2" else run_day_q43
        started = time.perf_counter()
        frame, audit = runner(data, arguments.day, 6000.0, config)
        solver_audits = ([audit["solver"]] if "solver" in audit else
                         [node["solver"] for node in audit["nodes"]])
        print({"seconds": time.perf_counter() - started, "mode": audit["mode"],
               "date": audit["date"], "node_gaps": [item["gap"] for item in solver_audits],
               "all_reliable": all(item["reliable"] for item in solver_audits)})
        if arguments.command == "smoke":
            mode = arguments.smoke_mode
            write_tables(frame, arguments.output)
            export_workbook(frame, arguments.output, mode, config, smoke=True)
        return
    mode = "4-2" if arguments.command == "q42" else "4-3"
    frame = run_period(data, mode, config, arguments.output, end=arguments.end)
    write_tables(frame, arguments.output)
    if arguments.end == 365:
        production_gates(data, frame, mode, config, arguments.output)
    export_workbook(frame, arguments.output, mode, config, smoke=arguments.end < 365)


if __name__ == "__main__":
    main()
