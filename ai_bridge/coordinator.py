import asyncio
import time

from .config import BridgeError
from .history import Message


class Coordinator:
    def __init__(self, config, conversation, adapters, store, ui):
        self.config = config
        self.conversation = conversation
        self.adapters = adapters
        self.store = store
        self.ui = ui

    def checkpoint(self):
        self.store.save(self.conversation)

    async def run(self):
        c = self.conversation
        c.status, c.error = "running", None
        self.checkpoint()
        try:
            while len(c.messages) < self.config.max_turns:
                speaker = c.next_speaker()
                self.ui.waiting(speaker, len(c.messages), self.config.max_turns)
                c.pending = {"speaker": speaker}
                self.checkpoint()
                start = time.monotonic()
                reply = await self.adapters[speaker].generate(c, self.checkpoint)
                m = Message(speaker, reply.model, reply.text, time.monotonic() - start, usage=reply.usage)
                c.messages.append(m)
                if speaker == "codex":
                    c.codex_turn_id = (c.pending or {}).get("turn_id", c.codex_turn_id)
                    c.codex_synced_messages = len(c.messages)
                c.pending = c.partial = None
                self.checkpoint()
                self.store.export(c)
                self.ui.message(m, len(c.messages), self.config.max_turns)
                if len(c.messages) < self.config.max_turns and self.config.delay:
                    await asyncio.sleep(self.config.delay)
            c.status = "completed"
        except asyncio.CancelledError:
            c.status = "interrupted"
            raise
        except BridgeError as e:
            c.status, c.error = "stopped", str(e)
            self.ui.error(str(e))
        except Exception as e:
            c.status, c.error = "failed", f"{type(e).__name__}: {e}"
            raise
        finally:
            self.checkpoint()
            self.store.export(c)
            self.ui.summary(c, self.store.path)
