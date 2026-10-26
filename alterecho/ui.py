from .i18n import number as format_number
from .i18n import t, localize, catalogs, preference, save_preference, date as local_date
import re
import sys
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.prompt import Prompt

from .stats import summarize
from .config import Config, BridgeError
from .history import participant_label


class LocalizedPrompt(Prompt):
    validate_error_message = t('ui.enter_one_of_the_listed_choices')
    illegal_choice_message = t('ui.enter_one_of_the_listed_choices')


def safe_text(value):
    # Strip terminal control sequences, without changing the saved/forwarded content.
    value = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))", "", str(value))
    return "".join(c for c in value if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159))


class Terminal:
    def __init__(self):
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        self.console = Console(highlight=False)
        self.mock = False
        self.labels = {}

    def say(self, text):
        # Plain strings may be conversation data; only tagged UI messages localize.
        self.console.print(Text(safe_text(localize(text) if hasattr(text, 'code') else text)))

    def waiting(self, speaker, count, total):
        status = t('ui.local_simulation') if self.mock else t('ui.connections_verified')
        self.say(t('ui.is_responding_ctrl_c_disconnects_the_client' ,p0=count, p1=total, p2=self.labels.get(speaker, speaker), p3=status))

    def message(self, m, count, total):
        style = "cyan" if m.speaker in {"codex", "A"} else "magenta"
        usage = m.usage
        details = f"{m.seconds:.2f}s"
        if usage.get("input_tokens") is not None:
            details += t('ui.input_tokens' ,p0=usage['input_tokens'])
        if usage.get("output_tokens") is not None:
            details += t('ui.output_tokens' ,p0=usage['output_tokens'])
        if usage.get("tokens_per_second") is not None:
            details += t('ui.generated_tokens_s' ,p0=format_number(usage['tokens_per_second'], 1))
        if usage.get("load_seconds") is not None:
            details += t('ui.loading_s' ,p0=format_number(usage['load_seconds'], 3))
        if usage.get("generation_seconds") is not None:
            details += t('ui.generation_s' ,p0=format_number(usage['generation_seconds'], 3))
        self.console.print(Panel(Text(safe_text(m.text)), title=Text(safe_text(f"{count}/{total} · {self.labels.get(m.speaker, m.speaker)} · {m.model}")), subtitle=Text(details), border_style=style))

    def error(self, text):
        self.console.print(Panel(Text(safe_text(localize(text))), title=t('ui.error'), border_style="red"))

    def summary(self, conversation, path):
        stats = summarize(conversation)
        states = {"ready": t('ui.ready'), "running": t('ui.running'), "completed": t('ui.completed'), "stopped": t('ui.stopped'), "interrupted": t('ui.interrupted'), "failed": t('ui.error_value')}
        self.say(t('ui.status_messages_generation_s' ,p0=states.get(conversation.status, conversation.status), p1=stats['messages'], p2=format_number(stats['seconds'], 2)))
        for speaker, values in stats["speakers"].items():
            self.say(t('ui.messages_measured_input_output_tokens_samples' ,p0=participant_label(conversation.config, speaker), p1=t('common.messages', count=values['messages']), p2=values['input_tokens'], p3=values['output_tokens'], p4=values['usage_samples']))
        self.say(t('ui.saved_md_txt_and_html' ,p0=path.resolve()))

    def select(self, label, values, default):
        if not values:
            raise ValueError(t('ui.no_models_available' ,p0=label))
        table = Table(title=label)
        table.add_column("#")
        table.add_column(t('ui.model'))
        for i, value in enumerate(values, 1):
            table.add_row(str(i), safe_text(value))
        self.console.print(table)
        index = values.index(default) + 1 if default in values else 1
        choice = self.ask(t('ui.select'), choices=[str(i) for i in range(1, len(values) + 1)], default=str(index))
        return values[int(choice) - 1]

    def configure(self, cfg, codex_models, ollama_models):
        cfg.ollama_model = self.select(t('ui.ollama_installed_models'), ollama_models, cfg.ollama_model)
        cfg.codex_model = self.select(t('ui.codex_cli_catalog_actual_access_is_checked_on_the_first_response'), [m["model"] for m in codex_models], cfg.codex_model)
        selected = next(m for m in codex_models if m["model"] == cfg.codex_model)
        efforts = [e["reasoningEffort"] for e in selected.get("supportedReasoningEfforts", [])]
        if efforts and cfg.codex_effort not in efforts:
            cfg.codex_effort = selected.get("defaultReasoningEffort", efforts[0])
            if cfg.codex_effort not in efforts:
                cfg.codex_effort = efforts[0]
            self.say(t('ui.reasoning_set_to_supported_by_the_selected_model' ,p0=cfg.codex_effort))
        cfg.topic = self.ask(t('ui.topic'), default=cfg.topic)
        cfg.max_turns = self.integer(t('ui.maximum_total_messages'), cfg.max_turns, minimum=1)
        cfg.validate()
        return self.confirm_run(cfg)

    def ask(self, label, **kwargs):
        # Text defaults may contain user content; never treat them as Rich markup.
        kwargs.setdefault("console", self.console)
        if "default" in kwargs:
            kwargs["default"] = safe_text(kwargs["default"])
        LocalizedPrompt.validate_error_message = t('ui.enter_one_of_the_listed_choices')
        LocalizedPrompt.illegal_choice_message = t('ui.enter_one_of_the_listed_choices')
        return LocalizedPrompt.ask(label, **kwargs)

    def integer(self, label, default, minimum=0):
        while True:
            value = self.ask(label, default=str(default))
            try:
                number = int(value)
                if number >= minimum:
                    return number
            except ValueError:
                pass
            self.say(t('ui.enter_an_integer_greater_than_or_equal_to' ,p0=minimum))

    def decimal(self, label, default, positive=False):
        import math
        while True:
            try:
                value = float(self.ask(label, default=str(default)).replace(",", "."))
                if math.isfinite(value) and (value > 0 if positive else value >= 0):
                    return value
            except ValueError:
                pass
            self.say(t('ui.enter_a_positive_number') if positive else t('ui.enter_a_finite_number_greater_than_or_equal_to_zero'))

    def confirm(self, label):
        yes = t('common.yes_key')
        return self.ask(label, choices=[yes, 'n'], default=yes, case_sensitive=False) == yes

    def confirm_run(self, cfg, completed=0):
        modes = {"free": t('ui.free_dialogue'), "debate": t('ui.debate'), "blind": t('ui.blind_experiment')}
        text = (t('ui.codex_ollama_topic_mode_first_messages' ,p0=cfg.codex_model, p1=cfg.ollama_model, p2=cfg.topic, p3=modes[cfg.mode], p4=cfg.first, p5=cfg.max_turns) + (t('ui.saved_new' ,p0=completed, p1=cfg.max_turns - completed) if completed else "") +
                t('ui.codex_reasoning_ollama_context_response_tokens_delay_s_timeout_s_storage' ,p0=cfg.codex_effort, p1=cfg.num_ctx, p2=cfg.num_predict, p3=cfg.delay, p4=cfg.timeout, p5=cfg.output_dir))
        text += t('ui.ollama_keep_alive_safe_final_unload' ,p0=cfg.ollama_keep_alive, p1=t('ui.yes') if cfg.ollama_unload_on_exit else t('ui.no'))
        if cfg.adapter_pair:
            text = (t('ui.a_b_topic_mode_first_total_messages_already_saved_storage_timeout_s' ,p0=participant_label(cfg, 'codex'), p1=cfg.codex_model, p2=participant_label(cfg, 'ollama'), p3=cfg.ollama_model, p4=cfg.topic, p5=modes[cfg.mode], p6=participant_label(cfg, cfg.first), p7=cfg.max_turns, p8=completed, p9=cfg.output_dir, p10=cfg.timeout))
            if any(p['provider'] in {'openai', 'openrouter'} for p in cfg.adapter_pair.values()):
                text += t('ui.api_provider_selected_generation_uses_its_api_account_and_may_incur_usage_charges')
        for speaker in ("codex", "ollama"):
            if cfg.roles[speaker]:
                text += t('ui.personality' ,p0=participant_label(cfg, speaker), p1=cfg.roles[speaker])
            if cfg.mode == "debate":
                text += t('ui.position' ,p0=participant_label(cfg, speaker), p1=cfg.positions[speaker])
        self.console.print(Panel(Text(safe_text(text)), title=t('ui.resume_conversation') if completed else t('ui.new_conversation'), border_style="cyan"))
        return self.confirm(t('ui.start'))

    def configure_profiles(self, cfg, catalogs):
        for slot in ("codex", "ollama"):
            profile = cfg.adapter_pair[slot]
            if profile['provider'] in {'openai', 'openrouter'}:
                self.say(t('ui.api_catalogs_may_include_models_incompatible_with_chat_access_and_compatibility_are_checked_on'))
            values = [m["model"] for m in catalogs[slot]] if profile["provider"] == "codex" else catalogs[slot]
            profile["model"] = self.select(profile["name"] + t('ui.available_models'), values, profile["model"])
            if profile["provider"] == "codex":
                selected = next(m for m in catalogs[slot] if m["model"] == profile["model"])
                efforts = [e["reasoningEffort"] for e in selected.get("supportedReasoningEfforts", [])]
                if efforts and cfg.codex_effort not in efforts:
                    cfg.codex_effort = selected.get("defaultReasoningEffort", efforts[0])
                    if cfg.codex_effort not in efforts:
                        cfg.codex_effort = efforts[0]
        cfg.codex_model, cfg.ollama_model = cfg.adapter_pair["codex"]["model"], cfg.adapter_pair["ollama"]["model"]
        cfg.topic = self.ask(t('ui.topic'), default=cfg.topic)
        cfg.max_turns = self.integer(t('ui.maximum_total_messages'), cfg.max_turns, minimum=1)
        cfg.validate()
        return self.confirm_run(cfg)

    def main_menu(self):
        while True:
            self.console.print(Panel(t('ui.alterecho_autonomous_dialogue_between_two_ais'), border_style="cyan"))
            self.say(t('ui.1_new_conversation_2_conversation_archive_resume_delete_or_view_a_saved_conversation_3_settings'))
            choice = self.ask(t('ui.select'), choices=["1", "2", "3", "0"], default="1")
            if choice == "0":
                return "6"
            if choice == "1":
                return "1"
            if choice == "3":
                return "5"
            self.say(t('ui.conversation_archive_1_resume_conversation_2_delete_conversation_3_view_html_0_back_to_main_men'))
            action = self.ask(t('ui.select'), choices=["1", "2", "3", "0"], default="0")
            if action != "0":
                return {"1": "2", "2": "3", "3": "4"}[action]

    def choose_history(self, entries, action=None):
        action = action or t('ui.resume')
        if not entries:
            self.say(t('ui.no_saved_conversations_in_the_configured_directories'))
            return None
        self.say(t('ui.conversations_to_newest_first' ,p0=action.upper()))
        states = {"ready": t('ui.ready_label'), "running": t('ui.running_label'), "completed": t('ui.completed_label'), "stopped": t('ui.stopped_label'), "interrupted": t('ui.interrupted_label'), "failed": t('ui.error_label')}
        for index, entry in enumerate(entries, 1):
            c = entry.conversation
            try:
                date = local_date(c.created_at)
            except ValueError:
                date = c.created_at
            self.say(t('ui.messages' ,p0=index, p1=date, p2=c.config['topic'], p3=participant_label(c.config, 'codex'), p4=c.config['codex_model'], p5=participant_label(c.config, 'ollama'), p6=c.config['ollama_model'], p7=t('common.messages', count=len(c.messages)), p8=states.get(c.status, c.status)))
        self.say(t('ui.0_back_to_menu'))
        value = self.ask(t('ui.select'), choices=[str(i) for i in range(len(entries) + 1)], default="0")
        return entries[int(value) - 1] if value != "0" else None

    def settings(self, preferences, diagnostics):
        groups = {
            "1": (t('ui.conversation'), [("1", t('ui.mode')), ("2", t('ui.personality_heading')), ("6", t('ui.first_participant'))]),
            "2": (t('ui.models_and_adapters'), [("10", t('ui.adapters_and_integrations')), ("3", t('ui.codex_reasoning_and_installation')), ("4", t('ui.ollama_parameters'))]),
            "3": (t('ui.execution_and_storage'), [("5", t('ui.limits_timeout_and_delay')), ("7", t('ui.storage_directory'))]),
            "4": (t('ui.diagnostics_and_maintenance'), [("8", t('ui.connection_diagnostics')), ("9", t('ui.reset_default_settings'))]),
        }
        section = None
        while True:
            cfg = preferences.load()
            if section is None:
                self.say(t('ui.settings' ,p0=preferences.path))
                for number, (title, _) in groups.items():
                    title = localize(title)
                    self.say(f"{number}. {title}")
                self.say(t('ui.0_back_to_menu'))
                self.say(t('language.menu'))
                section = self.ask(t('ui.select'), choices=["0", 'L', *groups], default="0")
                if section == "0":
                    return
                if section == 'L':
                    choices = ['auto', *catalogs()]
                    self.say(t('language.options', options=' · '.join(['auto: '+t('language.auto_cli'), *[code+': '+catalog['_meta']['name'] for code,catalog in catalogs().items()]])))
                    selected_language = self.ask(t('language.label'), choices=choices, default=preference())
                    save_preference(selected_language)
                    section = None
                continue
            title, actions = groups[section]
            title = localize(title)
            self.say(t('ui.settings_label' ,p0=title))
            for number, (_, label) in enumerate(actions, 1):
                label = localize(label)
                self.say(f"{number}. {label}")
            self.say(t('ui.0_back_to_settings'))
            selected = self.ask(t('ui.select'), choices=[str(i) for i in range(len(actions) + 1)], default="0")
            if selected == "0":
                section = None
                continue
            choice = actions[int(selected) - 1][0]
            if choice == "8":
                diagnostics(cfg)
                continue
            if choice == "10":
                self.adapter_settings(preferences)
                continue
            candidate = type(cfg)(**cfg.to_dict())
            try:
                if choice == "1":
                    modes = {"free": t('ui.free_dialogue'), "debate": t('ui.debate'), "blind": t('ui.blind_experiment')}
                    label = self.select(t('ui.mode'), list(modes.values()), modes[cfg.mode])
                    candidate.mode = next(key for key, value in modes.items() if value == label)
                    if candidate.mode == "debate":
                        for speaker in ("codex", "ollama"):
                            candidate.positions[speaker] = self.ask(t('ui.position_label' ,p0=speaker), default=cfg.positions[speaker])
                elif choice == "2":
                    self.say(t('ui.enter_keeps_the_value_clears_the_personality'))
                    for speaker in ("codex", "ollama"):
                        value = self.ask(t('ui.personality_label' ,p0=participant_label(cfg, speaker)), default=cfg.roles[speaker])
                        candidate.roles[speaker] = "" if value == "-" else value
                elif choice == "3":
                    self.say(t('ui.reasoning_support_is_checked_against_the_selected_model_catalog'))
                    candidate.codex_effort = self.select(t('ui.codex_reasoning'), ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"], cfg.codex_effort)
                    if getattr(preferences, "remote", False):
                        self.say(t('ui.configure_the_codex_executable_paths_and_authentication_directly_on_the_server'))
                        candidate.validate()
                        preferences.save(candidate)
                        continue
                    candidate.codex_binary = self.ask(t('ui.codex_executable_name_or_path'), default=cfg.codex_binary)
                    if ("/" in candidate.codex_binary or "\\" in candidate.codex_binary) and not Path(candidate.codex_binary).expanduser().is_absolute():
                        raise BridgeError(t('ui.use_a_codex_executable_in_path_or_an_absolute_path'))
                    self.say(t('ui.codex_directory_restores_automatic_detection_credentials_are_managed_only_by_codex'))
                    value = self.ask(t('ui.codex_home_optional'), default=cfg.codex_home)
                    candidate.codex_home = "" if value == "-" else value
                    if candidate.codex_home and not Path(candidate.codex_home).expanduser().is_absolute():
                        raise BridgeError(t('ui.codex_home_must_be_an_absolute_path'))
                elif choice == "4":
                    if getattr(preferences, "remote", False):
                        self.say(t('ui.edit_the_endpoint_in_adapters_and_integrations_network_hosts_must_be_authorized_on_the_server'))
                    else:
                        candidate.ollama_url = self.ask(t('ui.local_ollama_url'), default=cfg.ollama_url)
                    candidate.num_ctx = self.integer(t('ui.context_in_tokens_more_context_uses_more_memory'), cfg.num_ctx, 1)
                    candidate.num_predict = self.integer(t('ui.maximum_tokens_per_response'), cfg.num_predict, 1)
                    candidate.temperature = self.decimal(t('ui.temperature'), cfg.temperature)
                    self.say(t('ui.additional_json_options_e_g_top_p_0_9_clears_them'))
                    candidate.ollama_options = json.loads(self.ask(t('ui.ollama_options'), default=json.dumps(cfg.ollama_options)))
                    self.say(t('ui.ollama_memory_1_never_expires_10m_5m_expires_after_that_time_0_unloads_after_every_response'))
                    value = self.ask("keep_alive", choices=["-1", "10m", "5m", "0"], default=str(cfg.ollama_keep_alive))
                    candidate.ollama_keep_alive = int(value) if value in ("-1", "0") else value
                    self.say(t('ui.final_unloading_requires_verifiable_exclusive_use_shared_api_usage_skips_it_to_protect_other_cl'))
                    candidate.ollama_unload_on_exit = self.ask(t('ui.unload_the_model_after_the_conversation_only_if_safe'), choices=[t('common.yes_key'), 'n'], default=t('common.yes_key') if cfg.ollama_unload_on_exit else 'n', case_sensitive=False) == t('common.yes_key')
                elif choice == "5":
                    candidate.max_turns = self.integer(t('ui.default_messages'), cfg.max_turns, 1)
                    candidate.timeout = self.decimal(t('ui.generation_timeout_seconds'), cfg.timeout, positive=True)
                    candidate.delay = self.decimal(t('ui.delay_between_messages_seconds'), cfg.delay)
                elif choice == "6":
                    if cfg.adapter_pair:
                        slots = ["codex", "ollama"]
                        names = [f"{letter} · {participant_label(cfg, slot)}" for letter, slot in zip(("A", "B"), slots)]
                        selected = self.select(t('ui.first_participant'), names, names[slots.index(cfg.first)])
                        candidate.first = slots[names.index(selected)]
                    else:
                        candidate.first = self.select(t('ui.first_participant'), ["codex", "ollama"], cfg.first)
                elif choice == "7":
                    if getattr(preferences, "remote", False):
                        self.say(t('ui.configure_the_operational_directory_only_on_the_server_config_json_alterecho_home'))
                        continue
                    value = Path(self.ask(t('ui.storage_directory_absolute_path'), default=cfg.output_dir)).expanduser()
                    if not value.is_absolute():
                        raise BridgeError(t('ui.enter_an_absolute_path_to_run_alterecho_from_any_directory'))
                    candidate.output_dir = str(value.resolve())
                elif choice == "9":
                    if not self.confirm(t('ui.reset_settings_histories_remain_intact')):
                        continue
                    candidate = Config()
                candidate.validate()
                preferences.save(candidate)
                self.say(t('ui.settings_saved'))
            except (BridgeError, ValueError, TypeError, OSError) as e:
                self.error(t('ui.settings_not_saved' ,p0=e))

    def adapter_settings(self, preferences):
        from .integrations import AdapterCatalog, PROVIDERS, new_profile, validate_profile
        catalog = getattr(preferences, "catalog", None) or AdapterCatalog()
        while True:
            cfg = preferences.load()
            profiles = catalog.load(cfg)
            self.say(t('ui.adapters_and_integrations_1_list_adapters_2_add_adapter_3_edit_adapter_4_remove_adapter_5_choos'))
            choice = self.ask(t('ui.select'), choices=[str(i) for i in range(9)], default="0")
            if choice == "0":
                return
            try:
                if choice == "1":
                    for p in profiles:
                        self.say(t('ui.model_value' ,p0=p['name'], p1=PROVIDERS[p['provider']], p2=p['model'] or 'da scegliere'))
                    self.say(t('ui.active_pair') + (" ↔ ".join(p['name'] for p in cfg.adapter_pair.values()) if cfg.adapter_pair else t('ui.default_codex_ollama')))
                    continue
                if choice == "7":
                    self.say(t('ui.openai_and_openrouter_are_api_providers_add_them_as_adapters_mcp_connects_tools_and_resources_i'))
                    continue
                if choice == "8":
                    cfg.api_max_output_tokens = self.integer(t('ui.maximum_api_response_tokens'), cfg.api_max_output_tokens, 1)
                    preferences.save(cfg)
                    continue
                if choice == "6":
                    cfg.adapter_pair = {}
                    for p in profiles:
                        if p['id'] == 'codex-default':
                            cfg.codex_model, cfg.codex_binary = p['model'], p['binary']
                        elif p['id'] == 'ollama-default':
                            cfg.ollama_model, cfg.ollama_url = p['model'], p['url']
                    preferences.save(cfg)
                    self.say(t('ui.default_codex_and_ollama_restored'))
                    continue
                if choice == "5":
                    pair = {}
                    for slot, label in (("codex", "A"), ("ollama", "B")):
                        allowed = [p for p in profiles if not (slot == "ollama" and (p['provider'] == 'codex' or (pair['codex']['provider'] == 'ollama' and p['provider'] == 'ollama')))]
                        if not allowed:
                            raise BridgeError(t('ui.add_a_compatible_adapter_for_the_second_participant'))
                        values = [f"{p['name']} · {PROVIDERS[p['provider']]} · {p['id'][:8]}" for p in allowed]
                        value = self.select(t('ui.participant' ,p0=label), values, values[0])
                        pair[slot] = dict(allowed[values.index(value)])
                    cfg.adapter_pair = pair
                    cfg.validate()
                    preferences.save(cfg)
                    self.say(t('ui.participants_saved_for_new_conversations_histories_retain_their_own_adapters'))
                    continue
                if choice == "2":
                    labels = list(PROVIDERS.values())
                    label = self.select(t('ui.adapter_type'), labels, labels[0])
                    profile = new_profile(next(k for k, v in PROVIDERS.items() if v == label), self.ask(t('ui.profile_name')))
                else:
                    values = [f"{p['name']} · {p['id'][:8]}" for p in profiles]
                    value = self.select("Adapter", values, values[0])
                    profile = dict(profiles[values.index(value)])
                    if choice == "4":
                        if any(p['id'] == profile['id'] for p in cfg.adapter_pair.values()):
                            raise BridgeError(t('ui.adapter_in_the_active_pair_choose_other_participants_before_removing_it'))
                        if self.confirm(t('ui.remove_profile_histories_remain_intact')):
                            catalog.save([p for p in profiles if p['id'] != profile['id']])
                        continue
                    profile['name'] = self.ask(t('ui.profile_name'), default=profile['name'])
                if profile['provider'] == 'codex':
                    profile['binary'] = self.ask(t('ui.codex_executable'), default=profile['binary'])
                elif profile['provider'] == 'ollama':
                    profile['url'] = self.ask(t('ui.local_ollama_url'), default=profile['url'])
                else:
                    self.say(t('ui.enter_the_name_of_the_environment_variable_not_the_api_key_value_selecting_an_api_adapter_may_i'))
                    profile['api_key_env'] = self.ask(t('ui.api_key_variable'), default=profile['api_key_env'])
                model = self.ask(t('ui.preferred_model_optional_clears'), default=profile['model'])
                profile['model'] = '' if model == '-' else model
                validate_profile(profile)
                profiles = [p for p in profiles if p['id'] != profile['id']] + [profile]
                catalog.save(profiles)
                for slot, previous in cfg.adapter_pair.items():
                    if previous['id'] == profile['id']:
                        cfg.adapter_pair[slot] = dict(profile)
                preferences.save(cfg)
                self.say(t('ui.adapter_saved_use_choose_participants_a_and_b_to_select_it'))
            except (BridgeError, OSError, ValueError, TypeError) as e:
                self.error(localize(e))
