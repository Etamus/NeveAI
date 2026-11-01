param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cache = Join-Path $root 'backend\data\cache'
$relativeTargets = @(
    'image_quality_generation\edit_audit',
    'image_quality_generation\experimental_pe',
    'image_fast_generation\ComfyUI.previous-1793272785290449600',
    'video_generation\ComfyUI.previous-1793272831975159200',
    'image_fast_generation\models\diffusion_models\neve-image-2.2-UC-BF16.safetensors',
    'image_fast_generation\models\diffusion_models\qwen-image-2.1-UC-BF16.gguf',
    'image_fast_generation\models\text_encoders\qwen3vl_8b_bf16.safetensors',
    'image_quality_generation\pe\pe_i2i_heretic-Q8_0.gguf',
    'image_quality_generation\test_card.png',
    'image_quality_generation\test_cat.png'
)
$partialRoot = Join-Path $cache 'image_quality_generation\pe\.cache\huggingface\download'
if (Test-Path -LiteralPath $partialRoot) {
    $relativeTargets += @(Get-ChildItem -LiteralPath $partialRoot -File -Filter '*.incomplete' |
        Where-Object { $_.LastWriteTimeUtc -lt [datetime]'2026-10-30' } |
        ForEach-Object { $_.FullName.Substring($cache.Length + 1) })
}
$targets = @($relativeTargets | ForEach-Object {
    $path = [IO.Path]::GetFullPath((Join-Path $cache $_))
    if (-not $path.StartsWith($cache + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target escaped cache: $path"
    }
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        $links = @($item) + @(if ($item.PSIsContainer) {
            Get-ChildItem -LiteralPath $path -Recurse -Force
        })
        if ($links | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
            throw "Refusing reparse-point target: $path"
        }
        $path
    }
})

# Preserve every non-target file, including hardlinked runtime model names.
$protected = @(Get-ChildItem -LiteralPath $cache -File -Recurse -Force | Where-Object {
    $path = $_.FullName
    -not ($targets | Where-Object { $path -eq $_ -or $path.StartsWith($_ + '\', [StringComparison]::OrdinalIgnoreCase) })
} | Select-Object FullName, Length, LastWriteTimeUtc)
$logicalBytes = 0L
foreach ($path in $targets) {
    $item = Get-Item -LiteralPath $path -Force
    $bytes = if ($item.PSIsContainer) {
        (Get-ChildItem -LiteralPath $path -File -Recurse -Force | Measure-Object Length -Sum).Sum
    } else { $item.Length }
    $logicalBytes += $bytes
    Write-Output ("{0:N3} GiB {1}" -f ($bytes / 1GB), $path.Substring($cache.Length + 1))
}
if (-not $Apply) { Write-Output 'Dry run only. Use -Apply to remove these verified targets.'; exit 0 }
$before = (Get-PSDrive -Name ([IO.Path]::GetPathRoot($cache).Substring(0,1))).Free
foreach ($path in $targets) { Remove-Item -LiteralPath $path -Recurse -Force }
foreach ($file in $protected) {
    $current = Get-Item -LiteralPath $file.FullName -Force
    if ($current.Length -ne $file.Length -or $current.LastWriteTimeUtc -ne $file.LastWriteTimeUtc) {
        throw "Non-target file changed: $($file.FullName)"
    }
}
$after = (Get-PSDrive -Name ([IO.Path]::GetPathRoot($cache).Substring(0,1))).Free
$report = [ordered]@{
    targets = $targets; logical_bytes_removed = $logicalBytes
    volume_free_bytes_delta = $after - $before; protected_files_verified = $protected.Count
}
$log = Join-Path $root 'logs\cache-cleanup-20261031.json'
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $log -Encoding UTF8
$report | ConvertTo-Json -Depth 4
