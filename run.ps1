param(
    [ValidateSet('experiment', 'prepare', 'inspect', 'smoke')]
    [string]$Command = 'experiment'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    throw 'Run .\setup.ps1 first.'
}
& '.venv/Scripts/python.exe' scripts/lab.py $Command
if ($LASTEXITCODE -ne 0) { throw 'The experiment command failed; inspect its output and saved logs.' }
