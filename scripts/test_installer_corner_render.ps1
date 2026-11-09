$ErrorActionPreference='Stop'
Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase
$directory=Join-Path (Split-Path -Parent $PSScriptRoot) 'logs'
foreach($kind in @('dropdown','checkbox')){
 foreach($layered in @($false,$true)){
  $size=if($kind -eq 'checkbox'){18}else{120}
  $height=if($kind -eq 'checkbox'){18}else{36}
  $radius=if($kind -eq 'checkbox'){4}else{6}
  $color=if($kind -eq 'checkbox'){'#484848'}else{'#303030'}
  $canvas=[Windows.Controls.Canvas]::new();$canvas.Background=[Windows.Media.Brushes]::Black
  $border=[Windows.Controls.Border]::new();$border.Width=$size;$border.Height=$height
  $border.CornerRadius=[Windows.CornerRadius]::new($radius)
  if($layered){
   $border.Background=[Windows.Media.BrushConverter]::new().ConvertFromString($color)
   $border.Padding=[Windows.Thickness]::new(1)
   $inner=[Windows.Controls.Border]::new();$inner.Background=[Windows.Media.BrushConverter]::new().ConvertFromString('#0D0D0D')
   $inner.CornerRadius=[Windows.CornerRadius]::new($radius-1);$border.Child=$inner
  }else{
   $border.Background=[Windows.Media.BrushConverter]::new().ConvertFromString('#0D0D0D')
   $border.BorderBrush=[Windows.Media.BrushConverter]::new().ConvertFromString($color)
   $border.BorderThickness=[Windows.Thickness]::new(1)
  }
  [Windows.Controls.Canvas]::SetLeft($border,10);[Windows.Controls.Canvas]::SetTop($border,10)
  [void]$canvas.Children.Add($border)
  $canvas.Measure([Windows.Size]::new(150,70));$canvas.Arrange([Windows.Rect]::new(0,0,150,70));$canvas.UpdateLayout()
  $image=[Windows.Media.Imaging.RenderTargetBitmap]::new(150,70,96,96,[Windows.Media.PixelFormats]::Pbgra32)
  $image.Render($canvas)
  $pixels=New-Object byte[] 600;$image.CopyPixels([Windows.Int32Rect]::new(10,10,10,10),$pixels,40,0)
  Write-Output "$kind layered=$layered"
  for($y=0;$y -lt 8;$y++){
   $row=for($x=0;$x -lt 8;$x++){'{0,3}' -f $pixels[$y*40+$x*4]}
   Write-Output ($row -join ' ')
  }
  $encoder=[Windows.Media.Imaging.PngBitmapEncoder]::new();$encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($image))
  $stream=[IO.File]::Create((Join-Path $directory "installer-corner-$kind-$layered.png"))
  try{$encoder.Save($stream)}finally{$stream.Dispose()}
 }
}
