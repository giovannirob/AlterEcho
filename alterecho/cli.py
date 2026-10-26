from .i18n import status as status_label
from .i18n import t, configure, catalogs, localize
import argparse
import asyncio
from pathlib import Path
import sys
import webbrowser
from types import SimpleNamespace

from .config import Config, BridgeError
from .client import APIClient, Connection, RemotePreferences, configuration, to_config
from .history import Conversation, Message
from .ui import Terminal, safe_text


class LocalizedParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._positionals.title = t('cli.arguments')
        self._optionals.title = t('cli.options')
        if self._actions:
            self._actions[0].help = t('cli.show_this_help_and_exit')

    def format_help(self):
        return super().format_help().replace("usage:", t('cli.usage'))

    def format_usage(self):
        return super().format_usage().replace('usage:', t('cli.usage'))

    def error(self, message):
        message = argument_error(message)
        self.print_usage(sys.stderr)
        self.exit(2, t('cli.invalid_arguments_use_alterecho_help_for_help' ,p0=message))


def argument_error(message):
    import re
    match = re.fullmatch(r'argument ([^:]+): (.*)', message)
    if match:
        return t('cli.argument_error', argument=match[1], message=argument_error(match[2]))
    patterns = [
        (r'the following arguments are required: (.*)', 'cli.arguments_required'),
        (r'unrecognized arguments: (.*)', 'cli.arguments_unrecognized'),
        (r'invalid (?:int|float) value: (.*)', 'cli.argument_number'),
        (r'expected one argument', 'cli.argument_expected'),
        (r'not allowed with argument (.*)', 'cli.argument_conflict'),
        (r'invalid choice: (.*)', 'cli.argument_choice'),
    ]
    for pattern, key in patterns:
        match = re.fullmatch(pattern, message)
        if match:
            return t(key, value=match[1] if match.lastindex else '')
    return message


def parser():
    p = LocalizedParser(prog="alterecho", description=t('cli.alterecho_autonomous_conversations_with_codex_ollama_and_optional_openai_openrouter_api_adapter'),
                      formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=t('cli.get_started_alterecho_use_the_menu_to_start_resume_export_and_configure_conversations_settings'))
    p.add_argument("--server", help=t('cli.headless_server_endpoint'))
    p.add_argument('--lang', choices=['auto', *catalogs()], help=t('language.cli_help'))
    sub = p.add_subparsers(dest="action", title=t('cli.commands'))
    commands = {}
    for name, help_text in [("run", t('cli.new_conversation_choose_models_and_confirm')), ("doctor", t('cli.check_connections_and_authentication_without_generating')), ("demo", t('cli.server_simulation_without_models_or_ai_quotas'))]:
        command = sub.add_parser(name, help=help_text, description=help_text)
        commands[name] = command
        command.add_argument("--config", help=t('cli.toml_file_relative_paths_start_in_its_directory'))
        if name != "doctor":
            command.add_argument("--turns", type=int, help=t('cli.maximum_total_messages_not_pairs'))
        if name == "run":
            command.add_argument("--num-ctx", type=int, help=t('cli.ollama_context_in_tokens_more_context_uses_more_memory'))
            command.add_argument("--non-interactive", action="store_true", help=t('cli.use_settings_without_prompts_immediately_start_real_inference'))
    resume = sub.add_parser("resume", help=t('cli.resume_a_json_history_and_verify_the_codex_thread'), description=t('cli.advanced_resume_turns_is_the_new_total_maximum_use_the_menu_to_choose_a_conversation_and_additi'))
    commands["resume"] = resume
    resume.add_argument("path", help=t('cli.conversation_id_or_history_filename_on_the_server'))
    resume.add_argument("--turns", type=int, required=True, help=t('cli.new_total_maximum_including_saved_messages'))
    resume.add_argument("--num-ctx", type=int, help=t('cli.ollama_context_preserve_messages_and_the_codex_session'))
    export = sub.add_parser("export", help=t('cli.export_a_json_history_to_markdown_txt_and_html'), description=t('cli.generate_standalone_exports_without_contacting_models'))
    commands["export"] = export
    export.add_argument("path", help=t('cli.conversation_id_or_history_filename_on_the_server'))
    export.add_argument("--format", dest="formats", nargs="+", choices=["md", "txt", "html"], help=t('cli.generate_only_these_formats_by_default_generate_all_formats'))
    for name in ("status", "stop", "pause", "watch", "web", "connect", "serve", "down"):
        command = sub.add_parser(name, **({"help": t('cli.start_the_server_in_background_without_windows_default'),
                                          "description": t('cli.start_the_server_in_background_without_windows_detach_is_optional_use_foreground_for_diagnostic')} if name == "serve" else {'help': t('cli.command_' + name), 'description': t('cli.command_' + name)}))
        commands[name] = command
        if name in {"stop", "pause", "watch"}:
            command.add_argument("id", help=t('cli.conversation_id_on_the_server'))
        if name == "serve":
            command.add_argument("--host")
            command.add_argument("--port", type=int)
            mode = command.add_mutually_exclusive_group()
            mode.add_argument("--detach", action="store_true", help=t('cli.start_in_background_default'))
            mode.add_argument("--foreground", action="store_true", help=t('cli.foreground_for_diagnostics_docker_and_services'))
        if name == "connect":
            command.add_argument("--token-file", help=t('cli.protected_local_file_containing_the_service_token'))
    for name in ("run", "resume"):
        commands[name].add_argument("--confirm-paid", action="store_true", help=t('cli.explicitly_confirm_metered_api_usage'))
        commands[name].add_argument("--detach", action="store_true", help=t('cli.start_on_the_server_and_return_to_the_terminal'))
    migration = sub.add_parser("migrate", help=t('cli.plan_or_verify_a_copy_of_histories_without_moving_originals'))
    commands["migrate"] = migration
    migration.add_argument("source")
    migration.add_argument("destination")
    migration.add_argument("--apply", action="store_true", help=t('cli.copy_into_a_new_empty_directory_and_verify_sha_256'))
    guide = sub.add_parser("help", help=t('cli.general_or_command_specific_help'))
    guide.add_argument("command", nargs="?", choices=list(commands), help=t('cli.command_to_explain'))
    p.commands = commands
    return p


