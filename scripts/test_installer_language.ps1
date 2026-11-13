$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'launchers/instalar.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors | Out-String)}
$definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-DefaultInstallerLanguage'},$true)
. ([scriptblock]::Create($definition.Extent.Text))
foreach($culture in @('pt','pt-BR','pt-PT','PT-AO','pt_MZ')){if((Get-DefaultInstallerLanguage $culture) -ne 'pt-BR'){throw "Wrong Portuguese selection: $culture"}}
foreach($culture in @('en-US','en-GB','fr-FR','es-ES','de-DE','ja-JP','')){if((Get-DefaultInstallerLanguage $culture) -ne 'en-US'){throw "Wrong English fallback: $culture"}}
$statements=@($ast.EndBlock.Statements)
$index=0
while($index -lt $statements.Count -and $statements[$index].Extent.Text -ne '$script:InstallerLanguage = Get-DefaultInstallerLanguage'){$index++}
if($index -ge $statements.Count){throw 'Installer does not use detected language'}
$initialization=[scriptblock]::Create($statements[$index].Extent.Text+"`n"+$statements[$index+1].Extent.Text)
$directory=Join-Path ([IO.Path]::GetTempPath()) ('neve-language-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directory | Out-Null
$INSTALLER_LANGUAGE_FILE=Join-Path $directory 'installer-language.txt'
try{
 . $initialization
 if($script:InstallerLanguage -ne (Get-DefaultInstallerLanguage)){throw 'Missing preference did not detect computer language'}
 foreach($saved in @('en-US','pt-BR')){
  [IO.File]::WriteAllText($INSTALLER_LANGUAGE_FILE,$saved)
  . $initialization
  if($script:InstallerLanguage -ne $saved){throw 'Manual preference lost'}
 }
 [IO.File]::WriteAllText($INSTALLER_LANGUAGE_FILE,'invalid')
 . $initialization
 if($script:InstallerLanguage -ne (Get-DefaultInstallerLanguage)){throw 'Invalid preference did not detect computer language'}
 'Installer language: Portuguese regions, English fallback, missing/invalid preferences and manual selections passed'
}finally{
 $resolved=[IO.Path]::GetFullPath($directory)
 if($resolved.StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'neve-language-*'){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
