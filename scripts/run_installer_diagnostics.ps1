param([ValidateSet('home','install','update','build')][string]$StartPage = 'home')
$root = Split-Path -Parent $PSScriptRoot
$Error.Clear()
try { & (Join-Path $root 'launchers/instalar.ps1') -StartPage $StartPage }
finally {
    @($Error | ForEach-Object {
        @{ message=$_.Exception.Message; id=$_.FullyQualifiedErrorId; position=$_.InvocationInfo.PositionMessage; stack=$_.ScriptStackTrace }
    }) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $root 'logs/installer-native-errors.json') -Encoding UTF8
}
