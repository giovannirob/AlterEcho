"""Local process ownership, separate from the public application API.

An OS lease serializes launch/down; the server's existing leases own the data.
A private, nonce-authenticated loopback control channel identifies the live
instance, never a PID alone. No signals or force kills are sent to stored PIDs.
"""
from .i18n import t
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx

from .config import BridgeError
from .server_settings import ServerLease, ServerSettings
from .storage import atomic_write

_children = {}


class ExitHandle:
    """Wait-only OS handle captured after authenticating the live instance."""
    def __init__(self, pid):
        self.handle = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.kernel.OpenProcess.restype = wintypes.HANDLE
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = self.kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only

    def wait(self, timeout):
        if self.handle and self.kernel.WaitForSingleObject(self.handle, max(1, int(timeout * 1000))) != 0:
            raise BridgeError(t('managed.checkpoints_saved_but_the_process_has_not_exited_yet_no_forced_termination'))

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

def metadata_path(settings):
    return settings.runtime / "run" / "managed-server.json"


def read_metadata(settings):
    try:
        value = json.loads(metadata_path(settings).read_text(encoding="utf-8"))
        if (value.get("format") != 1 or not isinstance(value.get("pid"), int)
                or not isinstance(value.get("control_port"), int)
                or not 0 < value["control_port"] < 65536
                or len(value.get("secret", "")) < 32 or len(value.get("instance", "")) != 32):
            raise ValueError()
        return value
    except FileNotFoundError:
        return None
    except (ValueError, TypeError, AttributeError):
        raise BridgeError(t('managed.invalid_server_metadata_no_process_was_terminated'))


def control(meta, operation="identity"):
    """Authenticate and operate on one verified instance on the SAME socket."""
    try:
        with socket.create_connection(("127.0.0.1", meta["control_port"]), timeout=2) as sock:
            stream = sock.makefile("rwb")
            stream.write((json.dumps({"instance": meta["instance"], "secret": meta["secret"]}) + "\n").encode())
            stream.flush()
            reply = json.loads(stream.readline(4096))
            if reply != {"instance": meta["instance"], "pid": meta["pid"]}:
                return False
            stream.write((operation + "\n").encode())
            stream.flush()
            return stream.readline(128).strip() == b"ok"
    except (OSError, ValueError):
        return False


def local_status(settings=None):
    meta = read_metadata(settings or ServerSettings.from_env())
    if meta and control(meta):
        return {k: meta[k] for k in ("pid", "instance", "url", "log")}
    return None


def remove_owned(settings, instance):
    meta = read_metadata(settings)
    if meta and secrets.compare_digest(meta["instance"], instance):
        metadata_path(settings).unlink(missing_ok=True)


