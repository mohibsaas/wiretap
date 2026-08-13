"""Local FastAPI app for the wiretap dashboard."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from wiretap import __version__
from wiretap.paths import wiretap_root
from wiretap.services.batches import batch_public, get_batch, start_batch
from wiretap.services.generator import list_categories
from wiretap.services.onboard import (
    configure_caller,
    connect_agent,
    generate_onboard_suite,
    list_agents,
    onboard_status,
)
from wiretap.services.secrets import key_status, load_dotenv, upsert_secrets
from wiretap.services.simulations import get_simulation_detail, list_simulations
from wiretap.suite.evaluations import evaluation_run_detail, list_evaluation_runs
from wiretap.services.suites import get_suite, list_suites, suite_public_dict

STATIC_DIR = Path(__file__).resolve().parent / "static"


class StartBatchBody(BaseModel):
    suite: str = "default"
    all_scenarios: bool = Field(False, alias="all")
    scenario: str | None = None
    concurrency: int = 1
    strict: bool = False
    agent_id: str | None = None
    platform: str | None = None
    token_env: str | None = None
    agent_from: str | None = None

    model_config = {"populate_by_name": True}


class SecretsBody(BaseModel):
    secrets: dict[str, str]


class ConnectBody(BaseModel):
    platform: str
    agent_id: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    room_url: str | None = None


class CallerBody(BaseModel):
    llm_provider: str = "openai"
    llm_api_key: str | None = None
    simulator_model: str = "gpt-4o-mini"
    judge_model: str = "gpt-4o-mini"
    stt: str = "pyai"
    tts: str = "pyai"
    voice: str = "alloy"
    speech_api_key: str | None = None
    stt_api_key: str | None = None
    tts_api_key: str | None = None


class GenerateBody(BaseModel):
    purpose: str = ""
    categories: list[str]
    tests_per_category: int = Field(5, ge=1, le=10)
    suite_name: str | None = None


def create_app(*, cwd: Path | None = None) -> FastAPI:
    root = cwd or Path.cwd()
    load_dotenv(root)
    app = FastAPI(title="wiretap", version=__version__)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "version": __version__,
            "cwd": str(root),
            "wiretap_root": str(wiretap_root(root)),
        }

    @app.get("/api/onboard/status")
    def api_onboard_status() -> dict[str, Any]:
        return onboard_status(root)

    @app.get("/api/secrets/status")
    def api_secrets_status() -> dict[str, bool]:
        return key_status(root)

    @app.post("/api/secrets")
    def api_upsert_secrets(body: SecretsBody) -> dict[str, Any]:
        try:
            updated = upsert_secrets(body.secrets, root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"updated": updated, "status": key_status(root)}

    @app.get("/api/categories")
    def api_categories() -> list[dict[str, Any]]:
        return list_categories()

    @app.post("/api/onboard/caller")
    def api_caller(body: CallerBody) -> dict[str, Any]:
        try:
            return configure_caller(
                llm_provider=body.llm_provider,
                llm_api_key=body.llm_api_key,
                simulator_model=body.simulator_model,
                judge_model=body.judge_model,
                stt=body.stt,
                tts=body.tts,
                voice=body.voice,
                speech_api_key=body.speech_api_key,
                stt_api_key=body.stt_api_key,
                tts_api_key=body.tts_api_key,
                cwd=root,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/providers")
    def api_providers() -> dict[str, Any]:
        from wiretap.providers.catalog import provider_catalog

        return provider_catalog()

    @app.post("/api/onboard/connect")
    async def api_connect(body: ConnectBody) -> dict[str, Any]:
        try:
            return await connect_agent(
                platform=body.platform,
                agent_id=body.agent_id,
                api_key=body.api_key,
                api_secret=body.api_secret,
                room_url=body.room_url,
                cwd=root,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(502, f"Connect failed: {exc}") from exc
        except Exception as exc:
            msg = str(exc)
            if "API" in msg.upper() and "KEY" in msg.upper():
                msg = "Connect failed (check API key / agent id)"
            raise HTTPException(502, f"Connect failed: {msg}") from exc

    @app.post("/api/onboard/generate")
    def api_generate(body: GenerateBody) -> dict[str, Any]:
        try:
            return generate_onboard_suite(
                purpose=body.purpose,
                categories=body.categories,
                tests_per_category=body.tests_per_category,
                suite_name=body.suite_name,
                cwd=root,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/agents")
    def api_agents() -> list[dict[str, Any]]:
        return list_agents(root)

    @app.get("/api/suites")
    def api_list_suites() -> list[dict[str, Any]]:
        return list_suites(root)

    @app.get("/api/suites/{name}")
    def api_get_suite(name: str) -> dict[str, Any]:
        try:
            suite = get_suite(name, root)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return suite_public_dict(suite, name=name)

    @app.post("/api/batches")
    async def api_start_batch(body: StartBatchBody) -> dict[str, str]:
        try:
            batch = start_batch(
                suite=body.suite,
                all_scenarios=body.all_scenarios,
                scenario_id=body.scenario,
                concurrency=body.concurrency,
                strict=body.strict,
                agent_id=body.agent_id,
                platform=body.platform,
                token_env=body.token_env,
                agent_from=body.agent_from,
                cwd=root,
            )
        except (KeyError, ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"batch_id": batch.batch_id}

    @app.get("/api/batches/{batch_id}")
    def api_get_batch(batch_id: str) -> dict[str, Any]:
        batch = get_batch(batch_id)
        if not batch:
            raise HTTPException(404, "batch not found")
        return batch_public(batch)

    @app.get("/api/batches/{batch_id}/events")
    async def api_batch_events(batch_id: str) -> StreamingResponse:
        batch = get_batch(batch_id)
        if not batch:
            raise HTTPException(404, "batch not found")

        async def gen():
            q = batch.subscribe()
            while True:
                event = await q.get()
                if event is None:
                    yield "event: end\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/evaluations")
    def api_list_evaluations(limit: int = 40) -> list[dict[str, Any]]:
        """Parent evaluation runs (one suite execution each)."""
        return list_evaluation_runs(root, limit=limit)

    @app.get("/api/evaluations/{batch_id}")
    def api_get_evaluation(batch_id: str) -> dict[str, Any]:
        detail = evaluation_run_detail(batch_id, root)
        if not detail:
            raise HTTPException(404, "evaluation not found")
        return detail

    @app.get("/api/simulations")
    def api_list_simulations(limit: int = 50) -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in list_simulations(root, limit=limit)]

    @app.get("/api/simulations/{simulation_id}")
    def api_get_simulation(simulation_id: str) -> dict[str, Any]:
        art = get_simulation_detail(simulation_id, root)
        if not art:
            raise HTTPException(404, "simulation not found")
        return art.model_dump(mode="json")

    @app.get("/api/simulations/{simulation_id}/audio")
    def api_simulation_audio(simulation_id: str) -> FileResponse:
        from wiretap.suite.audio import resolve_audio_path

        art = get_simulation_detail(simulation_id, root)
        if not art:
            raise HTTPException(404, "simulation not found")
        if not art.audio_path:
            raise HTTPException(404, "no audio for this simulation")
        path = resolve_audio_path(art.audio_path, root)
        if not path:
            raise HTTPException(404, "audio file missing")
        return FileResponse(path, media_type="audio/wav", filename=f"{simulation_id}.wav")

    if STATIC_DIR.is_dir() and (STATIC_DIR / "index.html").is_file():
        assets = STATIC_DIR / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(404)
            candidate = STATIC_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")
    else:

        @app.get("/")
        def index_fallback() -> dict[str, str]:
            return {
                "message": "wiretap UI API is running. Build the SPA into wiretap/ui/static "
                "(see ui/ README) or open /api/health."
            }

    return app
