#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *arguments: str) -> None:
    command = [sys.executable, str(ROOT / "scripts" / script), *arguments]
    print(f"\n$ {' '.join(command)}")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download, build, split, and validate P2W-Bench.")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark_config.json")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--interim-dir", type=Path, default=ROOT / "data" / "interim")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "final")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    common = ["--config", str(args.config), "--raw-dir", str(args.raw_dir)]
    if not args.skip_download:
        download_args = [*common]
        if args.force_download:
            download_args.append("--force")
        run("download_sources.py", *download_args)
    run(
        "build_dataset.py",
        *common,
        "--interim-dir",
        str(args.interim_dir),
        "--output-dir",
        str(args.output_dir),
    )
    run("split_by_answer_verifiability.py", "--data-dir", str(args.output_dir))
    run("validate_dataset.py", *common, "--data-dir", str(args.output_dir))


if __name__ == "__main__":
    main()
