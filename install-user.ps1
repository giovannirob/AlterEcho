param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'AlterEcho\bin'),
    [switch]$Yes,
    [switch]$NoPath
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$source = Join-Path $projectRoot '.venv\Scripts\alterecho.exe'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw 'First create .venv and install the project: .\.venv\Scripts\python.exe -m pip install -e .'
}
$targetDir = [IO.Path]::GetFullPath($InstallDir)
$target = Join-Path $targetDir 'alterecho.exe'
Write-Host "Launcher: $target"
if (-not $NoPath) {
    Write-Host 'This adds the directory to the current user PATH only. Administrator privileges are not required.'
}
if (-not $Yes) {
    $answer = Read-Host 'Install? [y/N]'
    if ($answer -notmatch '^(y|yes|s|si|sì)$') {
        Write-Host 'Installation cancelled. No changes.'
        exit 0
    }
}
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Force
& $target help | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Launcher verification failed.' }
if (-not $NoPath) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @($userPath -split ';' | Where-Object { $_.Trim() })
    if (-not ($entries | Where-Object { $_.TrimEnd('\') -ieq $targetDir.TrimEnd('\') })) {
        $updatedPath = (@($entries) + $targetDir) -join ';'
        [Environment]::SetEnvironmentVariable('Path', $updatedPath, 'User')
    }
    if (-not (($env:Path -split ';') | Where-Object { $_.TrimEnd('\') -ieq $targetDir.TrimEnd('\') })) {
        $env:Path = "$targetDir;$env:Path"
    }
    # Notify Explorer so newly opened terminals inherit the updated user environment.
    try {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AlterEchoEnvironment {
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg, UIntPtr wParam,
        string lParam, uint flags, uint timeout, out UIntPtr result);
}
'@ -ErrorAction Stop
        $result = [UIntPtr]::Zero
        [void][AlterEchoEnvironment]::SendMessageTimeout([IntPtr]0xffff, 0x1a,
            [UIntPtr]::Zero, 'Environment', 2, 2000, [ref]$result)
    } catch {
        Write-Host 'PATH saved. Restart the terminal or VS Code if a new terminal does not inherit it.'
    }
}
Write-Host 'Installation succeeded. Run: alterecho. Help: alterecho help.'
Write-Host "The launcher uses the virtualenv in $projectRoot. After moving the checkout, recreate the virtualenv and reinstall."
