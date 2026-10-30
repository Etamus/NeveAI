param([int]$WindowProcessId)
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NativeHoverInput {
 [StructLayout(LayoutKind.Sequential)] public struct Point {public int X,Y;}
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h,ref Point p);
 [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point p);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern void mouse_event(uint flags,uint dx,uint dy,int data,UIntPtr extra);
}
'@
[NativeHoverInput]::SetProcessDPIAware() | Out-Null
$handle=(Get-Process -Id $WindowProcessId).MainWindowHandle
$origin=New-Object NativeHoverInput+Point
$saved=New-Object NativeHoverInput+Point
[NativeHoverInput]::ClientToScreen($handle,[ref]$origin) | Out-Null
[NativeHoverInput]::GetCursorPos([ref]$saved) | Out-Null
Write-Output 'READY'
try {
 while($line=[Console]::ReadLine()) {
  $command=$line | ConvertFrom-Json
  if($command.type -eq 'quit'){break}
  if([NativeHoverInput]::GetForegroundWindow() -ne $handle){throw 'Test window lost focus'}
  if($command.type -eq 'move'){
   [NativeHoverInput]::SetCursorPos(($origin.X+[int]$command.x),($origin.Y+[int]$command.y)) | Out-Null
  }elseif($command.type -eq 'wheel'){
   [NativeHoverInput]::mouse_event(0x0800,0,0,[int]$command.delta,[UIntPtr]::Zero)
  }
 }
} finally {[NativeHoverInput]::SetCursorPos($saved.X,$saved.Y) | Out-Null}
