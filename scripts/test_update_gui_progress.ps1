$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$root = Join-Path ([IO.Path]::GetTempPath()) ('neve-progress-probe-' + [guid]::NewGuid().ToString('N'))
$process = $null
try {
    New-Item -ItemType Directory -Path (Join-Path $root 'launchers') -Force | Out-Null
    foreach ($name in @('iniciar.ps1','runtime-validation.ps1','process-ownership.ps1')) {
        Copy-Item -LiteralPath (Join-Path $repository "launchers/$name") -Destination (Join-Path $root "launchers/$name")
    }
    $launcherPath = Join-Path $root 'launchers/iniciar.ps1'
    $source = [IO.File]::ReadAllText($launcherPath)
    $tokens=$null;$errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
    $pump=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Pump-Ui'},$true)
    # Inspect the real WPF controls on their own UI thread, in the temporary copy only.
    $probe = @'

    if ($progressBar -and $updatePercentText) {
        $probeState=ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $Root "backend/data/updates/$UpdateJob/manifest.json")))
        @{value=[int]$progressBar.Value;label=$updatePercentText.Text;status=$probeState.status} | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $Root 'probe.jsonl')
    }
'@
    $source=$source.Insert($pump.Body.Extent.StartOffset+1,$probe)
    [IO.File]::WriteAllText($launcherPath,$source,[Text.UTF8Encoding]::new($true))
    $job = 'a' * 32
    $jobRoot = Join-Path $root "backend/data/updates/$job"
    New-Item -ItemType Directory -Path $jobRoot -Force | Out-Null
    $manifestPath = Join-Path $jobRoot 'manifest.json'
    [IO.File]::WriteAllText($manifestPath, (@{id=$job;root=$root;status='ready';progress=100;phase='Download ready'} | ConvertTo-Json))
    # Only the worker is simulated; the native window and its polling are real.
    $worker = @'
param([string]$Root,[string]$Job,[switch]$ValidateOnly)
if($ValidateOnly){exit 0}
$path=Join-Path $Root "backend/data/updates/$Job/manifest.json"
Start-Sleep -Milliseconds 900
foreach($value in @(17,64,100)){
 $state=@{status='applying';progress=$value;phase='Fixture installation'}
 [IO.File]::WriteAllText("$path.tmp",($state | ConvertTo-Json))
 Move-Item -LiteralPath "$path.tmp" -Destination $path -Force
 Start-Sleep -Milliseconds 650
}
[IO.File]::WriteAllText("$path.tmp",(@{status='completed';progress=100;phase='Done'} | ConvertTo-Json))
Move-Item -LiteralPath "$path.tmp" -Destination $path -Force
Start-Sleep -Milliseconds 650
exit 0
'@
    [IO.File]::WriteAllText((Join-Path $root 'launchers/apply-update.ps1'), $worker)
    $shell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $arguments = @('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',"`"$(Join-Path $root 'launchers/iniciar.ps1')`"",'-UpdateOnly','-UpdateJob',$job)
    $process = Start-Process $shell -ArgumentList $arguments -WindowStyle Hidden -PassThru
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while (-not $process.HasExited -and $watch.Elapsed.TotalSeconds -lt 20) {
        Start-Sleep -Milliseconds 30
    }
    if (-not $process.HasExited) { throw 'Progress probe timed out' }
    if ($process.ExitCode -ne 0) { throw 'Progress launcher failed' }
    $samples=@(Get-Content -LiteralPath (Join-Path $root 'probe.jsonl') | ForEach-Object {ConvertFrom-Json $_})
    $observed=@($samples | ForEach-Object {$_.value} | Sort-Object -Unique)
    foreach($sample in $samples){
        if($sample.label -ne "$($sample.value)%"){throw 'Visible percentage disagrees with bar'}
        if($sample.status -eq 'ready' -and $sample.value -ne 0){throw 'Download 100% filled the installation bar prematurely'}
        if($sample.status -eq 'applying' -and $sample.value -gt 99){throw 'Application reached 100% before completion'}
    }
    foreach ($value in @(0,17,64,99,100)) { if ($value -notin $observed) { throw "GUI did not show $value%; observed: $observed" } }
    "Native GUI progress passed: $(@($observed | Sort-Object) -join ', ')%"
} finally {
    if ($process -and -not $process.HasExited) { $process | Stop-Process -Force }
    $resolved = [IO.Path]::GetFullPath($root)
    if ($resolved.StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'neve-progress-probe-*') {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
