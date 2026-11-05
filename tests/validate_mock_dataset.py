
import argparse
import hashlib
import json

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from backend.db import records
from backend.schemas import Event
from backend.settings import layer


class DataQualityValidator:
    def __init__(self):
        self.errors = []
        self.stats = Counter()

    def add_error(self, rule, message):
        self.errors.append({
            "rule": rule,
            "message": message
        })

    # ---------------------------------------
    # 1. SCHEMA VALIDATION
    # ---------------------------------------

    def validate_schema(self, event, line_number):
        try:
            Event.model_validate(event)
            self.stats["valid_schema"] += 1
            return True

        except (ValidationError, ValueError, TypeError) as exc:
            self.add_error(
                "SCHEMA",
                f"Line {line_number}: {exc}"
            )
            return False

    # ---------------------------------------
    # 2. DUPLICATE VALIDATION
    # ---------------------------------------

    def validate_duplicates(self, events):
        seen = set()

        for event in events:
            eid = event.get("event_id")

            if eid is None:
                continue

            if eid in seen:
                self.add_error(
                    "DUPLICATE",
                    f"Duplicate event_id: {eid}"
                )
                self.stats["duplicate_events"] += 1

            seen.add(eid)

    # ---------------------------------------
    # 3. REFERENTIAL INTEGRITY
    # ---------------------------------------

    def validate_references(
        self, events, user_ids, product_ids
    ):
        for event in events:
            uid = event.get("distinct_id")
            pid = event.get("product_id")

            if uid not in user_ids:
                self.add_error(
                    "USER_REFERENCE",
                    f"Unknown user: {uid}"
                )

            if pid is not None and pid not in product_ids:
                self.add_error(
                    "PRODUCT_REFERENCE",
                    f"Unknown product: {pid}"
                )

    # ---------------------------------------
    # 4. TIMESTAMP VALIDATION
    # ---------------------------------------

    def validate_timestamps(self, events):
        last_timestamp = {}

        for event in events:
            sid = event.get("session_id")
            raw_timestamp = event.get("timestamp")

            if not sid or not raw_timestamp:
                continue

            try:
                ts = datetime.fromisoformat(raw_timestamp)

                if ts.tzinfo is None:
                    raise ValueError("Missing timezone")

            except (ValueError, TypeError):
                self.add_error(
                    "TIMESTAMP",
                    f"Invalid timestamp: {raw_timestamp}"
                )
                continue

            if sid in last_timestamp:
                if ts <= last_timestamp[sid]:
                    self.add_error(
                        "TIMESTAMP_ORDER",
                        f"Non-increasing timestamp in session {sid}"
                    )

            last_timestamp[sid] = ts

    # ---------------------------------------
    # 5. BEHAVIORAL CONSISTENCY
    # ---------------------------------------

    def validate_behavior(self, events):
        """
        Kiểm tra event sequence theo
        (session_id, product_id).

        Không bắt buộc session kết thúc bằng purchase.
        """

        states = defaultdict(set)

        prerequisites = {
            "product_click": {"product_impression"},
            "product_view": {"product_click"},
            "add_to_wishlist": {"product_view"},
            "add_to_cart": {"product_view"},
            "purchase": {"add_to_cart"},
        }

        for event in events:
            name = event.get("event_name")
            sid = event.get("session_id")
            pid = event.get("product_id")

            if not sid or not pid or not name:
                continue

            key = (sid, pid)
            previous = states[key]

            required = prerequisites.get(name, set())

            missing = required - previous

            if missing:
                self.add_error(
                    "BEHAVIOR",
                    (
                        f"Session {sid}, product {pid}: "
                        f"{name} missing {sorted(missing)}"
                    )
                )

            # Không cho phép lặp hành động trong cùng
            # cặp session/product với simulator hiện tại.
            if name in previous:
                self.add_error(
                    "BEHAVIOR_DUPLICATE",
                    (
                        f"Repeated {name} in "
                        f"session {sid}, product {pid}"
                    )
                )

            previous.add(name)

    # ---------------------------------------
    # 6. GROUND TRUTH INTEGRITY
    # ---------------------------------------

    def validate_ground_truth(
        self, events, ground_truth_dir
    ):
        session_path = (
            ground_truth_dir / "session_profiles.json"
        )

        user_path = (
            ground_truth_dir / "user_profiles.json"
        )

        if not session_path.exists():
            self.add_error(
                "GROUND_TRUTH",
                "Missing session_profiles.json"
            )
            return

        if not user_path.exists():
            self.add_error(
                "GROUND_TRUTH",
                "Missing user_profiles.json"
            )
            return

        sessions = json.loads(
            session_path.read_text(encoding="utf-8")
        )

        users = json.loads(
            user_path.read_text(encoding="utf-8")
        )

        gt_sessions = {}

        for session in sessions:
            sid = session["session_id"]

            if sid in gt_sessions:
                self.add_error(
                    "GROUND_TRUTH_DUPLICATE",
                    f"Duplicate session profile: {sid}"
                )

            gt_sessions[sid] = session

        gt_users = {
            user["user_id"]
            for user in users
        }

        for event in events:
            sid = event.get("session_id")
            uid = event.get("distinct_id")

            if not sid or not uid:
                continue

            if sid not in gt_sessions:
                self.add_error(
                    "GROUND_TRUTH_REFERENCE",
                    f"Missing GT session: {sid}"
                )
                continue

            if uid != gt_sessions[sid]["user_id"]:
                self.add_error(
                    "GROUND_TRUTH_USER",
                    f"User mismatch in session {sid}"
                )

            if uid not in gt_users:
                self.add_error(
                    "GROUND_TRUTH_USER",
                    f"Missing GT user: {uid}"
                )

        event_sessions = {
            e["session_id"]
            for e in events
            if e.get("session_id")
        }

        extra_sessions = set(gt_sessions) - event_sessions

        if extra_sessions:
            self.add_error(
                "GROUND_TRUTH_EXTRA",
                (
                    f"{len(extra_sessions)} GT sessions "
                    "have no events"
                )
            )

        self.stats["gt_users"] = len(users)
        self.stats["gt_sessions"] = len(sessions)

    # ---------------------------------------
    # 7. DATASET VALIDATION
    # ---------------------------------------

    def validate_dataset(self, dataset_dir):
        dataset_dir = Path(dataset_dir)

        event_path = dataset_dir / "events.jsonl"
        manifest_path = dataset_dir / "manifest.json"

        if not event_path.exists():
            raise FileNotFoundError(event_path)

        if not manifest_path.exists():
            raise FileNotFoundError(manifest_path)

        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

        payload = event_path.read_bytes()
        actual_hash = hashlib.sha256(payload).hexdigest()

        if actual_hash != manifest.get("sha256"):
            self.add_error(
                "EVENT_HASH",
                "events.jsonl SHA-256 mismatch"
            )

        events = []

        for line_number, line in enumerate(
            payload.decode("utf-8").splitlines(), 1
        ):
            if not line.strip():
                self.add_error(
                    "EMPTY_LINE",
                    f"Empty line {line_number}"
                )
                continue

            try:
                event = json.loads(line)

                if not isinstance(event, dict):
                    raise ValueError(
                        "Event must be a JSON object"
                    )

                events.append(event)

                self.validate_schema(
                    event, line_number
                )

            except (json.JSONDecodeError, ValueError) as exc:
                self.add_error(
                    "JSON",
                    f"Line {line_number}: {exc}"
                )

        self.stats["events"] = len(events)

        if len(events) != manifest.get("count"):
            self.add_error(
                "EVENT_COUNT",
                (
                    f"Expected {manifest.get('count')}, "
                    f"found {len(events)}"
                )
            )

        # Đọc catalog thực tế từ SQLite
        users = records("users")
        products = records("products")

        user_ids = {
            u["id"] for u in users
        }

        product_ids = {
            p["id"] for p in products
        }

        # Kiểm tra catalog có khớp manifest
        catalog_hash = hashlib.sha256(
            json.dumps(
                products, sort_keys=True
            ).encode()
        ).hexdigest()

        if catalog_hash != manifest.get("catalog_sha256"):
            self.add_error(
                "CATALOG_HASH",
                "Catalog does not match dataset manifest"
            )

        self.validate_duplicates(events)

        self.validate_references(
            events, user_ids, product_ids
        )

        self.validate_timestamps(events)
        self.validate_behavior(events)

        # Ground Truth chỉ có ở attribute_based
        if manifest.get("ground_truth_exported"):

            gt_dir = (
                layer("mock")
                / "ground_truth"
                / dataset_dir.name
            )

            self.validate_ground_truth(
                events, gt_dir
            )

        self.stats["sessions"] = len({
            e.get("session_id")
            for e in events
            if e.get("session_id")
        })

        if self.stats["sessions"] != manifest.get("sessions"):
            self.add_error(
                "SESSION_COUNT",
                "Session count does not match manifest"
            )

        return self.report()

    # ---------------------------------------
    # 8. VALIDATION REPORT
    # ---------------------------------------

    def report(self):
        status = "PASS" if not self.errors else "FAIL"

        result = {
            "status": status,
            "statistics": dict(self.stats),
            "error_count": len(self.errors),
            "errors": self.errors[:100],
        }

        print("\n========== DATA QUALITY REPORT ==========")
        print(f"Status: {status}")
        print(f"Events: {self.stats['events']}")
        print(f"Sessions: {self.stats['sessions']}")
        print(f"Valid schema: {self.stats['valid_schema']}")
        print(f"Errors: {len(self.errors)}")

        if self.errors:
            print("\nFirst 10 errors:")

            for error in self.errors[:10]:
                print(
                    f"[{error['rule']}] {error['message']}"
                )

        return result


# ==========================================
# COMMAND LINE
# ==========================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Directory containing events.jsonl and manifest.json"
    )

    args = parser.parse_args()

    validator = DataQualityValidator()
    result = validator.validate_dataset(
        args.dataset_dir
    )

    report_path = args.dataset_dir / "data_quality_report.json"

    report_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"Report saved: {report_path}")

    raise SystemExit(
        0 if result["status"] == "PASS" else 1
    )
