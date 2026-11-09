$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework
$root = Split-Path -Parent $PSScriptRoot
$source = [IO.File]::ReadAllText((Join-Path $root 'launchers/instalar.ps1'))
$ast = [Management.Automation.Language.Parser]::ParseInput($source,[ref]$null,[ref]$null)
$definitions = foreach ($name in @('Log','P')) {
    ($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true) | Where-Object Name -eq $name | Select-Object -First 1).Extent.Text
}
$window = [Windows.Window]::new()
$window.Title = 'Installer progress validation'
$window.Width=400; $window.Height=300
$controls = @{LogBox=[Windows.Controls.TextBox]::new();LogScroll=[Windows.Controls.ScrollViewer]::new();Progress=[Windows.Controls.ProgressBar]::new();LblProgressTxt=[Windows.Controls.TextBlock]::new();LblPhase=[Windows.Controls.TextBlock]::new();LblStep=[Windows.Controls.TextBlock]::new()}
$window.Content = $controls.LogBox
$path = Join-Path $root 'logs/installer-progress-fixture.log'
$results = @()
try {
    $window.Show()
    foreach ($optional in @($true,$false)) {
        if (-not $optional) { foreach($name in @('LogScroll','LblPhase','LblStep')) { $controls.Remove($name) } }
        $controls.LogBox.Clear();$controls.Progress.Value=0
        $script:Window=$window; $script:Ctl=$controls; $LOG=$path
        . ([scriptblock]::Create(($definitions -join "`r`n")))
        $errorCount=$Error.Count
        for($i=1;$i -le 20;$i++){ Log "line-$i"; P $i "phase-$i" }
        if($Error.Count -ne $errorCount){throw ($Error[0] | Out-String)}
        if($controls.Progress.Value -ne 20 -or $controls.LblProgressTxt.Text -ne '20%' -or $controls.LogBox.LineCount -lt 20){throw 'Installation progress did not reach the UI'}
        $results+=@{optionalControls=$optional;logLines=$controls.LogBox.LineCount;progress=$controls.Progress.Value}
    }
    $results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'logs/installer-progress-results.json') -Encoding UTF8
    'Installation log/progress helpers passed, including absent optional controls'
} finally { $window.Close();if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path} }
