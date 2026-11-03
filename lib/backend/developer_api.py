"""Founder-only developer connection management; never returns stored API keys."""

import asyncio
from typing import Literal

from developer_connections import (
    connection,
    delete_connection,
    discover_models,
    local_developer_enabled,
    public_connection,
    save_connection,
    validated_settings,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field


class ConnectionSettings(BaseModel):
    provider: Literal["openai", "openrouter", "gemini", "ollama", "custom"]
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    model_name: str = Field(default="", max_length=200)
    api_key: str = Field(default="", max_length=4000, repr=False)
    supports_tools: bool = True
    confirm_usage: bool = False


def connection_failure(error):
    if getattr(error, "status_code", None) in {401, 403}:
        return HTTPException(
            401, "Your provider rejected that API key. Check it and try again."
        )
    return HTTPException(
        502,
        "Could not verify this connection. Check the API address, key, and model server.",
    )


def build_developer_router(access):
    router = APIRouter(prefix="/developer")

    def settings(actor, payload, request, *, discovery=False):
        try:
            value = validated_settings(actor, payload.model_dump(), discovery=discovery)
            if value["local"] and (
                not request.client
                or request.client.host not in {"127.0.0.1", "::1", "testclient"}
            ):
                raise ValueError("Local models are available only from this computer")
            return value
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @router.get("/connection")
    def current(actor=Depends(access)):
        return {
            "connection": public_connection(connection(actor)),
            "local_available": local_developer_enabled(),
        }

    @router.put("/connection")
    def save(payload: ConnectionSettings, request: Request, actor=Depends(access)):
        value = settings(actor, payload, request)
        try:
            available = discover_models(value)
        except Exception as error:
            raise connection_failure(error) from None
        selected = next((m for m in available if m["id"] == value["model"]), None)
        if selected is None:
            raise HTTPException(400, "Choose a model available from this connection")
        value["model_name"] = selected["name"]
        from agent_store import get_agent_store

        database = get_agent_store().work_store
        if database:
            database.pause_actor(actor)
        saved = save_connection(actor, value)
        if database:
            with database.connection() as db:
                db.execute(
                    "UPDATE companies SET model=?, price_limits='{}' WHERE actor=?",
                    (value["model"], actor),
                )
        return {"connection": saved}

    @router.delete("/connection")
    def remove(actor=Depends(access)):
        # Stop unattended work before returning to the server's default provider.
        from agent_store import get_agent_store

        database = get_agent_store().work_store
        if database:
            database.pause_actor(actor)
        delete_connection(actor)
        if database:
            with database.connection() as db:
                db.execute(
                    "UPDATE companies SET model='', price_limits='{}' WHERE actor=?",
                    (actor,),
                )
        return {"removed": True}

    @router.post("/models")
    async def models(
        payload: ConnectionSettings, request: Request, actor=Depends(access)
    ):
        value = settings(actor, payload, request, discovery=True)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(discover_models, value), timeout=18
            )
            return {
                "models": result,
                "selected_available": any(m["id"] == value["model"] for m in result),
            }
        except Exception as error:
            raise connection_failure(error) from None

    return router
