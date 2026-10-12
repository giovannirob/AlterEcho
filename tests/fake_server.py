"""JSON RPC fixture. No Codex binary, network or model is invoked."""
import json
import sys


def send(value):
    print(json.dumps(value), flush=True)


turns = []
for line in sys.stdin:
    r = json.loads(line)
    method, p = r.get("method"), r.get("params", {})
    if "id" not in r:
        continue
    result = {}
    if method == "initialize":
        result = {"userAgent": "fake"}
    elif method == "account/read":
        result = {"account": {"type": "chatgpt"}}
    elif method == "model/list":
        result = {"data": [{"model": "test-codex", "supportedReasoningEfforts": [{"reasoningEffort": "low"}]}], "nextCursor": None}
    elif method in {"thread/start", "thread/resume"}:
        result = {"thread": {"id": "thread-test", "turns": turns}}
    elif method == "turn/start":
        ident = f"t{len(turns)+1}"
        text = f"Risposta persistente {len(turns)+1}"
        item = {"id": f"a{ident}", "type": "agentMessage", "text": text, "phase": "final_answer"}
        turn = {"id": ident, "status": "completed", "items": [{"type": "userMessage", "content": p["input"]}, item]}
        turns.append(turn)
        send({"id": r["id"], "result": {"turn": {"id": ident, "status": "inProgress"}}})
        incoming = p["input"][0]["text"]
        if incoming == "REQUEST_TOOL":
            send({"id": "tool-request", "method": "item/commandExecution/requestApproval", "params": {"threadId": "thread-test", "turnId": ident, "command": "untrusted command"}})
            continue
        if incoming == "STALL":
            continue
        if incoming == "FAIL_QUOTA":
            turn["status"] = "failed"
            turn["error"] = {"message": "quota mock esaurita"}
            send({"method": "turn/completed", "params": {"threadId": "thread-test", "turn": turn}})
            continue
        send({"method": "item/agentMessage/delta", "params": {"threadId": "thread-test", "turnId": ident, "itemId": item["id"], "delta": text}})
        send({"method": "item/completed", "params": {"threadId": "thread-test", "turnId": ident, "item": item}})
        send({"method": "thread/tokenUsage/updated", "params": {"threadId": "thread-test", "turnId": ident, "tokenUsage": {"last": {"inputTokens": 12, "outputTokens": 5}, "modelContextWindow": 200000}}})
        send({"method": "turn/completed", "params": {"threadId": "thread-test", "turn": turn}})
        continue
    send({"id": r["id"], "result": result})
