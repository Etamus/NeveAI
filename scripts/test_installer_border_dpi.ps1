$ErrorActionPreference='Stop'
Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase
$project=Split-Path -Parent $PSScriptRoot
$source=[IO.File]::ReadAllText((Join-Path $project 'launchers/instalar.ps1'))
$xaml=[regex]::Match($source,'(?s)\[xml\]\$xaml = @"\r?\n(.*?)\r?\n"@').Groups[1].Value
$results=@()
foreach($scale in @(1.0,1.25,1.5,2.0)){
 foreach($rounded in @($false,$true)){
  [xml]$xml=$xaml
  $xml.DocumentElement.SetAttribute('UseLayoutRounding',$rounded.ToString())
  $xml.DocumentElement.SetAttribute('SnapsToDevicePixels',$rounded.ToString())
  $ns=[Xml.XmlNamespaceManager]::new($xml.NameTable)
  $ns.AddNamespace('w','http://schemas.microsoft.com/winfx/2006/xaml/presentation')
  foreach($setter in $xml.SelectNodes('//w:Setter[@Property="UseLayoutRounding"]',$ns)){$setter.SetAttribute('Value',$rounded.ToString())}
  $window=[Windows.Markup.XamlReader]::Load([Xml.XmlNodeReader]::new($xml))
  $combo=$window.FindName('CmbBackend');$combo.SelectedIndex=1
  $check=$window.FindName('ChkDesktopShortcut')
  $combo.UseLayoutRounding=$rounded;$check.UseLayoutRounding=$rounded
  # Compare geometry with the original colors, independently of brightness.
  $window.Resources['BorderStrongBrush']=[Windows.Media.SolidColorBrush]::new([Windows.Media.ColorConverter]::ConvertFromString('#484848'))
  $combo.BorderBrush=$window.Resources['BorderBrush']
  $root=$window.Content;$window.Content=$null
  $root.Resources.MergedDictionaries.Add($window.Resources)
  $root.UseLayoutRounding=$rounded;$root.SnapsToDevicePixels=$true
  [Windows.Media.TextOptions]::SetTextFormattingMode($root,[Windows.Media.TextFormattingMode]::Display)
  [Windows.Documents.TextElement]::SetFontFamily($root,[Windows.Media.FontFamily]::new('Segoe UI'))
  [Windows.Media.VisualTreeHelper]::SetRootDpi($root,[Windows.DpiScale]::new($scale,$scale))
  $root.Measure([Windows.Size]::new(980,600));$root.Arrange([Windows.Rect]::new(0,0,980,600));$root.UpdateLayout()
  $toggle=$combo.Template.FindName('DropDownToggle',$combo)
  $comboBorder=$toggle.Template.FindName('ComboBorder',$toggle)
  $checkBorder=$check.Template.FindName('CheckBorder',$check)
  $bitmap=[Windows.Media.Imaging.RenderTargetBitmap]::new([int](980*$scale),[int](600*$scale),96*$scale,96*$scale,[Windows.Media.PixelFormats]::Pbgra32)
  $bitmap.Render($root)
  foreach($entry in @(@('dropdown',$comboBorder),@('checkbox',$checkBorder))){
   $control=$entry[1];$point=$control.TransformToAncestor($root).Transform([Windows.Point]::new(0,0))
   $x=$point.X*$scale;$y=$point.Y*$scale
   $fraction=[Math]::Max([Math]::Abs($x-[Math]::Round($x)),[Math]::Abs($y-[Math]::Round($y)))
   $scan=[Windows.Int32Rect]::new([Math]::Max(0,[int][Math]::Floor($x)-3),[int][Math]::Floor($y+$control.ActualHeight*$scale/2),10,1)
   $pixels=New-Object byte[] 40;$bitmap.CopyPixels($scan,$pixels,40,0)
   $peak=0;for($p=0;$p -lt 40;$p+=4){$peak=[Math]::Max($peak,$pixels[$p])}
   $topScan=[Windows.Int32Rect]::new([int][Math]::Floor($x+$control.ActualWidth*$scale/2),[Math]::Max(0,[int][Math]::Floor($y)-3),1,10)
   $bitmap.CopyPixels($topScan,$pixels,4,0)
   $topPeak=0;for($p=0;$p -lt 40;$p+=4){$topPeak=[Math]::Max($topPeak,$pixels[$p])}
   $results+=[pscustomobject]@{scale=$scale;rounded=$rounded;control=$entry[0];x=$x;y=$y;fraction=$fraction;edgePeak=$peak;topPeak=$topPeak}
   if($rounded -and $fraction -gt 0.01){throw "Non-aligned $($entry[0]) at $scale : $fraction"}
  }
  $encoder=[Windows.Media.Imaging.PngBitmapEncoder]::new();$encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($bitmap))
  $path=Join-Path $project "logs/installer-border-dpi-$scale-$rounded.png"
  $file=[IO.File]::Create($path);try{$encoder.Save($file)}finally{$file.Dispose()}
  $window.Close()
 }
}
$results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $project 'logs/installer-border-dpi.json') -Encoding UTF8
$results | Format-Table control,scale,rounded,fraction,edgePeak,topPeak -AutoSize