def resolve_id(client, reference):
    from urllib.parse import quote
    entries = client.get("/conversations")
    matches = [c["id"] for c in entries if c["id"] == reference or c["id"] == Path(reference).stem or c.get("source_name") == Path(reference).name]
    if len(matches) != 1:
        raise BridgeError(t('cli.history_missing_or_ambiguous_on_the_server_use_the_id_from_alterecho_status_or_the_browser_loca'))
    return quote(matches[0], safe="")


from .watching import watch


async def diagnose(cfg, ui, client=None):
    owned = client is None
    client = client or APIClient()
    try:
        result = client.post("/doctor")
        for p in result["providers"]:
            if p["available"]:
                ui.say(t('cli.connected' ,p0=p['name']))
                for model in p["models"]:
                    ui.say("  " + (model["model"] if isinstance(model, dict) else model))
            else:
                ui.error(f"{p['name']}: {localize(p.get('error', t('cli.unavailable')))}")
        ui.say(t('cli.no_inference_started_api_keys_remain_in_the_server_environment'))
        return int(any(not p["available"] for p in result["providers"]))
    finally:
        if owned:
            client.close()


async def execute(args, ui, preferences=None, client=None):
    owned = client is None
    client = client or APIClient(Connection(getattr(args, "server", None)))
    preferences = RemotePreferences(client)
    try:
        action = args.action
        if action == "doctor":
            return await diagnose(None, ui, client)
        if action == "status":
            state = client.get("/status")
            if state.get("managed"):
                from .managed import local_status
                local = local_status()
                if local and local["instance"] == state["managed"]["instance"]:
                    ui.say(t('cli.managed_local_process_log' ,p0=local['pid'], p1=local['log']))
            ui.say(t('cli.server_alterecho_conversations' ,p0=status_label(state['status']), p1=state['version'], p2=t('common.conversations', count=state['history_count'])))
            for p in state["providers"]:
                ui.say(f"{p['name']}: {t('cli.available') if p['available'] else p.get('error', t('cli.error_value'))}")
            for c in state["active"]:
                ui.say(f"{c['id']} · {status_label(c['status'])} · {c['config']['topic']}")
            return 0
        if action in {"stop", "pause"}:
            ui.say(str(client.post(f"/conversations/{args.id}/{action}")))
            return 0
        if action == "watch":
            return await watch(client, resolve_id(client, args.id), ui)
        if action == "export":
            cid = resolve_id(client, args.path)
            for fmt in args.formats or ("md", "txt", "html"):
                response = client.request("GET", f"/conversations/{cid}/export/{fmt}")
                # Downloads are explicit exports, never operational histories.
                target = Path.cwd() / f"{cid}.{fmt}"
                if target.exists():
                    raise BridgeError(t('cli.export_already_exists_move_it_before_retrying' ,p0=target))
                target.write_bytes(response.content)
                ui.say(t('cli.exported' ,p0=target))
            return 0
        if action == "resume":
            cid = resolve_id(client, args.path)
            # Validate overrides before any provider preflight.
            current = client.get(f"/conversations/{cid}")
            candidate = to_config(current["config"], client.get("/profiles"))
            candidate.max_turns = args.turns
            if args.num_ctx is not None:
                candidate.num_ctx = args.num_ctx
            candidate.validate()
            preflight = client.post(f"/conversations/{cid}/preflight")
            cfg = to_config(preflight["configuration"], client.get("/profiles"))
            completed = preflight["messages"]
            cfg.max_turns = completed + args.additional_turns if getattr(args, "additional_turns", None) is not None else args.turns
            cfg.num_ctx = args.num_ctx if args.num_ctx is not None else cfg.num_ctx
            cfg.validate()
            interactive = getattr(args, "confirm", False)
            if interactive and not ui.confirm_run(cfg, completed):
                ui.say(t('cli.resume_cancelled_history_was_not_modified'))
                return 0
            client.post(f"/conversations/{cid}/resume", {"max_turns": cfg.max_turns, "num_ctx": cfg.num_ctx,
                                                        "confirm_paid": interactive or getattr(args, "confirm_paid", False)})
        else:
            cfg = preferences.load()
            if getattr(args, "config", None):
                local = Config.load(args.config)
                # A local TOML supplies dialogue options, never server paths,
                # executable overrides, credentials or unregistered profiles.
                from .client import ClientConfig
                values = cfg.to_dict()
                patch = configuration(local)
                values.update({k: v for k, v in local.to_dict().items() if k in patch and k not in {"first", "roles", "positions", "participants"}})
                values.update(first=local.first, roles=local.roles, positions=local.positions)
                if local.adapter_pair:
                    values["adapter_pair"] = local.adapter_pair
                else:
                    for slot, model in (("codex", local.codex_model), ("ollama", local.ollama_model)):
                        if model:
                            values["adapter_pair"][slot]["model"] = model
                cfg = ClientConfig(**values)
            if getattr(args, "turns", None) is not None:
                cfg.max_turns = args.turns
            if getattr(args, "num_ctx", None) is not None:
                cfg.num_ctx = args.num_ctx
            interactive = action == "run" and not getattr(args, "non_interactive", False)
            if interactive:
                diagnostics = client.post("/doctor")["providers"]
                catalogs = {}
                for slot, p in cfg.adapter_pair.items():
                    d = next((d for d in diagnostics if d["profile_id"] == p["id"]), None)
                    if not d or not d["available"]:
                        raise BridgeError(f"{p['name']}: {d.get('error') if d else t('cli.unregistered_profile')}")
                    catalogs[slot] = d["models"]
                if not ui.configure_profiles(cfg, catalogs):
                    ui.say(t('cli.start_cancelled_no_messages_generated'))
                    return 0
                preferences.save(cfg)
            cfg.validate()
            result = client.post("/conversations", {"configuration": configuration(cfg), "demo": action == "demo",
                                                    "confirm_paid": interactive or getattr(args, "confirm_paid", False)})
            cid = result["id"]
        ui.say(t('cli.started_on_the_server' ,p0=cid))
        if getattr(args, "detach", False):
            return 0
        return await watch(client, cid, ui)
    finally:
        if owned:
            client.close()


