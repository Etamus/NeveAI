param(
 [Parameter(Mandatory=$true)][int]$WindowProcessId,
 [Parameter(Mandatory=$true)][string]$OutputDirectory,
 [int]$X=0,[int]$Y=0,[int]$Width=800,[int]$Height=450,
 [int]$Count=240
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$process=Get-CimInstance Win32_Process -Filter "ProcessId = $WindowProcessId"
if ($process.Name -ne 'NeveAI.Window.exe' -or $process.CommandLine -notlike '*logs\tremor-repro\profile*') { throw 'Not the isolated diagnostic window' }
$output=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $output.StartsWith((Join-Path $root 'logs\tremor-repro\'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected diagnostic output directory' }
if ($Count -gt 300 -or $Width -gt 900 -or $Height -gt 500) { throw 'Capture memory limit exceeded' }
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class TremorCapture {
 [StructLayout(LayoutKind.Sequential)] public struct Point {public int X,Y;}
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h,ref Point p);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
[TremorCapture]::SetProcessDPIAware() | Out-Null
$handle=(Get-Process -Id $WindowProcessId).MainWindowHandle
if ($handle -eq [IntPtr]::Zero) { throw 'Diagnostic window has no handle' }
$origin=New-Object TremorCapture+Point
[TremorCapture]::ClientToScreen($handle,[ref]$origin) | Out-Null
$frames=New-Object 'System.Collections.Generic.List[System.Drawing.Bitmap]'
$times=New-Object 'System.Collections.Generic.List[long]'
[IO.Directory]::CreateDirectory($output) | Out-Null
Write-Output 'READY'
if ([Console]::ReadLine() -ne 'START') { exit 0 }
$timer=[Diagnostics.Stopwatch]::StartNew()
try {
 for($i=0;$i -lt $Count;$i++) {
  if ([TremorCapture]::GetForegroundWindow() -ne $handle) { throw 'Capture stopped: diagnostic window lost focus' }
  $frame=New-Object Drawing.Bitmap($Width,$Height)
  $graphics=[Drawing.Graphics]::FromImage($frame)
  try { $graphics.CopyFromScreen(($origin.X+$X),($origin.Y+$Y),0,0,$frame.Size) }
  catch { $frame.Dispose();throw }
  finally { $graphics.Dispose() }
  $frames.Add($frame);$times.Add($timer.ElapsedMilliseconds)
  Start-Sleep -Milliseconds 16
 }
 # Encode after the gesture so PNG compression does not affect the reproduction.
 for($i=0;$i -lt $frames.Count;$i++) {
  $frames[$i].Save((Join-Path $output ('frame-{0:D4}-{1}.png' -f $i,$times[$i])),[Drawing.Imaging.ImageFormat]::Png)
 }
 $times | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'times.json') -Encoding UTF8
 Write-Output 'CAPTURED'
} finally { foreach($frame in $frames){$frame.Dispose()} }
