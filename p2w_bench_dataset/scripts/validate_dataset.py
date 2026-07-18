#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p2w_bench.common import iter_jsonl, load_json, normalize_answer, sha256_file  # noqa: E402


def unique_index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise AssertionError(f"Duplicate {key}: {value}")
        result[value] = row
    return result


def length_bounds(config: dict[str, Any], family: str, variant_name: str) -> dict[str, int]:
    family_bounds = config.get("length_variants_by_family", {}).get(family, {})
    return family_bounds.get(variant_name, config["length_variants"][variant_name])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate P2W-Bench structure and construction invariants.")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark_config.json")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "final")
    args = parser.parse_args()

    config = load_json(args.config)
    queries = list(iter_jsonl(args.data_dir / "queries_zh.jsonl")) + list(iter_jsonl(args.data_dir / "queries_en.jsonl"))
    groups = list(iter_jsonl(args.data_dir / "prompt_groups.jsonl"))
    variants = list(iter_jsonl(args.data_dir / "prompt_variants.jsonl"))
    pairings = list(iter_jsonl(args.data_dir / "pairings.jsonl"))
    flattened = list(iter_jsonl(args.data_dir / "dataset.jsonl"))
    answer_verifiable = list(iter_jsonl(args.data_dir / "answer_verifiable.jsonl"))
    answer_nonverifiable = list(iter_jsonl(args.data_dir / "answer_nonverifiable.jsonl"))

    query_index = unique_index(queries, "query_id")
    group_index = unique_index(groups, "prompt_group_id")
    variant_index = unique_index(variants, "prompt_variant_id")
    pairing_index = unique_index(pairings, "pair_id")

    counts = config["counts_per_language"]
    qpi = {
        family: int(config.get("queries_per_instruction", {}).get(family, 1))
        for family in ["knowledge", "descriptive", "style", "format", "output_control"]
    }
    knowledge_count = counts["knowledge_public"] + counts["knowledge_synthetic"]
    instruction_count_per_language = knowledge_count + sum(
        counts[family] for family in ["descriptive", "style", "format", "output_control"]
    )
    query_count_per_language = knowledge_count + sum(
        counts[family] * qpi[family]
        for family in ["descriptive", "style", "format", "output_control"]
    )
    expected_groups = instruction_count_per_language * len(config["languages"])
    expected_queries = query_count_per_language * len(config["languages"])
    expected_variants = expected_groups * len(config["length_variants"])
    expected_pairings = expected_queries * len(config["length_variants"])
    assert len(queries) == expected_queries, (len(queries), expected_queries)
    assert len(groups) == expected_groups
    assert len(variants) == expected_variants
    assert len(pairings) == expected_pairings
    assert len(flattened) == expected_pairings
    assert len(answer_verifiable) + len(answer_nonverifiable) == len(flattened)
    assert {row["pair_id"] for row in answer_verifiable}.isdisjoint(
        {row["pair_id"] for row in answer_nonverifiable}
    )
    assert {row["pair_id"] for row in answer_verifiable + answer_nonverifiable} == {
        row["pair_id"] for row in flattened
    }
    assert all(row.get("gold_answers") for row in answer_verifiable)
    assert all(not row.get("gold_answers") for row in answer_nonverifiable)
    assert len(pairing_index) == expected_pairings

    queries_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in queries:
        assert row["prompt_group_id"] in group_index
        queries_by_group[row["prompt_group_id"]].append(row)
    for row in groups:
        assert "query_id" not in row
        assigned = queries_by_group[row["prompt_group_id"]]
        expected_assigned = 1 if row["task_family"] == "knowledge" else qpi[row["task_family"]]
        assert len(assigned) == expected_assigned, (row["prompt_group_id"], len(assigned), expected_assigned)
        assert sorted(query["query_index_within_group"] for query in assigned) == list(
            range(1, expected_assigned + 1)
        )
        if row["task_family"] == "knowledge":
            normalized_prompt = normalize_answer(row["core_prompt"], row["language"])
            for query in assigned:
                assert any(
                    normalize_answer(answer, row["language"]) in normalized_prompt
                    for answer in query["gold_answers"]
                ), f"Gold answer was clipped out of {row['prompt_group_id']}"
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in variants:
        assert row["prompt_group_id"] in group_index
        by_group[row["prompt_group_id"]].append(row)
        bounds = length_bounds(config, row["task_family"], row["length_variant"])
        assert bounds["min_tokens"] <= row["prompt_approx_tokens"] <= bounds["max_tokens"], (
            row["prompt_variant_id"],
            row["prompt_approx_tokens"],
            bounds,
        )
        assert "full_input" not in row and "full_prompt_output" not in row
    for group_id, rows in by_group.items():
        assert set(row["length_variant"] for row in rows) == set(config["length_variants"])
        assert len(set(row["semantic_signature"] for row in rows)) == 1
        ordered = sorted(rows, key=lambda row: list(config["length_variants"]).index(row["length_variant"]))
        counts = [row["prompt_approx_tokens"] for row in ordered]
        assert counts == sorted(counts), (group_id, counts)

    for row in pairings:
        assert row["query_id"] in query_index
        assert row["prompt_group_id"] in group_index
        assert row["prompt_variant_id"] in variant_index
        assert row["validator"].get("type")
        assert query_index[row["query_id"]]["prompt_group_id"] == row["prompt_group_id"]
        assert variant_index[row["prompt_variant_id"]]["prompt_group_id"] == row["prompt_group_id"]
    expected_cartesian = {
        (variant["prompt_variant_id"], query["query_id"])
        for variant in variants
        for query in queries_by_group[variant["prompt_group_id"]]
    }
    actual_cartesian = {(row["prompt_variant_id"], row["query_id"]) for row in pairings}
    assert actual_cartesian == expected_cartesian
    assert all("prompt" in row and "query" in row for row in flattened)
    assert all("full_input" not in row and "full_prompt_output" not in row for row in flattened)

    public_ratio = sum(bool(row["is_public_query"]) for row in queries) / len(queries)
    assert public_ratio >= 0.8, public_ratio
    expected_controls = {"fixed_prefix", "fixed_suffix", "item_marker", "exactly_two"}
    for language in config["languages"]:
        found = {row["subtype"] for row in groups if row["language"] == language and row["task_family"] == "output_control"}
        assert found == expected_controls, (language, found)

    manifest = load_json(args.raw_dir / "download_manifest.json")
    for source_name, source in manifest["sources"].items():
        path = ROOT / source["path"]
        assert path.exists(), f"Missing raw source: {source_name}"
        assert sha256_file(path) == source["sha256"], f"Checksum mismatch: {source_name}"

    build_manifest = load_json(args.data_dir / "build_manifest.json")
    for filename, metadata in build_manifest["files"].items():
        path = args.data_dir / filename
        assert path.exists(), f"Missing final artifact: {filename}"
        assert sha256_file(path) == metadata["sha256"], f"Final artifact checksum mismatch: {filename}"

    report = {
        "status": "ok",
        "queries": len(queries),
        "prompt_groups": len(groups),
        "prompt_variants": len(variants),
        "pairings": len(pairings),
        "public_query_ratio": public_ratio,
        "query_family_counts": dict(sorted(Counter(f"{row['language']}/{row['task_family']}" for row in queries).items())),
        "instruction_family_counts": dict(sorted(Counter(f"{row['language']}/{row['task_family']}" for row in groups).items())),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