def history_entries(client):
    entries = []
    profiles = client.get("/profiles")
    for c in client.get("/conversations"):
        cfg = to_config(c["config"], profiles)
        conversation = Conversation(cfg.to_dict(), id=c["id"], status=c["status"], created_at=c["created_at"])
        conversation.messages = [None] * c["message_count"]
        entries.append(SimpleNamespace(conversation=conversation, path=Path(c["id"]), modified=0))
    return entries


def interactive_menu(ui, preferences=None, client=None):
    owned = client is None
    client = client or APIClient()
    preferences = RemotePreferences(client)
    try:
        while True:
            selecting = True
            try:
                choice = ui.main_menu()
                selecting = False
                if choice == "6":
                    return 0
                if choice == "5":
                    ui.settings(preferences, lambda cfg: asyncio.run(diagnose(cfg, ui, client)))
                elif choice in {"2", "3", "4"}:
                    entry = ui.choose_history(history_entries(client))
                    if entry is None:
                        continue
                    cid = entry.conversation.id
                    if choice == "3":
                        if ui.confirm(t('cli.permanently_delete_the_conversation_and_exports_on_the_server')):
                            client.request("DELETE", f"/conversations/{cid}")
                    elif choice == "4":
                        ui.say(t('cli.use_the_web_ui_to_read_conversations_and_export_offline_html'))
                        webbrowser.open(client.connection.server + "/#conversation=" + cid)
                    else:
                        extra = ui.integer(t('cli.how_many_additional_messages'), 10, minimum=1)
                        args = parser().parse_args(["resume", cid, "--turns", str(len(entry.conversation.messages) + extra)])
                        args.additional_turns, args.confirm = extra, True
                        asyncio.run(execute(args, ui, client=client))
                else:
                    asyncio.run(execute(parser().parse_args(["run"]), ui, client=client))
            except KeyboardInterrupt:
                if selecting:
                    return 130
                ui.say(t('cli.client_disconnected_generation_continues_on_the_server_use_stop_to_stop_it'))
            except EOFError:
                return 0
            except (BridgeError, OSError, ValueError, TypeError, KeyError) as e:
                ui.error(localize(e))
    finally:
        if owned:
            client.close()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    language_parser = argparse.ArgumentParser(add_help=False)
    language_parser.add_argument('--lang')
    language_args, _ = language_parser.parse_known_args(argv)
    configure(language_args.lang)
    p = parser()
    args = p.parse_args(argv)
    if args.action == "help":
        (p.commands[args.command] if args.command else p).print_help()
        return 0
    ui = Terminal()
    try:
        if args.action == "serve":
            try:
                from .server import serve
            except ImportError as e:
                raise BridgeError(t('cli.install_the_server_with_pip_install_alterecho_server')) from e
            if args.foreground:
                serve(args.host, args.port)
            else:
                from .managed import background
                from . import __version__
                result = background(args.host, args.port)
                ui.say(t('cli.alterecho_server_server_started_address_process_mode_background_log_commands_alterecho_status_a' ,p0=__version__, p1=result['url'], p2=result['pid'], p3=result['log']))
            return 0
        if args.action == "down":
            if args.server:
                raise BridgeError(t('cli.down_only_manages_the_local_server_for_this_account_and_does_not_accept_server_use_the_supervis'))
            from .managed import down
            ui.say(t('cli.local_server_stopped_pid_checkpoints_saved' ,p0=down()))
            return 0
        if args.action == "migrate":
            from .migration import migrate
            import json
            ui.say(json.dumps(migrate(args.source, args.destination, args.apply), ensure_ascii=False, indent=2))
            return 0
        connection = Connection(args.server)
        if args.action == "connect":
            connection.save(args.token_file)
            ui.say(t('cli.endpoint_saved' ,p0=connection.server))
            return 0
        if args.action == "web":
            webbrowser.open(connection.server)
            ui.say(connection.server)
            return 0
        client = APIClient(connection)
        try:
            if args.action is None:
                return interactive_menu(ui, client=client)
            return asyncio.run(execute(args, ui, client=client))
        finally:
            client.close()
    except KeyboardInterrupt:
        ui.say(t('cli.foreground_server_stopped_checkpoints_preserved') if args.action == "serve" else t('cli.client_disconnected_conversations_continue_on_the_server'))
        return 130
    except (BridgeError, OSError, ValueError, TypeError, KeyError) as e:
        ui.error(localize(e))
        return 1
