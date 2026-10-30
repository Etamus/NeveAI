param(
    [Parameter(Mandatory=$true)][int]$WindowProcessId,
    [ValidateSet('Cycles','Close','Inspect')][string]$Action = 'Cycles'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$process = Get-Process -Id $WindowProcessId
$expected = [IO.Path]::GetFullPath((Join-Path $root '.desktop\'))
if (-not $process.Path.StartsWith($expected, [StringComparison]::OrdinalIgnoreCase) -or $process.Name -ne 'NeveAI.Window') { throw 'Unexpected window process.' }
$hwnd = $process.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { throw 'Native window is not visible.' }
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NeveWindowProbe {
 [StructLayout(LayoutKind.Sequential)] public struct Rect {public int Left, Top, Right, Bottom;}
 [StructLayout(LayoutKind.Sequential)] public struct Point {public int X,Y;}
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
 [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hwnd, out Rect rect);
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hwnd, ref Point point);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int command);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hwnd);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, IntPtr process);
 [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint first, uint second, bool attach);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd,System.Text.StringBuilder text,int size);
 [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr hwnd,int command);
 [DllImport("user32.dll")] public static extern void keybd_event(byte key,byte scan,uint flags,UIntPtr extra);
 [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hwnd, int message, IntPtr w, IntPtr l);
}
'@
if ($Action -eq 'Inspect') {
    @{ Minimized = [NeveWindowProbe]::IsIconic($hwnd); Visible = [NeveWindowProbe]::IsWindowVisible($hwnd); Foreground = [NeveWindowProbe]::GetForegroundWindow() -eq $hwnd } | ConvertTo-Json -Compress
    exit 0
}
if ($Action -eq 'Close') {
    [void][NeveWindowProbe]::PostMessage($hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
    if (-not $process.WaitForExit(10000)) { throw 'Native window did not close cleanly.' }
    exit 0
}
function Measure-WindowPixel {
    $rect = New-Object NeveWindowProbe+Rect
    [void][NeveWindowProbe]::GetClientRect($hwnd, [ref]$rect)
    $point = New-Object NeveWindowProbe+Point
    $point.X = [int]($rect.Right * 0.75)
    $point.Y = [int]($rect.Bottom * 0.75)
    [void][NeveWindowProbe]::ClientToScreen($hwnd, [ref]$point)
    $bitmap = New-Object Drawing.Bitmap(16,16)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($point.X,$point.Y,0,0,$bitmap.Size)
        $sum = 0
        for ($y=0;$y -lt 16;$y++) { for ($x=0;$x -lt 16;$x++) {
            $pixel = $bitmap.GetPixel($x,$y)
            $sum += ($pixel.R + $pixel.G + $pixel.B) / 3
        }}
        return [Math]::Round($sum / 256,2)
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
}
function Focus-Probe {
  for ($attempt=0;$attempt -lt 20;$attempt++) {
    $current = [NeveWindowProbe]::GetCurrentThreadId()
    $foreground = [NeveWindowProbe]::GetWindowThreadProcessId([NeveWindowProbe]::GetForegroundWindow(),[IntPtr]::Zero)
    if ($foreground -ne $current) { [void][NeveWindowProbe]::AttachThreadInput($current,$foreground,$true) }
    try {
        if ($attempt -eq 1) { [NeveWindowProbe]::keybd_event(0x12,0,0,[UIntPtr]::Zero) }
        [void][NeveWindowProbe]::SetForegroundWindow($hwnd)
    }
    finally {
        if ($attempt -eq 1) { [NeveWindowProbe]::keybd_event(0x12,0,2,[UIntPtr]::Zero) }
        if ($foreground -ne $current) { [void][NeveWindowProbe]::AttachThreadInput($current,$foreground,$false) }
    }
    if ([NeveWindowProbe]::GetForegroundWindow() -eq $hwnd) { return }
    Start-Sleep -Milliseconds 50
  }
  $active = [NeveWindowProbe]::GetForegroundWindow()
  $class = New-Object Text.StringBuilder(256)
  [void][NeveWindowProbe]::GetClassName($active,$class,256)
  throw "The diagnostic window could not acquire focus; pixel samples would not be valid. target=$hwnd active=$active class=$class owner=$([NeveWindowProbe]::GetWindow($active,4))"
}
Focus-Probe
Start-Sleep -Milliseconds 150
$bounds = New-Object NeveWindowProbe+Rect
[void][NeveWindowProbe]::GetWindowRect($hwnd,[ref]$bounds)
$windowBounds = [Drawing.Rectangle]::FromLTRB($bounds.Left,$bounds.Top,$bounds.Right,$bounds.Bottom)
$captureBounds = [Drawing.Rectangle]::Intersect($windowBounds,[Windows.Forms.Screen]::PrimaryScreen.Bounds)
if ($captureBounds.Width -gt 0 -and $captureBounds.Height -gt 0) {
    $frame = New-Object Drawing.Bitmap($captureBounds.Width,$captureBounds.Height)
    $graphics = [Drawing.Graphics]::FromImage($frame)
    try {
        $graphics.CopyFromScreen($captureBounds.Left,$captureBounds.Top,0,0,$frame.Size)
        $frame.Save((Join-Path $root 'logs\webview2-native-test\native-frame.png'),[Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose(); $frame.Dispose() }
}
$baseline = Measure-WindowPixel
$samples = @()
for ($cycle=0;$cycle -lt 12;$cycle++) {
    [void][NeveWindowProbe]::ShowWindow($hwnd,6)
    Start-Sleep -Milliseconds 80
    [void][NeveWindowProbe]::ShowWindow($hwnd,9)
    Focus-Probe
    foreach ($delay in @(0,16,50,100)) {
        if ($delay) { Start-Sleep -Milliseconds $delay }
        $mean = Measure-WindowPixel
        $samples += [pscustomobject]@{Cycle=$cycle;Delay=$delay;Mean=$mean;Difference=[Math]::Abs($mean-$baseline)}
    }
}
[pscustomobject]@{Hwnd=$hwnd.ToInt64();Baseline=$baseline;Samples=$samples} | ConvertTo-Json -Depth 5 -Compress
