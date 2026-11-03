import os
import unittest
from unittest.mock import patch

from company.provider_config import reasoning_options


class ReasoningOptionsTests(unittest.TestCase):
    def test_default_does_not_change_provider_behavior(self):
        with patch.dict(os.environ, {"ARC_CEO_REASONING": ""}):
            self.assertEqual(reasoning_options("ARC_CEO_REASONING"), {})

    def test_optional_reasoning_can_be_disabled_or_bounded(self):
        with patch.dict(os.environ, {"ARC_CEO_REASONING": "off"}):
            self.assertEqual(
                reasoning_options("ARC_CEO_REASONING"),
                {"reasoning": {"enabled": False}},
            )
        with patch.dict(os.environ, {"ARC_AGENT_REASONING": "low"}):
            self.assertEqual(
                reasoning_options("ARC_AGENT_REASONING"),
                {"reasoning": {"effort": "low"}},
            )

    def test_invalid_reasoning_setting_fails_instead_of_silently_changing_it(self):
        with patch.dict(os.environ, {"ARC_AGENT_REASONING": "unknown"}):
            with self.assertRaises(ValueError):
                reasoning_options("ARC_AGENT_REASONING")
