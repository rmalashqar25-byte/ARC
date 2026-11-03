"""Developer connections use synthetic credentials and mocked model services."""

import json
import os
import tempfile
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from app import app
from company.ceo import CeoProviderError, _generate
from company.provider_config import ceo_configuration, reasoning_options
from developer_connections import (
    DEVELOPER_ACTOR,
    ModelTransport,
    connection,
    delete_connection,
    save_connection,
    validate_endpoint,
    validated_settings,
)
from fastapi.testclient import TestClient

ACTOR = "guest:" + "a" * 64
OTHER = "guest:" + "b" * 64
PAYLOAD = {
    "provider": "openrouter",
    "model": "vendor/exact-model",
    "api_key": "synthetic-provider-key",
    "confirm_usage": True,
    "supports_tools": True,
}


class DeveloperTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.root = root
        self.stack.enter_context(
            patch.dict(
                os.environ,
                {
                    "ARC_PROVIDER_VAULT": str(root),
                    "ARC_LOCAL_DEVELOPER": "1",
                    "ARC_ENVIRONMENT": "development",
                    "CONTAINER_APP_NAME": "",
                    "ARC_BACKEND_API_KEY": "",
                },
            )
        )

    def test_vault_encrypts_secrets_and_isolates_workspaces(self):
        value = validated_settings(ACTOR, PAYLOAD)
        public = save_connection(ACTOR, value)
        self.assertNotIn("api_key", public)
        self.assertEqual(connection(ACTOR)["api_key"], PAYLOAD["api_key"])
        self.assertIsNone(connection(OTHER))
        self.assertNotIn(
            PAYLOAD["api_key"].encode(),
            (self.root / "connections.sqlite3").read_bytes(),
        )
        # A new read decrypts the saved record, rather than relying on an in-memory cache.
        self.assertEqual(connection(ACTOR)["model"], PAYLOAD["model"])
        delete_connection(ACTOR)
        self.assertIsNone(connection(ACTOR))

    def test_blank_key_reuse_is_bound_to_exact_provider_and_destination(self):
        save_connection(ACTOR, validated_settings(ACTOR, PAYLOAD))
        same = validated_settings(ACTOR, dict(PAYLOAD, api_key=""))
        self.assertEqual(same["api_key"], PAYLOAD["api_key"])
        with self.assertRaises(ValueError):
            validated_settings(ACTOR, dict(PAYLOAD, provider="gemini", api_key=""))
        with self.assertRaises(ValueError):
            validated_settings(
                ACTOR,
                dict(
                    PAYLOAD,
                    provider="custom",
                    base_url="https://other.example/v1",
                    api_key="",
                ),
            )
        with self.assertRaises(ValueError):
            validated_settings(OTHER, dict(PAYLOAD, api_key=""))

    def test_api_never_returns_key_and_removal_is_workspace_scoped(self):
        headers = {"X-Arc-Session": str(uuid.uuid4())}
        other = {"X-Arc-Session": str(uuid.uuid4())}
        with (
            TestClient(app) as client,
            patch(
                "developer_api.discover_models",
                return_value=[{"id": PAYLOAD["model"], "name": "Friendly Model"}],
            ),
        ):
            result = client.put("/developer/connection", headers=headers, json=PAYLOAD)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertNotIn(PAYLOAD["api_key"], result.text)
            self.assertEqual(result.headers["cache-control"], "no-store")
            self.assertEqual(
                client.get("/developer/connection", headers=other).json()["connection"],
                {},
            )
            self.assertNotIn(
                "api_key",
                client.get("/developer/connection", headers=headers).json()[
                    "connection"
                ],
            )
            self.assertEqual(
                client.delete("/developer/connection", headers=other).status_code, 200
            )
            self.assertTrue(
                client.get("/developer/connection", headers=headers).json()[
                    "connection"
                ]
            )
            self.assertEqual(
                client.delete("/developer/connection", headers=headers).status_code, 200
            )
            self.assertEqual(
                client.get("/developer/connection", headers=headers).json()[
                    "connection"
                ],
                {},
            )
            self.assertEqual(client.get("/developer/connection").status_code, 401)

    def test_model_discovery_needs_no_model_id_and_returns_friendly_names(self):
        with (
            TestClient(app) as client,
            patch("developer_connections.model_client") as factory,
        ):
            provider = MagicMock()
            factory.return_value.with_options.return_value.__enter__.return_value = (
                provider
            )
            provider.models.list.return_value = SimpleNamespace(
                data=[SimpleNamespace(id="vendor/exact-model", name="Friendly Model")]
            )
            result = client.post(
                "/developer/models",
                headers={"X-Arc-Session": str(uuid.uuid4())},
                json={"provider": "openrouter", "api_key": "synthetic-provider-key"},
            )
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(
                result.json()["models"],
                [{"id": "vendor/exact-model", "name": "Friendly Model"}],
            )
            provider.get.assert_called_once_with("/key", cast_to=dict[str, object])
            provider.chat.completions.create.assert_not_called()
            self.assertNotIn("synthetic-provider-key", result.text)

    def test_invalid_key_and_missing_model_cannot_replace_a_saved_connection(self):
        from openai import AuthenticationError

        headers = {"X-Arc-Session": str(uuid.uuid4())}
        with (
            TestClient(app) as client,
            patch("developer_api.discover_models") as discover,
        ):
            discover.return_value = [{"id": PAYLOAD["model"], "name": "Verified Model"}]
            self.assertEqual(
                client.put(
                    "/developer/connection", headers=headers, json=PAYLOAD
                ).status_code,
                200,
            )
            discover.side_effect = AuthenticationError(
                "synthetic-secret",
                response=httpx.Response(
                    401,
                    request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
                ),
                body=None,
            )
            denied = client.put(
                "/developer/connection",
                headers=headers,
                json=dict(
                    PAYLOAD, api_key="invalid-new-key", model="vendor/other-model"
                ),
            )
            self.assertEqual(denied.status_code, 401)
            self.assertNotIn("synthetic-secret", denied.text)
            self.assertEqual(
                client.get("/developer/connection", headers=headers).json()[
                    "connection"
                ]["model"],
                PAYLOAD["model"],
            )
            discover.side_effect = None
            discover.return_value = []
            self.assertEqual(
                client.put(
                    "/developer/connection", headers=headers, json=PAYLOAD
                ).status_code,
                400,
            )

    def test_endpoint_policy_blocks_metadata_credentials_and_remote_local_models(self):
        for endpoint in (
            "http://169.254.169.254/v1",
            "https://user:key@example.com/v1",
            "https://example.com/v1?key=secret",
            "file:///etc/passwd",
            "http://127.0.0.1:8765/v1",
            "http://127.0.0.1:11434/admin",
            "https://example.com:123/v1",
            "https://exam\nple.com/v1",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_endpoint(endpoint)
        self.assertEqual(
            validate_endpoint("http://127.0.0.1:11434/v1/"), "http://127.0.0.1:11434/v1"
        )
        with (
            patch.dict(os.environ, {"ARC_ENVIRONMENT": "production"}),
            self.assertRaises(ValueError),
        ):
            validate_endpoint("http://127.0.0.1:11434/v1")

    def test_transport_blocks_private_dns_and_destination_changes_before_sending_key(
        self,
    ):
        with ModelTransport("https://models.example/v1") as transport:
            with (
                patch(
                    "developer_connections.socket.getaddrinfo",
                    return_value=[(2, 1, 6, "", ("169.254.169.254", 443))],
                ),
                patch.object(transport.inner, "handle_request") as send,
            ):
                with self.assertRaises(ValueError):
                    transport.handle_request(
                        httpx.Request(
                            "GET",
                            "https://models.example/v1/models",
                            headers={"Authorization": "Bearer synthetic"},
                        )
                    )
                send.assert_not_called()
            with self.assertRaises(ValueError):
                transport.handle_request(
                    httpx.Request("GET", "https://other.example/v1/models")
                )

    def test_transport_pins_public_dns_and_preserves_tls_name(self):
        with ModelTransport("https://models.example/v1") as transport:
            with (
                patch(
                    "developer_connections.socket.getaddrinfo",
                    return_value=[(2, 1, 6, "", ("8.8.8.8", 443))],
                ),
                patch.object(
                    transport.inner, "handle_request", return_value=httpx.Response(200)
                ) as send,
            ):
                transport.handle_request(
                    httpx.Request("GET", "https://models.example/v1/models")
                )
                request = send.call_args.args[0]
                self.assertEqual(request.url.host, "8.8.8.8")
                self.assertEqual(request.headers["host"], "models.example")
                self.assertEqual(request.extensions["sni_hostname"], "models.example")

    def test_ollama_requires_no_key_and_remote_usage_requires_confirmation(self):
        value = validated_settings(
            ACTOR, dict(PAYLOAD, provider="ollama", api_key="", confirm_usage=False)
        )
        self.assertTrue(value["local"])
        with self.assertRaises(ValueError):
            validated_settings(ACTOR, dict(PAYLOAD, confirm_usage=False))

    def test_request_context_selects_own_marketplace_and_never_another_workspace(self):
        save_connection(ACTOR, validated_settings(ACTOR, PAYLOAD))
        token = DEVELOPER_ACTOR.set(ACTOR)
        try:
            from company.team import marketplace

            self.assertEqual(ceo_configuration()["provider"], "developer")
            self.assertEqual(marketplace()[0]["model_id"], PAYLOAD["model"])
            self.assertEqual(reasoning_options("ARC_CEO_REASONING"), {})
            self.assertIsNone(marketplace()[0]["input_price_per_million"])
        finally:
            DEVELOPER_ACTOR.reset(token)
        token = DEVELOPER_ACTOR.set(OTHER)
        try:
            self.assertNotEqual(ceo_configuration()["provider"], "developer")
        finally:
            DEVELOPER_ACTOR.reset(token)

    def test_optional_reasoning_controls_apply_only_to_matching_openrouter_model(self):
        own = dict(PAYLOAD, base_url="https://openrouter.ai/api/v1", local=False)
        with (
            patch("developer_connections.connection", return_value=own),
            patch(
                "company.model_catalog.catalog",
                return_value=[
                    {"model_id": PAYLOAD["model"], "reasoning_mandatory": False}
                ],
            ),
        ):
            self.assertEqual(
                reasoning_options("ARC_CEO_REASONING", PAYLOAD["model"]),
                {"reasoning": {"enabled": False}},
            )
            self.assertEqual(
                reasoning_options("ARC_CEO_REASONING", "another/model"), {}
            )
        with patch(
            "developer_connections.connection",
            return_value=dict(own, provider="gemini"),
        ):
            self.assertEqual(
                reasoning_options("ARC_CEO_REASONING", PAYLOAD["model"]), {}
            )

    def test_terminal_automatic_connection_is_local_single_owner_only(self):
        from terminal_connection import auto_connect_terminal, terminal_is_connected

        path = self.root / "grants.json"
        path.write_text(json.dumps({"actors": [], "paired": False}))
        with (
            patch.dict(
                os.environ,
                {
                    "ARC_TERMINAL_GRANTS_FILE": str(path),
                    "ARC_TERMINAL_AUTO_CONNECT": "1",
                },
            ),
            patch("terminal_connection.terminal_service_ready", return_value=True),
        ):
            self.assertTrue(auto_connect_terminal(ACTOR))
            self.assertTrue(auto_connect_terminal(ACTOR))
            self.assertFalse(auto_connect_terminal(OTHER))
            self.assertTrue(terminal_is_connected(ACTOR))
            self.assertFalse(terminal_is_connected(OTHER))
        with patch.dict(os.environ, {"ARC_TERMINAL_AUTO_CONNECT": "0"}):
            self.assertFalse(auto_connect_terminal(OTHER))

    def test_terminal_auto_endpoint_rejects_foreign_origin(self):
        with (
            TestClient(app) as client,
            patch("terminal_connection.auto_connect_terminal") as connect,
        ):
            result = client.post(
                "/plugins/terminal/auto-connect",
                headers={
                    "X-Arc-Session": str(uuid.uuid4()),
                    "Origin": "https://untrusted.example",
                },
            )
            self.assertEqual(result.status_code, 403)
            connect.assert_not_called()


class DeveloperCeoTests(unittest.IsolatedAsyncioTestCase):
    async def test_ceo_uses_exact_custom_model_and_never_shared_provider(self):
        own = dict(PAYLOAD, base_url="https://models.example/v1", local=False)
        token = DEVELOPER_ACTOR.set(ACTOR)
        try:
            with (
                patch("developer_connections.connection", return_value=own),
                patch("developer_connections.model_client") as factory,
                patch("company.ceo.httpx.AsyncClient") as shared,
            ):
                client = MagicMock()
                factory.return_value.__enter__.return_value = client
                client.chat.completions.create.return_value = SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='{"message":"hello"}')
                        )
                    ]
                )
                result = await _generate(
                    system_instruction="Return JSON", prompt="Hello", json_output=True
                )
                self.assertIn("hello", result)
                self.assertEqual(
                    client.chat.completions.create.call_args.kwargs["model"],
                    PAYLOAD["model"],
                )
                shared.assert_not_called()
                client.chat.completions.create.side_effect = RuntimeError(
                    "synthetic-provider-key"
                )
                with self.assertRaises(CeoProviderError) as error:
                    await _generate(system_instruction="System", prompt="Hello")
                self.assertNotIn("synthetic-provider-key", str(error.exception))
                shared.assert_not_called()
        finally:
            DEVELOPER_ACTOR.reset(token)


class DirectProviderRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_company_roles_and_reviews_use_the_workspace_provider(
        self,
    ):
        from company.collaboration import ensure_director_group
        from company.organization import PROFILES
        from company.runtime import run_company_agent
        from company.work_runtime import CompanyWorker
        from company.work_store import WorkStore
        from developer_api import ConnectionSettings
        from developer_connections import PRESETS, discover_models

        for provider in ("openai", "gemini", "ollama"):
            with (
                self.subTest(provider=provider),
                tempfile.TemporaryDirectory() as directory,
                patch.dict(
                    os.environ,
                    {
                        "ARC_PROVIDER_VAULT": directory,
                        "ARC_LOCAL_DEVELOPER": "1",
                        "ARC_ENVIRONMENT": "development",
                        "CONTAINER_APP_NAME": "",
                    },
                ),
            ):
                actor = "guest:" + uuid.uuid4().hex * 2
                model = "contract-test-model"
                supplied = ConnectionSettings(
                    provider=provider,
                    model=model,
                    api_key="" if provider == "ollama" else "synthetic-owned-key",
                    confirm_usage=provider != "ollama",
                ).model_dump()
                value = validated_settings(actor, supplied)
                requests = []

                def respond(request):
                    requests.append(request)
                    self.assertEqual(
                        str(request.url),
                        PRESETS[provider]
                        + (
                            "/models"
                            if request.method == "GET"
                            else "/chat/completions"
                        ),
                    )
                    self.assertEqual(
                        request.headers["authorization"],
                        "Bearer "
                        + (
                            "local-model"
                            if provider == "ollama"
                            else "synthetic-owned-key"
                        ),
                    )
                    if request.method == "GET":
                        return httpx.Response(
                            200,
                            json={
                                "object": "list",
                                "data": [
                                    {
                                        "id": model,
                                        "name": "Test model",
                                        "object": "model",
                                        "created": 0,
                                        "owned_by": provider,
                                    }
                                ],
                            },
                        )
                    body = json.loads(request.content)
                    self.assertEqual(body["model"], model)
                    limit_key = (
                        "max_completion_tokens"
                        if provider == "openai"
                        else "max_tokens"
                    )
                    self.assertIn(limit_key, body)
                    if provider == "ollama":
                        self.assertEqual(body["reasoning_effort"], "none")
                    else:
                        self.assertNotIn("reasoning_effort", body)
                    self.assertNotIn(
                        "max_tokens"
                        if provider == "openai"
                        else "max_completion_tokens",
                        body,
                    )
                    return httpx.Response(
                        200,
                        json={
                            "id": "chatcmpl-test",
                            "object": "chat.completion",
                            "created": 0,
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "finish_reason": "stop",
                                    "message": {
                                        "role": "assistant",
                                        "content": '{"decision":"accepted","feedback":"Meets the assigned brief."}'
                                        if body.get("response_format")
                                        else "Connection contract passed.",
                                    },
                                }
                            ],
                        },
                    )

                with patch(
                    "developer_connections.ModelTransport",
                    side_effect=lambda _: httpx.MockTransport(respond),
                ):
                    self.assertEqual(
                        discover_models(value), [{"id": model, "name": "Test model"}]
                    )
                    save_connection(actor, value)
                    token = DEVELOPER_ACTOR.set(actor)
                    try:
                        with patch("company.ceo.httpx.AsyncClient") as shared:
                            text = await _generate(
                                system_instruction="System", prompt="Hello"
                            )
                            self.assertEqual(text, "Connection contract passed.")
                            shared.assert_not_called()
                        with (
                            patch(
                                "company.team.get_team",
                                return_value={"mode": "undecided", "members": []},
                            ),
                            patch("company.team.assignment", return_value=None),
                            patch("company.runtime._openrouter_client") as shared,
                        ):
                            for profile in PROFILES.values():
                                if profile.slug == "ceo":
                                    continue
                                project = "direct-" + uuid.uuid4().hex[:12]
                                group = None
                                if profile.reports_to != "ceo":
                                    group = ensure_director_group(
                                        actor,
                                        project,
                                        profile.reports_to,
                                        "Verify workspace API routing",
                                    )
                                report = await run_company_agent(
                                    profile.slug,
                                    "Report the connection status.",
                                    project,
                                    actor_id=actor,
                                    requested_by=profile.reports_to,
                                    delegation_depth=1
                                    if profile.reports_to == "ceo"
                                    else 2,
                                    group_id=group["group_id"] if group else None,
                                )
                                self.assertEqual(
                                    report["message"],
                                    "Connection contract passed.",
                                    profile.slug,
                                )
                                self.assertEqual(report["model"], model, profile.slug)
                            shared.assert_not_called()
                    finally:
                        DEVELOPER_ACTOR.reset(token)
                    # Worker reviews set their own workspace context, even without a founder request.
                    database = WorkStore(Path(directory) / "review.sqlite3")
                    project = "review-check"
                    manager = PROFILES["finance"].slug
                    database.configure(actor, project, True, model)
                    parent = database.create(
                        actor,
                        project,
                        title="Financial summary",
                        description="Provide the requested report.",
                        kind="human",
                        assignee="human:test",
                        manager=manager,
                    )
                    database.update(
                        actor,
                        project,
                        parent["id"],
                        status="submitted",
                        result="Completed financial summary.",
                    )
                    review = database.create(
                        actor,
                        project,
                        title="Review financial summary",
                        description="Review the submission.",
                        kind="review",
                        assignee=manager,
                        manager=manager,
                        parent=parent["id"],
                    )
                    with patch("company.ceo.httpx.AsyncClient") as shared:
                        await CompanyWorker(database).execute(review)
                        shared.assert_not_called()
                    self.assertEqual(
                        database.get(actor, project, parent["id"])["status"], "accepted"
                    )
                self.assertEqual(len(requests), len(PROFILES) + 2)
