param(
    [string]$Python,
    [string]$NodePath,
    [switch]$BuildRelease
)
$ErrorActionPreference = 'Stop'
$bcProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$bcWorkRoot = Join-Path $bcProjectRoot 'work'
$bcTempRoot = Join-Path $bcWorkRoot 'tmp'
$bcTestRoot = Join-Path $bcWorkRoot 'pytest'
foreach ($bcPath in @($bcTempRoot, $bcTestRoot)) {
    $bcResolved = [IO.Path]::GetFullPath($bcPath)
    if (-not $bcResolved.StartsWith($bcProjectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Check directory escaped project workspace'
    }
    [void][IO.Directory]::CreateDirectory($bcResolved)
}
if (-not $Python) { $Python = Join-Path $bcWorkRoot '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Development Python runtime is required' }
if (-not $NodePath) {
    $bcNodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $bcNodeCommand) { throw 'Provide the host Node.js executable with -NodePath, or expose node on PATH' }
    $NodePath = $bcNodeCommand.Source
}
if (-not (Test-Path -LiteralPath $NodePath -PathType Leaf)) { throw 'Node.js executable is required for host bridge checks' }
$bcOldEnvironment = @{}
foreach ($bcName in @('TEMP', 'TMP', 'PIP_CACHE_DIR', 'PYTHONDONTWRITEBYTECODE', 'BC_TEST_PYTHON', 'PYTHONUTF8')) {
    $bcOldEnvironment[$bcName] = [Environment]::GetEnvironmentVariable($bcName, 'Process')
}
function Invoke-BcCheck([string[]]$Arguments) {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Verification failed with exit code $LASTEXITCODE" }
}
Push-Location -LiteralPath $bcProjectRoot
try {
    $env:TEMP = $bcTempRoot
    $env:TMP = $bcTempRoot
    $env:PIP_CACHE_DIR = Join-Path $bcWorkRoot 'pip-cache'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:BC_TEST_PYTHON = [IO.Path]::GetFullPath($Python)
    $env:PYTHONUTF8 = '1'
    Invoke-BcCheck @('-m', 'pytest', '-q', '--basetemp', $bcTestRoot)
    & $NodePath --test tests/host_browser.test.mjs tests/grade_editor.test.mjs tests/mit_coursework.test.mjs tests/uc_personal.test.mjs tests/uc_courses.test.mjs tests/uc_term_setup.test.mjs tests/uc_course_refill.test.mjs tests/uc_factual.test.mjs tests/common_ielts.test.mjs tests/common_factual.test.mjs tests/common_academic.test.mjs tests/common_schools.test.mjs tests/common_workflow.test.mjs tests/common_current.test.mjs tests/generic_forms.test.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Host bridge safety tests failed' }
    if ($BuildRelease) {
        Invoke-BcCheck @('-m', 'build', '--wheel', '--no-isolation', '--outdir', (Join-Path $bcWorkRoot 'wheels'))
        Invoke-BcCheck @('tools/build_plugin.py')
        $bcManifest = Get-Content -LiteralPath (Join-Path $bcProjectRoot 'plugin.json') -Raw | ConvertFrom-Json
        $bcArchive = Join-Path $bcProjectRoot "outputs/$($bcManifest.name)-$($bcManifest.version).zip"
        Invoke-BcCheck @('tools/verify_release.py', $bcArchive, '--node', $NodePath, '--report', (Join-Path $bcProjectRoot 'outputs/release-verification.json'))
    }
} finally {
    Pop-Location
    foreach ($bcName in $bcOldEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($bcName, $bcOldEnvironment[$bcName], 'Process')
    }
}
