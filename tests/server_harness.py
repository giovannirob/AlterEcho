"""Regression harness: the real CLI talks HTTP to the real FastAPI server.

Provider patches belong exclusively to profile_runtime. The test-only transport
does not create an operational generation path in the installed CLI.
"""
import asyncio
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from alterecho.client import APIClient, Connection
from alterecho.server import create_app
from alterecho.server_settings import ServerSettings
from alterecho.sessions import SessionManager
from alterecho.preferences import UserSettings
from alterecho.paths import config_dir, data_dir
from alterecho.cli import execute as remote_execute, diagnose as remote_diagnose


@contextmanager
def server_client(preferences=None, history=None):
    temporary = TemporaryDirectory()
    settings = ServerSettings(token="test-service-token-" + "x" * 32,
                              allowed_hosts=["testserver", "127.0.0.1", "localhost"],
                              config_path=Path(temporary.name) / "config", data_path=Path(temporary.name) / "data")
    settings.prepare()
    manager = SessionManager(settings, preferences)
    if history:
        manager.config.output_dir = str(Path(history).resolve().parent)
    app = create_app(settings, manager)
    with TestClient(app) as session:
        connection = Connection("http://testserver", settings.token)
        yield APIClient(connection, session), manager
    temporary.cleanup()


async def execute(args, ui, preferences=None):
    preferences = preferences or UserSettings()
    history = getattr(args, "path", None) if args.action in {"resume", "export"} else None
    with server_client(preferences, history) as (client, manager):
        return await remote_execute(args, ui, client=client)


async def diagnose(cfg, ui):
    class Preferences:
        path = config_dir() / "config.json"
        def load(self): return cfg
        def known_history_dirs(self): return []
    with server_client(Preferences()) as (client, manager):
        return await remote_diagnose(cfg, ui, client)
