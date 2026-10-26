"""Client-local presentation catalogs; application data never passes through them."""
from contextvars import ContextVar
from datetime import datetime
from functools import lru_cache
from gettext import c2py
from importlib.resources import files
import json
import locale
import logging
import os
import re
import sys

_language = ContextVar('alterecho_language', default='en')
_override = None
_missing = set()


@lru_cache
def catalogs():
    return {p.name[:-5]: json.loads(p.read_text(encoding='utf-8'))
            for p in files('alterecho').joinpath('locales').iterdir() if p.name.endswith('.json')}


def normalize(value):
    value = str(value or '').split('.')[0].split('@')[0].replace('_', '-').lower()
    supported = {code.lower(): code for code in catalogs()}
    return supported.get(value) or supported.get(value.split('-')[0])


def detect_system():
    candidates = ([os.environ['LC_ALL']] if os.environ.get('LC_ALL') else
                  [value for value in os.environ.get('LANGUAGE', '').split(':') if value] +
                  [os.environ[key] for key in ('LC_MESSAGES', 'LANG') if os.environ.get(key)])
    if not candidates:
        if sys.platform == 'win32':
            try:
                import ctypes
                buffer = ctypes.create_unicode_buffer(85)
                if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                    candidates.append(buffer.value)
            except (AttributeError, OSError):
                pass
        try:
            candidates.append(locale.getlocale()[0])
        except (ValueError, TypeError):
            pass
    return next((code for value in candidates if (code := normalize(value))), 'en')


def preference_path():
    from .paths import config_dir
    return config_dir() / 'client-language.json'


def preference():
    try:
        value = json.loads(preference_path().read_text(encoding='utf-8')).get('language', 'auto')
        return value if value == 'auto' or normalize(value) else 'auto'
    except (OSError, ValueError, TypeError, AttributeError):
        return 'auto'


def configure(explicit=None):
    global _override
    _override = explicit
    choice = explicit or os.environ.get('ALTERECHO_LANG') or preference()
    _language.set(detect_system() if choice == 'auto' else normalize(choice) or 'en')
    return language()


def save_preference(value):
    from .storage import atomic_write
    if value != 'auto' and value not in catalogs():
        raise ValueError('Unsupported language preference')
    atomic_write(preference_path(), json.dumps({'language': value}, indent=2))
    # An explicit command/environment override remains authoritative.
    configure(_override)


def language():
    return _language.get()


def set_language(value):
    """Set this presentation context, without saving or changing other clients."""
    _language.set(normalize(value) or 'en')


class LocalizedText(str):
    def __new__(cls, value, code, params):
        obj = super().__new__(cls, value)
        obj.code, obj.params = code, params
        return obj

    def __reduce__(self):
        return type(self), (str(self), self.code, self.params)


def t(key, *, count=None, language=None, **params):
    code = normalize(language) if language else _language.get()
    catalog = catalogs().get(code, catalogs()['en'])
    value = catalog.get(key, catalogs()['en'].get(key))
    if value is None:
        if key not in _missing:
            _missing.add(key)
            logging.getLogger(__name__).debug('Missing translation: %s', key)
        value = 'Message unavailable.'
    if count is not None:
        params['count'] = count
    if isinstance(value, dict):
        meta = catalog['_meta']
        index = c2py(meta.get('plural', 'n != 1'))(count or 0)
        category = meta.get('pluralCategories', ['one', 'other'])[index]
        value = value.get(category, value.get('other', ''))
    # Replace only named fields: literal JSON examples and braces stay intact.
    value = re.sub(r'\{([A-Za-z_][A-Za-z_0-9]*)\}', lambda m: str(params.get(m[1], m[0])), value)
    return LocalizedText(value, key, params)


def message(key, **params):
    """Server messages always have an English detail and a stable catalog code."""
    return t(key, language='en', **params)


def localize(value):
    if hasattr(value, 'code'):
        return t(value.code, **value.params)
    if isinstance(value, BaseException) and value.args:
        return localize(value.args[0])
    info = error_info(value)
    if info:
        return t(info['code'], **info['params'])
    return str(value)


def status(value):
    key = 'state.' + value
    return t(key) if key in catalogs()['en'] else value


def error_info(value):
    """Recognize only application-owned error templates, never translate provider text."""
    if isinstance(value, BaseException) and value.args:
        return error_info(value.args[0])
    if hasattr(value, 'code'):
        return {'code': value.code, 'params': value.params}
    if isinstance(value, str):
        for key, pattern, names in error_patterns():
            match = pattern.fullmatch(value)
            if match:
                return {'code': key, 'params': dict(zip(names, match.groups()))}
    return {}


@lru_cache
def error_patterns():
    result = []
    for key, value in catalogs()['en'].items():
        if not key.startswith(('errors.', 'config.', 'sessions.', 'server.', 'integrations.')) or not isinstance(value, str):
            continue
        names = re.findall(r'\{([A-Za-z_][A-Za-z_0-9]*)\}', value)
        literal = re.sub(r'\{[A-Za-z_][A-Za-z_0-9]*\}', '', value).strip()
        # Broad fragments such as "Invalid {name}" are not enough evidence
        # to classify an external provider's diagnostic as an application error.
        if names and len(literal) < 15:
            continue
        pattern = re.escape(value)
        for name in names:
            pattern = pattern.replace(re.escape('{'+name+'}'), '(.*?)', 1)
        result.append((len(literal), key, re.compile(pattern, re.DOTALL), names))
    return [(key, pattern, names) for _, key, pattern, names in sorted(result, key=lambda entry: -entry[0])]


def error_payload(error, profiles=()):
    from .security import safe_error
    result = {'detail': safe_error(error, profiles)}
    info = error_info(error)
    if info:
        result.update(code=info['code'], params={key: safe_error(str(value), profiles)
                      for key, value in info['params'].items()})
    return result


def number(value, digits=0):
    meta = catalogs()[language()]['_meta']
    raw = f'{value:,.{digits}f}'
    return raw.replace(',', '\0').replace('.', meta.get('decimal', '.')).replace('\0', meta.get('group', ','))


def date(value):
    parsed = datetime.fromisoformat(value).astimezone()
    return parsed.strftime(catalogs()[language()]['_meta'].get('dateFormat', '%Y-%m-%d %H:%M'))
