"""Provider-routing regressions use synthetic keys and mocked network responses."""

import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from app import app
from company.ceo import CEO_PROFILE, CeoProviderError, _generate
from company.provider_config import ceo_configuration
from fastapi.testclient import TestClient


class CeoProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_openrouter_ceo_calls_configured_model_and_json_contract(self):
        with patch.dict(
            os.environ,
            {
                "ARC_CEO_PROVIDER": "openrouter",
                "ARC_CEO_MODEL": "vendor/exact-model",
                "OPENROUTER_API_KEY": "synthetic-key",
            },
        ):
            response = httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": '{"message":"Hello","delegations":[]}'}}
                    ]
                },
            )
            with patch("company.ceo.httpx.AsyncClient") as factory:
                client = AsyncMock()
                client.post.return_value = response
                factory.return_value.__aenter__.return_value = client
                text = await _generate(
                    system_instruction="System", prompt="Hello", json_output=True
                )
            self.assertIn("Hello", text)
            args = client.post.call_args
            self.assertEqual(
                args.args[0], "https://openrouter.ai/api/v1/chat/completions"
            )
            self.assertEqual(args.kwargs["json"]["model"], "vendor/exact-model")
            self.assertEqual(
                args.kwargs["json"]["response_format"], {"type": "json_object"}
            )
            self.assertEqual(CEO_PROFILE.public_dict()["provider"], "openrouter")
            self.assertEqual(CEO_PROFILE.model, "vendor/exact-model")

    async def test_placeholder_google_key_is_unconfigured_and_never_sent(self):
        with (
            patch.dict(
                os.environ,
                {
                    "ARC_CEO_PROVIDER": "google_ai_studio",
                    "GEMINI_API_KEY": "replace_with_your_key",
                    "GOOGLE_AI_API_KEY": "",
                },
            ),
            patch("company.ceo.httpx.AsyncClient") as factory,
        ):
            self.assertFalse(ceo_configuration()["configured"])
            with self.assertRaises(CeoProviderError):
                await _generate(system_instruction="System", prompt="Hello")
            factory.assert_not_called()

    async def test_selected_provider_does_not_silently_fall_back(self):
        with patch.dict(
            os.environ,
            {
                "ARC_CEO_PROVIDER": "google_ai_studio",
                "GEMINI_API_KEY": "",
                "GOOGLE_AI_API_KEY": "",
                "OPENROUTER_API_KEY": "synthetic-key",
            },
        ):
            with self.assertRaises(CeoProviderError):
                await _generate(system_instruction="System", prompt="Hello")

    async def test_provider_error_does_not_expose_upstream_details(self):
        with patch.dict(
            os.environ,
            {
                "ARC_CEO_PROVIDER": "openrouter",
                "ARC_CEO_MODEL": "vendor/model",
                "OPENROUTER_API_KEY": "synthetic-key",
            },
        ):
            with patch("company.ceo.httpx.AsyncClient") as factory:
                client = AsyncMock()
                client.post.return_value = httpx.Response(
                    401, json={"error": {"message": "SYNTHETIC_SECRET"}}
                )
                factory.return_value.__aenter__.return_value = client
                with self.assertRaises(CeoProviderError) as error:
                    await _generate(system_instruction="System", prompt="Hello")
            self.assertEqual(error.exception.status_code, 401)
            self.assertNotIn("SYNTHETIC_SECRET", str(error.exception))

    async def test_readiness_uses_the_selected_provider(self):
        with patch.dict(
            os.environ,
            {
                "ARC_CEO_PROVIDER": "openrouter",
                "ARC_CEO_MODEL": "vendor/model",
                "OPENROUTER_API_KEY": "synthetic-key",
                "GEMINI_API_KEY": "",
                "GOOGLE_AI_API_KEY": "",
                "ARC_BACKEND_API_KEY": "",
                "ARC_ENVIRONMENT": "development",
            },
        ):
            with TestClient(app) as client:
                response = client.get("/health/ready")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["checks"]["ceo_provider"])

    async def test_greetings_do_not_send_the_market_catalog(self):
        import uuid

        from company.ceo import run_ceo_agent

        with (
            patch(
                "company.ceo._generate",
                new_callable=AsyncMock,
                return_value='{"message":"Hello","delegations":[]}',
            ) as generate,
            patch("company.team.planning_marketplace") as market,
        ):
            await run_ceo_agent(
                "Hello", "greeting", actor_id="greeting-" + uuid.uuid4().hex
            )
        market.assert_not_called()
        self.assertLess(len(generate.call_args.kwargs["system_instruction"]), 400)
        self.assertEqual(generate.call_args.kwargs["max_output_tokens"], 128)
        self.assertEqual(generate.call_args.kwargs["prompt"], "Hello")

    async def test_response_budget_cannot_exceed_security_ceiling(self):
        from company.provider_config import output_token_limit

        for value, expected in [
            ("999999", 4096),
            ("-1", 64),
            ("broken", 1024),
            ("512", 512),
        ]:
            with patch.dict(os.environ, {"ARC_CEO_MAX_OUTPUT_TOKENS": value}):
                self.assertEqual(
                    output_token_limit("ARC_CEO_MAX_OUTPUT_TOKENS"), expected
                )

    async def test_truncated_json_plan_is_not_returned_as_chat_text(self):
        with patch.dict(
            os.environ,
            {
                "ARC_CEO_PROVIDER": "openrouter",
                "ARC_CEO_MODEL": "vendor/model",
                "OPENROUTER_API_KEY": "synthetic-key",
            },
        ):
            with patch("company.ceo.httpx.AsyncClient") as factory:
                client = AsyncMock()
                client.post.return_value = httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": '{"message":"unfinished'}}]
                    },
                )
                factory.return_value.__aenter__.return_value = client
                with self.assertRaises(CeoProviderError):
                    await _generate(
                        system_instruction="System", prompt="Hello", json_output=True
                    )


if __name__ == "__main__":
    unittest.main()
