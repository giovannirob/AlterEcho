from .i18n import number as format_number
from .i18n import status as status_label, localize
"""A single in-progress Rich render, indexed completed messages and SSE replay."""
from .i18n import t
import asyncio

from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .config import BridgeError
from .history import Message
from .ui import safe_text


class WatchRenderer:
    def __init__(self, ui):
        self.ui, self.seen, self.cursors = ui, set(), {}
        self.state, self.partial, self.live = None, None, None

    def close(self):
        if self.live:
            self.live.stop()
            self.live = None

    def draw(self):
        if not self.partial:
            self.close()
            return
        if not getattr(getattr(self.ui, "console", None), "is_terminal", False):
            return  # Pipes receive complete messages exactly once, no ANSI redraw.
        p = self.partial
        panel = Panel(Text(safe_text(p.get("text") or t('watching.waiting_for_the_model'))),
                      title=Text(safe_text(f"{p['index']}/{self.state['config']['max_turns']} · {p['speaker']} · {p['model']}")),
                      subtitle=t('watching.generating_response'), border_style="cyan" if p["speaker"] == "A" else "magenta")
        if not self.live:
            self.live = Live(panel, console=self.ui.console, transient=True, refresh_per_second=12,
                             vertical_overflow="ellipsis")
            self.live.start()
        else:
            self.live.update(panel)

    def complete(self, index, message):
        if index in self.seen:
            return
        self.close()
        self.partial = None
        self.ui.message(Message(**message), index, self.state["config"]["max_turns"])
        self.seen.add(index)

    def snapshot(self, state):
        self.state = state
        self.ui.labels = {s: f"{s} · {p.get('name', s)}" for s, p in state["config"]["participants"].items()}
        self.close()
        for index, message in enumerate(state["messages"], 1):
            self.complete(index, message)
        self.partial = dict(state["partial"], index=len(state["messages"]) + 1) if state.get("partial") else None
        self.draw()

    def event(self, event):
        epoch, _, sequence = event["id"].rpartition(":")
        if sequence.isdigit():
            number = int(sequence)
            if number <= self.cursors.get(epoch, -1):
                return
            self.cursors[epoch] = number
        kind, data = event["type"], event["data"]
        if kind == "state.snapshot":
            self.snapshot(data)
        elif kind == "turn.started":
            if data["index"] in self.seen:
                return
            self.partial = {"index": data["index"], "speaker": data["speaker"],
                            "model": self.state["config"]["participants"][data["speaker"]]["model"], "text": ""}
            self.draw()
        elif kind == "message.delta":
            index = data.get("index", self.partial["index"] if self.partial else len(self.seen) + 1)
            if index in self.seen:
                return
            if not self.partial or self.partial["index"] != index:
                self.partial = {"index": index, "speaker": data["speaker"], "model": data["model"], "text": ""}
            self.partial["text"] += data["delta"]
            self.draw()
        elif kind == "message.completed":
            self.complete(data["index"], data["message"])


async def watch(client, cid, ui):
    renderer = WatchRenderer(ui)
    cursor = None
    ui.say(t('watching.conversation_ctrl_c_disconnects_the_client_alterecho_stop_stops_generation' ,p0=cid, p1=cid))
    try:
        # Missing IDs fail immediately. SSE then supplies an atomic snapshot and
        # cursor, so events racing this initial GET cannot be lost or doubled.
        state = client.get(f"/conversations/{cid}")
        if not state["active"]:
            renderer.snapshot(state)
        else:
            for attempt in range(10):
                try:
                    for event in client.events(cid, cursor):
                        renderer.event(event)
                        cursor = event["id"]
                    state = client.get(f"/conversations/{cid}")
                    if not state["active"]:
                        renderer.snapshot(state)
                        break
                except BridgeError:
                    if attempt == 9:
                        raise
                    renderer.close()
                    ui.say(t('watching.stream_disconnected_reconnecting_to_the_server'))
                await asyncio.sleep(min(attempt + 1, 5))
            else:
                raise BridgeError(t('watching.stream_recovery_failed_the_conversation_continues_on_the_server_retry_watch'))
        renderer.close()
        if renderer.partial:
            ui.say(t('watching.partial_response_incomplete'))
            ui.say(renderer.partial["text"])
        ui.say(t('watching.status_messages_s' ,p0=status_label(state['status']), p1=t('common.messages', count=len(state['messages'])), p2=format_number(state['stats']['seconds'], 2)))
        if state.get("error"):
            ui.error(state["error"])
        return 0 if state["status"] in {"completed", "paused"} else 1
    finally:
        renderer.close()
