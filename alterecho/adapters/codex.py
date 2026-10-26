from ..i18n import message as t
"""Official app-server JSON lines protocol over stdio; no credentials are read."""
import asyncio
from collections import deque
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .base import Reply
from .. import __version__
from ..config import Config, BridgeError
from ..history import Message, instructions, initial_input, now


SAFE_CONFIG = {
    "model_provider": "openai",
    "forced_login_method": "chatgpt",
    "web_search": "disabled",
    "features.shell_tool": False,
    "features.unified_exec": False,
    "features.shell_snapshot": False,
    "features.multi_agent": False,
    "features.goals": False,
    "features.apps": False,
    "features.hooks": False,
    "features.memories": False,
    "features.remote_plugin": False,
    "features.plugins": False,
    "features.view_image": False,
    "features.computer_use": False,
    "features.browser_use": False,
    "features.browser_use_external": False,
    "features.image_generation": False,
    "features.skill_search": False,
    "features.skill_mcp_dependency_install": False,
    "features.tool_suggest": False,
    "features.sleep_tool": False,
    "features.unbounded_connection_retries": False,
    "features.daemon_auto_start": False,
    "features.code_mode.enabled": False,
    "apps._default.enabled": False,
    "project_doc_max_bytes": 0,
    "model_auto_compact_token_limit": 1000000000,
    "analytics.enabled": False,
}


def child_environment(config):
    env = dict(os.environ)
    # Explicit official home path fixes the desktop Windows CLI home-discovery issue.
    # It points to the existing store. Tokens stay exclusively inside Codex.
    if config.codex_home:
        env["CODEX_HOME"] = str(Path(config.codex_home).expanduser().resolve())
    elif not env.get("CODEX_HOME") and os.name == "nt" and env.get("USERPROFILE"):
        env["CODEX_HOME"] = str(Path(env["USERPROFILE"]) / ".codex")
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    for key in list(env):
        if key.endswith("_API_KEY") or key.startswith("ALTERECHO_TOKEN"):
            env.pop(key, None)
    for profile in config.adapter_pair.values():
        if profile.get("api_key_env"):
            env.pop(profile["api_key_env"], None)
    return env


def safe_config(env):
    values = dict(SAFE_CONFIG)
    # Read configuration only (never auth.json); disable inherited MCP servers/apps.
    import tomllib
    home = env.get("CODEX_HOME")
    if not home:
        home = str(Path.home() / ".codex")
    file = Path(home) / "config.toml"
    if file.exists():
        with file.open("rb") as f:
            loaded = tomllib.load(f)
        for name in loaded.get("mcp_servers", {}):
            values[f"mcp_servers.{name}.enabled"] = False
        for name in loaded.get("apps", {}):
            values[f"apps.{name}.enabled"] = False
    return values


def desktop_codex_candidates(env):
    """Discover native binaries in the observed Windows desktop installation layout."""
    local = env.get("LOCALAPPDATA")
    if not local and env.get("USERPROFILE"):
        local = str(Path(env["USERPROFILE"]) / "AppData" / "Local")
    if not local:
        return []
    directory = Path(local) / "OpenAI" / "Codex" / "bin"
    try:
        candidates = [p for p in directory.glob("*/codex.exe") if p.is_file()]
        direct = directory / "codex.exe"
        if direct.is_file():
            candidates.append(direct)
        return sorted(candidates, key=lambda p: (p.stat().st_mtime_ns, str(p)), reverse=True)
    except OSError:
        return []


def resolve_codex(config, env):
    requested = config.codex_binary
    binary = shutil.which(requested, path=env.get("PATH"))
    if binary:
        return binary
    explicit = Path(requested).expanduser()
    if explicit.is_file():
        return str(explicit.resolve())
    # Respect explicit overrides: a typo must not silently launch another installation.
    if sys.platform == "win32" and requested.lower() in {"codex", "codex.exe"}:
        candidates = desktop_codex_candidates(env)
        if candidates:
            return str(candidates[0])
    raise BridgeError(
        t('errors.codex.codex_cli_not_found_set_codex_binary_in_toml_to_the_full_codex_exe_path_or_make_the_cli_availab' ,p0=requested)
    )


