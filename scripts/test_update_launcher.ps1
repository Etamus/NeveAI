param([switch]$Automatic,[switch]$InvalidAutomatic,[switch]$StaleAutomatic)
$ErrorActionPreference='Stop'
$repository=Split-Path -Parent $PSScriptRoot
$root=Join-Path ([IO.Path]::GetTempPath()) ('neve-update-window-'+[guid]::NewGuid().ToString('N'))
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Drawing
function Put([string]$path,[string]$content){New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null;[IO.File]::WriteAllText($path,$content)}
$process=$null
try {
 foreach($name in @('iniciar.ps1','apply-update.ps1','update-core.ps1','runtime-validation.ps1','process-ownership.ps1')){
  New-Item -ItemType Directory -Path (Join-Path $root 'launchers') -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $repository "launchers/$name") -Destination (Join-Path $root "launchers/$name")
 }
 Put (Join-Path $root 'version.txt') 'v1.0.0'
 New-Item -ItemType Directory -Path (Join-Path $root 'static/static') -Force | Out-Null
 Copy-Item -LiteralPath (Join-Path $repository 'static/static/splash-dark.png') -Destination (Join-Path $root 'static/static/splash-dark.png')
 Put (Join-Path $root 'backend/data/neve.db') 'preserved'
 Put (Join-Path $root 'llamacpp-server/version.txt') "b1`ncpu`nllama-b1-bin-win-cpu-x64.zip"
 Put (Join-Path $root 'source/llama-server.exe') 'fixture-not-executed'
 $job='b'*32;$jobRoot=Join-Path $root "backend/data/updates/$job"
 New-Item -ItemType Directory -Path $jobRoot -Force | Out-Null
 $package=Join-Path $jobRoot 'llama.zip'
 Compress-Archive -Path (Join-Path $root 'source/llama-server.exe') -DestinationPath $package
 $url='https://github.com/ggml-org/llama.cpp/releases/download/b2/llama-b2-bin-win-cpu-x64.zip'
 $manifest=@{id=$job;root=$root;owner='fixture';targets=@('llama');status='ready';progress=100;phase='Ready';versions=@{llama='b2'};packages=@(@{file='llama.zip';url=$url;sha256=(Get-FileHash $package).Hash.ToLowerInvariant()});llama=@{backend='cpu';release=@{tag_name='b2';assets=@(@{name='llama-b2-bin-win-cpu-x64.zip';browser_download_url=$url})}}}
 $manifestPath=Join-Path $jobRoot 'manifest.json'
 Put $manifestPath ($manifest | ConvertTo-Json -Depth 24)
 $shell=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
 $args=@('-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$(Join-Path $root 'launchers/apply-update.ps1')`"",'-Root',"`"$root`"",'-Job',$job,'-ValidateOnly')
 $valid=Start-Process $shell -ArgumentList $args -WindowStyle Hidden -Wait -PassThru
 if($valid.ExitCode -ne 0){throw 'Valid package rejected'}
 Add-Content -LiteralPath $package -Value 'tamper'
 $invalid=Start-Process $shell -ArgumentList $args -WindowStyle Hidden -Wait -PassThru
 if($invalid.ExitCode -eq 0){throw 'Tampered package accepted'}
 Remove-Item -LiteralPath $package
 Compress-Archive -Path (Join-Path $root 'source/llama-server.exe') -DestinationPath $package
 $manifest.packages[0].sha256=(Get-FileHash $package).Hash.ToLowerInvariant()
 Put $manifestPath ($manifest | ConvertTo-Json -Depth 24)
 if($InvalidAutomatic){Add-Content -LiteralPath $package -Value 'tamper'}
 if($StaleAutomatic){Put (Join-Path $root 'llamacpp-server/version.txt') "b3`ncpu`nllama-b3-bin-win-cpu-x64.zip"}
 $launchArgs=@('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',"`"$(Join-Path $root 'launchers/iniciar.ps1')`"",'-UpdateOnly')
 if(-not ($Automatic -or $InvalidAutomatic -or $StaleAutomatic)){$launchArgs+=@('-UpdateJob',$job)}
 $process=Start-Process $shell -ArgumentList $launchArgs -WindowStyle Hidden -PassThru
 $captured=$false;$watch=[Diagnostics.Stopwatch]::StartNew()
 while(-not $process.HasExited -and $watch.Elapsed.TotalSeconds -lt 30){
  $process.Refresh()
  if(-not $captured -and $process.MainWindowHandle -ne 0){
   $window=[Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
   $bounds=$window.Current.BoundingRectangle
   if([Math]::Abs($bounds.Height-245) -gt 2){throw "Incorrect progress window size: $($bounds.Height)"}
   $bitmap=[Drawing.Bitmap]::new([int]$bounds.Width,[int]$bounds.Height);$graphics=[Drawing.Graphics]::FromImage($bitmap)
   try{$graphics.CopyFromScreen([int]$bounds.X,[int]$bounds.Y,0,0,$bitmap.Size);$bitmap.Save((Join-Path $repository 'logs/update-progress-window.png'))}finally{$graphics.Dispose();$bitmap.Dispose()}
   $captured=$true
  }
  Start-Sleep -Milliseconds 25
 }
 if(-not $process.HasExited){throw 'Update launcher did not finish'}
 $state=ConvertFrom-Json ([IO.File]::ReadAllText($manifestPath))
 $expectedStatus=if($InvalidAutomatic -or $StaleAutomatic){'failed'}else{'completed'}
 if($state.status -ne $expectedStatus){throw "Unexpected update result: $($state | ConvertTo-Json -Depth 6)"}
 if(-not $captured){throw 'No progress window captured'}
 if([IO.File]::ReadAllText((Join-Path $root 'backend/data/neve.db')) -ne 'preserved'){throw 'Database changed'}
 $expectedTag=if($InvalidAutomatic){'b1'}elseif($StaleAutomatic){'b3'}else{'b2'}
 if((Get-Content (Join-Path $root 'llamacpp-server/version.txt') -First 1) -ne $expectedTag){throw 'Llama version mismatch'}
 Write-Output 'Branded native update window, staged llama application, tamper detection and data preservation passed'
}finally{
 if($process -and -not $process.HasExited){$process | Stop-Process -Force}
 $resolved=[IO.Path]::GetFullPath($root)
 if($resolved.StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'neve-update-window-*'){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
