#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p2w_bench.common import iter_jsonl  # noqa: E402
from p2w_bench.output_validators import validate_output  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a P2W-Bench output validator.")
    parser.add_argument("pair_id")
    parser.add_argument("output_file", type=Path)
    parser.add_argument("--pairings", type=Path, default=ROOT / "data" / "final" / "pairings.jsonl")
    args = parser.parse_args()

    pairing = next((row for row in iter_jsonl(args.pairings) if row["pair_id"] == args.pair_id), None)
    if pairing is None:
        raise SystemExit(f"Unknown pair_id: {args.pair_id}")
    text = args.output_file.read_text(encoding="utf-8")
    passed, detail = validate_output(text, pairing["validator"])
    print(json.dumps({"pair_id": args.pair_id, "passed": passed, "detail": detail}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
