$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
foreach ($relative in @('launchers/instalar.ps1','launchers/iniciar.ps1','launchers/apply-update.ps1','launchers/update-core.ps1','launchers/runtime-validation.ps1','launchers/process-ownership.ps1','launchers/installer-release-cache.ps1')) {
    $tokens = $null; $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $root $relative), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
}
. (Join-Path $root 'launchers/runtime-validation.ps1')
$health = Get-NeveRuntimeHealth $root
if (-not $health.Ok) { throw ($health.Missing -join '; ') }
$health | ConvertTo-Json
