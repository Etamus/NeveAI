$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'launchers/iniciar.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors | Out-String)}
$function=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Set-SplashProgress'},$true)
. ([scriptblock]::Create($function.Extent.Text))
function Pump-Ui {}
$statusText=[pscustomobject]@{Text=''}
$updatePercentText=[pscustomobject]@{Text=''}
$progressBar=[pscustomobject]@{Value=0}
$UpdateJob='fixture'
foreach($value in @(0,37,11,100,123)){
 $previous=$progressBar.Value
 Set-SplashProgress 'Internal stage' $value
 $expected=[Math]::Min(100,[Math]::Max($previous,$value))
 if($progressBar.Value -ne $expected -or $statusText.Text -ne 'Atualizando' -or $updatePercentText.Text -ne "$expected%"){
  throw "Incorrect update progress: $value"
 }
}
$UpdateJob=''
Set-SplashProgress 'Preparando ambiente...' 8
if($statusText.Text -ne 'Preparando ambiente...' -or $progressBar.Value -ne 8){throw 'Normal startup progress changed'}
$sync=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Sync-UpdateManifestProgress'},$true)
. ([scriptblock]::Create($sync.Extent.Text))
$UpdateJob='fixture';$progressBar.Value=0
foreach($state in @('ready','restarting','downloading','failed')){
 Sync-UpdateManifestProgress ([pscustomobject]@{status=$state;progress=100;phase='Download finished'})
 if($progressBar.Value -ne 0){throw "Download progress leaked into installation: $state"}
}
foreach($value in @(0,17,64,100)){
 Sync-UpdateManifestProgress ([pscustomobject]@{status='applying';progress=$value;phase='Applying'})
 $expected=[Math]::Min(99,$value)
 if($progressBar.Value -ne $expected -or $updatePercentText.Text -ne "$expected%") {throw "Installation progress mismatch: $value"}
}
Sync-UpdateManifestProgress ([pscustomobject]@{status='completed';progress=100;phase='Done'})
if($progressBar.Value -ne 100 -or $updatePercentText.Text -ne '100%'){throw 'Completion missing'}
'Update label, download/application separation, percentage, monotonic progress and normal startup passed'
