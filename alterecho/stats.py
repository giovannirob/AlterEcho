def summarize(conversation):
    result = {"messages": len(conversation.messages), "seconds": 0.0, "speakers": {}}
    for m in conversation.messages:
        result["seconds"] += m.seconds
        s = result["speakers"].setdefault(m.speaker, {"messages": 0, "seconds": 0.0, "input_tokens": 0, "output_tokens": 0, "usage_samples": 0})
        s["messages"] += 1
        s["seconds"] += m.seconds
        if m.usage:
            s["usage_samples"] += 1
            for key in ("input_tokens", "output_tokens"):
                s[key] += m.usage.get(key, 0) or 0
    return result
