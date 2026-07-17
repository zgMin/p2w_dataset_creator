#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import re
import shutil
import time
import urllib.request
from collections import Counter
from html import unescape
from pathlib import Path
from typing import Any, Iterable, Iterator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT.parent / "p2w_bench_dataset" / "data" / "final" / "answer_verifiable.jsonl"

MULTI_ANSWER_RE = re.compile(
    r"\b(two|three|four|five|both|list|name all|which countries|what countries|what are the|who are the)\b",
    re.IGNORECASE,
)
REGEX_META_RE = re.compile(r"\\|\.\*|\.\+|\[|\]|\(|\)|\||\?|\^|\$")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(text))).strip()


def normalize_answer(text: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", normalize_space(text).lower())


def stable_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = normalize_space(value)
        key = normalize_answer(value)
        if value and key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def valid_download(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    if path.suffix != ".gz":
        return True
    try:
        with gzip.open(path, "rb") as handle:
            for _ in iter(lambda: handle.read(1024 * 1024), b""):
                pass
        return True
    except (EOFError, OSError):
        return False


def download(url: str, destination: Path) -> None:
    if valid_download(destination):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    destination.unlink(missing_ok=True)
    for attempt in range(1, 4):
        partial.unlink(missing_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "p2w-verifiable-builder/1.0"})
        try:
            with urllib.request.urlopen(request) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            partial.replace(destination)
            if valid_download(destination):
                return
        except (EOFError, OSError):
            pass
        destination.unlink(missing_ok=True)
        time.sleep(attempt)
    raise RuntimeError(f"failed to download a complete file after 3 attempts: {url}")


def iter_gzip_json_array(path: Path) -> Iterator[dict[str, Any]]:
    """Incrementally decode a top-level JSON array without loading it into RAM."""
    decoder = json.JSONDecoder()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        buffer = ""
        started = False
        finished = False
        while not finished:
            chunk = handle.read(1024 * 1024)
            if chunk:
                buffer += chunk
            elif not buffer.strip():
                break
            offset = 0
            while True:
                while offset < len(buffer) and (buffer[offset].isspace() or buffer[offset] == ","):
                    offset += 1
                if not started:
                    if offset >= len(buffer):
                        break
                    if buffer[offset] != "[":
                        raise ValueError(f"{path} does not contain a top-level JSON array")
                    started = True
                    offset += 1
                    continue
                while offset < len(buffer) and (buffer[offset].isspace() or buffer[offset] == ","):
                    offset += 1
                if offset < len(buffer) and buffer[offset] == "]":
                    finished = True
                    offset += 1
                    break
                if offset >= len(buffer):
                    break
                try:
                    item, end = decoder.raw_decode(buffer, offset)
                except json.JSONDecodeError:
                    break
                if not isinstance(item, dict):
                    raise ValueError(f"unexpected non-object item in {path}")
                yield item
                offset = end
            buffer = buffer[offset:]
            if not chunk and not finished:
                raise ValueError(f"truncated JSON array in {path}")


def answer_in_context(answers: list[str], context: str) -> bool:
    normalized_context = normalize_answer(context)
    for answer in answers:
        if normalize_answer(answer) in normalized_context:
            return True
        if REGEX_META_RE.search(answer):
            pattern = re.sub(r"\.\*[?$]?\s*$", "", answer)
            try:
                if re.search(pattern, context, re.IGNORECASE):
                    return True
            except re.error:
                pass
    return False


def canonical_answers(answers: list[str], context: str) -> list[str]:
    canonical: list[str] = []
    for answer in answers:
        if not REGEX_META_RE.search(answer):
            canonical.append(answer)
            continue
        pattern = re.sub(r"\.\*[?$]?\s*$", "", answer)
        try:
            match = re.search(pattern, context, re.IGNORECASE)
        except re.error:
            match = None
        if match:
            canonical.append(match.group(0))
    return stable_unique(canonical)


def valid_common(query: str, answers: list[str], language: str, selection: dict[str, int]) -> bool:
    if not query or not answers or MULTI_ANSWER_RE.search(query):
        return False
    if language == "en":
        if len(query.split()) > selection["max_query_words"]:
            return False
        return min(len(answer.split()) for answer in answers) <= selection["max_answer_words"]
    if len(query) > selection["max_query_chars"]:
        return False
    return min(len(answer) for answer in answers) <= selection["max_answer_chars"]


def parse_dpr_rows(path: Path, source: str, selection: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(iter_gzip_json_array(path)):
        query = normalize_space(item.get("question", ""))
        answers = stable_unique(item.get("answers", []))
        if not valid_common(query, answers, "en", selection):
            continue
        positive = next(
            (
                context
                for context in item.get("positive_ctxs", [])
                if answer_in_context(answers, normalize_space(context.get("text", "")))
            ),
            None,
        )
        if positive is None:
            continue
        context = normalize_space(positive.get("text", ""))
        answers = canonical_answers(answers, context)
        if not answers:
            continue
        if not context or len(context.split()) > selection["max_english_context_words"]:
            continue
        title = normalize_space(positive.get("title", ""))
        rows.append(
            {
                "source": source,
                "source_id": f"{source}-{index:06d}",
                "source_group": title or str(positive.get("psg_id", index)),
                "source_title": title,
                "language": "en",
                "query": query,
                "context": context,
                "gold_answers": answers,
                "is_public_query": True,
            }
        )
    return rows


def clip_english_context(context: str, answer: str, max_words: int) -> str:
    words = context.split()
    if len(words) <= max_words:
        return context
    lower_words = [word.lower() for word in words]
    answer_words = answer.lower().split()
    position = next(
        (index for index in range(len(words)) if lower_words[index : index + len(answer_words)] == answer_words),
        len(words) // 2,
    )
    start = max(0, position - max_words // 2)
    end = min(len(words), start + max_words)
    start = max(0, end - max_words)
    return ("... " if start else "") + " ".join(words[start:end]) + (" ..." if end < len(words) else "")


def parse_mrqa_rows(path: Path, source: str, selection: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for context_index, line in enumerate(handle):
            item = json.loads(line)
            if "header" in item:
                continue
            raw_context = normalize_space(re.sub(r"</?[^>]+>", " ", str(item.get("context", ""))))
            for qa in item.get("qas", []):
                query = normalize_space(qa.get("question", ""))
                detected = stable_unique(answer.get("text", "") for answer in qa.get("detected_answers", []))
                # MRQA's detected answers are exact context spans. Original aliases
                # can include distant-supervision noise, so scoring uses spans only.
                answers = detected
                if not detected or not valid_common(query, answers, "en", selection):
                    continue
                context = clip_english_context(raw_context, detected[0], selection["max_english_context_words"])
                if not answer_in_context(answers, context):
                    continue
                rows.append(
                    {
                        "source": source,
                        "source_id": str(qa.get("qid", f"{source}-{context_index:06d}")),
                        "source_group": f"{source}-context-{context_index:06d}",
                        "source_title": "",
                        "language": "en",
                        "query": query,
                        "context": context,
                        "gold_answers": answers,
                        "is_public_query": True,
                    }
                )
    return rows


def parse_squad_rows(path: Path, source: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for article in payload.get("data", []):
        title = normalize_space(article.get("title", ""))
        for paragraph in article.get("paragraphs", []):
            context = normalize_space(paragraph.get("context", ""))
            for qa in paragraph.get("qas", []):
                answers = stable_unique(answer.get("text", "") for answer in qa.get("answers", []))
                rows.append(
                    {
                        "source": source,
                        "source_id": str(qa.get("id", "")),
                        "source_group": title,
                        "source_title": title,
                        "language": "zh",
                        "query": normalize_space(qa.get("question", "")),
                        "context": context,
                        "gold_answers": answers,
                        "is_public_query": True,
                    }
                )
    return rows


def clip_chinese_context(context: str, answers: list[str], max_chars: int) -> str:
    if len(context) <= max_chars:
        return context
    position = next((context.find(answer) for answer in answers if context.find(answer) >= 0), len(context) // 2)
    start = max(0, position - max_chars // 2)
    end = min(len(context), start + max_chars)
    start = max(0, end - max_chars)
    return ("..." if start else "") + context[start:end].strip() + ("..." if end < len(context) else "")


def select_diverse(
    rows: list[dict[str, Any]],
    count: int,
    rng: random.Random,
    excluded_ids: set[tuple[str, str]],
    selection: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates = [
        row
        for row in rows
        if (row["source"], row["source_id"]) not in excluded_ids
        and valid_common(row["query"], row["gold_answers"], row["language"], selection)
        and answer_in_context(row["gold_answers"], row["context"])
    ]
    rng.shuffle(candidates)
    selected: list[dict[str, Any]] = []
    groups: set[str] = set()
    queries: set[str] = set()
    for row in candidates:
        query_key = normalize_answer(row["query"])
        if query_key in queries or row["source_group"] in groups:
            continue
        selected.append(row)
        queries.add(query_key)
        groups.add(row["source_group"])
        if len(selected) == count:
            break
    if len(selected) < count:
        # Prefer distinct contexts, then relax only that preference. Query text
        # remains unique, so increasing a source count does not duplicate tasks.
        for row in candidates:
            query_key = normalize_answer(row["query"])
            if query_key in queries:
                continue
            selected.append(row)
            queries.add(query_key)
            if len(selected) == count:
                break
    capacity = {
        "eligible_rows": len(candidates),
        "unique_queries": len({normalize_answer(row["query"]) for row in candidates}),
        "unique_context_groups": len({row["source_group"] for row in candidates}),
        "requested": count,
        "selected": len(selected),
    }
    if len(selected) != count:
        raise ValueError(
            f"requested {count} rows but source capacity is {capacity['unique_queries']} unique queries"
        )
    return selected, capacity


def knowledge_prompt(row: dict[str, Any], selection: dict[str, int]) -> str:
    if row["language"] == "zh":
        context = clip_chinese_context(row["context"], row["gold_answers"], selection["max_chinese_context_chars"])
        return f"资料：{context}\n请仅依据资料回答查询。"
    title = f" ({row['source_title']})" if row.get("source_title") else ""
    return f"Reference{title}: {row['context']}\nAnswer the query using only the reference."


def format_row(row: dict[str, Any], selection: dict[str, int]) -> dict[str, Any]:
    identity = f"{row['source']}\0{row['source_id']}".encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()[:12]
    query_id = f"{row['language']}-{row['source'].replace('_', '-')}-{suffix}"
    return {
        "pair_id": f"pair--{query_id}",
        "query_id": query_id,
        "prompt_variant_id": f"{query_id}--single",
        "language": row["language"],
        "task_family": "knowledge",
        "subtype": "public_extractive",
        "length_variant": "single",
        "source": row["source"],
        "source_id": row["source_id"],
        "source_title": row.get("source_title", ""),
        "dataset_partition": "expanded_public",
        "prompt": knowledge_prompt(row, selection),
        "query": row["query"],
        "gold_answers": row["gold_answers"],
        "is_public_query": bool(row.get("is_public_query", True)),
    }


def parse_source(
    path: Path,
    source: str,
    source_config: dict[str, Any],
    selection: dict[str, int],
) -> list[dict[str, Any]]:
    parser_name = source_config["parser"]
    if parser_name == "mrqa":
        return parse_mrqa_rows(path, source, selection)
    if parser_name == "squad_zh":
        return parse_squad_rows(path, source)
    raise ValueError(f"Unsupported parser {parser_name!r} for source {source!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--base-dataset", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "final")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    rng = random.Random(config["seed"])
    counts = config["additional_counts"]
    unknown_counts = set(counts) - set(config["sources"])
    if unknown_counts:
        raise ValueError(f"additional_counts contains unknown sources: {sorted(unknown_counts)}")
    for source_name, source in config["sources"].items():
        if int(counts.get(source_name, 0)) <= 0:
            continue
        path = args.raw_dir / source["filename"]
        if args.no_download:
            if not valid_download(path):
                raise FileNotFoundError(f"Missing source while --no-download is set: {path}")
        else:
            download(source["url"], path)

    base_config = config.get(
        "base_rows",
        {"length_variant": "short", "limit": config.get("base_short_count", 0)},
    )
    available_base_rows = [
        row
        for row in read_jsonl(args.base_dataset)
        if row.get("length_variant") == base_config["length_variant"]
    ]
    base_limit = base_config.get("limit")
    if base_limit is None:
        base_rows = available_base_rows
    else:
        base_limit = int(base_limit)
        if base_limit > len(available_base_rows):
            raise ValueError(
                f"requested {base_limit} base rows, found {len(available_base_rows)} "
                f"for length_variant={base_config['length_variant']!r}"
            )
        base_rows = available_base_rows[:base_limit]
    excluded = {(row["source"], row["source_id"]) for row in base_rows}
    selection = config["selection"]

    selected: list[dict[str, Any]] = []
    capacity_by_source: dict[str, dict[str, int]] = {}
    for source, requested in counts.items():
        requested = int(requested)
        if requested < 0:
            raise ValueError(f"additional_counts.{source} cannot be negative")
        if requested == 0:
            capacity_by_source[source] = {
                "eligible_rows": 0,
                "unique_queries": 0,
                "unique_context_groups": 0,
                "requested": 0,
                "selected": 0,
            }
            continue
        source_config = config["sources"][source]
        rows = parse_source(
            args.raw_dir / source_config["filename"], source, source_config, selection
        )
        source_selected, capacity = select_diverse(rows, requested, rng, excluded, selection)
        selected.extend(source_selected)
        capacity_by_source[source] = capacity

    capacity_report = {
        "version": config["version"],
        "seed": config["seed"],
        "base": {
            "available": len(available_base_rows),
            "selected": len(base_rows),
            "length_variant": base_config["length_variant"],
        },
        "sources": capacity_by_source,
    }
    write_json(args.output_dir / "capacity_report.json", capacity_report)
    if args.plan_only:
        print(json.dumps(capacity_report, ensure_ascii=False, indent=2))
        return

    new_rows = [format_row(row, selection) for row in selected]
    combined = []
    for row in base_rows:
        retained = dict(row)
        retained["length_variant"] = "single"
        retained["prompt_variant_id"] = retained["query_id"] + "--single"
        retained["pair_id"] = "pair--" + retained["query_id"]
        retained["dataset_partition"] = "base_short"
        combined.append(retained)
    combined.extend(new_rows)
    combined.sort(key=lambda row: (row["language"], row["source"], row["query_id"]))

    expected = len(base_rows) + sum(int(value) for value in counts.values())
    if len(combined) != expected or len({row["pair_id"] for row in combined}) != expected:
        raise ValueError("combined row count or pair-id uniqueness check failed")
    for row in combined:
        if not row.get("gold_answers") or not row.get("prompt") or not row.get("query"):
            raise ValueError(f"incomplete row: {row.get('pair_id')}")

    output_path = args.output_dir / "answer_verifiable_expanded.jsonl"
    write_jsonl(output_path, combined)
    stats = {
        "version": config["version"],
        "seed": config["seed"],
        "row_count": len(combined),
        "query_count": len({row["query_id"] for row in combined}),
        "counts_by_language": dict(sorted(Counter(row["language"] for row in combined).items())),
        "counts_by_source": dict(sorted(Counter(row["source"] for row in combined).items())),
        "requested_additional_counts": {key: int(value) for key, value in counts.items()},
        "capacity_report": "capacity_report.json",
        "public_query_count": sum(bool(row.get("is_public_query")) for row in combined),
        "output_sha256": sha256_file(output_path),
    }
    write_json(args.output_dir / "stats.json", stats)
    write_json(
        args.output_dir / "source_manifest.json",
        {
            name: {**source, "sha256": sha256_file(args.raw_dir / source["filename"])}
            for name, source in config["sources"].items()
            if int(counts.get(name, 0)) > 0
        },
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
