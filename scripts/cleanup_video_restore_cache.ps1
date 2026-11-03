param([switch]$Apply, [ValidatePattern('^[a-zA-Z0-9_.-]+$')][string]$ReportName='cache-restore-cleanup-20261103.json')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cache = Join-Path $root 'backend\data\cache'
$relative = @(
 'backend\data\cache\video_generation\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',
 'backend\data\cache\video_generation\models\text_encoders\qwen3vl_8b_int8_convrot.safetensors',
 'backend\data\cache\video_generation\models\.cache\huggingface\download\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors.metadata',
 'backend\data\cache\video_generation\models\.cache\huggingface\download\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors.lock',
 'backend\data\cache\video_vdn_generation',
 'backend\data\cache\video_generation\input',
 'backend\data\cache\video_generation\output',
 'backend\data\cache\video_generation\temp',
 'backend\data\cache\image_fast_generation\input',
 'backend\data\cache\image_fast_generation\output',
 'backend\data\cache\image_fast_generation\temp',
 '.pytest_cache', 'backend\.pytest_cache'
)
$obsolete = @(
 @('backend\neveai\utils\__pycache__','video_prompt.*.pyc'),
 @('backend\__pycache__','test_video_prompt.*.pyc'),
 @('scripts\__pycache__','study_video_ir.*.pyc'),
 @('scripts\__pycache__','study_video_native_encoder.*.pyc'),
 @('scripts\__pycache__','study_video15_vlog.*.pyc'),
 @('scripts\__pycache__','test_video15_profile.*.pyc'),
 @('scripts\__pycache__','test_video15_replay.*.pyc')
)
foreach ($entry in $obsolete) {
 $directory = Join-Path $root $entry[0]
 if (Test-Path -LiteralPath $directory) {
  $relative += @(Get-ChildItem -LiteralPath $directory -File -Filter $entry[1] | ForEach-Object { $_.FullName.Substring($root.Length+1) })
 }
}
$targets = @($relative | ForEach-Object {
 $path = [IO.Path]::GetFullPath((Join-Path $root $_))
 if (-not $path.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) { throw "Outside workspace: $path" }
 if (Test-Path -LiteralPath $path) {
  $item=Get-Item -LiteralPath $path -Force
  $tree=@($item)+@(if($item.PSIsContainer){Get-ChildItem -LiteralPath $path -Recurse -Force})
  if($tree|Where-Object{ $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw "Reparse point target: $path" }
  $path
 }
})
$logical=0L
foreach($path in $targets){
 $item=Get-Item -LiteralPath $path -Force
 $size=if($item.PSIsContainer){(Get-ChildItem -LiteralPath $path -File -Recurse -Force|Measure-Object Length -Sum).Sum}else{$item.Length}
 $logical += $size
 Write-Output ('{0:N3} GiB {1}' -f ($size/1GB),$path.Substring($root.Length+1))
}
if(-not $Apply){Write-Output 'Dry run only';exit 0}
$tasks=Invoke-RestMethod http://127.0.0.1:8080/api/tasks
$video=Invoke-RestMethod http://127.0.0.1:8080/api/v1/video-generation/status
if($tasks.tasks.Count -gt 0 -or $video.running){throw 'Generation active; refusing cleanup'}
$protected=@{}
Get-ChildItem -LiteralPath $cache -File -Recurse -Force | ForEach-Object {
 $file=$_; $remove=$false
 foreach($target in $targets){if($file.FullName -eq $target -or $file.FullName.StartsWith($target+'\',[StringComparison]::OrdinalIgnoreCase)){$remove=$true;break}}
 if(-not $remove){$protected[$file.FullName]=@($file.Length,$file.LastWriteTimeUtc.Ticks)}
}
$before=(Get-PSDrive -Name $root.Substring(0,1)).Free
foreach($path in $targets){Remove-Item -LiteralPath $path -Recurse -Force}
$verified=0
Get-ChildItem -LiteralPath $cache -File -Recurse -Force|ForEach-Object {
 if($protected.ContainsKey($_.FullName)){
  $prior=$protected[$_.FullName]
  if($_.Length -ne $prior[0] -or $_.LastWriteTimeUtc.Ticks -ne $prior[1]){throw "Protected file changed: $($_.FullName)"}
  $verified++
 }
}
if($verified -ne $protected.Count){throw 'Protected cache files disappeared'}
$after=(Get-PSDrive -Name $root.Substring(0,1)).Free
$report=[ordered]@{targets=$targets;logical_bytes_removed=$logical;volume_free_bytes_delta=$after-$before;protected_cache_files_verified=$verified}
$report|ConvertTo-Json -Depth 4|Set-Content -LiteralPath (Join-Path (Join-Path $root 'logs') $ReportName) -Encoding UTF8
$report|ConvertTo-Json -Depth 4
