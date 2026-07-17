#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p2w_bench.common import iter_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a flattened dataset by answer verifiability.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "final")
    args = parser.parse_args()
    final_dir = args.data_dir
    source_path = final_dir / "dataset.jsonl"
    rows = list(iter_jsonl(source_path))
    verifiable = [row for row in rows if bool(row.get("gold_answers"))]
    nonverifiable = [row for row in rows if not row.get("gold_answers")]

    verifiable_path = final_dir / "answer_verifiable.jsonl"
    nonverifiable_path = final_dir / "answer_nonverifiable.jsonl"
    write_jsonl(verifiable_path, verifiable)
    write_jsonl(nonverifiable_path, nonverifiable)

    manifest = {
        "criterion": "A row is answer-verifiable iff gold_answers is a non-empty list.",
        "source_file": source_path.name,
        "source_count": len(rows),
        "answer_verifiable": {
            "file": verifiable_path.name,
            "count": len(verifiable),
            "sha256": sha256_file(verifiable_path),
            "by_language": dict(sorted(Counter(row["language"] for row in verifiable).items())),
            "by_subtype": dict(sorted(Counter(row["subtype"] for row in verifiable).items())),
        },
        "answer_nonverifiable": {
            "file": nonverifiable_path.name,
            "count": len(nonverifiable),
            "sha256": sha256_file(nonverifiable_path),
            "by_language": dict(sorted(Counter(row["language"] for row in nonverifiable).items())),
            "by_task_family": dict(sorted(Counter(row["task_family"] for row in nonverifiable).items())),
        },
    }
    write_json(final_dir / "answer_verifiability_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
