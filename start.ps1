$taskRoot = $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Write-Error 'Ambiente virtuale mancante. Segui README.md per installare.'
    exit 1
}
& $taskPython -m alterecho @args
exit $LASTEXITCODE