class LocalControl:
    def __init__(self, settings, instance, secret, stop):
        self.settings, self.instance, self.secret, self.stop = settings, instance, secret, stop
        self.listener = None
        self.clients = set()
        self.adopted = False
        self.watchdog = None

    async def start(self):
        self.listener = await asyncio.start_server(self.handle, "127.0.0.1", 0, limit=4096)
        host = "127.0.0.1" if self.settings.host in {"0.0.0.0", "localhost"} else "::1" if self.settings.host == "::" else self.settings.host
        host = f"[{host}]" if ":" in host else host
        meta = {"format": 1, "instance": self.instance, "secret": self.secret, "pid": os.getpid(),
                "control_port": self.listener.sockets[0].getsockname()[1],
                "url": f"http://{host}:{self.settings.port}",
                "log": str(self.settings.runtime / "logs" / "server.log")}
        path = metadata_path(self.settings)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path.with_name(path.name + ".tmp"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
        atomic_write(path, json.dumps(meta))
        deadline = float(os.environ.pop("ALTERECHO_MANAGED_DEADLINE", str(time.time() + 30)))
        self.watchdog = asyncio.get_running_loop().call_later(max(0, deadline - time.time()), self.expire)

    def expire(self):
        if not self.adopted:
            self.stop()

    async def handle(self, reader, writer):
        self.clients.add(writer)
        try:
            auth = json.loads(await asyncio.wait_for(reader.readline(), 2))
            if not isinstance(auth, dict):
                return
            if not (secrets.compare_digest(str(auth.get("instance", "")), self.instance)
                    and secrets.compare_digest(str(auth.get("secret", "")), self.secret)):
                return
            writer.write((json.dumps({"instance": self.instance, "pid": os.getpid()}) + "\n").encode())
            await writer.drain()
            operation = (await asyncio.wait_for(reader.readline(), 2)).strip()
            if operation not in {b"identity", b"stop", b"adopt"}:
                return
            if operation == b"adopt":
                self.adopted = True
            if operation == b"stop":
                self.stop()
            writer.write(b"ok\n")
            await writer.drain()
        except (OSError, ValueError, TimeoutError):
            pass
        finally:
            writer.close()
            self.clients.discard(writer)

    async def close(self):
        if self.watchdog:
            self.watchdog.cancel()
        if self.listener:
            self.listener.close()
            await self.listener.wait_closed()
        for writer in list(self.clients):
            writer.close()
        remove_owned(self.settings, self.instance)


def background(host=None, port=None, timeout=30):
    settings = ServerSettings.from_env(host, port)
    settings.prepare()
    lease = ServerLease(settings.runtime / "launcher.lock")
    lease.acquire()
    try:
        meta = read_metadata(settings)
        if meta and control(meta):
            raise BridgeError(t('managed.local_server_already_running_pid_use_alterecho_status_down' ,p0=meta['pid']))
        # Only remove stale metadata after proving no server owns the data lease.
        data_lease = ServerLease(settings.runtime / "server.lock")
        data_lease.acquire()
        try:
            if meta:
                remove_owned(settings, meta["instance"])
        finally:
            data_lease.release()
        instance, secret = secrets.token_hex(16), secrets.token_urlsafe(32)
        log = settings.runtime / "logs" / "server.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "alterecho"]
        command += ["serve", "--foreground", "--host", settings.host, "--port", str(settings.port)]
        env = dict(os.environ, ALTERECHO_MANAGED_ID=instance, ALTERECHO_MANAGED_SECRET=secret,
                   ALTERECHO_MANAGED_DEADLINE=str(time.time() + timeout))
        if getattr(sys, "frozen", False):
            # A detached onefile child must own its extraction directory;
            # otherwise the exiting launcher deletes the server's resources.
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        if os.name == "nt":
            # DETACHED_PROCESS makes Windows ignore CREATE_NO_WINDOW. In a
            # venv/onefile launcher the next console child can then open a new
            # visible window. Keep a windowless console and propagate SW_HIDE
            # through launchers instead; the process group isolates Ctrl+C.
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                      "startupinfo": startup}
        else:
            kwargs = {"start_new_session": True}
        with os.fdopen(fd, "ab", buffering=0) as output:
            output.write(f"\n--- AlterEcho startup {instance} ---\n".encode())
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                       close_fds=True, env=env, **kwargs)
        for key, child in list(_children.items()):
            if child.poll() is not None:
                del _children[key]
        _children[instance] = process
        # Authenticated application readiness AND the private instance identity.
        deadline = time.monotonic() + timeout
        with httpx.Client(timeout=1, trust_env=False) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise BridgeError(t('managed.startup_failed_code_see' ,p0=process.returncode, p1=log))
                meta = read_metadata(settings)
                if meta and meta["instance"] == instance and control(meta):
                    try:
                        response = client.get(meta["url"] + "/api/v1/status", headers={"Authorization": "Bearer " + settings.token,
                                              "Host": settings.allowed_hosts[0] + ":" + str(settings.port)})
                        if (response.status_code == 200 and response.json().get("managed") == {"instance": instance, "pid": meta["pid"]}
                                and control(meta, "adopt")):
                            return {k: meta[k] for k in ("pid", "url", "log")}
                    except (httpx.HTTPError, ValueError):
                        pass
                time.sleep(.1)
        if meta and meta["instance"] == instance:
            control(meta, "stop")
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass  # The child's unadopted-instance watchdog remains responsible.
        raise BridgeError(t('managed.startup_timed_out_success_not_confirmed_see_check_alterecho_status_down' ,p0=log))
    finally:
        lease.release()


def down(timeout=45):
    settings = ServerSettings.from_env()
    lease = ServerLease(settings.runtime / "launcher.lock")
    lease.acquire()
    try:
        meta = read_metadata(settings)
        if not meta or not control(meta):
            data_lease = ServerLease(settings.runtime / "server.lock")
            data_lease.acquire()
            try:
                if meta:
                    remove_owned(settings, meta["instance"])
            finally:
                data_lease.release()
            raise BridgeError(t('managed.no_managed_local_server_reachable_use_the_supervisor_for_docker_systemd_launchd_winsw_no_proces'))
        handle = ExitHandle(meta["pid"])
        deadline = time.monotonic() + timeout
        try:
            if not control(meta, "stop"):
                raise BridgeError(t('managed.server_identity_not_verified_shutdown_not_sent'))
            while time.monotonic() < deadline:
                current = read_metadata(settings)
                if not current or current["instance"] != meta["instance"]:
                    handle.wait(max(.1, deadline - time.monotonic()))
                    child = _children.pop(meta["instance"], None)
                    if child:
                        try:
                            child.wait(timeout=max(.1, deadline - time.monotonic()))
                        except subprocess.TimeoutExpired:
                            raise BridgeError(t('managed.python_launcher_has_not_exited_yet_no_forced_termination'))
                    return meta["pid"]
                time.sleep(.1)
        finally:
            handle.close()
        raise BridgeError(t('managed.shutdown_still_in_progress_checkpoints_or_providers_have_not_finished_check_the_logs_no_forced'))
    finally:
        lease.release()
