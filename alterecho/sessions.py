"""Server-owned tasks, native provider sessions, canonical persistence and replay."""
from .i18n import message as t, error_info
import asyncio
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import time

from . import profile_runtime as providers
from .config import Config, BridgeError
from .coordinator import Coordinator
from .events import EventLog
from .history import Conversation, now
from .integrations import AdapterCatalog
from .preferences import UserSettings, history_directories, resumed_config
from .stats import summarize
from .storage import Store, scan_conversations, atomic_write
from .security import safe_error


SLOTS = providers.SLOTS
LETTERS = {v: k for k, v in SLOTS.items()}


class Conflict(BridgeError):
    pass


def public_profile(profile):
    return {k: v for k, v in profile.items() if k != "binary"} | {"billable": profile["provider"] in {"openai", "openrouter"}}


def public_config(cfg):
    values = cfg.to_dict()
    allowed = {"topic", "mode", "max_turns", "delay", "timeout", "codex_effort", "ollama_keep_alive", "ollama_unload_on_exit", "num_ctx", "num_predict", "api_max_output_tokens", "temperature", "ollama_options"}
    result = {k: v for k, v in values.items() if k in allowed}
    result.update(first=LETTERS[cfg.first], roles={LETTERS[s]: v for s, v in cfg.roles.items()},
                  positions={LETTERS[s]: v for s, v in cfg.positions.items()},
                  participants={LETTERS[s]: {"profile_id": p["id"], "model": p["model"], "name": p["name"], "provider": p["provider"], "billable": p["provider"] in {"openai", "openrouter"}}
                                for s, p in providers.effective_pair(cfg).items()})
    return result


def public_message(message):
    result = asdict(message)
    result["speaker"] = LETTERS[result["speaker"]]
    return result


