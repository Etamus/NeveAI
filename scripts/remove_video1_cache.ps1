$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\backend\data\cache\video_generation\models\diffusion_models'))
$name = 'minimax_h3_fl2va_pruned_w4a8_mixed.safetensors'
$targets = @($name, ".cache\huggingface\download\$name.metadata", ".cache\huggingface\download\$name.lock")
$removed = @()
foreach ($relative in $targets) {
    $path = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $path.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Outside video model cache: $path" }
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $file = Get-Item -LiteralPath $path -Force
    if ($file.PSIsContainer) { throw "Expected a file: $path" }
    $removed += [pscustomobject]@{ Path = $path; Bytes = $file.Length }
    Remove-Item -LiteralPath $path -Force
}
$removed | ConvertTo-Json -Compress
