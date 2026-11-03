import os
import unittest
import uuid
from unittest.mock import patch

from company.model_catalog import catalog, normalize_models
from company.team import assignment, save_team


class ModelCatalogTests(unittest.TestCase):
    def test_model_facts_keep_exact_version_and_correct_token_prices(self):
        models = normalize_models(
            [
                {
                    "id": "vendor/specific-model-v2",
                    "name": "Vendor: Specific Model V2",
                    "description": "A multilingual coding model with reasoning capabilities.",
                    "context_length": 131072,
                    "supported_parameters": ["tools", "reasoning"],
                    "architecture": {
                        "input_modalities": ["text", "image"],
                        "output_modalities": ["text"],
                    },
                    "pricing": {"prompt": "0.000002", "completion": "0.000006"},
                }
            ],
            "2026-10-21",
        )
        model = models[0]
        self.assertEqual(model["id"], "vendor/specific-model-v2")
        self.assertEqual(model["name"], "Specific Model V2")
        self.assertEqual(model["input_price_per_million"], 2)
        self.assertEqual(model["output_price_per_million"], 6)
        self.assertTrue(model["agent_compatible"])
        self.assertIn("research", model["categories"])
        self.assertIn("it", model["categories"])
        self.assertIn("131,072-token", model["summary"])
        self.assertEqual(
            model["source_url"], "https://openrouter.ai/vendor/specific-model-v2"
        )

    def test_image_only_models_are_discoverable_without_claiming_agent_compatibility(
        self,
    ):
        model = normalize_models(
            [
                {
                    "id": "vendor/image-v1",
                    "name": "Image V1",
                    "architecture": {
                        "input_modalities": ["text"],
                        "output_modalities": ["image"],
                    },
                    "supported_parameters": [],
                }
            ]
        )[0]
        self.assertIn("design", model["categories"])
        self.assertFalse(model["agent_compatible"])
        self.assertIsNone(model["input_price_per_million"])

    def test_complete_snapshot_has_specific_models_and_routes_the_selected_id(self):
        models = catalog()
        self.assertGreaterEqual(len(models), 400)
        self.assertEqual(len(models), len({m["id"] for m in models}))
        selected = next(m for m in models if m["agent_compatible"])
        actor, project = str(uuid.uuid4()), str(uuid.uuid4())
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}):
            save_team(
                actor,
                project,
                "manual",
                [{"agent_id": selected["id"], "role_id": "cto"}],
            )
            self.assertEqual(
                assignment(actor, project, "cto")["model"], selected["model_id"]
            )
            incompatible = next(m for m in models if not m["agent_compatible"])
            with self.assertRaises(ValueError):
                save_team(
                    actor,
                    project,
                    "manual",
                    [{"agent_id": incompatible["id"], "role_id": "cto"}],
                )


if __name__ == "__main__":
    unittest.main()