def command(config, env):
    binary = resolve_codex(config, env)
    args = [binary, "app-server", "--listen", "stdio://", "--strict-config"]
    for key, value in safe_config(env).items():
        # JSON scalars are valid TOML scalars here; no shell interpolation.
        args.extend(["-c", f"{key}={json.dumps(value)}"])
    if os.name == "nt" and Path(binary).suffix.lower() in {".cmd", ".bat"}:
        # npm's Windows shim cannot be passed safely to a shell with arbitrary prompts.
        js = Path(binary).parent / "node_modules/@openai/codex/bin/codex.js"
        node = shutil.which("node")
        if not node or not js.exists():
            raise BridgeError(t('errors.codex.use_native_codex_exe_or_install_node_and_the_standard_npm_cli'))
        args = [node, str(js), *args[1:]]
    return args


def agent_text(turn):
    items = [i for i in turn.get("items", []) if i.get("type") == "agentMessage"]
    finals = [i for i in items if i.get("phase") == "final_answer"]
    return "\n\n".join(i.get("text", "") for i in (finals or items))


class CodexAdapter:
    def __init__(self, config: Config):
        self.config = config
        self.process = None
        self.reader = None
        self.stderr_reader = None
        self.stderr_tail = deque(maxlen=12)
        self.requests = {}
        self.events = asyncio.Queue()
        self.sequence = 0
        self.thread_id = None
        self.turn_id = None
        self.catalog = []

    async def start(self):
        env = child_environment(self.config)
        cwd = Path(self.config.codex_work_dir).resolve()
        cwd.mkdir(parents=True, exist_ok=True)
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        self.process = await asyncio.create_subprocess_exec(
            *command(self.config, env), env=env, cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            limit=8 * 1024 * 1024, **kwargs)
        self.reader = asyncio.create_task(self._read())
        self.stderr_reader = asyncio.create_task(self._stderr())
        try:
            await self.rpc("initialize", {"clientInfo": {"name": "alterecho_local", "title": "AlterEcho", "version": __version__}})
        except BridgeError as e:
            await asyncio.sleep(0.05)
            if not self.stderr_tail:
                raise BridgeError(t('errors.codex.startup_home_access', error=e)) from e
            diagnostic = self.stderr_tail[-1]
            raise BridgeError(t('errors.codex.codex_startup_failed' ,p0=e, p1=diagnostic)) from e
        await self.send({"method": "initialized", "params": {}})
        account = (await self.rpc("account/read", {"refreshToken": False})).get("account")
        if not account or account.get("type") != "chatgpt":
            raise BridgeError(t('errors.codex.alterecho_requires_chatgpt_authentication_managed_by_codex_run_codex_login_api_keys_and_other_p'))
        cursor = None
        while True:
            page = await self.rpc("model/list", {"includeHidden": False, "cursor": cursor})
            self.catalog.extend(page.get("data", []))
            cursor = page.get("nextCursor")
            if not cursor:
                break
        return self.catalog

    async def send(self, payload):
        if not self.process or self.process.returncode is not None:
            raise BridgeError(t('errors.codex.codex_app_server_is_not_running'))
        try:
            self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionError) as e:
            raise BridgeError(t('errors.codex.codex_stdio_connection_interrupted')) from e

    async def rpc(self, method, params):
        self.sequence += 1
        ident = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.requests[ident] = future
        try:
            await self.send({"id": ident, "method": method, "params": params})
            return await asyncio.wait_for(future, min(self.config.timeout, 30))
        except TimeoutError as e:
            raise BridgeError(t('errors.codex.codex_rpc_timeout' ,p0=method)) from e
        finally:
            self.requests.pop(ident, None)

    async def _stderr(self):
        while line := await self.process.stderr.readline():
            self.stderr_tail.append(line.decode(errors="replace").rstrip())

    async def _read(self):
        problem = BridgeError(t('errors.codex.connection_closed'))
        try:
            while line := await self.process.stdout.readline():
                event = json.loads(line)
                if "method" in event and "id" in event:
                    # Deny every server-originated tool/approval/input request. Never execute it.
                    method = event["method"]
                    if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
                        await self.send({"id": event["id"], "result": {"decision": "decline"}})
                    else:
                        await self.send({"id": event["id"], "error": {"code": -32601, "message": t('errors.codex.tools_disabled')}})
                    await self.events.put({"method": "bridge/securityError", "params": {"message": t('errors.codex.request_rejected', method=method)}})
                elif "id" in event:
                    future = self.requests.get(event["id"])
                    if future and not future.done():
                        if "error" in event:
                            future.set_exception(BridgeError(f"Codex RPC: {event['error'].get('message', event['error'])}"))
                        else:
                            future.set_result(event.get("result", {}))
                else:
                    await self.events.put(event)
        except (ValueError, OSError) as e:
            problem = BridgeError(t('errors.codex.protocol', error=e))
        finally:
            for future in list(self.requests.values()):
                if not future.done():
                    future.set_exception(problem)
            await self.events.put({"method": "bridge/disconnected", "params": {"message": str(problem)}})

    async def attach(self, conversation, checkpoint):
        cfg = self.config
        # Codex does not persist a rollout for a thread that has never had a turn.
        # Before the first Codex reply, Ollama history is sufficient to start a fresh empty thread.
        if (conversation.codex_thread_id and not conversation.codex_turn_id
                and not any(m.speaker == "codex" for m in conversation.messages)
                and (conversation.pending or {}).get("speaker") != "codex"):
            conversation.codex_thread_id = None
        if cfg.codex_model not in {m.get("model") for m in self.catalog}:
            raise BridgeError(t('errors.codex.codex_model_absent_from_catalog_use_doctor_or_interactive_selection'))
        selected = next(m for m in self.catalog if m.get("model") == cfg.codex_model)
        efforts = {e["reasoningEffort"] for e in selected.get("supportedReasoningEfforts", [])}
        if efforts and cfg.codex_effort not in efforts:
            raise BridgeError(t('errors.codex.reasoning_unsupported_available' ,p0=cfg.codex_effort, p1=', '.join(sorted(efforts))))
        params = {"model": cfg.codex_model, "modelProvider": "openai", "cwd": str(Path(cfg.codex_work_dir).resolve()),
                  "approvalPolicy": "never", "approvalsReviewer": "user", "sandbox": "read-only",
                  "baseInstructions": instructions(cfg, "codex"), "developerInstructions": "Dialogo soltanto testuale. Nessuno strumento è autorizzato.",
                  "config": safe_config(child_environment(cfg))}
        if conversation.codex_thread_id:
            params["threadId"] = conversation.codex_thread_id
            response = await self.rpc("thread/resume", params)
            self.thread_id = conversation.codex_thread_id
            await self._verify_resume(conversation, checkpoint, response["thread"])
        else:
            if conversation.codex_synced_messages or any(m.speaker == "codex" for m in conversation.messages):
                raise BridgeError(t('errors.codex.codex_session_missing_memory_cannot_be_restored_without_duplication'))
            response = await self.rpc("thread/start", params)
            self.thread_id = response["thread"]["id"]
            conversation.codex_thread_id = self.thread_id
            checkpoint()
        if response.get("model") and response["model"] != cfg.codex_model:
            raise BridgeError(t('errors.codex.codex_selected_a_different_model_than_requested'))

    async def _verify_resume(self, conversation, checkpoint, thread):
        turns = thread.get("turns", [])
        last = turns[-1] if turns else None
        pending = conversation.pending
        if pending and pending.get("speaker") == "codex":
            if pending.get("turn_id") and (not last or last.get("id") == conversation.codex_turn_id):
                raise BridgeError(t('errors.codex.codex_turn_started_but_absent_from_restored_history_resume_rejected'))
            # A completed response may have reached Codex's rollout before the local atomic save.
            if last and last.get("id") != conversation.codex_turn_id:
                actual = pending.get("turn_id")
                inputs = [i for i in last.get("items", []) if i.get("type") == "userMessage"]
                text = "".join(p.get("text", "") for i in inputs for p in i.get("content", []) if p.get("type") == "text")
                if (actual and last.get("id") != actual) or text != pending.get("input"):
                    raise BridgeError(t('errors.codex.codex_session_externally_modified_resume_rejected'))
                if last.get("status") != "completed" or not agent_text(last):
                    raise BridgeError(t('errors.codex.incomplete_interrupted_codex_turn_history_saved_automatic_resume_rejected_to_avoid_duplicates_s'))
                if any(i.get("type") in {"contextCompaction", "commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall"} for i in last.get("items", [])):
                    raise BridgeError(t('errors.codex.codex_turn_used_tools_or_compaction_resume_rejected'))
                conversation.messages.append(Message("codex", self.config.codex_model, agent_text(last), pending.get("seconds", 0)))
                conversation.codex_turn_id = last["id"]
                conversation.codex_synced_messages = len(conversation.messages)
                conversation.partial = None
            conversation.pending = None
            checkpoint()
        elif last and last.get("id") != conversation.codex_turn_id:
            raise BridgeError(t('errors.codex.codex_thread_out_of_sync_with_local_history'))
        completed = [m for m in conversation.messages if m.speaker == "codex"]
        if completed and (not last or agent_text(last) != completed[-1].text):
            raise BridgeError(t('errors.codex.last_codex_response_does_not_match_saved_history'))

    async def generate(self, conversation, checkpoint):
        cfg = self.config
        text = conversation.messages[-1].text if conversation.messages else initial_input()
        if len(conversation.messages) - conversation.codex_synced_messages > 1:
            raise BridgeError(t('errors.codex.codex_history_is_out_of_sync'))
        # Discard only notifications from setup/previous completed turns, never protocol failures.
        while not self.events.empty():
            event = self.events.get_nowait()
            if event.get("method", "").startswith("bridge/"):
                raise BridgeError(event["params"]["message"])
        conversation.pending = {"speaker": "codex", "input": text, "timestamp": now()}
        checkpoint()
        pieces = {}
        items = {}
        usage = {}
        final = None
        last_save = 0.0
        started = time.monotonic()
        try:
            async with asyncio.timeout(cfg.timeout):
                result = await self.rpc("turn/start", {"threadId": self.thread_id, "input": [{"type": "text", "text": text}], "effort": cfg.codex_effort})
                self.turn_id = result["turn"]["id"]
                conversation.pending["turn_id"] = self.turn_id
                checkpoint()
                while True:
                    event = await self.events.get()
                    method = event.get("method", "")
                    p = event.get("params", {})
                    if method.startswith("bridge/"):
                        raise BridgeError(p["message"])
                    if p.get("threadId") not in (None, self.thread_id) or p.get("turnId") not in (None, self.turn_id):
                        continue
                    if method == "error" and not p.get("willRetry", False):
                        raise BridgeError(t('errors.codex.codex' ,p0=p.get('error', p)))
                    if method == "thread/compacted":
                        raise BridgeError(t('errors.codex.codex_compacted_context_stopped_to_prevent_silent_memory_loss'))
                    if method in {"item/started", "item/completed"}:
                        item = p.get("item", {})
                        kind = item.get("type")
                        if kind not in {"userMessage", "agentMessage", "reasoning"}:
                            raise BridgeError(t('errors.codex.unauthorized_codex_item_dialogue_stopped' ,p0=kind))
                        if method == "item/completed" and kind == "agentMessage":
                            items[item["id"]] = item
                    if method == "item/agentMessage/delta":
                        ident = p["itemId"]
                        pieces[ident] = pieces.get(ident, "") + p["delta"]
                        conversation.partial = {"speaker": "codex", "model": cfg.codex_model, "text": "\n\n".join(pieces.values()), "timestamp": now()}
                        if hasattr(checkpoint, "delta"):
                            checkpoint.delta("codex", cfg.codex_model, p["delta"])
                        if time.monotonic() - last_save > 0.5:
                            checkpoint()
                            last_save = time.monotonic()
                    if method == "thread/tokenUsage/updated":
                        raw = p["tokenUsage"]["last"]
                        usage = {"input_tokens": raw.get("inputTokens"), "output_tokens": raw.get("outputTokens"), "cached_input_tokens": raw.get("cachedInputTokens"), "reasoning_output_tokens": raw.get("reasoningOutputTokens")}
                        window = p["tokenUsage"].get("modelContextWindow")
                        if window and raw.get("totalTokens", 0) >= window - 2048:
                            raise BridgeError(t('errors.codex.codex_approaching_the_actual_context_limit'))
                    if method == "turn/completed":
                        final = p["turn"]
                        if final["id"] != self.turn_id:
                            continue
                        if final.get("status") != "completed":
                            raise BridgeError(t('errors.codex.codex_turn' ,p0=final.get('status'), p1=final.get('error')))
                        break
            text = agent_text(final) or agent_text({"items": list(items.values())})
            if not text.strip():
                raise BridgeError(t('errors.codex.empty_codex_response_or_missing_final_agentmessage_event'))
            self.turn_id = None
            return Reply(text, cfg.codex_model, usage)
        except TimeoutError as e:
            raise BridgeError(t('errors.codex.codex_turn_timed_out_history_preserved')) from e
        finally:
            if conversation.pending:
                conversation.pending["seconds"] = time.monotonic() - started
            checkpoint()

    async def close(self):
        if self.process and self.process.returncode is None:
            if self.turn_id and self.thread_id:
                try:
                    await asyncio.wait_for(self.rpc("turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id}), 3)
                except (BridgeError, TimeoutError):
                    pass
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), 3)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        for task in (self.reader, self.stderr_reader):
            if task:
                task.cancel()
        await asyncio.gather(*[t for t in (self.reader, self.stderr_reader) if t], return_exceptions=True)
