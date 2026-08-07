Option Explicit

Dim shell, fso, launcherDir, root, scriptPath, powershellPath, command, debugMode, index, argument
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

launcherDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(launcherDir)
scriptPath = fso.BuildPath(launcherDir, "iniciar.ps1")
powershellPath = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
debugMode = False

For index = 0 To WScript.Arguments.Count - 1
    argument = LCase(WScript.Arguments(index))
    If argument = "--validate" Then
        WScript.Quit 0
    End If
    If argument = "--debug" Then debugMode = True
Next

command = Quote(powershellPath) & " -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File " & Quote(scriptPath)
If debugMode Then command = command & " -DebugConsole"

shell.Run command, 0, False

Function Quote(ByVal value)
    Quote = Chr(34) & Replace(value, Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
