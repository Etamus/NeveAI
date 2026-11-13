$ErrorActionPreference='Stop'
$repository=Split-Path -Parent $PSScriptRoot
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $repository 'launchers/iniciar.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors | Out-String)}
$function=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-NevePreparedUpdateJob'},$true)
. ([scriptblock]::Create($function.Extent.Text))
function Write-StartLog([string]$message){}
$root=Join-Path ([IO.Path]::GetTempPath()) ('neve-prepared-detection-'+[guid]::NewGuid().ToString('N'))
function Put-Job([string]$id,[string]$status,[string]$ownerRoot){
 $folder=Join-Path $root "backend/data/updates/$id";New-Item -ItemType Directory -Path $folder -Force | Out-Null
 [IO.File]::WriteAllText((Join-Path $folder 'manifest.json'),(@{id=$id;status=$status;root=$ownerRoot} | ConvertTo-Json))
}
try{
 if(Get-NevePreparedUpdateJob $root){throw 'Missing directory returned a job'}
 foreach($status in @('downloading','completed','failed','applying','restarting')){Put-Job ([guid]::NewGuid().ToString('N')) $status $root}
 Put-Job ('a'*32) 'ready' (Join-Path $root 'other')
 Put-Job 'not-a-job-id' 'ready' $root
 if(Get-NevePreparedUpdateJob $root){throw 'Ineligible job was selected'}
 $id='b'*32;Put-Job $id 'ready' $root
 if((Get-NevePreparedUpdateJob $root) -ne $id){throw 'Ready job was not detected'}
 $id2='c'*32;Put-Job $id2 'ready' $root
 (Get-Item -LiteralPath (Join-Path $root "backend/data/updates/$id2/manifest.json")).LastWriteTimeUtc=[DateTime]::UtcNow.AddSeconds(5)
 if((Get-NevePreparedUpdateJob $root) -ne $id2){throw 'Latest ready job was not selected'}
 'Prepared update detection: empty, incomplete, foreign, invalid and ready states passed'
}finally{
 $resolved=[IO.Path]::GetFullPath($root)
 if($resolved.StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'neve-prepared-detection-*'){Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue}
}
