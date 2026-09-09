param([string]$PythonExe = 'py')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) { throw 'Install official Python 3.12 x64, or pass -PythonExe with its full path.' }
$pythonArgs = @()
if ($PythonExe -eq 'py') { $pythonArgs = @('-3.12') }
& $PythonExe @pythonArgs -I -c "import sys,struct,sqlite3,ssl; assert sys.version_info[:2] == (3,12), 'Python 3.12 required'; assert struct.calcsize('P') == 8, '64-bit Python required'; print('Python / SQLite / SSL: OK')"
if ($LASTEXITCODE -ne 0) { throw 'Python validation failed. Use a complete official installation, not a copied python.exe.' }
$venv = Join-Path $projectRoot '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
    & $PythonExe @pythonArgs -I -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
$venvPython = Join-Path $venv 'Scripts\python.exe'
& $venvPython -I -m pip --isolated install --disable-pip-version-check --index-url https://pypi.org/simple --requirement (Join-Path $projectRoot 'backend\requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $venvPython -I -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22, reopen the terminal, and rerun setup.' }
Push-Location (Join-Path $projectRoot 'frontend')
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
Write-Host 'Source environment ready. Next: .venv\Scripts\python.exe -I scripts\prepare_models.py'
