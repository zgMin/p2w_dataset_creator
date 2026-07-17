#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p2w_bench.common import (  # noqa: E402
    approx_token_count,
    iter_jsonl,
    load_json,
    normalize_answer,
    normalize_space,
    semantic_hash,
    sha256_file,
    stable_unique,
    write_json,
    write_jsonl,
)


FAMILY_ORDER = ["knowledge", "descriptive", "style", "format", "output_control"]

BELLE_SAFE_TASKS = [
    "explain_behavior",
    "explain_natural_phenomenon",
    "movie_ending",
    "why’s_it_not_funny",
    "coach_planning",
    "cooking_recipe",
    "one_sentence_description",
    "new_ice_cream",
    "cover_letter",
    "workout_motivation",
    "exercise_explanation",
    "pre-run_warmup",
    "birthday_planning_checklist",
    "game_suggestion",
    "snack_suggestion",
    "word_definition",
    "email_subject_generation",
    "start_conversation",
    "grocery_list",
    "fact_to_conversation",
    "new_year's_resolutions",
    "horror_movie_opening",
    "three_sentence_story",
    "meaning_to_phrase",
    "question-answer_jokes",
    "add_to_the_list",
]

DOLLY_CATEGORY_ORDER = [
    "summarization",
    "brainstorming",
    "creative_writing",
    "open_qa",
    "general_qa",
    "closed_qa",
    "information_extraction",
    "classification",
]

CONSTRAINT_TERMS = re.compile(
    r"\b(json|xml|markdown|lowercase|uppercase|exactly|prefix|suffix|format|words?|sentences?|bullet|numbered)\b",
    re.IGNORECASE,
)
ZH_CONSTRAINT_TERMS = re.compile(r"JSON|XML|Markdown|小写|大写|严格格式|恰好|前缀|后缀|字数|句数|编号列表")
HIGH_RISK_TERMS = re.compile(
    r"\b(diabetes|surgery|rupture|diagnos(?:e|is)|medication|prescription|disease|cancer|suicide|legal advice)\b",
    re.IGNORECASE,
)


