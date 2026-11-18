param([int]$HostPid,[string]$Destination,[switch]$Cancel,[string]$ExpectedFilter)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$ae = [Windows.Automation.AutomationElement]
$all = [Windows.Automation.TreeScope]::Descendants
$class = New-Object Windows.Automation.PropertyCondition($ae::ClassNameProperty, '#32770')
$pidMatch = New-Object Windows.Automation.PropertyCondition($ae::ProcessIdProperty, $HostPid)
$condition = New-Object Windows.Automation.AndCondition($class, $pidMatch)
$deadline = [DateTime]::UtcNow.AddSeconds(15)
do {
    $dlg = $ae::RootElement.FindFirst($all, $condition)
    if (!$dlg) {
        $procs = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'")
        $owned = @($HostPid)
        do {
            $next = @($procs | Where-Object { $_.ParentProcessId -in $owned -and $_.ProcessId -notin $owned } | ForEach-Object ProcessId)
            $owned += $next
        } while ($next.Count)
        $dlg = @($ae::RootElement.FindAll($all,$class) | Where-Object { $_.Current.ProcessId -in $owned }) | Select-Object -First 1
    }
    if ($dlg) { break }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)
if (!$dlg) { throw "Save dialog missing for test host $HostPid" }
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class TestEdit { public delegate bool EnumChild(IntPtr hwnd,IntPtr param); [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent,EnumChild cb,IntPtr param); [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h,System.Text.StringBuilder b,int size); [DllImport("user32.dll", EntryPoint="SendMessageW", CharSet=CharSet.Unicode)] public static extern IntPtr ReadText(IntPtr h,int m,IntPtr w,System.Text.StringBuilder text); [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h,int m,IntPtr w,string text); [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,int m,IntPtr w,IntPtr l); }'
if ($ExpectedFilter) {
    $values = New-Object 'System.Collections.Generic.List[string]'
    $visit = [TestEdit+EnumChild]{
        param($handle,$param)
        $className = New-Object System.Text.StringBuilder 80
        [void][TestEdit]::GetClassName($handle,$className,80)
        if ($className.ToString() -eq 'ComboBox') {
            $selected = [TestEdit]::SendMessage($handle,327,[IntPtr]::Zero,$null)
            if ($selected.ToInt32() -ge 0) {
                $length = [TestEdit]::SendMessage($handle,329,$selected,$null).ToInt32()
                if ($length -ge 0 -and $length -lt 8192) {
                    $value = New-Object System.Text.StringBuilder ($length+1)
                    [void][TestEdit]::ReadText($handle,328,$selected,$value)
                    $values.Add($value.ToString())
                }
            }
        }
        return $true
    }
    [void][TestEdit]::EnumChildWindows([IntPtr]$dlg.Current.NativeWindowHandle,$visit,[IntPtr]::Zero)
    if ($values -notcontains $ExpectedFilter) { throw "Missing file type: $ExpectedFilter (found: $values)" }
}
if (!$Cancel) {
    $hostId = New-Object Windows.Automation.PropertyCondition($ae::AutomationIdProperty, 'FileNameControlHost')
    $editId = New-Object Windows.Automation.PropertyCondition($ae::ClassNameProperty, 'Edit')
    $field = $dlg.FindFirst($all,$hostId).FindFirst($all,$editId)
    if (!$field.Current.NativeWindowHandle) { throw 'Missing native filename control' }
    [void][TestEdit]::SendMessage([IntPtr]$field.Current.NativeWindowHandle,12,[IntPtr]::Zero,$Destination)
}
$id = if ($Cancel) { '2' } else { '1' }
[void][TestEdit]::PostMessage([IntPtr]$dlg.Current.NativeWindowHandle,273,[IntPtr]([int]$id),[IntPtr]::Zero)
