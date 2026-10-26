$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Write-Error 'Virtual environment missing. Follow README.md to install.'
    exit 1
}
& $taskPython -m alterecho @args
exit $LASTEXITCODE
