"""Inspect only a test-owned server's console; never show/hide/close windows."""
import json
import os
import subprocess
import sys


def console_state(pid):
    if os.name != 'nt':
        raise RuntimeError('Windows-only console probe')
    # FreeConsole must run in an isolated helper, never in the test runner or
    # the application. This also works when the runner itself has a console.
    code = '''import ctypes,json,sys
from ctypes import wintypes
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
user=ctypes.WinDLL('user32',use_last_error=True)
kernel.GetConsoleWindow.restype=wintypes.HWND
kernel.AttachConsole.argtypes=[wintypes.DWORD]
user.IsWindowVisible.argtypes=[wintypes.HWND]
kernel.FreeConsole()
attached=bool(kernel.AttachConsole(int(sys.argv[1])))
error=ctypes.get_last_error() if not attached else 0
window=kernel.GetConsoleWindow() if attached else None
print(json.dumps({'attached':attached,'error':error,'visible':bool(window and user.IsWindowVisible(window))}))
if attached:kernel.FreeConsole()
'''
    result = subprocess.run([sys.executable, '-c', code, str(pid)], capture_output=True,
                            text=True, check=True, timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(result.stdout)
