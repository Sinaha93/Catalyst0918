$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Push-Location frontend
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'UI build failed' }
} finally { Pop-Location }
& .\.venv\Scripts\python.exe tools/build_exe.py
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