class SessionManager:
    def __init__(self, settings, preferences=None):
        self.settings = settings
        self.preferences = preferences or UserSettings(settings.directory / "config.json")
        self.catalog = AdapterCatalog(settings.directory / "adapters.json")
        self.config = self.preferences.load()
        self.tasks, self.loaded, self.stores = {}, {}, {}
        self.logs, self.signals, self.pauses = {}, {}, set()
        self.lock = asyncio.Lock()
        self.closing = False
        self.provider_status = {}
        self.active_threads = set()

    def refresh(self):
        roots = history_directories(self.config, self.preferences)
        entries, errors = scan_conversations(roots)
        seen, duplicate = set(), set()
        for entry in entries:
            if not any(entry.path.is_relative_to(root) for root in roots):
                continue
            cid = entry.conversation.id
            if cid in seen:
                duplicate.add(cid)
            seen.add(cid)
            if cid not in self.tasks:
                self.loaded[cid], self.stores[cid] = entry.conversation, Store(entry.path)
        self.duplicates = duplicate
        self.scan_errors = len(errors)

    def get(self, cid):
        if cid not in self.loaded:
            self.refresh()
        if cid in getattr(self, "duplicates", set()):
            raise Conflict(t('sessions.duplicate_id_in_multiple_histories_resolve_the_duplicate_before_proceeding'))
        if cid not in self.loaded:
            raise KeyError(cid)
        return self.loaded[cid]

    def snapshot(self, cid):
        c = self.get(cid)
        cfg = Config(**c.config)
        status = c.status
        if cid not in self.tasks and status in {"running", "starting", "stopping"}:
            status = "interrupted"
        partial = None
        if c.partial:
            partial = {k: c.partial[k] for k in ("speaker", "model", "text", "timestamp") if k in c.partial}
            partial["speaker"] = LETTERS.get(partial.get("speaker"), "A")
        stats = summarize(c)
        stats["speakers"] = {LETTERS[s]: v for s, v in stats["speakers"].items()}
        return {"id": c.id, "created_at": c.created_at, "config": public_config(cfg),
                "status": status, "error": safe_error(c.error, providers.effective_pair(cfg).values()) if c.error else None, "error_info": error_info(safe_error(c.error, providers.effective_pair(cfg).values())) if c.error else {}, "messages": [public_message(m) for m in c.messages],
                "partial": partial, "stats": stats, "active": cid in self.tasks,
                "pause_requested": cid in self.pauses, "demo": bool(c.messages and c.messages[0].model.startswith("mock-"))}

    def list(self):
        self.refresh()
        result = []
        for cid in self.loaded:
            if cid in self.duplicates:
                continue
            s = self.snapshot(cid)
            s["message_count"] = len(s.pop("messages"))
            s["source_name"] = self.stores[cid].path.name
            s.pop("partial")
            result.append(s)
        return sorted(result, key=lambda c: c["created_at"], reverse=True)

    def log(self, cid):
        return self.logs.setdefault(cid, EventLog())

    def emit(self, cid, kind, data=None):
        data = deepcopy(data or {})
        if data.get('error'):
            data['error_info'] = error_info(data['error'])
        if "speaker" in data:
            data["speaker"] = LETTERS.get(data["speaker"], data["speaker"])
        if "message" in data:
            data["message"]["speaker"] = LETTERS[data["message"]["speaker"]]
        if "speakers" in data:
            data["speakers"] = {LETTERS[s]: v for s, v in data["speakers"].items()}
        self.log(cid).append(kind, cid, data)
        self.signals.setdefault(cid, asyncio.Event()).set()

    def configuration(self, patch):
        cfg = Config(**self.config.to_dict())
        cfg.adapter_pair = providers.effective_pair(cfg)
        values = patch.model_dump(exclude_none=True)
        participants = values.pop("participants", None)
        if participants is not None:
            if set(participants) != {"A", "B"}:
                raise BridgeError(t('sessions.select_both_participants_a_and_b'))
            profiles = {p["id"]: p for p in self.catalog.load(cfg)}
            for letter, selection in participants.items():
                if selection["profile_id"] not in profiles:
                    raise BridgeError(t('sessions.profile_not_registered_on_the_server'))
                cfg.adapter_pair[SLOTS[letter]] = deepcopy(profiles[selection["profile_id"]])
                cfg.adapter_pair[SLOTS[letter]]["model"] = selection["model"]
        for name, value in values.items():
            if name == "first":
                value = SLOTS[value]
            elif name in {"roles", "positions"}:
                value = {SLOTS[k]: v for k, v in value.items()}
            setattr(cfg, name, value)
        return providers.normalize_config(cfg)

    def require_paid(self, cfg, confirmation):
        if any(p["provider"] in {"openai", "openrouter"} for p in providers.effective_pair(cfg).values()) and not confirmation:
            raise BridgeError(t('sessions.metered_api_provider_explicit_confirmation_required_confirm_paid_true_confirm_paid'))

    async def diagnose(self):
        profiles = self.catalog.load(self.config)
        result = []
        # Sequential catalog probing avoids a process/request burst; never calls
        # prepare(), attach() or generate(). No inference and no model unload.
        for profile in profiles:
            cfg = Config(**self.config.to_dict())
            slot = "codex" if profile["provider"] == "codex" else "ollama"
            cfg.adapter_pair = {slot: profile}
            adapters = providers.build_adapters(cfg)
            try:
                models = await providers.catalog(adapters[slot], profile)
                if profile["provider"] == "codex":
                    models = [{k: m[k] for k in ("model", "defaultReasoningEffort", "supportedReasoningEfforts") if k in m} for m in models]
                result.append({"profile_id": profile["id"], "name": profile["name"], "provider": profile["provider"], "available": True,
                               "models": models, "checked_at": now()})
            except Exception as e:
                result.append({"profile_id": profile["id"], "name": profile["name"], "provider": profile["provider"], "available": False,
                               "models": [], "error": safe_error(e, [profile]) if isinstance(e, BridgeError) else t('errors.provider_unreachable'), "checked_at": now(), "error_info": error_info(safe_error(e, [profile]))})
            finally:
                await providers.close_adapters(adapters)
        self.provider_status = {r["profile_id"]: r for r in result}
        return result

    async def create(self, request):
        async with self.lock:
            self.check_capacity()
            cfg = self.configuration(request.configuration)
            if not request.demo:
                self.require_paid(cfg, request.confirm_paid)
                if any(not p["model"] for p in cfg.adapter_pair.values()):
                    raise BridgeError(t('sessions.choose_a_model_for_both_participants'))
            else:
                cfg.codex_model, cfg.ollama_model = "mock-codex", "mock-ollama"
            c = Conversation(cfg.to_dict())
            store = Store(Path(cfg.output_dir) / c.id / f"{c.id}.json")
            self.loaded[c.id], self.stores[c.id] = c, store
            store.save(c)
            self.emit(c.id, "conversation.created")
            self.launch(c, cfg, request.demo)
            return c.id

    def check_capacity(self):
        if self.closing:
            raise Conflict(t('sessions.server_shutting_down'))
        if len(self.tasks) >= self.settings.max_active:
            raise Conflict(t('sessions.active_conversation_limit_reached'))

    def backup(self, cid):
        store = self.stores[cid]
        target = store.path.parent / ".backups" / f"{store.path.name}.{time.time_ns()}.bak"
        atomic_write(target, store.path.read_text(encoding="utf-8"))

    async def preflight(self, cid):
        # Read-only Codex recovery on a copy; the actual resume verifies again.
        async with self.lock:
            c = deepcopy(self.get(cid))
            if cid in self.tasks:
                raise Conflict(t('sessions.conversation_already_active'))
            if c.messages and any(m.model.startswith("mock-") for m in c.messages):
                raise BridgeError(t('sessions.demo_histories_cannot_be_resumed_with_real_models'))
            if c.codex_thread_id and c.codex_thread_id in self.active_threads:
                raise Conflict(t('sessions.codex_thread_already_used_by_another_conversation'))
            cfg = providers.normalize_config(resumed_config(c, self.stores[cid].path))
            adapters = providers.build_adapters(cfg)
            try:
                for slot, p in cfg.adapter_pair.items():
                    if p["provider"] == "codex":
                        await adapters[slot].start()
                        await adapters[slot].attach(c, lambda: None)
            finally:
                await providers.close_adapters(adapters)
            return {"messages": len(c.messages), "configuration": public_config(cfg)}

    async def resume(self, cid, request):
        async with self.lock:
            self.check_capacity()
            c = self.get(cid)
            if cid in self.tasks:
                raise Conflict(t('sessions.conversation_already_active'))
            if c.messages and any(m.model.startswith("mock-") for m in c.messages):
                raise BridgeError(t('sessions.demo_histories_cannot_be_resumed_with_real_models'))
            if c.codex_thread_id and c.codex_thread_id in self.active_threads:
                raise Conflict(t('sessions.codex_thread_already_used_by_another_conversation'))
            cfg = providers.normalize_config(resumed_config(c, self.stores[cid].path))
            cfg.max_turns = request.max_turns
            if request.num_ctx is not None:
                cfg.num_ctx = request.num_ctx
            cfg.validate()
            if cfg.max_turns <= len(c.messages):
                raise BridgeError(t('sessions.new_maximum_must_exceed_saved_messages'))
            self.require_paid(cfg, request.confirm_paid)
            self.backup(cid)
            self.pauses.discard(cid)
            self.emit(cid, "conversation.resumed")
            self.launch(c, cfg)

    def launch(self, c, cfg, demo=False):
        c.status = "starting"
        if c.codex_thread_id:
            self.active_threads.add(c.codex_thread_id)
        self.tasks[c.id] = asyncio.create_task(self.run(c, cfg, demo), name=f"conversation:{c.id}")

    async def run(self, c, cfg, demo):
        adapters = {}
        thread = c.codex_thread_id
        owned_threads = {thread} if thread else set()
        if thread:
            self.active_threads.add(thread)
        try:
            adapters = {s: providers.DemoAdapter(s) for s in SLOTS.values()} if demo else providers.build_adapters(cfg)
            if not demo:
                for slot, p in cfg.adapter_pair.items():
                    adapter = adapters[slot]
                    models = await providers.catalog(adapter, p)
                    values = [m["model"] for m in models] if p["provider"] == "codex" else models
                    if p["model"] not in values:
                        raise BridgeError(t('sessions.model_unavailable_in_the_catalog' ,p0=p['name']))
                    if p["provider"] == "codex":
                        await adapter.attach(c, lambda: self.stores[c.id].save(c))
                        if c.codex_thread_id != thread:
                            if c.codex_thread_id in self.active_threads:
                                raise Conflict(t('sessions.codex_thread_already_in_use'))
                            self.active_threads.add(c.codex_thread_id)
                            owned_threads.add(c.codex_thread_id)
                    elif p["provider"] == "ollama":
                        await adapter.prepare()
            # Preserve a partial in the pre-resume backup before retrying a
            # stateless provider. Native Codex verifies its pending turn first.
            c.config, c.partial, c.pending = cfg.to_dict(), None, None
            await Coordinator(cfg, c, adapters, self.stores[c.id], lambda k, d: self.emit(c.id, k, d), lambda: c.id in self.pauses).run()
        except asyncio.CancelledError:
            if c.status != "interrupted":
                self.emit(c.id, "conversation.stopped", {"status": "interrupted"})
            c.status = "interrupted"
        except Exception as e:
            c.status, c.error = "failed", safe_error(e, cfg.adapter_pair.values()) if isinstance(e, BridgeError) else t('errors.internal_provider')
            self.emit(c.id, "conversation.failed", {"status": c.status, "error": c.error})
        finally:
            try:
                await providers.close_adapters(adapters)
                self.stores[c.id].save(c)
                self.stores[c.id].export(c)
            except Exception:
                c.status, c.error = "failed", t('errors.save_failed')
                self.emit(c.id, "conversation.failed", {"status": c.status, "error": c.error})
            finally:
                self.tasks.pop(c.id, None)
                self.active_threads.difference_update(owned_threads)
                self.pauses.discard(c.id)
                self.signals.setdefault(c.id, asyncio.Event()).set()

    async def stop(self, cid):
        self.get(cid)
        task = self.tasks.get(cid)
        if task:
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.snapshot(cid)

    async def shutdown(self):
        self.closing = True
        tasks = list(self.tasks.values())
        await asyncio.sleep(0)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
