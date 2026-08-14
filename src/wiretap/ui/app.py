"""Local FastAPI app for the wiretap dashboard."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

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
from wiretap.services.suites import (
    AddSuiteCaseBody,
    CreateSuiteBody,
    UpdateSuiteBody,
    add_suite_case,
    create_blank_suite,
    delete_suite,
    get_suite,
    list_suites,
    suite_public_dict,
    update_suite_cases,
    validate_suite_name,
)
from wiretap.suite.evaluations import evaluation_run_detail, list_evaluation_runs

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
    # Per-run: "web" or "phone" (or a literal transport kind). None keeps the
    # suite's own transport.
    transport: str | None = None
    phone: str | None = None

    model_config = {"populate_by_name": True}


class SecretsBody(BaseModel):
    secrets: dict[str, str]


class FromNumberBody(BaseModel):
    from_number: str


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
    voice: str = ""
    speech_api_key: str | None = None
    stt_api_key: str | None = None
    tts_api_key: str | None = None


class TtsVoicesBody(BaseModel):
    api_key: str | None = None


class LlmModelsBody(BaseModel):
    api_key: str | None = None


class GenerateBody(BaseModel):
    purpose: str = ""
    categories: list[str]
    tests_per_category: int = Field(5, ge=1, le=10)
    suite_name: str | None = None


def create_app(*, cwd: Path | None = None) -> FastAPI:
    """Create the dashboard app.

    ``cwd=None`` uses the global data dir (``~/.wiretap`` / ``WIRETAP_HOME``).
    Pass an explicit ``cwd`` in tests to isolate under ``{cwd}/.wiretap``.
    """
    load_dotenv(cwd)
    app = FastAPI(title="wiretap", version=__version__)

    @app.middleware("http")
    async def _reload_dotenv(request, call_next):  # type: ignore[no-untyped-def]
        # Re-hydrate os.environ from dotenv on each API call so the UI picks up
        # keys written by `wiretap init` / CLI after the server started.
        if request.url.path.startswith("/api/"):
            load_dotenv(cwd)
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        from wiretap.services.secrets import env_file, key_report

        report = key_report(cwd)
        return {
            "version": __version__,
            "cwd": str(cwd) if cwd is not None else str(Path.cwd()),
            "wiretap_root": str(wiretap_root(cwd)),
            "secrets_file": str(env_file(cwd)),
            "secrets_file_exists": bool(report.get("wiretap_env_exists")),
            "project_env": report.get("project_env"),
            "legacy_env": report.get("legacy_env"),
        }

    @app.get("/api/onboard/status")
    def api_onboard_status() -> dict[str, Any]:
        return onboard_status(cwd)

    @app.get("/api/secrets/status")
    def api_secrets_status() -> dict[str, bool]:
        return key_status(cwd)

    @app.post("/api/secrets")
    def api_upsert_secrets(body: SecretsBody) -> dict[str, Any]:
        try:
            updated = upsert_secrets(body.secrets, cwd)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"updated": updated, "status": key_status(cwd)}

    @app.get("/api/pstn/status")
    def api_pstn_status() -> dict[str, Any]:
        """Phone-testing readiness: presence of credentials, extra and caller number."""
        from wiretap.services.twilio_pstn import pstn_status

        return pstn_status(cwd)

    @app.get("/api/pstn/agent-number")
    def api_pstn_agent_number(
        suite: str,
        agent_from: str | None = None,
    ) -> dict[str, Any]:
        """The number a phone run would dial for this suite, when one is known.

        Lets the run dialog show the target up front instead of failing at dial
        time, and tells it when the user has to type one in.
        """
        from wiretap.services.agent_numbers import resolve_agent_number
        from wiretap.suite.agent_override import with_agent_override

        try:
            cfg = get_suite(validate_suite_name(suite), cwd)
            if agent_from:
                cfg = with_agent_override(cfg, agent_from=agent_from, cwd=cwd)
            number, source = resolve_agent_number(cfg, cwd=cwd)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"number": number, "source": source}

    @app.get("/api/twilio/phone-numbers")
    def api_twilio_numbers(limit: int = 20, contains: str | None = None) -> dict[str, Any]:
        """Caller numbers on the user's Twilio account, plus the saved pick.

        Paged: large accounts hold thousands of numbers, so callers search.
        """
        from wiretap.services.twilio_pstn import list_phone_numbers, saved_from_number

        try:
            numbers = list_phone_numbers(limit=max(1, min(limit, 100)), contains=contains)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # surface Twilio SDK errors as 502, not a 500
            raise HTTPException(502, f"Twilio lookup failed: {exc}") from exc
        return {"numbers": numbers, "selected": saved_from_number(cwd)}

    @app.post("/api/twilio/from-number")
    def api_twilio_from_number(body: FromNumberBody) -> dict[str, Any]:
        from wiretap.services.twilio_pstn import save_from_number

        try:
            selected = save_from_number(body.from_number, cwd)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"selected": selected}

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
                cwd=cwd,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/providers")
    def api_providers() -> dict[str, Any]:
        from wiretap.providers.catalog import provider_catalog

        return provider_catalog()

    @app.post("/api/providers/tts/{provider}/voices")
    def api_tts_voices(provider: str, body: TtsVoicesBody | None = None) -> dict[str, Any]:
        """Live TTS voices when a key is configured or supplied; curated fallback.

        Optional ``api_key`` is used only for this lookup (never logged/returned).
        """
        from wiretap.providers.voice_catalog import resolve_tts_voices

        load_dotenv(cwd)
        key = (body.api_key if body else None) or None
        return resolve_tts_voices(provider, api_key=key, cwd=cwd)

    @app.post("/api/providers/llm/{provider}/models")
    def api_llm_models(provider: str, body: LlmModelsBody | None = None) -> dict[str, Any]:
        """Live LLM models when a key is configured or supplied; curated fallback."""
        from wiretap.providers.model_catalog import resolve_llm_models

        load_dotenv(cwd)
        key = (body.api_key if body else None) or None
        return resolve_llm_models(provider, api_key=key, cwd=cwd)

    @app.post("/api/platforms/{platform}/agents")
    def api_platform_agents(
        platform: str, body: LlmModelsBody | None = None
    ) -> dict[str, Any]:
        """List remote agents for a platform when an API key is available."""
        from wiretap.importers.remote_agents import list_remote_agents

        load_dotenv(cwd)
        key = (body.api_key if body else None) or None
        return list_remote_agents(platform, api_key=key, cwd=cwd)

    @app.post("/api/onboard/connect")
    async def api_connect(body: ConnectBody) -> dict[str, Any]:
        try:
            return await connect_agent(
                platform=body.platform,
                agent_id=body.agent_id,
                api_key=body.api_key,
                api_secret=body.api_secret,
                room_url=body.room_url,
                cwd=cwd,
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
                cwd=cwd,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/agents")
    def api_agents() -> list[dict[str, Any]]:
        return list_agents(cwd)

    @app.get("/api/suites")
    def api_list_suites() -> list[dict[str, Any]]:
        return list_suites(cwd)

    @app.post("/api/suites")
    def api_create_suite(body: CreateSuiteBody) -> dict[str, Any]:
        """Create a blank suite; cases are added later on the detail page."""
        try:
            suite = create_blank_suite(
                name=body.name,
                title=body.title,
                agent_from=body.agent_from,
                cwd=cwd,
            )
            stem = validate_suite_name(body.name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return suite_public_dict(suite, name=stem)

    @app.get("/api/suites/{name}")
    def api_get_suite(name: str) -> dict[str, Any]:
        try:
            stem = validate_suite_name(name)
            suite = get_suite(stem, cwd)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return suite_public_dict(suite, name=stem)

    @app.put("/api/suites/{name}")
    def api_update_suite(name: str, body: UpdateSuiteBody) -> dict[str, Any]:
        """Update suite title and/or editable test-case rows in suite YAML."""
        try:
            stem = validate_suite_name(name)
            suite = update_suite_cases(stem, body, cwd)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return suite_public_dict(suite, name=stem)

    @app.post("/api/suites/{name}/cases")
    def api_add_suite_case(name: str, body: AddSuiteCaseBody) -> dict[str, Any]:
        """Append one test case (persona + scenario) to a suite."""
        try:
            stem = validate_suite_name(name)
            suite = add_suite_case(stem, body, cwd)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return suite_public_dict(suite, name=stem)

    @app.delete("/api/suites/{name}")
    def api_delete_suite(name: str) -> dict[str, Any]:
        """Delete a suite YAML and its companion agent graph, if any."""
        try:
            return delete_suite(name, cwd)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/batches")
    async def api_start_batch(body: StartBatchBody) -> dict[str, Any]:
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
                transport=body.transport,
                phone=body.phone,
                cwd=cwd,
            )
        except (KeyError, ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc
        # Include planned cases so the Simulations list can render immediately
        # (before disk progress / finished artifacts exist).
        from wiretap.suite.run_progress import progress_public, read_run_progress

        progress = read_run_progress(batch.batch_id, cwd)
        return {
            "batch_id": batch.batch_id,
            "suite_id": batch.suite,
            "scenario_ids": list(batch.scenario_ids),
            "progress": progress_public(progress) if progress else None,
        }

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
        return list_evaluation_runs(cwd, limit=limit)

    # Separate prefix — avoids /api/evaluations/{batch_id} swallowing "progress".
    @app.get("/api/progress")
    def api_list_run_progress() -> list[dict[str, Any]]:
        """Active (CLI or UI) evaluation progress sidecars."""
        from wiretap.suite.run_progress import list_run_progress, progress_public

        return [progress_public(p) for p in list_run_progress(cwd, active_only=True)]

    @app.get("/api/progress/{batch_id}")
    def api_get_run_progress(batch_id: str) -> dict[str, Any]:
        from wiretap.suite.run_progress import progress_public, read_run_progress

        progress = read_run_progress(batch_id, cwd)
        if not progress:
            raise HTTPException(404, "no live progress for this evaluation")
        return progress_public(progress)

    # Legacy alias — must stay above /api/evaluations/{batch_id}.
    @app.get("/api/evaluations/progress")
    def api_list_evaluation_progress_legacy() -> list[dict[str, Any]]:
        from wiretap.suite.run_progress import list_run_progress, progress_public

        return [progress_public(p) for p in list_run_progress(cwd, active_only=True)]

    @app.get("/api/evaluations/{batch_id}/progress")
    def api_get_evaluation_progress_legacy(batch_id: str) -> dict[str, Any]:
        from wiretap.suite.run_progress import progress_public, read_run_progress

        progress = read_run_progress(batch_id, cwd)
        if not progress:
            raise HTTPException(404, "no live progress for this evaluation")
        return progress_public(progress)

    @app.get("/api/evaluations/{batch_id}")
    def api_get_evaluation(batch_id: str) -> dict[str, Any]:
        detail = evaluation_run_detail(batch_id, cwd)
        if not detail:
            raise HTTPException(404, "evaluation not found")
        return detail

    @app.get("/api/simulations")
    def api_list_simulations(limit: int = 50) -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in list_simulations(cwd, limit=limit)]

    @app.get("/api/simulations/{simulation_id}")
    def api_get_simulation(simulation_id: str) -> dict[str, Any]:
        art = get_simulation_detail(simulation_id, cwd)
        if not art:
            raise HTTPException(404, "simulation not found")
        return art.model_dump(mode="json")

    @app.get("/api/simulations/{simulation_id}/audio")
    def api_simulation_audio(simulation_id: str) -> FileResponse:
        from wiretap.suite.audio import resolve_audio_path

        art = get_simulation_detail(simulation_id, cwd)
        if not art:
            raise HTTPException(404, "simulation not found")
        if not art.audio_path:
            raise HTTPException(404, "no audio for this simulation")
        path = resolve_audio_path(art.audio_path, cwd)
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
