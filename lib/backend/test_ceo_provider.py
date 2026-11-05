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
    async def google_response(
        self, responses, *, structured=False, model="gemini-3.5-flash"
    ):
        with (
            patch.dict(
                os.environ,
                {
                    "ARC_CEO_PROVIDER": "google_ai_studio",
                    "GEMINI_API_KEY": "synthetic-key",
                    "GEMINI_CEO_MODEL": model,
                },
            ),
            patch("company.ceo.httpx.AsyncClient") as factory,
            patch("company.ceo.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            client = AsyncMock()
            client.post.side_effect = responses
            factory.return_value.__aenter__.return_value = client
            text = await _generate(
                system_instruction="System",
                prompt="what u can do",
                json_output=structured,
            )
            return text, client, sleep

    async def test_google_retries_overload_once_without_switching_provider(self):
        text, client, sleep = await self.google_response(
            [
                httpx.Response(
                    503, json={"error": {"message": "private upstream details"}}
                ),
                httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {"content": {"parts": [{"text": "Complete answer."}]}}
                        ]
                    },
                ),
            ]
        )
        self.assertEqual(text, "Complete answer.")
        self.assertEqual(client.post.await_count, 2)
        sleep.assert_awaited_once_with(1)
        self.assertEqual(client.post.call_args_list[0], client.post.call_args_list[1])
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(
            payload["generationConfig"]["thinkingConfig"], {"thinkingLevel": "minimal"}
        )
        self.assertNotIn("temperature", payload["generationConfig"])

    async def test_google_auth_and_quota_failures_are_not_retried(self):
        for status in (400, 401, 403, 429):
            with self.subTest(status=status):
                with (
                    patch.dict(
                        os.environ,
                        {
                            "ARC_CEO_PROVIDER": "google_ai_studio",
                            "GEMINI_API_KEY": "synthetic-key",
                        },
                    ),
                    patch("company.ceo.httpx.AsyncClient") as factory,
                ):
                    client = AsyncMock()
                    client.post.return_value = httpx.Response(
                        status, json={"error": {"message": "SYNTHETIC_SECRET"}}
                    )
                    factory.return_value.__aenter__.return_value = client
                    with self.assertRaises(CeoProviderError) as error:
                        await _generate(system_instruction="System", prompt="test")
                    self.assertEqual(client.post.await_count, 1)
                    self.assertNotIn("SYNTHETIC_SECRET", str(error.exception))

    async def test_google_retry_is_bounded(self):
        with self.assertRaises(CeoProviderError) as error:
            await self.google_response([httpx.Response(503), httpx.Response(503)])
        self.assertEqual(error.exception.status_code, 503)

    async def test_google_hides_thought_parts_and_rejects_truncated_plans(self):
        text, _, _ = await self.google_response(
            [
                httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "thought": True,
                                            "text": "SYNTHETIC_INTERNAL_THOUGHT",
                                        },
                                        {"text": "Final answer."},
                                    ]
                                }
                            }
                        ]
                    },
                )
            ]
        )
        self.assertEqual(text, "Final answer.")
        with self.assertRaises(CeoProviderError):
            await self.google_response(
                [
                    httpx.Response(
                        200,
                        json={
                            "candidates": [
                                {
                                    "content": {
                                        "parts": [{"text": '{"message":"unfinished'}]
                                    }
                                }
                            ]
                        },
                    )
                ],
                structured=True,
            )

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

    async def test_capabilities_followup_is_a_small_plain_text_request(self):
        import uuid

        from company.ceo import run_ceo_agent

        with (
            patch(
                "company.ceo._generate",
                new_callable=AsyncMock,
                return_value="I can help you plan and build your company.",
            ) as generate,
            patch("company.team.planning_marketplace") as market,
        ):
            result = await run_ceo_agent(
                "what u can do",
                "capabilities",
                actor_id="capabilities-" + uuid.uuid4().hex,
            )
        market.assert_not_called()
        self.assertEqual(result["response_kind"], "capabilities")
        self.assertEqual(result["delegations"], [])
        self.assertNotIn("json_output", generate.call_args.kwargs)
        self.assertEqual(generate.call_args.kwargs["max_output_tokens"], 256)

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
