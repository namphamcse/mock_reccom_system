from datetime import datetime, timezone
from uuid import uuid4

from pipeline.run_pipeline import run_pipeline
from pipeline.storage import append_bronze
from scripts.benchmark import peak_process_rss


def test_metrics_account_for_rejected_and_duplicate_rows(dataset):
    event = {"event_id": str(uuid4()), "timestamp": "2026-01-01T00:00:00+00:00",
             "distinct_id": "U0001", "product_id": "P0001",
             "event_name": "product_view", "source": "simulator", "synthetic": True}
    append_bronze([event, event, {**event, "event_id": str(uuid4()), "product_id": "missing"}])
    metrics = {}
    result = run_pipeline(source="bronze", as_of=datetime(2026, 2, 1, tzinfo=timezone.utc), metrics=metrics)
    assert result["events"] == 1
    quality = metrics["quality"]
    assert (quality["input_events"], quality["accepted_events"],
            quality["rejected_events"], quality["duplicate_events"]) == (3, 1, 1, 1)
    assert sum(quality["rejection_reasons"].values()) == 1
    times = metrics["seconds"]
    assert all(value >= 0 for value in times.values())
    assert abs(sum(times[k] for k in ("initialize", "bronze", "silver", "gold")) - times["total"]) < 1e-8


def test_metrics_for_empty_dataset_and_peak_memory(dataset):
    metrics = {}
    result = run_pipeline(metrics=metrics)
    assert result["events"] == metrics["quality"]["input_events"] == 0
    assert metrics["quality"]["rejection_reasons"] == {}
    assert peak_process_rss() > 0
