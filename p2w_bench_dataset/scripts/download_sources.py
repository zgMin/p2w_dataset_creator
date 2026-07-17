#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p2w_bench.common import load_json, sha256_file, write_json  # noqa: E402


def download(url: str, destination: Path, retries: int = 4) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "P2W-Bench/0.1 (+dataset research pipeline)"},
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            if temporary.stat().st_size == 0:
                raise OSError("downloaded file is empty")
            os.replace(temporary, destination)
            return
        except (OSError, urllib.error.URLError) as exc:
            temporary.unlink(missing_ok=True)
            if attempt == retries:
                raise RuntimeError(f"Failed to download {url}: {exc}") from exc
            time.sleep(2**attempt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download public source datasets for P2W-Bench.")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark_config.json")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config = load_json(args.config)
    manifest: dict[str, object] = {"dataset_version": config["version"], "sources": {}}
    for source_name, source in config["sources"].items():
        destination = args.raw_dir / source["filename"]
        if args.force or not destination.exists() or destination.stat().st_size == 0:
            print(f"Downloading {source_name} -> {destination}")
            download(source["url"], destination)
        else:
            print(f"Using cached {source_name} -> {destination}")
        try:
            recorded_path = str(destination.resolve().relative_to(ROOT))
        except ValueError:
            recorded_path = str(destination.resolve())
        manifest["sources"][source_name] = {
            **source,
            "path": recorded_path,
            "bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
        }

    write_json(args.raw_dir / "download_manifest.json", manifest)
    print(json.dumps({"downloaded_sources": len(config["sources"]), "raw_dir": str(args.raw_dir)}, indent=2))


if __name__ == "__main__":
    main()
