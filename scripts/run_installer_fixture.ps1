param([ValidateSet('slow','offline')][string]$Mode)
$path=Join-Path (Split-Path -Parent $PSScriptRoot) 'launchers\instalar.ps1'
$source=[IO.File]::ReadAllText($path)
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$null,[ref]$null)
$assignment=$ast.Find({param($n) $n -is [Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$script:UpdateLegacySource'},$true)
$legacy=$assignment.Right.Extent.Text.Substring(2).TrimStart("`r","`n")
$legacy=$legacy.Substring(0,$legacy.LastIndexOf("'@"))
$legacyAst=[Management.Automation.Language.Parser]::ParseInput($legacy,[ref]$null,[ref]$null)
$functions=@($legacyAst.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -in @('Get-GitHubLatestRelease','Get-GitHubLatestLlamaRelease')},$true))
foreach ($function in ($functions | Sort-Object {$_.Extent.StartOffset} -Descending)) {
    $body=if($Mode -eq 'offline'){"throw 'Offline fixture'"}elseif($function.Name -eq 'Get-GitHubLatestRelease'){
        "Start-Sleep -Milliseconds 200; [pscustomobject]@{tag_name='v999.0.0';body='Fixture';zipball_url='https://example.invalid/fixture'}"
    }else{"Start-Sleep -Seconds 8; [pscustomobject]@{tag_name='b999999';assets=@()}"}
    $replacement='function '+$function.Name+' { '+$body+' }'
    $legacy=$legacy.Remove($function.Extent.StartOffset,$function.Extent.EndOffset-$function.Extent.StartOffset).Insert($function.Extent.StartOffset,$replacement)
}
$cache=". (Join-Path `$ROOT 'launchers\installer-release-cache.ps1')"
$legacy=$legacy.Replace($cache,$cache+"`r`nfunction Get-InstallerReleaseCachePath([string]`$Key) { return Join-Path `$env:NEVE_INSTALLER_FIXTURE_CACHE ((`$Key -replace '[^A-Za-z0-9-]','_') + '.json') }")
$source=$source.Remove($assignment.Right.Extent.StartOffset,$assignment.Right.Extent.EndOffset-$assignment.Right.Extent.StartOffset).Insert($assignment.Right.Extent.StartOffset,"@'`r`n$legacy`r`n'@")
$source=[regex]::Replace($source,'(?m)^\$SCRIPT_PATH = if .*$',('$SCRIPT_PATH = '''+$path+''''),1)
& ([scriptblock]::Create($source)) -StartPage update
