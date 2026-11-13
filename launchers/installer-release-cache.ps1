function Get-InstallerReleaseCachePath([string]$Key) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Key))).Replace('-','').Substring(0,20) }
    finally { $sha.Dispose() }
    return Join-Path $ROOT ".desktop\release-$hash.json"
}

function Test-InstallerReleaseTag([string]$Key, [string]$Tag) {
    if ($Key -like 'llama:*') { return $Tag -match '^b\d+$' }
    return $Tag -match '^v?\d+(?:\.\d+)+(?:[-+][\w.-]+)?$'
}

function Get-InstallerCachedRelease([string]$Key) {
    try {
        $path = Get-InstallerReleaseCachePath $Key
        if ((Get-Item -LiteralPath $path -ErrorAction Stop).Length -gt 2097152) { return $null }
        $cached = Get-Content -LiteralPath $path -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json
        $age = ([DateTime]::UtcNow - [DateTime]::Parse($cached.saved, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)).TotalSeconds
        if ($age -ge 0 -and $age -lt 60 -and $cached.key -eq $Key -and (Test-InstallerReleaseTag $Key $cached.release.tag_name)) { return $cached.release }
    } catch {}
    return $null
}

function Save-InstallerCachedRelease([string]$Key, $Release) {
    try {
        if (-not (Test-InstallerReleaseTag $Key $Release.tag_name)) { return }
        $path = Get-InstallerReleaseCachePath $Key
        [void][IO.Directory]::CreateDirectory((Split-Path $path))
        $temporary = "$path.$([guid]::NewGuid().ToString('N')).tmp"
        $data = @{ key=$Key; saved=[DateTime]::UtcNow.ToString('o'); release=$Release } | ConvertTo-Json -Depth 20 -Compress
        [IO.File]::WriteAllText($temporary, $data, [Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $path) { [IO.File]::Replace($temporary, $path, [Management.Automation.Language.NullString]::Value) } else { [IO.File]::Move($temporary, $path) }
    } catch {} finally {
        if ($temporary -and (Test-Path -LiteralPath $temporary)) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    }
}
