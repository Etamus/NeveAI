param([Parameter(Mandatory=$true)][string]$RuntimePath)
$ErrorActionPreference = 'Stop'
foreach ($name in @('msedgewebview2.exe', 'msedge.dll')) {
    $signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $RuntimePath $name)
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
        throw "Assinatura Microsoft invalida: $name"
    }
}
