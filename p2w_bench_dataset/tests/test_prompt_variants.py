import json
import unittest
from pathlib import Path

from p2w_bench.common import approx_token_count


ROOT = Path(__file__).resolve().parents[1]
VARIANT_ORDER = ("short", "medium_redundant", "long_redundant")


class DescriptivePromptVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.templates = json.loads(
            (ROOT / "config" / "prompt_templates.json").read_text(encoding="utf-8")
        )["descriptive"]
        cls.bounds = json.loads(
            (ROOT / "benchmark_config.json").read_text(encoding="utf-8")
        )["length_variants_by_family"]["descriptive"]

    def test_all_templates_have_complete_semantic_elaborations(self):
        for language, templates in self.templates.items():
            for template in templates:
                with self.subTest(language=language, template=template["name"]):
                    self.assertEqual(set(template["variant_prompts"]), set(VARIANT_ORDER))
                    self.assertEqual(template["text"], template["variant_prompts"]["short"])

    def test_lengths_are_in_range_and_strictly_increase(self):
        for language, templates in self.templates.items():
            for template in templates:
                counts = []
                for variant_name in VARIANT_ORDER:
                    count = approx_token_count(template["variant_prompts"][variant_name], language)
                    bounds = self.bounds[variant_name]
                    self.assertGreaterEqual(count, bounds["min_tokens"])
                    self.assertLessEqual(count, bounds["max_tokens"])
                    counts.append(count)
                with self.subTest(language=language, template=template["name"]):
                    self.assertEqual(counts, sorted(set(counts)))

    def test_old_mechanical_restatement_markers_are_absent(self):
        banned = (
            "再次说明",
            "含义不变",
            "上述说明仅规定",
            "restated with the same meaning",
            "the statement above only specifies",
        )
        for language, templates in self.templates.items():
            for template in templates:
                for variant_name, prompt in template["variant_prompts"].items():
                    normalized = prompt.lower()
                    with self.subTest(
                        language=language,
                        template=template["name"],
                        variant=variant_name,
                    ):
                        self.assertFalse(any(marker in normalized for marker in banned))


if __name__ == "__main__":
    unittest.main()
