param([int]$WindowProcessId, [string]$OutputPath, [int]$Count=1, [int]$X=0, [int]$Y=0, [int]$Width=0, [int]$Height=0)
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class HoverWindowCapture {
 [StructLayout(LayoutKind.Sequential)] public struct Rect {public int Left,Top,Right,Bottom;}
 [StructLayout(LayoutKind.Sequential)] public struct Point {public int X,Y;}
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h,ref Point p);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
[HoverWindowCapture]::SetProcessDPIAware() | Out-Null
$handle = (Get-Process -Id $WindowProcessId).MainWindowHandle
if ($handle -eq [IntPtr]::Zero -or [HoverWindowCapture]::GetForegroundWindow() -ne $handle) { throw 'Test window is not foreground' }
$rect = New-Object HoverWindowCapture+Rect
$point = New-Object HoverWindowCapture+Point
[HoverWindowCapture]::GetClientRect($handle,[ref]$rect) | Out-Null
[HoverWindowCapture]::ClientToScreen($handle,[ref]$point) | Out-Null
$w = if($Width -gt 0){$Width}else{$rect.Right}
$h = if($Height -gt 0){$Height}else{$rect.Bottom}
$image = New-Object System.Drawing.Bitmap($w,$h)
$graphics = [System.Drawing.Graphics]::FromImage($image)
try {
 Write-Output 'READY'
 $timer = [System.Diagnostics.Stopwatch]::StartNew()
 for($i=0;$i -lt $Count;$i++) {
  $graphics.CopyFromScreen(($point.X+$X),($point.Y+$Y),0,0,$image.Size)
  $name = if($Count -gt 1){$OutputPath + '-' + $timer.ElapsedMilliseconds + '.png'}else{$OutputPath}
  $image.Save($name,[System.Drawing.Imaging.ImageFormat]::Png)
  if($Count -gt 1){Start-Sleep -Milliseconds 12}
 }
} finally { $graphics.Dispose(); $image.Dispose() }
