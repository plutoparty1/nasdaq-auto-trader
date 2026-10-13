param([switch]$Status, [switch]$StartPaused)
$ErrorActionPreference = 'Stop'
$RepoPath = Split-Path -Parent $PSScriptRoot
$EntryPath = Join-Path $PSScriptRoot 'run_p1_operator.py'
$PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
if ($Status) {
    & $PythonPath -B $EntryPath --status
    exit $LASTEXITCODE
}
$PythonWindowPath = Join-Path (Split-Path -Parent $PythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $PythonWindowPath)) { $PythonWindowPath = $PythonPath }
$Arguments = '-B "' + $EntryPath + '"'
if ($StartPaused) { $Arguments += ' --start-paused' }
Start-Process -FilePath $PythonWindowPath -ArgumentList $Arguments -WorkingDirectory $RepoPath -WindowStyle Hidden
