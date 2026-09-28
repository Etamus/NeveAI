Option Explicit

Dim shell, fso, launcherDir, root, scriptPath, powershellPath, command, startPage, index, result, languageFile, language, message, languageStream
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

launcherDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(launcherDir)
scriptPath = fso.BuildPath(launcherDir, "instalar.ps1")
powershellPath = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
startPage = "home"
language = "pt-BR"
languageFile = fso.BuildPath(fso.BuildPath(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%"), "NeveAI"), "installer-language.txt")
If fso.FileExists(languageFile) Then
    On Error Resume Next
    Set languageStream = fso.OpenTextFile(languageFile, 1, False, 0)
    language = Trim(languageStream.ReadAll)
    languageStream.Close
    Set languageStream = Nothing
    On Error GoTo 0
End If

If WScript.Arguments.Count > 0 Then
    If LCase(WScript.Arguments(0)) = "--validate" Then
        WScript.Quit 0
    End If
End If

For index = 0 To WScript.Arguments.Count - 2
    If LCase(WScript.Arguments(index)) = "--page" Or LCase(WScript.Arguments(index)) = "/page" Then
        startPage = WScript.Arguments(index + 1)
        Exit For
    End If
Next

Select Case LCase(startPage)
    Case "instalar": startPage = "install"
    Case "atualizar": startPage = "update"
    Case "buildar": startPage = "build"
End Select

command = Quote(powershellPath) & " -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Quote(scriptPath) & " -StartPage " & Quote(startPage)
result = shell.Run(command, 0, True)

If result <> 0 Then
    If LCase(language) = "en-us" Then
        message = "Failed to open Neve Hub." & vbCrLf & vbCrLf & "See the files in logs for details."
    Else
        message = "Falha ao abrir o Neve Hub." & vbCrLf & vbCrLf & "Veja os arquivos em logs para mais detalhes."
    End If
    MsgBox message, vbCritical, "NeveAI"
End If

Function Quote(ByVal value)
    Quote = Chr(34) & Replace(value, Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
