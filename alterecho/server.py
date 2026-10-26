"""FastAPI application. One process/worker owns every conversation task."""
import asyncio
from contextlib import asynccontextmanager
from collections import defaultdict, deque
import json
import secrets
from pathlib import Path
import time

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.cors import CORSMiddleware

from . import __version__
from .api_models import Configuration, RunRequest, ResumeRequest, ProfilesRequest
from .config import BridgeError
from .history import now
from .integrations import new_profile
from .server_settings import ServerSettings, ServerLease
from .sessions import SessionManager, Conflict, public_config, public_profile
from .security import safe_error


def create_app(settings=None, manager=None):
    settings = settings or ServerSettings.from_env()
    settings.prepare()
    manager = manager or SessionManager(settings)
    leases = [ServerLease(settings.runtime / "server.lock"), ServerLease(Path(manager.config.output_dir) / ".server.lock")]

    @asynccontextmanager
    async def lifespan(app):
        try:
            for lease in leases:
                lease.acquire()
            manager.refresh()
            if getattr(app.state, "local_control", None):
                await app.state.local_control.start()
            yield
        finally:
            await manager.shutdown()
            for lease in leases:
                lease.release()
            if getattr(app.state, "local_control", None):
                await app.state.local_control.close()

    app = FastAPI(title="AlterEcho", version=__version__, lifespan=lifespan,
                  docs_url="/api/v1/docs", openapi_url="/api/v1/openapi.json", redoc_url=None)
    app.state.manager, app.state.settings = manager, settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    limits = defaultdict(deque)
    streams = defaultdict(int)

    @app.middleware("http")
    async def security(request, call_next):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in settings.origins:
            return JSONResponse({"detail": "Origine non autorizzata."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Richiesta browser da un sito terzo rifiutata."}, status_code=403)
        path = request.url.path
        if path.startswith("/api/") and path != "/api/v1/health":
            supplied = request.headers.get("authorization", "")
            if not secrets.compare_digest(supplied, "Bearer " + settings.token):
                return JSONResponse({"detail": "Token del servizio richiesto."}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
            address = request.client.host if request.client else "unknown"
            bucket = (address, "write" if request.method not in {"GET", "HEAD"} else "read")
            current = time.monotonic()
            q = limits[bucket]
            while q and q[0] < current - 60:
                q.popleft()
            if len(q) >= (30 if bucket[1] == "write" else 240):
                return JSONResponse({"detail": "Troppe richieste. Riprova tra un minuto."}, status_code=429, headers={"Retry-After": "60"})
            q.append(current)
            # Bound memory used by per-client rate buckets.
            if len(limits) > 4096:
                for key in list(limits):
                    if not limits[key] or limits[key][-1] < current - 60:
                        del limits[key]
        if request.method in {"POST", "PUT", "PATCH"}:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Usa application/json."}, status_code=415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 262144:
                    return JSONResponse({"detail": "Richiesta troppo grande."}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                                 "Cache-Control": "no-store", "X-Frame-Options": "DENY",
                                 "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
        return response

    @app.exception_handler(BridgeError)
    async def operational_error(request, error):
        return JSONResponse({"detail": safe_error(error, manager.config.adapter_pair.values())}, status_code=409 if isinstance(error, Conflict) else 400)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Pydantic's default errors include the rejected input. A mistaken
        # credential submission must never be reflected into clients or logs.
        return JSONResponse({"detail": [{k: e[k] for k in ("loc", "msg", "type")} for e in error.errors()]}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({"detail": "Conversazione non trovata."}, status_code=404)

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/version")
    async def version():
        return {"version": __version__, "api": "v1"}

    @app.get("/api/v1/status")
    async def status():
        conversations = manager.list()
        return {"status": "stopping" if manager.closing else "ready", "version": __version__,
                "active": [c for c in conversations if c["active"]], "providers": list(manager.provider_status.values()),
                "history_count": len(conversations), "unreadable_histories": manager.scan_errors,
                "single_worker": True, "managed": getattr(app.state, "managed_identity", None)}

    @app.get("/api/v1/providers")
    async def available_providers():
        from .integrations import PROVIDERS
        return [{"id": k, "name": v, "billable": k in {"openai", "openrouter"}} for k, v in PROVIDERS.items()]

    @app.get("/api/v1/profiles")
    async def profiles():
        return [public_profile(p) for p in manager.catalog.load(manager.config)]

    @app.put("/api/v1/profiles")
    async def update_profiles(request: ProfilesRequest):
        current = {p["id"]: p for p in manager.catalog.load(manager.config)}
        profiles = []
        for p in request.profiles:
            profile = new_profile(p.provider, p.name)
            profile.update(p.model_dump())
            profile["binary"] = current.get(p.id, {}).get("binary", "codex" if p.provider == "codex" else "")
            profiles.append(profile)
        manager.catalog.validate(profiles)
        selected = {p["id"] for p in manager.config.adapter_pair.values()}
        if selected - {p["id"] for p in profiles}:
            raise Conflict("Scegli altri interlocutori nelle impostazioni prima di rimuovere un profilo selezionato.")
        if manager.catalog.path.exists():
            from .storage import atomic_write
            atomic_write(manager.catalog.path.with_name("adapters.json.bak"), manager.catalog.path.read_text(encoding="utf-8"))
        manager.catalog.save(profiles)
        return [public_profile(p) for p in profiles]

    @app.get("/api/v1/models")
    async def models():
        return list(manager.provider_status.values())

    @app.post("/api/v1/doctor")
    async def doctor():
        return {"providers": await manager.diagnose(), "inference": False}

    @app.get("/api/v1/settings")
    async def get_settings():
        return public_config(manager.config)

    @app.put("/api/v1/settings")
    async def put_settings(request: Configuration):
        cfg = manager.configuration(request)
        if manager.preferences.path.exists():
            from .storage import atomic_write
            atomic_write(manager.preferences.path.with_name("config.json.bak"), manager.preferences.path.read_text(encoding="utf-8"))
        manager.preferences.save(cfg)
        manager.config = cfg
        return public_config(cfg)

    @app.get("/api/v1/conversations")
    @app.get("/api/v1/history")
    async def conversations(q: str = "", status: str = "", provider: str = ""):
        return [c for c in manager.list() if q.casefold() in (c["config"]["topic"] + " " + c["id"]).casefold()
                and (not status or c["status"] == status)
                and (not provider or any(p["provider"] == provider for p in c["config"]["participants"].values()))]

    @app.post("/api/v1/conversations", status_code=202)
    async def create_conversation(request: RunRequest):
        cid = await manager.create(request)
        return {"id": cid, "events": f"/api/v1/conversations/{cid}/events"}

    @app.get("/api/v1/conversations/{cid}")
    async def conversation(cid: str):
        return manager.snapshot(cid)

    @app.post("/api/v1/conversations/{cid}/preflight")
    async def preflight(cid: str):
        return await manager.preflight(cid)

    @app.post("/api/v1/conversations/{cid}/resume", status_code=202)
    async def resume(cid: str, request: ResumeRequest):
        await manager.resume(cid, request)
        return {"id": cid}

    @app.post("/api/v1/conversations/{cid}/stop")
    async def stop(cid: str):
        return await manager.stop(cid)

    @app.post("/api/v1/conversations/{cid}/pause")
    async def pause(cid: str):
        manager.get(cid)
        if cid not in manager.tasks:
            raise Conflict("La conversazione non è attiva.")
        manager.pauses.add(cid)
        return {"id": cid, "pause_requested": True}

    @app.get("/api/v1/conversations/{cid}/stats")
    async def stats(cid: str):
        return manager.snapshot(cid)["stats"]

    @app.delete("/api/v1/conversations/{cid}")
    async def delete(cid: str):
        async with manager.lock:
            manager.get(cid)
            if cid in manager.tasks:
                raise Conflict("Arresta la conversazione prima di eliminarla.")
            manager.stores[cid].delete(cid)
            manager.loaded.pop(cid, None)
            manager.stores.pop(cid, None)
            manager.logs.pop(cid, None)
            return {"deleted": cid}

    @app.get("/api/v1/conversations/{cid}/export/{format}")
    async def export(cid: str, format: str):
        c = manager.get(cid)
        if format not in {"json", "md", "txt", "html"}:
            raise HTTPException(400, "Formato non supportato.")
        store = manager.stores[cid]
        if format == "json":
            return JSONResponse(c.to_dict(), headers={"Content-Disposition": f'attachment; filename="conversation.json"'})
        path = store.export(c, [format])[0]
        return FileResponse(path, filename=f"conversation.{format}", media_type="application/octet-stream")

    @app.get("/api/v1/conversations/{cid}/events")
    async def events(cid: str, request: Request):
        manager.get(cid)
        address = request.client.host if request.client else "unknown"
        if streams[address] >= 8:
            raise HTTPException(429, "Troppi stream simultanei.")
        streams[address] += 1
        cursor = request.headers.get("last-event-id")

        async def stream():
            nonlocal cursor
            signal = manager.signals.setdefault(cid, asyncio.Event())
            try:
                while True:
                    signal.clear()
                    log = manager.log(cid)
                    batch = log.after(cursor) if cursor else None
                    if batch is None:
                        snapshot = manager.snapshot(cid)
                        cursor = log.cursor
                        event = {"id": cursor, "type": "state.snapshot", "conversation_id": cid, "timestamp": now(), "data": snapshot}
                        yield f"id: {cursor}\nevent: state.snapshot\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    else:
                        for event in batch:
                            cursor = event.id
                            yield f"id: {cursor}\nevent: {event.type}\ndata: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
                    if cid not in manager.tasks:
                        return
                    if await request.is_disconnected():
                        return
                    try:
                        await asyncio.wait_for(signal.wait(), 15)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
            finally:
                streams[address] -= 1
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

    static = Path(__file__).parent / "static"
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def web():
        if not (static / "index.html").is_file():
            return JSONResponse({"detail": "Frontend non compilato: esegui npm ci e npm run build in web/."}, status_code=503)
        return FileResponse(static / "index.html")
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins,
                       allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
                       allow_credentials=False)
    return app


def serve(host=None, port=None):
    import os
    import uvicorn
    settings = ServerSettings.from_env(host, port)
    app = create_app(settings)
    print(f"AlterEcho headless: http://{settings.host}:{settings.port}")
    print(f"Token locale: {settings.directory / 'server-token'} (oppure ALTERECHO_TOKEN)")
    # No reload/multiple workers: every task belongs to this process.
    trusted_proxies = os.environ.get("ALTERECHO_PROXY_IPS", "")
    def request_shutdown():
        # End owned generation tasks/checkpoints before Uvicorn drains SSE
        # connections, so attached clients cannot delay graceful shutdown.
        server.should_exit = True
        try:
            asyncio.get_running_loop().create_task(app.state.manager.shutdown())
        except RuntimeError:
            pass  # Lifespan still performs cleanup if startup has no loop yet.

    class HeadlessServer(uvicorn.Server):
        def handle_exit(self, sig, frame):
            super().handle_exit(sig, frame)
            request_shutdown()

    server = HeadlessServer(uvicorn.Config(app, host=settings.host, port=settings.port, workers=1, access_log=False,
                proxy_headers=bool(trusted_proxies), forwarded_allow_ips=trusted_proxies,
                timeout_graceful_shutdown=30))
    instance = os.environ.pop("ALTERECHO_MANAGED_ID", "")
    secret = os.environ.pop("ALTERECHO_MANAGED_SECRET", "")
    if instance and secret:
        from .managed import LocalControl
        app.state.managed_identity = {"instance": instance, "pid": os.getpid()}
        app.state.local_control = LocalControl(settings, instance, secret, request_shutdown)
    server.run()
