from .i18n import message as t
import asyncio
import time
from dataclasses import asdict
from .stats import summarize

from .config import BridgeError
from .history import Message
from .security import safe_error


class Coordinator:
    def __init__(self, config, conversation, adapters, store, emit=None, pause_requested=None):
        self.config = config
        self.conversation = conversation
        self.adapters = adapters
        self.store = store
        self.emit = emit if callable(emit) else lambda *_: None
        self.pause_requested = pause_requested or (lambda: False)

    def checkpoint(self):
        self.store.save(self.conversation)

    async def run(self):
        c = self.conversation
        c.status, c.error = "running", None
        self.checkpoint()
        self.emit("conversation.started", {})
        try:
            while len(c.messages) < self.config.max_turns:
                if self.pause_requested():
                    c.status = "paused"
                    break
                speaker = c.next_speaker()
                self.emit("turn.started", {"speaker": speaker, "index": len(c.messages) + 1})
                c.pending = {"speaker": speaker}
                self.checkpoint()
                start = time.monotonic()
                # The same callback preserves existing atomic checkpoints and
                # exposes native deltas without synthesizing streaming.
                def checkpoint():
                    self.checkpoint()
                checkpoint.delta = lambda slot, model, text: self.emit("message.delta", {"speaker": slot, "model": model, "delta": text, "index": len(c.messages) + 1})
                reply = await self.adapters[speaker].generate(c, checkpoint)
                m = Message(speaker, reply.model, reply.text, time.monotonic() - start, usage=reply.usage)
                c.messages.append(m)
                if speaker == "codex" and self.config.adapter_pair.get(speaker, {}).get("provider", "codex") == "codex":
                    c.codex_turn_id = (c.pending or {}).get("turn_id", c.codex_turn_id)
                    c.codex_synced_messages = len(c.messages)
                c.pending = c.partial = None
                self.checkpoint()
                self.store.export(c)
                self.emit("message.completed", {"message": asdict(m), "index": len(c.messages)})
                self.emit("stats.updated", summarize(c))
                if len(c.messages) < self.config.max_turns and self.config.delay:
                    await asyncio.sleep(self.config.delay)
            else:
                c.status = "completed"
        except asyncio.CancelledError:
            c.status = "interrupted"
            raise
        except BridgeError as e:
            c.status, c.error = "stopped", safe_error(e, self.config.adapter_pair.values())

        except Exception as e:
            c.status, c.error = "failed", t('errors.internal_generation')
            raise
        finally:
            self.checkpoint()
            self.store.export(c)
            event = {"completed": "completed", "paused": "paused", "failed": "failed", "stopped": "failed"}.get(c.status, "stopped")
            self.emit(f"conversation.{event}", {"status": c.status, "error": c.error})
