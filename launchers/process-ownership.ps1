function Get-NeveProjectProcessIds([string]$ProjectRoot, [int]$InstallerProcessId, [object[]]$Processes) {
    $root = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\').ToLowerInvariant() + '\'
    $rootAlt = $root.Replace('\','/')
    $projectTree = [Collections.Generic.HashSet[int]]::new()
    foreach ($process in $Processes) {
        $command = ([string]$process.CommandLine).ToLowerInvariant()
        $executable = ([string]$process.ExecutablePath).ToLowerInvariant()
        if ($executable.StartsWith($root) -or $command.Contains($root) -or $command.Contains($rootAlt)) { [void]$projectTree.Add([int]$process.ProcessId) }
    }
    do {
        $changed = $false
        foreach ($process in $Processes) {
            if ($projectTree.Contains([int]$process.ParentProcessId) -and $projectTree.Add([int]$process.ProcessId)) { $changed = $true }
        }
    } while ($changed)
    $installerTree = [Collections.Generic.HashSet[int]]::new()
    [void]$installerTree.Add($InstallerProcessId)
    do {
        $changed = $false
        foreach ($process in $Processes) {
            if ($installerTree.Contains([int]$process.ParentProcessId) -and $installerTree.Add([int]$process.ProcessId)) { $changed = $true }
        }
    } while ($changed)
    foreach ($process in $Processes) {
        $id = [int]$process.ProcessId
        if ($installerTree.Contains($id)) { continue }
        $name = ([string]$process.Name).ToLowerInvariant()
        $command = ([string]$process.CommandLine).ToLowerInvariant()
        $executable = ([string]$process.ExecutablePath).ToLowerInvariant()
        $owned = $projectTree.Contains($id)
        if (-not $owned) { continue }
        if ($name -like 'llama-server*' -or $name -like 'llama_server*' -or $name -eq 'neveai.window.exe' -or
            $name -eq 'msedgewebview2.exe' -or $command.Contains('neveai.main:app') -or $command.Contains('neve_window.py') -or
            $command.Contains('--app=http://localhost:8080') -or $command.Contains('--app=http://127.0.0.1:8080')) {
            Write-Output $id
        }
    }
}