def clip_context_around_answer(
    context: str,
    answer: str,
    language: str,
    max_tokens: int,
    answer_start: int | None = None,
) -> str:
    context = normalize_space(context)
    answer = normalize_space(answer)
    if approx_token_count(context, language) <= max_tokens:
        return context

    index = answer_start if answer_start is not None else -1
    if index < 0 or context[index : index + len(answer)].lower() != answer.lower():
        index = context.lower().find(answer.lower())
    if index < 0:
        index = len(context) // 2
    chars_per_token = 1.25 if language == "zh" else 5.5
    width = max(int(max_tokens * chars_per_token), len(answer) + 16)
    start = max(0, index - (width - len(answer)) // 2)
    end = min(len(context), start + width)
    start = max(0, end - width)
    excerpt = context[start:end].strip()

    if start > 0:
        excerpt = "..." + excerpt
    if end < len(context):
        excerpt += "..."
    return excerpt


def parse_squad_like(path: Path, source: str, language: str) -> list[dict[str, Any]]:
    payload = load_json(path)
    rows: list[dict[str, Any]] = []
    for article in payload.get("data", []):
        title = normalize_space(str(article.get("title", "")))
        for paragraph in article.get("paragraphs", []):
            raw_context = str(paragraph.get("context", ""))
            context = normalize_space(raw_context)
            for qa in paragraph.get("qas", []):
                answer_records = qa.get("answers", [])
                answers = stable_unique(str(item.get("text", "")) for item in answer_records)
                if not answers:
                    continue
                raw_start = int(answer_records[0].get("answer_start", -1)) if answer_records else -1
                normalized_start = None
                if raw_start >= 0:
                    target = len(normalize_space(raw_context[:raw_start]))
                    starts = [match.start() for match in re.finditer(re.escape(answers[0]), context, re.IGNORECASE)]
                    if starts:
                        normalized_start = min(starts, key=lambda value: abs(value - target))
                rows.append(
                    {
                        "source": source,
                        "source_id": str(qa.get("id", semantic_hash([title, qa.get("question")]))),
                        "source_group": title,
                        "language": language,
                        "query": normalize_space(str(qa.get("question", ""))),
                        "context": context,
                        "gold_answers": answers,
                        "answer_start": normalized_start,
                    }
                )
    return rows


def apply_knowledge_answer_aliases(rows: list[dict[str, Any]], aliases: dict[str, Any]) -> None:
    for row in rows:
        extra = aliases.get(row["source"], {}).get(row["source_id"], [])
        row["gold_answers"] = stable_unique([*row["gold_answers"], *extra])


def valid_knowledge_row(row: dict[str, Any], config: dict[str, Any]) -> bool:
    language = row["language"]
    query_tokens = approx_token_count(row["query"], language)
    answer_tokens = min(approx_token_count(answer, language) for answer in row["gold_answers"])
    selection = config["selection"]
    return (
        selection["min_query_tokens"] <= query_tokens <= selection["max_query_tokens"]
        and answer_tokens <= selection["max_answer_tokens"]
        and any(normalize_answer(answer, language) in normalize_answer(row["context"], language) for answer in row["gold_answers"])
    )


def select_diverse(rows: Iterable[dict[str, Any]], count: int, rng: random.Random) -> list[dict[str, Any]]:
    candidates = list(rows)
    rng.shuffle(candidates)
    chosen: list[dict[str, Any]] = []
    groups: set[str] = set()
    normalized_queries: set[str] = set()
    for row in candidates:
        key = normalize_space(row["query"]).lower()
        group = row.get("source_group", row["source_id"])
        if key in normalized_queries or group in groups:
            continue
        chosen.append(row)
        normalized_queries.add(key)
        groups.add(group)
        if len(chosen) == count:
            return chosen
    for row in candidates:
        key = normalize_space(row["query"]).lower()
        if key in normalized_queries:
            continue
        chosen.append(row)
        normalized_queries.add(key)
        if len(chosen) == count:
            return chosen
    raise ValueError(f"Only found {len(chosen)} diverse rows; requested {count}")


def select_knowledge_by_source(
    rows: list[dict[str, Any]],
    count: int,
    language: str,
    config: dict[str, Any],
    rng: random.Random,
) -> list[dict[str, Any]]:
    weights = config["knowledge_source_weights"][language]
    sources = list(weights)
    allocations = {source: int(count * float(weights[source])) for source in sources}
    remaining = count - sum(allocations.values())
    for source in sources[:remaining]:
        allocations[source] += 1

    chosen: list[dict[str, Any]] = []
    for source in sources:
        source_rows = [row for row in rows if row["source"] == source and valid_knowledge_row(row, config)]
        chosen.extend(select_diverse(source_rows, allocations[source], rng))
    if len(chosen) != count:
        raise ValueError(f"Knowledge source allocation produced {len(chosen)} rows; expected {count}")
    return chosen


def load_dolly_queries(path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    selection = config["selection"]
    for index, item in enumerate(iter_jsonl(path)):
        instruction = normalize_space(str(item.get("instruction", "")))
        context = normalize_space(str(item.get("context", "")))
        if not instruction or CONSTRAINT_TERMS.search(instruction) or HIGH_RISK_TERMS.search(instruction):
            continue
        query = instruction if not context else f"{instruction}\n\nTask context: {context}"
        tokens = approx_token_count(query, "en")
        if not selection["min_query_tokens"] <= tokens <= selection["max_query_tokens"]:
            continue
        rows.append(
            {
                "source": "dolly",
                "source_id": f"dolly-{index:05d}",
                "source_group": str(item.get("category", "unknown")),
                "source_category": str(item.get("category", "unknown")),
                "language": "en",
                "query": query,
            }
        )
    return rows


def load_belle_queries(path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    selection = config["selection"]
    for item in iter_jsonl(path):
        name = str(item.get("name", ""))
        if name not in BELLE_SAFE_TASKS or name in by_name:
            continue
        instruction = normalize_space(str(item.get("instruction", "")))
        instances = item.get("instances") or []
        instance_input = normalize_space(str(instances[0].get("input", ""))) if instances else ""
        if not instruction or ZH_CONSTRAINT_TERMS.search(instruction):
            continue
        query = instruction if not instance_input else f"{instruction}\n\n输入：{instance_input}"
        tokens = approx_token_count(query, "zh")
        if not selection["min_query_tokens"] <= tokens <= selection["max_query_tokens"]:
            continue
        by_name[name] = {
            "source": "belle_seed",
            "source_id": str(item.get("id", name)),
            "source_group": name,
            "source_category": name,
            "language": "zh",
            "query": query,
        }
    missing = [name for name in BELLE_SAFE_TASKS if name not in by_name]
    if len(by_name) < 22:
        raise ValueError(f"BELLE safe query pool is too small; missing examples include {missing[:5]}")
    return [by_name[name] for name in BELLE_SAFE_TASKS if name in by_name]


def repeat_to_count(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count == 0:
        return []
    if not rows:
        raise ValueError("Cannot allocate queries from an empty source pool")
    return [rows[index % len(rows)] for index in range(count)]


def select_general_queries(
    rows: list[dict[str, Any]],
    count: int,
    language: str,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if language == "zh":
        # BELLE seed tasks contain one instance per task. Reuse across different
        # prompt groups is therefore allowed, while a prompt group's own slice
        # remains unique as long as queries_per_instruction <= len(rows).
        return repeat_to_count(rows, count)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("source_category", "unknown")].append(row)
    for values in grouped.values():
        rng.shuffle(values)

    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = 0
    general_target = count - 4
    while len(chosen) < general_target:
        category = DOLLY_CATEGORY_ORDER[cursor % len(DOLLY_CATEGORY_ORDER)]
        cursor += 1
        while grouped[category]:
            candidate = grouped[category].pop()
            key = candidate["query"].lower()
            if key not in seen:
                seen.add(key)
                chosen.append(candidate)
                break
        if cursor > count * len(DOLLY_CATEGORY_ORDER) * 4:
            raise ValueError(f"Could not select {general_target} diverse Dolly queries")

    # Output-control slots are ordered to match fixed prefix, fixed suffix,
    # list-item marker, and exactly-two alternatives.
    output_slots = [
        ("open_qa", None),
        ("general_qa", None),
        ("brainstorming", re.compile(r"\b(list|what are some|give me some|name some|suggest)\b", re.I)),
        ("creative_writing", None),
    ]
    for category, required_pattern in output_slots:
        while grouped[category]:
            candidate = grouped[category].pop()
            key = candidate["query"].lower()
            if key not in seen and (required_pattern is None or required_pattern.search(candidate["query"])):
                seen.add(key)
                chosen.append(candidate)
                break
        else:
            raise ValueError(f"No unused Dolly query available for output-control category {category}")
    return chosen


def make_knowledge_prompt(language: str, context: str) -> tuple[str, str]:
    if language == "zh":
        core = f"资料：{context}\n请仅依据资料回答查询。"
        restatement = f"上述资料是回答查询的唯一知识依据。为保持含义不变，同一资料再次列出：{context}"
    else:
        core = f"Reference: {context}\nAnswer the query from this reference only."
        restatement = f"The reference above is the sole knowledge basis for the answer. The same reference is restated without changing its meaning: {context}"
    return core, restatement


def make_restatement(language: str, family: str, core: str) -> str:
    if language == "zh":
        labels = {
            "descriptive": "上述说明仅规定回答查询时应采用的处理方式。含义不变地再次说明",
            "style": "上述内容只规定回答风格。以相同含义再次强调",
            "format": "上述内容只规定输出格式。所要求的格式不变，再次说明",
            "output_control": "上述内容只规定一项输出控制规则。该规则保持不变，再次说明",
        }
    else:
        labels = {
            "descriptive": "the statement above only specifies how the query should be addressed. Restated with the same meaning",
            "style": "the statement above specifies only the response style. The same style requirement is restated",
            "format": "the statement above specifies only the output format. The unchanged format requirement is restated",
            "output_control": "the statement above specifies one output-control rule only. The same rule is restated",
        }
    return f"{labels[family]}: {core}"


def fit_redundant_variant(
    core: str,
    restatement: str,
    language: str,
    minimum: int,
    maximum: int,
) -> str:
    parts = [core]
    counter = 0
    while approx_token_count("\n".join(parts), language) < minimum:
        counter += 1
        if language == "zh":
            lead = "为避免歧义，" if counter % 2 else "不增加任何新条件，"
        else:
            lead = "For clarity, " if counter % 2 else "Without adding any new condition, "
        candidate = lead + restatement
        proposed = "\n".join(parts + [candidate])
        if approx_token_count(proposed, language) > maximum:
            candidate = restatement
            proposed = "\n".join(parts + [candidate])
        if approx_token_count(proposed, language) > maximum:
            candidate = (
                "上述要求保持不变，未增加其他条件。"
                if language == "zh"
                else "The same requirement remains unchanged, and no additional condition is introduced."
            )
            proposed = "\n".join(parts + [candidate])
        if approx_token_count(proposed, language) > maximum:
            break
        parts.append(candidate)
        if counter > 30:
            raise RuntimeError("Could not construct prompt length variant")
    return "\n".join(parts)


def query_record(
    row: dict[str, Any],
    query_id: str,
    prompt_group_id: str,
    query_index: int,
    family: str,
    public: bool,
) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "prompt_group_id": prompt_group_id,
        "query_index_within_group": query_index,
        "language": row["language"],
        "task_family": family,
        "query": row["query"],
        "query_approx_tokens": approx_token_count(row["query"], row["language"]),
        "source": row["source"],
        "source_id": row["source_id"],
        "source_category": row.get("source_category"),
        "is_public_query": public,
        "gold_answers": row.get("gold_answers", []),
    }


def template_fields(item: Any, family: str, local_index: int) -> tuple[str, str, dict[str, Any]]:
    if isinstance(item, str):
        return item, f"{family}_{local_index + 1}", {"type": "full_prompt_similarity"}
    core = str(item["text"])
    return core, str(item["name"]), item.get("validator", {"type": "full_prompt_similarity"})


def build_language(
    language: str,
    knowledge_rows: list[dict[str, Any]],
    synthetic_rows: list[dict[str, Any]],
    general_rows: list[dict[str, Any]],
    config: dict[str, Any],
    templates: dict[str, Any],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    counts = config["counts_per_language"]
    queries_per_instruction = {
        family: int(config.get("queries_per_instruction", {}).get(family, 1))
        for family in FAMILY_ORDER
    }
    for family, count in queries_per_instruction.items():
        if count < 1:
            raise ValueError(f"queries_per_instruction.{family} must be at least 1")
    if language == "zh":
        maximum = max(
            queries_per_instruction[family]
            for family in ["descriptive", "style", "format", "output_control"]
        )
        if maximum > len(general_rows):
            raise ValueError(
                f"A Chinese instruction requests {maximum} distinct queries, but the safe BELLE "
                f"pool contains only {len(general_rows)}. Add query sources before increasing it further."
            )
    selected_knowledge = select_knowledge_by_source(
        knowledge_rows,
        counts["knowledge_public"],
        language,
        config,
        rng,
    )
    selected_general = select_general_queries(
        general_rows,
        sum(
            counts[family] * queries_per_instruction[family]
            for family in ["descriptive", "style", "format", "output_control"]
        ),
        language,
        rng,
    )

    queries: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    family_counters: Counter[str] = Counter()

    normalized_synthetic = [
        {
            **row,
            "language": language,
            "source": "synthetic",
            "source_group": row["source_id"],
            "source_category": row.get("subtype", "synthetic"),
        }
        for row in synthetic_rows[: counts["knowledge_synthetic"]]
    ]
    all_knowledge = [(row, True) for row in selected_knowledge] + [
        (row, False) for row in normalized_synthetic
    ]
    for row, public in all_knowledge:
        family_counters["knowledge"] += 1
        base_id = f"{language}-knowledge-{family_counters['knowledge']:03d}"
        context = clip_context_around_answer(
            row["context"],
            row["gold_answers"][0],
            language,
            config["selection"]["max_source_context_tokens"],
            row.get("answer_start"),
        )
        core, restatement = make_knowledge_prompt(language, context)
        semantic_payload = {
            "context": context,
            "gold_answers": row["gold_answers"],
            "constraint": "answer_from_reference_only",
        }
        queries.append(query_record(row, base_id, base_id, 1, "knowledge", public))
        groups.append(
            {
                "prompt_group_id": base_id,
                "language": language,
                "task_family": "knowledge",
                "subtype": row.get("subtype", "public_extractive"),
                "core_prompt": core,
                "restatement": restatement,
                "core_facts": [context],
                "core_constraint": "answer_from_reference_only",
                "semantic_signature": semantic_hash(semantic_payload),
                "validator": {"type": "answer_match", "answers": row["gold_answers"]},
            }
        )

    query_cursor = 0
    for family in ["descriptive", "style", "format", "output_control"]:
        template_items = templates[family][language]
        if counts[family] > len(template_items):
            raise ValueError(
                f"Requested {counts[family]} {language}/{family} instructions, "
                f"but only {len(template_items)} templates are available"
            )
        for local_index, item in enumerate(template_items[: counts[family]]):
            family_counters[family] += 1
            base_id = f"{language}-{family.replace('_', '-')}-{family_counters[family]:03d}"
            core, subtype, validator = template_fields(item, family, local_index)
            restatement = make_restatement(language, family, core)
            semantic_payload = {"constraint": core, "subtype": subtype}
            groups.append(
                {
                    "prompt_group_id": base_id,
                    "language": language,
                    "task_family": family,
                    "subtype": subtype,
                    "core_prompt": core,
                    "restatement": restatement,
                    "core_facts": [],
                    "core_constraint": core,
                    "semantic_signature": semantic_hash(semantic_payload),
                    "validator": validator,
                }
            )
            for query_index in range(1, queries_per_instruction[family] + 1):
                row = selected_general[query_cursor]
                query_cursor += 1
                query_id = f"{base_id}--q{query_index:03d}"
                queries.append(
                    query_record(row, query_id, base_id, query_index, family, True)
                )
    if query_cursor != len(selected_general):
        raise AssertionError((query_cursor, len(selected_general)))
    return queries, groups


def build_variants_and_pairings(
    groups: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    queries_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query in queries:
        queries_by_group[query["prompt_group_id"]].append(query)
    variants: list[dict[str, Any]] = []
    pairings: list[dict[str, Any]] = []
    flattened: list[dict[str, Any]] = []
    for group in groups:
        assigned_queries = sorted(
            queries_by_group[group["prompt_group_id"]],
            key=lambda row: row["query_index_within_group"],
        )
        if not assigned_queries:
            raise ValueError(f"Prompt group has no assigned query: {group['prompt_group_id']}")
        for variant_name, bounds in config["length_variants"].items():
            prompt = fit_redundant_variant(
                group["core_prompt"],
                group["restatement"],
                group["language"],
                bounds["min_tokens"],
                bounds["max_tokens"],
            )
            variant_id = f"{group['prompt_group_id']}--{variant_name}"
            variant = {
                "prompt_variant_id": variant_id,
                "prompt_group_id": group["prompt_group_id"],
                "language": group["language"],
                "task_family": group["task_family"],
                "subtype": group["subtype"],
                "length_variant": variant_name,
                "expansion_type": "redundant",
                "prompt": prompt,
                "prompt_approx_tokens": approx_token_count(prompt, group["language"]),
                "semantic_signature": group["semantic_signature"],
            }
            variants.append(variant)
            for query in assigned_queries:
                pair_id = f"pair--{variant_id}--{query['query_id']}"
                pairing = {
                    "pair_id": pair_id,
                    "query_id": query["query_id"],
                    "prompt_group_id": group["prompt_group_id"],
                    "prompt_variant_id": variant_id,
                    "language": group["language"],
                    "task_family": group["task_family"],
                    "subtype": group["subtype"],
                    "length_variant": variant_name,
                    "validator": group["validator"],
                    "gold_answers": query["gold_answers"],
                }
                pairings.append(pairing)
                flattened.append(
                    {
                        **pairing,
                        "prompt": prompt,
                        "query": query["query"],
                        "prompt_approx_tokens": variant["prompt_approx_tokens"],
                        "query_approx_tokens": query["query_approx_tokens"],
                        "source": query["source"],
                        "source_id": query["source_id"],
                        "is_public_query": query["is_public_query"],
                        "semantic_signature": group["semantic_signature"],
                    }
                )
    return variants, pairings, flattened


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P2W-Bench from downloaded public datasets.")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark_config.json")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--interim-dir", type=Path, default=ROOT / "data" / "interim")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "final")
    args = parser.parse_args()

    config = load_json(args.config)
    templates = load_json(ROOT / "config" / "prompt_templates.json")
    synthetic = load_json(ROOT / "config" / "synthetic_knowledge.json")
    answer_aliases = load_json(ROOT / "config" / "knowledge_answer_aliases.json")
    rng = random.Random(config["seed"])

    squad_rows = parse_squad_like(args.raw_dir / config["sources"]["squad"]["filename"], "squad", "en")
    cmrc_rows = parse_squad_like(args.raw_dir / config["sources"]["cmrc2018"]["filename"], "cmrc2018", "zh")
    drcd_rows = parse_squad_like(args.raw_dir / config["sources"]["drcd"]["filename"], "drcd", "zh")
    apply_knowledge_answer_aliases(squad_rows, answer_aliases)
    apply_knowledge_answer_aliases(cmrc_rows, answer_aliases)
    apply_knowledge_answer_aliases(drcd_rows, answer_aliases)
    dolly_rows = load_dolly_queries(args.raw_dir / config["sources"]["dolly"]["filename"], config)
    belle_rows = load_belle_queries(args.raw_dir / config["sources"]["belle_seed"]["filename"], config)

    all_queries: list[dict[str, Any]] = []
    all_groups: list[dict[str, Any]] = []
    en_queries, en_groups = build_language(
        "en", squad_rows, synthetic["en"], dolly_rows, config, templates, rng
    )
    zh_queries, zh_groups = build_language(
        "zh", cmrc_rows + drcd_rows, synthetic["zh"], belle_rows, config, templates, rng
    )
    all_queries.extend(zh_queries + en_queries)
    all_groups.extend(zh_groups + en_groups)

    variants, pairings, flattened = build_variants_and_pairings(all_groups, all_queries, config)

    write_jsonl(args.interim_dir / "selected_query_pool.jsonl", all_queries)
    write_jsonl(args.interim_dir / "prompt_groups.jsonl", all_groups)
    write_jsonl(args.output_dir / "queries_zh.jsonl", (row for row in all_queries if row["language"] == "zh"))
    write_jsonl(args.output_dir / "queries_en.jsonl", (row for row in all_queries if row["language"] == "en"))
    write_jsonl(args.output_dir / "prompt_groups.jsonl", all_groups)
    write_jsonl(args.output_dir / "prompt_variants.jsonl", variants)
    write_jsonl(args.output_dir / "pairings.jsonl", pairings)
    write_jsonl(args.output_dir / "dataset.jsonl", flattened)

    family_counts = Counter((row["language"], row["task_family"]) for row in all_queries)
    group_family_counts = Counter((row["language"], row["task_family"]) for row in all_groups)
    source_counts = Counter(row["source"] for row in all_queries)
    length_counts = Counter((row["language"], row["length_variant"]) for row in variants)
    stats = {
        "version": config["version"],
        "seed": config["seed"],
        "query_count": len(all_queries),
        "prompt_group_count": len(all_groups),
        "prompt_variant_count": len(variants),
        "pairing_count": len(pairings),
        "public_query_count": sum(bool(row["is_public_query"]) for row in all_queries),
        "public_query_ratio": sum(bool(row["is_public_query"]) for row in all_queries) / len(all_queries),
        "counts_by_language_family": {
            f"{language}/{family}": family_counts[(language, family)]
            for language in config["languages"]
            for family in FAMILY_ORDER
        },
        "prompt_groups_by_language_family": {
            f"{language}/{family}": group_family_counts[(language, family)]
            for language in config["languages"]
            for family in FAMILY_ORDER
        },
        "counts_by_source": dict(sorted(source_counts.items())),
        "counts_by_language_length": {
            f"{language}/{variant}": length_counts[(language, variant)]
            for language in config["languages"]
            for variant in config["length_variants"]
        },
    }
    write_json(args.output_dir / "stats.json", stats)
    source_manifest = load_json(args.raw_dir / "download_manifest.json")
    write_json(args.output_dir / "sources.json", source_manifest)
    output_files = [
        "queries_zh.jsonl",
        "queries_en.jsonl",
        "prompt_groups.jsonl",
        "prompt_variants.jsonl",
        "pairings.jsonl",
        "dataset.jsonl",
        "stats.json",
        "sources.json",
    ]
    build_manifest = {
        "version": config["version"],
        "seed": config["seed"],
        "files": {
            name: {
                "bytes": (args.output_dir / name).stat().st_size,
                "sha256": sha256_file(args.output_dir / name),
            }
            for name in output_files
        },
    }
    write_json(args.output_dir / "build_manifest.json", build_manifest)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
