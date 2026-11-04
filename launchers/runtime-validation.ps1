param([Alias('Root')][string]$ValidationRoot, [switch]$Check)

function Stop-NeveRuntimeProbe([int]$ProcessId) {
    foreach ($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue)) {
        Stop-NeveRuntimeProbe ([int]$child.ProcessId)
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Get-NeveRuntimeHealth([string]$ProjectRoot, [ValidateRange(100,120000)][int]$TimeoutMs = 30000) {
    $missing = [System.Collections.Generic.List[string]]::new()
    foreach ($relative in @('.env', 'backend\neveai\venv\Scripts\python.exe', 'backend\neveai\venv\pyvenv.cfg',
        'llamacpp-server\bin\llama-server.exe', 'backend\neveai\frontend\index.html',
        'backend\neveai\models\users.py', 'neve_window.py', '.desktop\installed.json',
        'desktop\setup_runtime.py')) {
        $path = Join-Path $ProjectRoot $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            $missing.Add($relative)
        }
    }
    $indexPath = Join-Path $ProjectRoot 'backend\neveai\frontend\index.html'
    if (Test-Path -LiteralPath $indexPath) {
        $html = [IO.File]::ReadAllText($indexPath)
        foreach ($match in [regex]::Matches($html, '["'']\.?/?(_app/[^"''\s<>]+)["'']')) {
            $asset = ($match.Groups[1].Value -split '[?#]', 2)[0]
            if (-not (Test-Path -LiteralPath (Join-Path (Split-Path $indexPath) $asset) -PathType Leaf)) {
                $missing.Add("frontend/$asset")
            }
        }
    }
    if ($missing.Count -eq 0) {
        $process = [Diagnostics.Process]::new()
        try {
            $process.StartInfo.FileName = Join-Path $ProjectRoot 'backend\neveai\venv\Scripts\python.exe'
            $process.StartInfo.Arguments = '"' + (Join-Path $ProjectRoot 'desktop\setup_runtime.py') + '" --check'
            $process.StartInfo.WorkingDirectory = $ProjectRoot
            $process.StartInfo.UseShellExecute = $false
            $process.StartInfo.CreateNoWindow = $true
            $process.StartInfo.RedirectStandardOutput = $true
            $process.StartInfo.RedirectStandardError = $true
            [void]$process.Start()
            $stdout = $process.StandardOutput.ReadToEndAsync()
            $stderr = $process.StandardError.ReadToEndAsync()
            if (-not $process.WaitForExit($TimeoutMs)) {
                Stop-NeveRuntimeProbe $process.Id
                $missing.Add('WebView2: validation timed out')
            } elseif ($process.ExitCode -ne 0) {
                $missing.Add('WebView2: runtime/host missing, changed or invalid')
            }
        } catch {
            $missing.Add("Runtime: $($_.Exception.Message)")
        } finally { $process.Dispose() }
    }
    return @{ Ok = $missing.Count -eq 0; Missing = @($missing) }
}

if ($Check) {
    $result = Get-NeveRuntimeHealth $ValidationRoot
    if ($result.Ok) { Write-Output 'Runtime validated'; exit 0 }
    Write-Output ($result.Missing -join '; ')
    exit 1
}
