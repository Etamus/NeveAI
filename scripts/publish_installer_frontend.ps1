$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'launchers/update-core.ps1')
$destination=[IO.Path]::GetFullPath((Join-Path $root 'backend\neveai\frontend'))
if ((Get-Item -LiteralPath $destination).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to publish over a linked frontend folder' }
$transaction=Publish-FrontendAtomically (Join-Path $root 'build') $destination
try {
    . (Join-Path $root 'launchers\runtime-validation.ps1')
    $health=Get-NeveRuntimeHealth $root
    if (-not $health.Ok) { throw ($health.Missing -join '; ') }
} catch {
    if (-not $destination.Equals([IO.Path]::GetFullPath($transaction.Destination),[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected frontend transaction target' }
    Remove-Item -LiteralPath $destination -Recurse -Force
    if ($transaction.Backup) { Move-Item -LiteralPath $transaction.Backup -Destination $destination }
    throw
}
if ($transaction.Backup) {
    $backup=[IO.Path]::GetFullPath($transaction.Backup)
    if (-not $backup.StartsWith($destination+'.neve-old-',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected frontend backup path' }
    Remove-Item -LiteralPath $backup -Recurse -Force
}
Write-Output 'Frontend published and startup assets validated'
