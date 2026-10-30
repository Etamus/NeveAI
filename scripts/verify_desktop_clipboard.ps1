param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$Expected,[switch]$VerifyHtml)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$copy = New-Object Windows.Forms.DataObject
$original = [Windows.Forms.Clipboard]::GetDataObject()
$safe = $true
$formats = if ($original) { @($original.GetFormats($false)) } else { @() }
foreach ($format in $formats) {
    $value = $original.GetData($format,$false)
    if ($value -is [string] -and $value.Length -le 1048576) { $copy.SetData($format,$false,$value) }
    elseif ($value -is [IO.MemoryStream] -and $value.Length -le 1048576) { $copy.SetData($format,$false,[IO.MemoryStream]::new($value.ToArray())) }
    else { $safe = $false; break }
}
$ready = Join-Path $Directory 'clipboard-ready.json'
[IO.File]::WriteAllText($ready,(@{safe=$safe}|ConvertTo-Json -Compress))
if (-not $safe) { @{skipped='Clipboard contains non-text formats; left untouched'}|ConvertTo-Json -Compress; exit 0 }
$done = Join-Path $Directory 'clipboard-done.tmp'
$verified = $false
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while (-not (Test-Path -LiteralPath $done)) {
        if ([DateTime]::UtcNow -ge $deadline) { throw 'Clipboard test did not complete.' }
        Start-Sleep -Milliseconds 30
    }
    $verified = [Windows.Forms.Clipboard]::GetText() -eq $Expected
    $htmlCopied = [Windows.Forms.Clipboard]::ContainsText([Windows.Forms.TextDataFormat]::Html) -and [Windows.Forms.Clipboard]::GetText([Windows.Forms.TextDataFormat]::Html).Contains($Expected)
    if ($VerifyHtml -and -not $htmlCopied) { $verified = $false }
} finally {
    if ($formats.Count) { [Windows.Forms.Clipboard]::SetDataObject($copy,$true,10,100) }
    else { [Windows.Forms.Clipboard]::Clear() }
}
if (-not $verified) { throw 'Native clipboard did not receive the browser text.' }
@{copied=$true;htmlCopied=$htmlCopied;restored=$true;formatsPreserved=$formats.Count}|ConvertTo-Json -Compress
