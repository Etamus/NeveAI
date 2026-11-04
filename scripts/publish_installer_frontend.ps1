$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$source=[IO.File]::ReadAllText((Join-Path $root 'launchers\instalar.ps1'))
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$null,[ref]$null)
$assignment=$ast.Find({param($n) $n -is [Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$script:UpdateLegacySource'},$true)
$legacy=$assignment.Right.Extent.Text.Substring(2).TrimStart("`r","`n")
$legacy=$legacy.Substring(0,$legacy.LastIndexOf("'@"))
$functions=[Management.Automation.Language.Parser]::ParseInput($legacy,[ref]$null,[ref]$null)
$publish=$functions.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Publish-FrontendAtomically'},$true)
. ([scriptblock]::Create($publish.Extent.Text))
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
