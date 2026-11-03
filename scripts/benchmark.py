"""Isolated, repeatable local ETL benchmark. Never uses the application dataset."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sqlite3
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def peak_process_rss():
    """Lifetime peak working set/RSS in bytes; called immediately after ETL."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def tree_bytes(path):
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def table_digest(frame, keys):
    # Canonical logical content, independent of parquet metadata/row ordering.
    normalized = frame.sort_values(keys).reset_index(drop=True)
    payload = normalized.reindex(sorted(normalized.columns), axis=1).to_json(
        orient="records", date_format="iso", date_unit="ns")
    return hashlib.sha256(payload.encode()).hexdigest()


def worker(args):
    dataset = args.dataset.resolve()
    if not (dataset / ".benchmark-dataset").is_file():
        raise ValueError("Refusing to operate on an unmarked application dataset")
    # Set before importing application settings, whose dotenv does not override these.
    os.environ["NUTEE_DATA_DIR"] = str(dataset)
    os.environ["APP_ENV"] = "dev"
    os.environ["POSTHOG_TEST_PROJECT"] = "false"
    if args.worker == "generate":
        from data_generator.simulate_sessions import generate
        started = time.perf_counter()
        result = generate(args.count, args.seed, send=False)
        result["generation_seconds"] = time.perf_counter() - started
        write_json(args.result, result)
        return

    import pandas as pd
    from pipeline.run_pipeline import run_pipeline
    metrics = {}
    cpu_start = time.process_time()
    result = run_pipeline(as_of=datetime.fromisoformat(args.as_of), metrics=metrics)
    cpu_seconds = time.process_time() - cpu_start
    peak = peak_process_rss()  # Before loading output tables for validation.
    elapsed = metrics["seconds"]["total"]
    gold = dataset / "synthetic/gold" / result["generation"]
    silver = pd.read_parquet(dataset / "synthetic/silver/events.parquet")
    counts = pd.read_parquet(gold / "user_item_event_counts.parquet")
    sequences = pd.read_parquet(gold / "session_sequences.parquet")
    checks = {
        "accepted_matches_requested": result["events"] == args.count,
        "quality_conservation": sum(metrics["quality"][k] for k in
                                    ("accepted_events", "rejected_events", "duplicate_events"))
                                == metrics["quality"]["input_events"],
        "count_conservation": int(counts.event_count.sum()) == int(silver.product_id.notna().sum()),
        "sequence_conservation": sum(len(x) for x in sequences.event_types) == len(silver),
    }
    snapshot = {
        "silver": table_digest(silver.drop(columns=["ingested_at"]), ["event_id"]),
        "counts": table_digest(counts, ["user_id", "product_id", "event_name"]),
        "sequences": table_digest(sequences, ["user_id", "session_id"]),
    }
    report = {
        **metrics, "cpu_seconds": cpu_seconds,
        "cpu_percent_one_core": 100 * cpu_seconds / elapsed,
        "peak_process_rss_bytes": peak,
        "input_events_per_second": metrics["quality"]["input_events"] / elapsed,
        "accepted_events_per_second": result["events"] / elapsed,
        "rows": result["tables"], "checks": checks, "fingerprints": snapshot,
        "storage_bytes": {
            "bronze": tree_bytes(dataset / "synthetic/bronze"),
            "silver": tree_bytes(dataset / "synthetic/silver"),
            "gold_current": tree_bytes(gold),
            "gold_all_generations": tree_bytes(dataset / "synthetic/gold"),
            "sqlite": sum(p.stat().st_size for p in dataset.glob("app.sqlite3*")),
        },
        "bronze_files": len(list((dataset / "synthetic/bronze").glob("*.parquet"))),
    }
    write_json(args.result, report)
    if not all(checks.values()):
        raise RuntimeError("Benchmark data checks failed; inspect result JSON")


