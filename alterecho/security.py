"""Redact server credentials from errors before persistence or serialization."""
import os
import re


def safe_error(value, profiles=()):
    text = str(value)
    references = {p.get('api_key_env') for p in profiles}
    for key, secret in os.environ.items():
        if secret and (key in references or key.endswith('_API_KEY') or key.startswith('ALTERECHO_TOKEN')):
            text = text.replace(secret, '[redacted]')
    text = re.sub(r'(?i)(bearer\s+)[^\s,;]+', r'\1[redacted]', text)
    return text[:2000]
