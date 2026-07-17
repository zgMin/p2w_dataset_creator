import unittest

from p2w_bench.output_validators import validate_output


class OutputValidatorTests(unittest.TestCase):
    def assert_passes(self, text, spec):
        passed, detail = validate_output(text, spec)
        self.assertTrue(passed, detail)

    def assert_fails(self, text, spec):
        passed, _ = validate_output(text, spec)
        self.assertFalse(passed)

    def test_fixed_prefix_and_suffix(self):
        self.assert_passes("I2W-START: answer", {"type": "fixed_prefix", "value": "I2W-START:"})
        self.assert_passes("answer:I2W-END", {"type": "fixed_suffix", "value": ":I2W-END"})
        self.assert_fails("answer", {"type": "fixed_prefix", "value": "I2W-START:"})

    def test_list_item_suffix(self):
        spec = {"type": "list_item_suffix", "value": "I2W"}
        self.assert_passes("1. first I2W\n2. second I2W", spec)
        self.assert_fails("1. first I2W\n2. second", spec)

    def test_exact_item_count(self):
        spec = {"type": "exact_item_count", "count": 2}
        self.assert_passes("1. first\n2. second", spec)
        self.assert_fails("1. first\n2. second\n3. third", spec)

    def test_json_schema(self):
        spec = {"type": "json_schema", "required_keys": ["answer"], "allow_extra_keys": False}
        self.assert_passes('{"answer": "ok"}', spec)
        self.assert_fails('{"answer": "ok", "extra": 1}', spec)

    def test_xml_and_table(self):
        self.assert_passes("<answer>ok</answer>", {"type": "xml_tag", "tag": "answer"})
        self.assert_passes(
            "| Point | Content |\n|---|---|\n| A | B |",
            {"type": "markdown_table", "columns": ["Point", "Content"]},
        )


if __name__ == "__main__":
    unittest.main()
