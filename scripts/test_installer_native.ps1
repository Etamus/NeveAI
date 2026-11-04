param([ValidateSet('normal','slow','offline')][string]$Mode = 'normal')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$directory = Join-Path $root ('logs/native-installer-test-' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($directory)
$oldReady = $env:NEVE_INSTALLER_READY_FILE
$oldCache = $env:NEVE_INSTALLER_FIXTURE_CACHE
$process = $null
$initialLanguage = $null
function Find-Control([string]$Id) {
    $process.Refresh()
    $view = [Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
    $matches = $view.FindAll([Windows.Automation.TreeScope]::Descendants,[Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::AutomationIdProperty,$Id))
    foreach ($element in $matches) { if (-not $element.Current.IsOffscreen) { return $element } }
    return $null
}
function Wait-For([scriptblock]$Condition, [int]$Timeout = 15000) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    do { if (& $Condition) { return }; Start-Sleep -Milliseconds 50 } while ($watch.ElapsedMilliseconds -lt $Timeout)
    throw "Timed out: $Condition"
}
function Click-Control([string]$Id) {
    $control = Find-Control $Id
    if (-not $control -or -not $control.Current.IsEnabled) { throw "Unavailable: $Id" }
    $control.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
}
function Select-Language([int]$Index) {
    $combo = Find-Control 'CmbLanguage'
    $combo.GetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
    $items = $combo.FindAll([Windows.Automation.TreeScope]::Descendants,[Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,[Windows.Automation.ControlType]::ListItem))
    $items[$Index].GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
    $combo.GetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern).Collapse()
}
function Save-Window([string]$Suffix) {
    $process.Refresh()
    $view = [Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
    $bounds = $view.Current.BoundingRectangle
    $bitmap = [Drawing.Bitmap]::new([int]$bounds.Width,[int]$bounds.Height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen([int]$bounds.X,[int]$bounds.Y,0,0,$bitmap.Size)
        $bitmap.Save((Join-Path $root "logs/installer-native-$Mode-$Suffix.png"))
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
}
try {
    $env:NEVE_INSTALLER_READY_FILE = Join-Path $directory 'ready'
    $env:NEVE_INSTALLER_FIXTURE_CACHE = Join-Path $directory 'cache'
    [void][IO.Directory]::CreateDirectory($env:NEVE_INSTALLER_FIXTURE_CACHE)
    $arguments = if ($Mode -eq 'normal') { @('-File','launchers/instalar.ps1') } else { @('-File','scripts/run_installer_fixture.ps1','-Mode',$Mode) }
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process powershell.exe -ArgumentList (@('-NoProfile','-STA','-ExecutionPolicy','Bypass') + $arguments) -WorkingDirectory $root -WindowStyle Hidden -PassThru
    Wait-For { Test-Path -LiteralPath $env:NEVE_INSTALLER_READY_FILE }
    $readyMs = $watch.ElapsedMilliseconds
    Wait-For { Find-Control 'NavOverview' }
    Click-Control 'NavOverview'
    Wait-For { Find-Control 'CmbBackend' }
    if ((Find-Control 'BtnPrimary').Current.BoundingRectangle.Height -ne 34) { throw 'Native action button size changed' }
    $combo = Find-Control 'CmbLanguage'
    $selected = $combo.GetCurrentPattern([Windows.Automation.SelectionPattern]::Pattern).Current.GetSelection()[0]
    $initialLanguage = if ($selected.Current.Name -eq 'English') { 1 } else { 0 }
    Select-Language 1
    Wait-For { (Find-Control 'LblNavInstall').Current.Name -match 'Repair|Install' }
    Select-Language 0
    Save-Window 'install'
    Click-Control 'NavSettings'
    Wait-For { Find-Control 'LblLatest' }
    if ($Mode -eq 'slow') {
        Wait-For { (Find-Control 'LblLatest').Current.Name -eq 'v999.0.0' }
        if ((Find-Control 'LblLlamaLatest').Current.Name -ne '...') { throw 'Neve query waited for llama query' }
        $check = Find-Control 'ChkUpdateNeve'
        $check.GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern).Toggle()
        Wait-For { (Find-Control 'LblLlamaLatest').Current.Name -eq 'b999999' }
        if ((Find-Control 'ChkUpdateNeve').GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern).Current.ToggleState -ne 'On') { throw 'Late result reset selection' }
    } elseif ($Mode -eq 'offline') {
        Wait-For { (Find-Control 'LblStatus').Current.Name -match 'Erro|Error' }
        Wait-For { (Find-Control 'LblLlamaStatus').Current.Name -match 'Erro|Error' }
    }
    Save-Window 'update'
    foreach ($page in @('build','update')) {
        Remove-Item -LiteralPath $env:NEVE_INSTALLER_READY_FILE
        $wrapper = Start-Process cmd.exe -ArgumentList @('/c','instalar.bat','--page',$page) -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru
        if ($wrapper.ExitCode -ne 0) { throw 'BAT entrypoint failed' }
        Wait-For { Test-Path -LiteralPath $env:NEVE_INSTALLER_READY_FILE }
        if ($page -eq 'build') { Wait-For { Find-Control 'LblDeployPath' }; Save-Window 'publish' }
        else { Wait-For { Find-Control 'LblLatest' } }
    }
    Click-Control 'NavOverview'
    Select-Language $initialLanguage
    $initialLanguage = $null
    $descendants = @(Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $process.Id })
    if ($descendants | Where-Object { $_.Name -eq 'msedgewebview2.exe' }) { throw 'Native installer started a browser' }
    Click-Control 'BtnClose'
    if (-not $process.WaitForExit(5000)) { throw 'Native installer did not close' }
    @{ mode=$Mode; readyMs=$readyMs; native=$true; language=$true; batPageForwarding=$true; browserStarted=$false; closed=$true } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root "logs/installer-native-$Mode-results.json") -Encoding UTF8
    Write-Output "Native installer $Mode passed; ready in $readyMs ms"
} finally {
    if ($process -and -not $process.HasExited) {
        try { if ($null -ne $initialLanguage) { Select-Language $initialLanguage } } catch {}
        [void]$process.CloseMainWindow()
        if (-not $process.WaitForExit(5000)) { throw 'Test installer did not close' }
    }
    $env:NEVE_INSTALLER_READY_FILE = $oldReady
    $env:NEVE_INSTALLER_FIXTURE_CACHE = $oldCache
    $resolved = [IO.Path]::GetFullPath($directory)
    if (-not $resolved.StartsWith(([IO.Path]::GetFullPath((Join-Path $root 'logs')) + '\'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test directory cleanup' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
