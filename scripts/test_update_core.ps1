param([string]$Repository=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$Repository=[IO.Path]::GetFullPath($Repository)
. (Join-Path $Repository 'launchers/update-core.ps1')
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('neve-update-tests-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
function Put([string]$path,[string]$content){New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null;[IO.File]::WriteAllText($path,$content)}
function Assert($value,[string]$message){if(-not $value){throw $message}}
function L([string]$message,[string]$kind){}
function P([int]$value,[string]$phase){}
try {
 $ROOT=$testRoot
 foreach($executable in @((Get-Command node.exe).Source,(Get-Command npm.cmd).Source)){
  $rc=Run $executable @('--version') 'real process smoke' 20
  Assert ($rc -eq 0) "Real process failed: $executable"
 }
 $release=Join-Path $testRoot 'release'
 $required=@('instalar.bat','launchers/instalar.ps1','launchers/instalar.vbs','launchers/iniciar.ps1','launchers/iniciar.vbs','launchers/runtime-validation.ps1','launchers/process-ownership.ps1','launchers/installer-release-cache.ps1','backend/neveai/__init__.py','backend/neveai/main.py','backend/neveai/routers/music_generation.py','backend/neveai/routers/video_generation.py','backend/neveai/models/users.py','backend/neveai/models/models.py','backend/neveai/models/auths.py','backend/neveai/routers/auths.py','backend/neveai/utils/auth.py','desktop/runtime.json','desktop/setup_runtime.py','desktop/NeveWindow.cs','desktop/app.manifest','desktop/verify-runtime.ps1','desktop/profile_migration.py','backend/requirements.txt')
 $required+=@('launchers/update-core.ps1','launchers/apply-update.ps1')
 foreach($file in $required){Put (Join-Path $release $file) 'release-content'}
 Put (Join-Path $release 'new.txt') 'new'
 $archive=Join-Path $testRoot 'release.zip'
 Compress-Archive -Path $release -DestinationPath $archive
 function Invoke-ReleaseDownload([string]$uri,[string]$destination){Copy-Item -LiteralPath $archive -Destination $destination}
 function Resolve-FrontendNodeLaunch {return [pscustomobject]@{NodeDir='fixture';NpmExecutable='fixture';NodeVersion='22';NpmVersion='10'}}
 function Run([string]$exe,[string[]]$argv,[string]$desc,[int]$timeoutSeconds){
  if($desc -like 'npm run build*') {Put (Join-Path $ROOT 'build/index.html') 'new-frontend'}
  if($desc -eq 'validar inicializacao apos atualizacao' -and $script:FailValidation){return 1}
  return 0
 }
 $results=@()
 foreach($fail in @($false,$true)){
  $ROOT=Join-Path $testRoot $(if($fail){'rollback'}else{'success'})
  foreach($file in $required){Put (Join-Path $ROOT $file) 'old-content'}
  foreach($file in @('.env','models/keep.gguf','backend/data/neve.db','backend/data/updates/job/manifest.json','backend/neveai/venv/pyvenv.cfg','backend/neveai/venv/Scripts/python.exe','node_modules/@officecli/officecli/vendor/officecli.exe','.desktop/installed.json','llamacpp-server/version.txt')){Put (Join-Path $ROOT $file) 'protected'}
  Put (Join-Path $ROOT 'backend/neveai/frontend/index.html') 'old-frontend'
  Put (Join-Path $ROOT 'obsolete.txt') 'old'
  $VERSION_FILE=Join-Path $ROOT 'version.txt';Put $VERSION_FILE 'v1.0.0'
  $latestTag='v1.1.0';$currentVersion='v1.0.0';$zipUrl='fixture';$updateLlama=$false;$script:FailValidation=$fail
  $failed=$false
  try{[void](Update-NeveAI)}catch{$failed=$true}
  Assert ($failed -eq $fail) "Unexpected update result: $fail"
  foreach($file in @('.env','models/keep.gguf','backend/data/neve.db','backend/data/updates/job/manifest.json','.desktop/installed.json','llamacpp-server/version.txt')){Assert ([IO.File]::ReadAllText((Join-Path $ROOT $file)) -eq 'protected') "Protected file changed: $file"}
  Assert (([IO.File]::ReadAllText($VERSION_FILE)).Trim() -eq $(if($fail){'v1.0.0'}else{'v1.1.0'})) 'Version not transactional'
  Assert ([IO.File]::ReadAllText((Join-Path $ROOT 'backend/neveai/frontend/index.html')) -eq $(if($fail){'old-frontend'}else{'new-frontend'})) 'Frontend not transactional'
  Assert ((Test-Path -LiteralPath (Join-Path $ROOT 'obsolete.txt')) -eq $fail) 'Orphan/rollback mismatch'
  $results+=@{failureInjected=$fail;passed=$true}
 }
 $results | ConvertTo-Json
}finally{
 Set-Location -LiteralPath $Repository
 $resolved=[IO.Path]::GetFullPath($testRoot)
 if($resolved.StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'neve-update-tests-*'){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
