from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Iterator


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False))
            handle.write("\n")
            count += 1
    return count


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def approx_tokenize(text: str, language: str) -> list[str]:
    if language == "zh":
        return re.findall(r"[\u3400-\u9fff]|[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:\.\d+)?|[^\s]", text)
    return re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:\.\d+)?|[^\w\s]", text)


def approx_token_count(text: str, language: str) -> int:
    return len(approx_tokenize(text, language))


def normalize_answer(text: str, language: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "", text) if language == "zh" else re.sub(r"\s+", " ", text)
    return re.sub(r"[^\w\u3400-\u9fff]", "", text)


def stable_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result
