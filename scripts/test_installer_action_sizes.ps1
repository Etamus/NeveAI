$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
$root = Split-Path -Parent $PSScriptRoot
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'launchers/instalar.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$markup = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.StringConstantExpressionAst] -and $node.Value.StartsWith('<Window') -or
    $node -is [System.Management.Automation.Language.ExpandableStringExpressionAst] -and $node.Value.StartsWith('<Window')
}, $true)
if (-not $markup) { throw 'Installer XAML not found' }
$window = [Windows.Markup.XamlReader]::Parse($markup.Value)
$results = @()
foreach ($style in @('AccentActionBtn','CompletionActionBtn')) {
    foreach ($text in @('Instalar','Reparar','Atualizar','Publicar','Cancelar','Install','Repair','Update','Publish','Cancel')) {
        $button = New-Object Windows.Controls.Button
        $button.Style = $window.FindResource($style)
        $button.Content = $text
        $button.Measure([Windows.Size]::new(500,100))
        $button.Arrange([Windows.Rect]::new(0,0,$button.DesiredSize.Width,$button.DesiredSize.Height))
        $button.UpdateLayout()
        if ($button.ActualHeight -ne 34 -or $button.MinWidth -ne 92 -or $button.Padding.Left -ne 16 -or $button.FontSize -ne 15) {
            throw "Unexpected dimensions: $style $text"
        }
        if ($button.DesiredSize.Width -gt 150) { throw "Unexpected label width: $text" }
        $results += @{style=$style;label=$text;width=$button.ActualWidth;height=$button.ActualHeight;fontSize=$button.FontSize}
    }
}
$grid = New-Object Windows.Controls.Grid
$grid.Resources = $window.Resources
$grid.Background = $window.FindResource('BackgroundBrush')
foreach ($width in @(140,130,130)) {
    $column = New-Object Windows.Controls.ColumnDefinition
    $column.Width = [Windows.GridLength]::new($width)
    [void]$grid.ColumnDefinitions.Add($column)
}
$labels = @('Acao','Instalar','Reparar','Atualizar','Publicar','Cancelar')
for ($row=0; $row -lt $labels.Count; $row++) {
    $definition = New-Object Windows.Controls.RowDefinition
    $definition.Height = [Windows.GridLength]::new(44)
    [void]$grid.RowDefinitions.Add($definition)
    for ($column=0; $column -lt 3; $column++) {
        if ($column -eq 0 -or $row -eq 0) {
            $control = New-Object Windows.Controls.TextBlock
            $control.Text = if ($column -eq 0) { $labels[$row] } elseif ($column -eq 1) { 'Antes' } else { 'Depois' }
            $control.VerticalAlignment = 'Center'
            $control.Margin = [Windows.Thickness]::new(12,0,0,0)
        } else {
            $control = New-Object Windows.Controls.Button
            $control.Style = $window.FindResource($(if ($labels[$row] -eq 'Cancelar') { 'CompletionActionBtn' } else { 'AccentActionBtn' }))
            $control.Content = $labels[$row]
            $control.HorizontalAlignment = 'Center'
            $control.VerticalAlignment = 'Center'
            if ($column -eq 1) {
                $control.Height = 36
                $control.MinWidth = 96
                $control.Padding = [Windows.Thickness]::new(18,0,18,0)
            }
        }
        [Windows.Controls.Grid]::SetRow($control,$row)
        [Windows.Controls.Grid]::SetColumn($control,$column)
        [void]$grid.Children.Add($control)
    }
}
$grid.Measure([Windows.Size]::new(400,264))
$grid.Arrange([Windows.Rect]::new(0,0,400,264))
$grid.UpdateLayout()
$bitmap = New-Object Windows.Media.Imaging.RenderTargetBitmap(400,264,96,96,[Windows.Media.PixelFormats]::Pbgra32)
$bitmap.Render($grid)
$encoder = New-Object Windows.Media.Imaging.PngBitmapEncoder
$encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($bitmap))
$stream = [IO.File]::Create((Join-Path $root 'logs/installer-action-sizes.png'))
try { $encoder.Save($stream) } finally { $stream.Dispose() }
$window.Close()
$results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'logs/installer-action-sizes.json') -Encoding UTF8
Write-Output "PowerShell syntax and $($results.Count) rendered WPF buttons passed."
