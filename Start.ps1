$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required.' }
    & $pythonPath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
& $pythonPath -c "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in ['numpy','scipy','pygame','sounddevice']) else 1)"
if ($LASTEXITCODE -ne 0) {
    & $pythonPath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
& $pythonPath -c "import json,pathlib,sys; p=pathlib.Path('assets/samples/manifest.json'); sys.exit(0 if p.exists() and all((p.parent/s['file']).exists() for s in json.loads(p.read_text(encoding='utf-8'))['samples']) else 1)"
if ($LASTEXITCODE -ne 0) {
    & $pythonPath fetch_samples.py
    if ($LASTEXITCODE -ne 0) { throw 'Sample download failed. Check your internet connection.' }
}
& $pythonPath app.py
