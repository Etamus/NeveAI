param([switch]$Maximize)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase
Add-Type -AssemblyName System.Windows.Forms
$root=Split-Path -Parent $PSScriptRoot
$source=[IO.File]::ReadAllText((Join-Path $root 'launchers/instalar.ps1'))
$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$null,[ref]$errors)
if($errors.Count){throw ($errors -join '; ')}
$xamlMatches=[regex]::Matches($source,'(?s)\[xml\]\$xaml = @"\r?\n(.*?)\r?\n"@')
if($xamlMatches.Count -ne 2){throw 'Unexpected installer layouts'}
$converter=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Convert-LegacyWindowXamlToHubPage'},$true)
. ([scriptblock]::Create($converter.Extent.Text))
[xml]$mainXaml=$xamlMatches[0].Groups[1].Value
$window=[Windows.Markup.XamlReader]::Load([Xml.XmlNodeReader]::new($mainXaml))
if($window.Width -ne 940 -or $window.ResizeMode -ne 'CanMinimize' -or $window.FindName('BtnMaximize')){throw 'Installer size/maximize policy changed'}
$stateHandler=$ast.Find({param($node) $node -is [Management.Automation.Language.InvokeMemberExpressionAst] -and $node.Member.Value -eq 'Add_StateChanged'},$true)
$window.Add_StateChanged($stateHandler.Arguments[0].ScriptBlock.GetScriptBlock())
foreach($name in @('LblGpuCaption','LblBackendCaption','LblVramCaption')){
 $label=$window.FindName($name)
 if($label.FontSize -ne 14 -or $label.Foreground.Color.ToString() -ne '#FFF3F5F7'){throw "Incorrect caption style: $name"}
}
foreach($name in @('LblGpu','CmbBackend','CmbVram')){if($window.FindName($name).Foreground.Color.ToString() -ne '#FFD1D5DB'){throw "Incorrect value color: $name"}}
if($Maximize){
 $native=[regex]::Match($source,"(?s)Add-Type @'\r?\n(.*?)\r?\n'@")
 Add-Type -TypeDefinition $native.Groups[1].Value
 $hookAssignment=$ast.Find({param($node) $node -is [Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -eq '$script:InstallerWindowHook'},$true)
 $testWindowHook=& ([scriptblock]::Create($hookAssignment.Right.Extent.Text))
 $window.Add_SourceInitialized({
  $handle=[Windows.Interop.WindowInteropHelper]::new($window).Handle
  [Windows.Interop.HwndSource]::FromHwnd($handle).AddHook($testWindowHook)
 })
}
function Save-View([string]$Name){
 $window.UpdateLayout()
 [void]$window.Dispatcher.Invoke([Action]{},[Windows.Threading.DispatcherPriority]::Render)
 $bitmap=[Windows.Media.Imaging.RenderTargetBitmap]::new([int]$window.ActualWidth,[int]$window.ActualHeight,96,96,[Windows.Media.PixelFormats]::Pbgra32)
 $bitmap.Render($window.Content)
 $encoder=[Windows.Media.Imaging.PngBitmapEncoder]::new()
 $encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($bitmap))
 $stream=[IO.File]::Create((Join-Path $root "logs/installer-surfaces-$Name.png"))
 try{$encoder.Save($stream)}finally{$stream.Dispose()}
}
function Assert-ProgressSurface($Progress){
 $surface=$Progress.Parent.Parent
 if($surface.Background.Color.ToString() -ne '#FF171717'){throw 'Progress background not restored'}
 if($surface.BorderThickness -ne [Windows.Thickness]::new(0)){throw 'Progress border should remain removed'}
 $Progress.Value=45
}
function Assert-SelectedTextColor($Combo){
 $Combo.ApplyTemplate() | Out-Null
 $toggle=$Combo.Template.FindName('DropDownToggle',$Combo);$toggle.ApplyTemplate() | Out-Null
 $presenter=$toggle.Template.FindName('SelectedContent',$toggle);$window.UpdateLayout()
 if($presenter.GetValue([Windows.Documents.TextElement]::ForegroundProperty).Color.ToString() -ne '#FFD1D5DB'){throw 'Selected presenter ignores the hardware text color'}
 $pending=[Collections.Generic.Queue[Windows.DependencyObject]]::new();$pending.Enqueue($presenter);$found=$false
 while($pending.Count){$node=$pending.Dequeue();if($node -is [Windows.Controls.TextBlock] -and $node.Text){$found=$true;if($node.Foreground.Color.ToString() -ne '#FFD1D5DB'){throw "Rendered selected text is not darker: $($node.Text) / $($node.Foreground)"}};for($i=0;$i -lt [Windows.Media.VisualTreeHelper]::GetChildrenCount($node);$i++){$pending.Enqueue([Windows.Media.VisualTreeHelper]::GetChild($node,$i))}}
 if(-not $found){throw 'Selected text was not rendered'}
}
try{
 $window.Show()
 if($Maximize){
  $window.WindowState='Maximized';$window.UpdateLayout()
  if($window.WindowState -ne 'Normal'){throw 'Programmatic maximize was not blocked'}
  [void]$window.Dispatcher.Invoke([Action]{},[Windows.Threading.DispatcherPriority]::ApplicationIdle)
  $handle=[Windows.Interop.WindowInteropHelper]::new($window).Handle
  $area=[Windows.Forms.Screen]::FromHandle($handle).WorkingArea
  $bounds=@()
  foreach($name in @('BtnPrimary','CmbLanguage')){
   $control=$window.FindName($name)
   $topLeft=$control.PointToScreen([Windows.Point]::new(0,0))
   $bottomRight=$control.PointToScreen([Windows.Point]::new($control.ActualWidth,$control.ActualHeight))
   $bounds+=[pscustomobject]@{name=$name;top=$topLeft.Y;bottom=$bottomRight.Y;right=$bottomRight.X;workBottom=$area.Bottom;workRight=$area.Right}
  }
  $bounds | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'logs/installer-maximized-bounds.json') -Encoding UTF8
  Save-View 'maximized'
  foreach($entry in $bounds){if($entry.bottom -gt $entry.workBottom+1 -or $entry.right -gt $entry.workRight+1){throw "Control outside working area: $($entry.name)"}}
  $cycles=@()
  foreach($screen in [Windows.Forms.Screen]::AllScreens){
   foreach($cycle in 1..2){
    $window.WindowState='Normal'
    $window.UpdateLayout()
    $transform=[Windows.PresentationSource]::FromVisual($window).CompositionTarget.TransformFromDevice
    $position=$transform.Transform([Windows.Point]::new($screen.WorkingArea.Left+25,$screen.WorkingArea.Top+25))
    $window.Left=$position.X;$window.Top=$position.Y
    $window.WindowState='Maximized';$window.UpdateLayout()
    [void]$window.Dispatcher.Invoke([Action]{},[Windows.Threading.DispatcherPriority]::ApplicationIdle)
    $area=[Windows.Forms.Screen]::FromHandle($handle).WorkingArea
    foreach($name in @('BtnPrimary','CmbLanguage')){
     $control=$window.FindName($name)
     $topLeft=$control.PointToScreen([Windows.Point]::new(0,0))
     $bottomRight=$control.PointToScreen([Windows.Point]::new($control.ActualWidth,$control.ActualHeight))
     if($topLeft.X -lt $area.Left-1 -or $topLeft.Y -lt $area.Top-1 -or $bottomRight.X -gt $area.Right+1 -or $bottomRight.Y -gt $area.Bottom+1){throw "Control outside working area on $($screen.DeviceName): $name"}
     $cycles+=[pscustomobject]@{monitor=$screen.DeviceName;cycle=$cycle;name=$name;bottom=$bottomRight.Y;workBottom=$area.Bottom}
    }
    $window.WindowState='Normal';$window.UpdateLayout()
    if([Math]::Abs($window.ActualWidth-940) -gt 1 -or [Math]::Abs($window.ActualHeight-600) -gt 1){throw 'Restore changed normal window dimensions'}
   }
  }
  $cycles | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'logs/installer-maximized-cycles.json') -Encoding UTF8
 }
 $backend=$window.FindName('CmbBackend');$backend.SelectedIndex=1
 $window.FindName('CmbVram').SelectedIndex=1
 $window.UpdateLayout()
 Assert-SelectedTextColor $backend
 Assert-SelectedTextColor ($window.FindName('CmbVram'))
 if($backend.SelectedItem.Content -notmatch 'CUDA 13\.5'){throw 'RTX 50xx label not corrected'}
 if($backend.BorderBrush.Color.ToString() -ne '#FF303030'){throw 'Dropdown border color was not restored'}
 $check=$window.FindName('ChkDesktopShortcut');$check.ApplyTemplate() | Out-Null
 $checkBorder=$check.Template.FindName('CheckBorder',$check)
 if($checkBorder.Background.Color.ToString() -ne '#FF484848'){throw 'Checkbox border color was not restored'}
 $check.IsChecked=$true;$window.UpdateLayout()
 $mark=$check.Template.FindName('CheckMark',$check)
 $surface=$check.Template.FindName('CheckSurface',$check)
 if($mark.Visibility -ne 'Visible' -or $surface.Background.Color.ToString() -ne '#FFF1F3F5'){throw 'Selected checkbox lost its check or fill'}
 $check.IsChecked=$false;$window.UpdateLayout()
 if($mark.Visibility -ne 'Collapsed' -or $checkBorder.Background.Color.ToString() -ne '#FF484848'){throw 'Unchecked checkbox did not restore its border'}
 foreach($combo in @($backend,$window.FindName('CmbVram'),$window.FindName('CmbLanguage'))){
  $combo.IsDropDownOpen=$true;$window.UpdateLayout()
  $popup=$combo.Template.FindName('Popup',$combo)
  if(-not $popup.Child.UseLayoutRounding -or -not $popup.Child.SnapsToDevicePixels){throw 'Popup borders do not inherit pixel-aligned layout'}
  if($combo.Name -in @('CmbBackend','CmbVram')){foreach($item in $combo.Items){if($item.Foreground.Color.ToString() -ne '#FFD1D5DB'){throw 'Hardware dropdown option color differs from selected value'}}}
  $combo.IsDropDownOpen=$false
 }
 $window.FindName('PageHeader').Visibility='Collapsed'
 $window.FindName('PageHeaderRow').Height=[Windows.GridLength]::new(0)
 $window.UpdateLayout()
 $repairGpu=$window.FindName('LblGpuCaption').PointToScreen([Windows.Point]::new(0,0))
 $repairBackend=$window.FindName('LblBackendCaption').PointToScreen([Windows.Point]::new(0,0))
 $repairValue=$window.FindName('LblGpu').PointToScreen([Windows.Point]::new(0,0))
 Save-View 'controls'
 $window.FindName('ConfigPanel').Visibility='Collapsed'
 $window.FindName('InstallPanel').Visibility='Visible'
 Assert-ProgressSurface ($window.FindName('Progress'))
 Save-View 'install-progress'
 $window.FindName('InstallBodyHost').Visibility='Collapsed'
 $hostControl=$window.FindName('HubPageHost');$hostControl.Visibility='Visible'
 foreach($index in @(1)){
  [xml]$pageXml=Convert-LegacyWindowXamlToHubPage $xamlMatches[$index].Groups[1].Value
  $page=[Windows.Markup.XamlReader]::Load([Xml.XmlNodeReader]::new($pageXml))
  $hostControl.Content=$page
  foreach($name in @('LblBuildCaption','LblDestinationCaption')){ $label=$page.FindName($name);if($label.FontSize -ne 14 -or $label.Foreground.Color.ToString() -ne '#FFF3F5F7'){throw "Incorrect build caption style: $name"} }
  foreach($name in @('LblBuildPath','LblDeployPath')){if($page.FindName($name).Foreground.Color.ToString() -ne '#FFD1D5DB'){throw "Incorrect path color: $name"}}
  $intro='IntroPanel'
  $introPanel=$page.FindName($intro)
  if($introPanel.Children[1].Background.Color.A -ne 0){throw 'An intro card background was restored accidentally'}
  $introPanel.Children[0].Visibility='Collapsed'
  $introPanel.Children[1].VerticalAlignment='Top';$introPanel.Children[1].Margin=[Windows.Thickness]::new(0)
  $window.UpdateLayout()
  foreach($pair in @(@('LblBuildCaption',$repairGpu),@('LblDestinationCaption',$repairBackend))){
   $point=$page.FindName($pair[0]).PointToScreen([Windows.Point]::new(0,0))
   if([Math]::Abs($point.X-$pair[1].X) -gt 1 -or [Math]::Abs($point.Y-$pair[1].Y) -gt 1){throw "Caption alignment differs: $($pair[0]), actual $point, expected $($pair[1])"}
  }
  if([Math]::Abs($page.FindName('LblBuildPath').PointToScreen([Windows.Point]::new(0,0)).X-$repairValue.X) -gt 1){throw 'Path and GPU value columns do not align'}
  Save-View 'build-aligned'
  $introPanel.Visibility='Collapsed'
  $work='WorkPanel'
  $page.FindName($work).Visibility='Visible'
  Assert-ProgressSurface ($page.FindName('Progress'))
  Save-View 'build-progress'
 }
 Write-Output 'PASS: captions, blocked maximize, CUDA label, dropdown/checkbox contrast, progress backgrounds, and unframed intro panels. No installer actions executed.'
}finally{$window.Close()}
