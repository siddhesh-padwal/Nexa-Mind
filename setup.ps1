param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
& $Python -c "import sys; assert (3,10) <= sys.version_info[:2] <= (3,12), 'Use Python 3.10, 3.11, or 3.12'"
if ($LASTEXITCODE -ne 0) { throw "A supported Python installation is required. Pass -Python with its executable path." }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
}
& '.\.venv\Scripts\python.exe' -m pip install --no-compile -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& '.\.venv\Scripts\python.exe' prepare_models.py
if ($LASTEXITCODE -ne 0) { throw "Model preparation failed. Check the error above and run setup again." }
Write-Host 'Ready. Run .\start.ps1 and open http://127.0.0.1:5000'