def summarize(runs):
    summaries = []
    for count, phase in sorted({(r["count"], r["phase"]) for r in runs}):
        selected = [r for r in runs if r["count"] == count and r["phase"] == phase]
        entry = {"count": count, "phase": phase, "samples": len(selected)}
        values = {
            "total_seconds": [r["seconds"]["total"] for r in selected],
            "events_per_second": [r["input_events_per_second"] for r in selected],
            "peak_rss_mib": [r["peak_process_rss_bytes"] / 2**20 for r in selected],
            "cpu_seconds": [r["cpu_seconds"] for r in selected],
            "cpu_percent_one_core": [r["cpu_percent_one_core"] for r in selected],
        }
        for stage in ("initialize", "bronze", "silver", "gold"):
            values[f"{stage}_seconds"] = [r["seconds"][stage] for r in selected]
        entry["metrics"] = {name: {"min": min(v), "median": statistics.median(v), "max": max(v)}
                            for name, v in values.items()}
        summaries.append(entry)
    return summaries


def markdown(report):
    lines = ["# Kết quả benchmark pipeline NUTEE", "",
             f"- Thời điểm bắt đầu (UTC): `{report['started_at']}`",
             f"- Python: `{report['environment']['python']}`",
             f"- Hệ điều hành: `{report['environment']['platform']}`",
             f"- CPU: `{report['environment']['processor']}`; logical CPUs: {report['environment']['logical_cpus']}",
             f"- Seed: {report['seed']}; số lần lặp mỗi mức: {report['repeats']}",
             f"- Cutoff ETL: `{report['as_of']}`",
             f"- Kiểm tra dữ liệu và tính nhất quán: **{'PASS' if report['passed'] else 'FAIL'}**", "",
             "## Thời gian và tài nguyên", "",
             "Các cột dùng median; khoảng min–max và từng lần chạy nằm trong results.json.", "",
             "| Events | Chế độ | Tổng (s) | Bronze (s) | Silver (s) | Gold (s) | Events/s | Peak RSS (MiB) | CPU (s) |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in report["summary"]:
        m = row["metrics"]
        names = ["total_seconds", "bronze_seconds", "silver_seconds", "gold_seconds", "events_per_second", "peak_rss_mib", "cpu_seconds"]
        lines.append(f"| {row['count']:,} | {row['phase']} | " + " | ".join(f"{m[n]['median']:,.3f}" for n in names) + " |")
    lines += ["", "## Chất lượng và dung lượng", "",
              "Mỗi dòng dưới đây là lần lặp 1; JSON lưu tất cả lần lặp.", "",
              "| Events | Chế độ | Hợp lệ | Bị loại | Trùng | Bronze MiB | Silver MiB | Gold hiện hành MiB |",
              "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in report["runs"]:
        if r["repeat"] == 1:
            q, s = r["quality"], r["storage_bytes"]
            lines.append(f"| {r['count']:,} | {r['phase']} | {q['accepted_events']:,} | {q['rejected_events']:,} | {q['duplicate_events']:,} | "
                         + " | ".join(f"{s[k] / 2**20:.3f}" for k in ("bronze", "silver", "gold_current")) + " |")
    lines += ["", "## Phương pháp và giới hạn", "",
              "- first_load: SQLite đã có dữ liệu, Bronze/Silver/Gold chưa có. rerun: chạy lại trên cùng dataset.",
              "- Mỗi lượt ETL dùng một process mới. Không xóa OS disk cache; first_load không có nghĩa là cold-cache.",
              "- Tổng thời gian gồm khởi tạo DB/audit, Bronze, Silver và Gold; không gồm sinh dữ liệu, import module, kiểm tra đầu ra hoặc tạo báo cáo.",
              "- Bronze gồm đọc dữ liệu cũ để kiểm tra trùng, đọc SQLite/catalog, append và đọc lại Bronze. Silver gồm làm sạch, ghi Parquet và audit; Gold gồm tổng hợp và publish manifest.",
              "- Peak RSS là đỉnh bộ nhớ của process đến ngay sau ETL, gồm imports; không phải tổng RAM máy hay memory delta. CPU seconds chỉ đo ETL; phần trăm CPU trong JSON lấy một core = 100%.",
              "- So sánh nội dung Silver (bỏ ingested_at), cả hai bảng Gold, số file/dung lượng Bronze và bảo toàn số sự kiện. Các generation Gold mới vẫn chiếm thêm dung lượng khi chạy lại.",
              "- Dữ liệu sạch synthetic; chưa là phép đo khả năng chống dữ liệu lỗi ở quy mô lớn. Không gọi PostHog, không đo API tải đồng thời, độ trễ event-to-Gold hay chất lượng mô hình gợi ý.",
              "- Với 3 lần lặp, chỉ báo median/min/max; không suy diễn p95/p99 hoặc năng lực production.",
              "- Xem results.json để lấy phiên bản dependencies, hash mã nguồn/config, hash dataset, các kiểm tra và từng lượt đo.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10000, 100000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-root", type=Path, default=ROOT / "runtime/benchmarks")
    parser.add_argument("--worker", choices=["generate", "pipeline"], help=argparse.SUPPRESS)
    parser.add_argument("--dataset", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--result", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--count", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--as-of", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if args.repeats < 1 or any(n < 1 for n in args.sizes) or len(set(args.sizes)) != len(args.sizes):
        parser.error("sizes must be unique positive integers; repeats must be positive")
    started = datetime.now(timezone.utc)
    output = args.output_root.resolve() / (started.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / "configs/simulator.json").read_text())
    cutoff = (datetime.fromisoformat(config["start"]) + timedelta(days=config["days"] + 1)).isoformat()
    env = os.environ.copy()
    env.update({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "2", "PYTHONHASHSEED": str(args.seed), "PYTHONDONTWRITEBYTECODE": "1"})
    files = sorted(p for folder in ("backend", "pipeline", "data_generator", "scripts", "configs")
                   for p in (ROOT / folder).rglob("*") if p.suffix in {".py", ".json", ".sql", ".txt"})
    report = {
        "started_at": started.isoformat(), "seed": args.seed, "repeats": args.repeats,
        "as_of": cutoff, "output": str(output),
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
                        "thread_limits": {k: env[k] for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")},
                        "packages": {p: importlib.metadata.version(p) for p in ("pandas", "pyarrow", "pydantic", "fastapi")}},
        "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "datasets": [], "runs": [], "passed": True,
    }

    def execute(mode, dataset, count, result):
        command = [sys.executable, "-m", "scripts.benchmark", "--worker", mode,
                   "--dataset", str(dataset), "--count", str(count), "--seed", str(args.seed),
                   "--result", str(result), "--as-of", cutoff]
        with result.with_suffix(".log").open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        return json.loads(result.read_text(encoding="utf-8"))

    def new_dataset(path):
        path.mkdir()
        (path / ".benchmark-dataset").write_text("Isolated benchmark data", encoding="utf-8")

    print(f"Benchmark output: {output}", flush=True)
    for count in args.sizes:
        base = output / f"seed-{count}"
        new_dataset(base)
        print(f"Generating {count:,} events", flush=True)
        generated = execute("generate", base, count, output / f"generated-{count}.json")
        report["datasets"].append(generated)
        reference = None
        for repeat in range(1, args.repeats + 1):
            dataset = output / f"data-{count}-{repeat}"
            new_dataset(dataset)
            with sqlite3.connect(base / "app.sqlite3") as src, sqlite3.connect(dataset / "app.sqlite3") as dest:
                src.backup(dest)
            first = None
            for phase in ("first_load", "rerun"):
                print(f"{count:,} events, repeat {repeat}/{args.repeats}, {phase}", flush=True)
                r = execute("pipeline", dataset, count, output / f"run-{count}-{repeat}-{phase}.json")
                r.update({"count": count, "repeat": repeat, "phase": phase})
                if reference is None:
                    reference = r["fingerprints"]
                r["checks"]["same_logical_output_all_runs"] = r["fingerprints"] == reference
                if phase == "rerun":
                    r["checks"]["bronze_unchanged"] = (r["bronze_files"] == first["bronze_files"]
                        and r["storage_bytes"]["bronze"] == first["storage_bytes"]["bronze"])
                first = r
                report["runs"].append(r)
                report["passed"] = report["passed"] and all(r["checks"].values())
                write_json(output / "results.json", report)
    report["summary"] = summarize(report["runs"])
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "results.json", report)
    (output / "report.md").write_text(markdown(report), encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}: {output / 'report.md'}", flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
