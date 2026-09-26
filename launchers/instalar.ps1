# NeveAI - Instalador Grafico (WPF)
# UI bonita + progresso visual + log em tempo real.
# Toda a logica original (deteccao de GPU, llama.cpp, venv, requirements, npm)
# roda em runspace separado para nao travar a interface.

param(
    [ValidateSet('home', 'install', 'update', 'build')]
    [string]$StartPage = 'home'
)

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [Console]::OutputEncoding
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11 -bor [Net.SecurityProtocolType]::Tls
} catch {
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
}

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class NeveInstallerWindowIdentity
{
    private const uint WM_SETICON = 0x0080;
    private const int ICON_SMALL = 0;
    private const int ICON_BIG = 1;
    private const int ICON_SMALL2 = 2;
    private const uint IMAGE_ICON = 1;
    private const uint LR_LOADFROMFILE = 0x0010;
    private const uint LR_DEFAULTSIZE = 0x0040;

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadImage(
        IntPtr instance,
        string name,
        uint type,
        int width,
        int height,
        uint loadFlags
    );

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr SendMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    public static void ApplyIcon(IntPtr window, string iconPath)
    {
        IntPtr icon = LoadImage(
            IntPtr.Zero,
            iconPath,
            IMAGE_ICON,
            0,
            0,
            LR_LOADFROMFILE | LR_DEFAULTSIZE
        );
        if (icon == IntPtr.Zero) return;

        SendMessage(window, WM_SETICON, new IntPtr(ICON_BIG), icon);
        SendMessage(window, WM_SETICON, new IntPtr(ICON_SMALL), icon);
        SendMessage(window, WM_SETICON, new IntPtr(ICON_SMALL2), icon);
    }
}
'@

[NeveInstallerWindowIdentity]::SetCurrentProcessExplicitAppUserModelID('NeveAI.Installer') | Out-Null

# =============================================================================
# Caminhos globais
# =============================================================================
$SCRIPT_PATH = if ($PSCommandPath) { $PSCommandPath } elseif ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { throw 'Não foi possível determinar o caminho do instalador.' }
$LAUNCHER_DIR = (Resolve-Path -LiteralPath (Split-Path -Parent $SCRIPT_PATH)).ProviderPath
$ROOT         = (Resolve-Path -LiteralPath (Join-Path $LAUNCHER_DIR '..')).ProviderPath
$WINDOW_ICON_PATH = Join-Path $ROOT 'static\static\faviconbar.ico'
Set-Location -LiteralPath $ROOT
$VENV_DIR = Join-Path $ROOT 'backend\neveai\venv'
$VENV_PY  = Join-Path $VENV_DIR 'Scripts\python.exe'
$BACKEND  = Join-Path $ROOT 'backend'
$LOG_DIR  = Join-Path $ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) { New-Item $LOG_DIR -ItemType Directory | Out-Null }
$LOG = Join-Path $LOG_DIR 'install.log'
$STATE_FILE = Join-Path $LOG_DIR 'install-state.txt'
$INSTALLER_REVISION = '2026-09-25-update-validation-v2'
'' | Set-Content $LOG
Add-Content -LiteralPath $LOG -Value ("[INSTALLER] revision={0}; script={1}; root={2}" -f $INSTALLER_REVISION, $SCRIPT_PATH, $ROOT) -Encoding UTF8
[System.IO.File]::WriteAllText($STATE_FILE, 'idle', [System.Text.UTF8Encoding]::new($false))

# Logo (favicon do projeto)
$LOGO_PATH = Join-Path $ROOT 'static\favicon.png'
if (-not (Test-Path $LOGO_PATH)) {
    $LOGO_PATH = Join-Path $ROOT 'static\static\favicon.png'
}

# =============================================================================
# XAML - Interface
# =============================================================================
[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:shell="clr-namespace:System.Windows.Shell;assembly=PresentationFramework"
        Title="NeveAI"
        Width="980" Height="600" MinWidth="980" MinHeight="600"
        WindowStartupLocation="CenterScreen" ResizeMode="CanResize"
        WindowStyle="None" AllowsTransparency="True"
        Background="Transparent" FontFamily="Segoe UI" TextOptions.TextFormattingMode="Display">
    <shell:WindowChrome.WindowChrome>
        <shell:WindowChrome CaptionHeight="0" ResizeBorderThickness="6" GlassFrameThickness="0" CornerRadius="18"/>
    </shell:WindowChrome.WindowChrome>
    <Window.Resources>
        <SolidColorBrush x:Key="BackgroundBrush" Color="#000000"/>
        <SolidColorBrush x:Key="SidebarBrush" Color="#151515"/>
        <SolidColorBrush x:Key="SurfaceBrush" Color="#171717"/>
        <SolidColorBrush x:Key="SurfaceRaisedBrush" Color="#202020"/>
        <SolidColorBrush x:Key="SurfaceHoverBrush" Color="#292929"/>
        <SolidColorBrush x:Key="InputBrush" Color="#0D0D0D"/>
        <SolidColorBrush x:Key="BorderBrush" Color="#303030"/>
        <SolidColorBrush x:Key="BorderStrongBrush" Color="#484848"/>
        <SolidColorBrush x:Key="TextPrimaryBrush" Color="#F3F5F7"/>
        <SolidColorBrush x:Key="TextSecondaryBrush" Color="#A9B1BC"/>
        <SolidColorBrush x:Key="TextMutedBrush" Color="#8B8B8B"/>
        <SolidColorBrush x:Key="AccentBrush" Color="#F1F3F5"/>
        <SolidColorBrush x:Key="AccentHoverBrush" Color="#DDE1E6"/>
        <SolidColorBrush x:Key="AccentTextBrush" Color="#111317"/>
        <SolidColorBrush x:Key="SuccessBrush" Color="#55C894"/>
        <SolidColorBrush x:Key="DangerBrush" Color="#EC7272"/>

        <Style TargetType="TextBlock"><Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/></Style>
        <Style x:Key="PageTitle" TargetType="TextBlock"><Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/><Setter Property="FontSize" Value="24"/><Setter Property="FontWeight" Value="SemiBold"/></Style>
        <Style x:Key="CaptionText" TargetType="TextBlock"><Setter Property="Foreground" Value="{DynamicResource TextSecondaryBrush}"/><Setter Property="FontSize" Value="12"/></Style>
        <Style x:Key="Section" TargetType="Border"><Setter Property="Background" Value="{DynamicResource SurfaceBrush}"/><Setter Property="BorderBrush" Value="{DynamicResource BorderBrush}"/><Setter Property="BorderThickness" Value="1"/><Setter Property="CornerRadius" Value="8"/><Setter Property="Padding" Value="20"/></Style>

        <Style x:Key="PrimaryBtn" TargetType="Button">
            <Setter Property="Background" Value="{DynamicResource SurfaceRaisedBrush}"/><Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/><Setter Property="BorderBrush" Value="{DynamicResource BorderStrongBrush}"/>
            <Setter Property="BorderThickness" Value="0"/><Setter Property="Padding" Value="18,0"/><Setter Property="MinWidth" Value="96"/><Setter Property="Height" Value="36"/>
            <Setter Property="FontSize" Value="15"/><Setter Property="FontWeight" Value="Medium"/><Setter Property="HorizontalContentAlignment" Value="Center"/><Setter Property="VerticalContentAlignment" Value="Center"/><Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="Button"><Border x:Name="bd" Background="{TemplateBinding Background}" BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}" CornerRadius="6" Padding="{TemplateBinding Padding}"><ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/></Border><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="bd" Property="Background" Value="{DynamicResource SurfaceHoverBrush}"/></Trigger><Trigger Property="IsPressed" Value="True"><Setter TargetName="bd" Property="Opacity" Value="0.8"/></Trigger><Trigger Property="IsEnabled" Value="False"><Setter TargetName="bd" Property="Opacity" Value="0.4"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style x:Key="AccentActionBtn" TargetType="Button" BasedOn="{StaticResource PrimaryBtn}">
            <Setter Property="Background" Value="{DynamicResource AccentBrush}"/><Setter Property="Foreground" Value="{DynamicResource AccentTextBrush}"/><Setter Property="BorderBrush" Value="{DynamicResource AccentBrush}"/><Setter Property="FontWeight" Value="Medium"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="Button"><Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="6" Padding="{TemplateBinding Padding}"><ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/></Border><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="bd" Property="Background" Value="{DynamicResource AccentHoverBrush}"/></Trigger><Trigger Property="IsPressed" Value="True"><Setter TargetName="bd" Property="Opacity" Value="0.82"/></Trigger><Trigger Property="IsEnabled" Value="False"><Setter TargetName="bd" Property="Opacity" Value="0.38"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style x:Key="GhostBtn" TargetType="Button" BasedOn="{StaticResource PrimaryBtn}">
            <Setter Property="Background" Value="{DynamicResource SurfaceRaisedBrush}"/><Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/><Setter Property="BorderBrush" Value="{DynamicResource BorderBrush}"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="Button"><Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="6" Padding="{TemplateBinding Padding}"><ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/></Border><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="bd" Property="Background" Value="{DynamicResource SurfaceHoverBrush}"/></Trigger><Trigger Property="IsEnabled" Value="False"><Setter TargetName="bd" Property="Opacity" Value="0.4"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style x:Key="CompletionActionBtn" TargetType="Button" BasedOn="{StaticResource PrimaryBtn}">
            <Setter Property="BorderThickness" Value="0"/>
        </Style>
        <Style x:Key="WindowButton" TargetType="Button">
            <Setter Property="Width" Value="46"/><Setter Property="Height" Value="44"/><Setter Property="Background" Value="Transparent"/><Setter Property="Foreground" Value="{DynamicResource TextSecondaryBrush}"/><Setter Property="BorderThickness" Value="0"/><Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="Button"><Border x:Name="bd" Background="{TemplateBinding Background}"><ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/></Border><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="bd" Property="Background" Value="{DynamicResource SurfaceHoverBrush}"/><Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style x:Key="CloseWindowButton" TargetType="Button" BasedOn="{StaticResource WindowButton}">
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="Button"><Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="0,16,0,0"><ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/></Border><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="bd" Property="Background" Value="#C42B1C"/><Setter Property="Foreground" Value="White"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style x:Key="NavigationButton" TargetType="Button">
            <Setter Property="Height" Value="46"/><Setter Property="Margin" Value="10,3"/><Setter Property="Padding" Value="14,0"/><Setter Property="HorizontalContentAlignment" Value="Left"/><Setter Property="Background" Value="Transparent"/><Setter Property="Foreground" Value="#B8B8B8"/><Setter Property="FontSize" Value="16"/><Setter Property="FontFamily" Value="Segoe UI"/><Setter Property="FontWeight" Value="Medium"/><Setter Property="BorderThickness" Value="0"/><Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="Button"><Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="6" Padding="{TemplateBinding Padding}"><ContentPresenter HorizontalAlignment="{TemplateBinding HorizontalContentAlignment}" VerticalAlignment="Center"/></Border><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="bd" Property="Background" Value="{DynamicResource SurfaceHoverBrush}"/><Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/></Trigger><Trigger Property="Tag" Value="active"><Setter TargetName="bd" Property="Background" Value="{DynamicResource SurfaceRaisedBrush}"/><Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/></Trigger><Trigger Property="IsEnabled" Value="False"><Setter Property="Opacity" Value="0.4"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style x:Key="ComboBoxItemStyle" TargetType="ComboBoxItem">
            <Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/><Setter Property="Background" Value="Transparent"/><Setter Property="Padding" Value="10,8"/><Setter Property="HorizontalContentAlignment" Value="Stretch"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="ComboBoxItem"><Border x:Name="ItemBorder" Background="{TemplateBinding Background}" CornerRadius="4" Padding="{TemplateBinding Padding}" Margin="3,1"><ContentPresenter/></Border><ControlTemplate.Triggers><Trigger Property="IsHighlighted" Value="True"><Setter TargetName="ItemBorder" Property="Background" Value="{DynamicResource SurfaceHoverBrush}"/></Trigger><Trigger Property="IsSelected" Value="True"><Setter TargetName="ItemBorder" Property="Background" Value="#303030"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style TargetType="ComboBox">
            <Setter Property="Background" Value="{DynamicResource InputBrush}"/><Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/><Setter Property="BorderBrush" Value="{DynamicResource BorderBrush}"/><Setter Property="BorderThickness" Value="1"/><Setter Property="Padding" Value="11,0"/><Setter Property="MinHeight" Value="36"/><Setter Property="FontSize" Value="13"/><Setter Property="MaxDropDownHeight" Value="260"/><Setter Property="ItemContainerStyle" Value="{StaticResource ComboBoxItemStyle}"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="ComboBox"><Grid><ToggleButton x:Name="DropDownToggle" Background="Transparent" BorderThickness="0" Focusable="False" ClickMode="Press" IsChecked="{Binding IsDropDownOpen, Mode=TwoWay, RelativeSource={RelativeSource TemplatedParent}}"><ToggleButton.Template><ControlTemplate TargetType="ToggleButton"><Border x:Name="ComboBorder" Background="{Binding Background, RelativeSource={RelativeSource AncestorType=ComboBox}}" BorderBrush="{Binding BorderBrush, RelativeSource={RelativeSource AncestorType=ComboBox}}" BorderThickness="{Binding BorderThickness, RelativeSource={RelativeSource AncestorType=ComboBox}}" CornerRadius="6"><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="34"/></Grid.ColumnDefinitions><ContentPresenter Margin="11,0,6,0" VerticalAlignment="Center" HorizontalAlignment="Stretch" TextElement.Foreground="{DynamicResource TextPrimaryBrush}" Content="{Binding SelectionBoxItem, RelativeSource={RelativeSource AncestorType=ComboBox}}" ContentTemplate="{Binding SelectionBoxItemTemplate, RelativeSource={RelativeSource AncestorType=ComboBox}}"/><Path Grid.Column="1" Width="10" Height="6" HorizontalAlignment="Center" VerticalAlignment="Center" Stroke="{DynamicResource TextSecondaryBrush}" StrokeThickness="1.6" StrokeStartLineCap="Round" StrokeEndLineCap="Round" Data="M 1 1 L 5 5 L 9 1"/></Grid></Border><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="ComboBorder" Property="BorderBrush" Value="{DynamicResource BorderStrongBrush}"/></Trigger></ControlTemplate.Triggers></ControlTemplate></ToggleButton.Template></ToggleButton><Popup x:Name="Popup" IsOpen="{TemplateBinding IsDropDownOpen}" Placement="Bottom" PlacementTarget="{Binding ElementName=DropDownToggle}" AllowsTransparency="True" Focusable="False" PopupAnimation="Fade"><Border Width="{Binding ActualWidth, ElementName=DropDownToggle}" MaxHeight="{TemplateBinding MaxDropDownHeight}" Margin="0,4,0,0" Padding="3" Background="{DynamicResource SurfaceRaisedBrush}" BorderBrush="{DynamicResource BorderStrongBrush}" BorderThickness="1" CornerRadius="6"><ScrollViewer VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled"><StackPanel IsItemsHost="True"/></ScrollViewer></Border></Popup></Grid><ControlTemplate.Triggers><Trigger Property="IsEnabled" Value="False"><Setter TargetName="DropDownToggle" Property="Opacity" Value="0.48"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style x:Key="OptionCheckBox" TargetType="CheckBox">
            <Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}"/><Setter Property="FontSize" Value="13"/><Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="CheckBox"><StackPanel Orientation="Horizontal"><Border x:Name="CheckBorder" Width="18" Height="18" Background="{DynamicResource InputBrush}" BorderBrush="{DynamicResource BorderStrongBrush}" BorderThickness="1" CornerRadius="4"><Path x:Name="CheckMark" Width="10" Height="7" Data="M 1 3.5 L 4 6.5 L 9 1" Stroke="#111317" StrokeThickness="1.8" StrokeStartLineCap="Round" StrokeEndLineCap="Round" Visibility="Collapsed"/></Border><ContentPresenter Margin="9,0,0,0" VerticalAlignment="Center"/></StackPanel><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="CheckBorder" Property="BorderBrush" Value="{DynamicResource TextSecondaryBrush}"/></Trigger><Trigger Property="IsChecked" Value="True"><Setter TargetName="CheckBorder" Property="Background" Value="{DynamicResource AccentBrush}"/><Setter TargetName="CheckBorder" Property="BorderBrush" Value="{DynamicResource AccentBrush}"/><Setter TargetName="CheckMark" Property="Visibility" Value="Visible"/></Trigger><Trigger Property="IsEnabled" Value="False"><Setter Property="Opacity" Value="0.45"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
        </Style>
        <Style TargetType="ScrollBar">
            <Setter Property="Width" Value="10"/><Setter Property="MinWidth" Value="10"/><Setter Property="Background" Value="Transparent"/>
            <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="ScrollBar"><Grid Background="{TemplateBinding Background}"><Track x:Name="PART_Track" IsDirectionReversed="True"><Track.DecreaseRepeatButton><RepeatButton Command="ScrollBar.PageUpCommand" Background="Transparent" BorderThickness="0"/></Track.DecreaseRepeatButton><Track.Thumb><Thumb><Thumb.Template><ControlTemplate TargetType="Thumb"><Border Margin="2,1" Background="#4A4A4A" CornerRadius="3"/></ControlTemplate></Thumb.Template></Thumb></Track.Thumb><Track.IncreaseRepeatButton><RepeatButton Command="ScrollBar.PageDownCommand" Background="Transparent" BorderThickness="0"/></Track.IncreaseRepeatButton></Track></Grid></ControlTemplate></Setter.Value></Setter>
        </Style>
    </Window.Resources>

    <Border Margin="1" BorderBrush="{DynamicResource BorderStrongBrush}" BorderThickness="1" CornerRadius="18" Background="Transparent">
        <Grid>
            <Grid.RowDefinitions><RowDefinition Height="44"/><RowDefinition Height="*"/></Grid.RowDefinitions>
            <Border x:Name="TitleBar" Grid.Row="0" Background="{DynamicResource SidebarBrush}" CornerRadius="17,17,0,0">
                <Grid><Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
                    <StackPanel Grid.Column="1" Orientation="Horizontal">
                        <Button x:Name="BtnMinimize" Style="{StaticResource WindowButton}" ToolTip="Minimizar"><Path Width="10" Stroke="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" StrokeThickness="1.4" Data="M 0 5 L 10 5"/></Button>
                        <Button x:Name="BtnMaximize" Style="{StaticResource WindowButton}" ToolTip="Maximizar"><Path Width="10" Height="10" Stroke="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" StrokeThickness="1.2" Data="M 0.6 0.6 L 9.4 0.6 L 9.4 9.4 L 0.6 9.4 Z"/></Button>
                        <Button x:Name="BtnClose" Style="{StaticResource CloseWindowButton}" ToolTip="Fechar"><Path Width="10" Height="10" Stroke="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" StrokeThickness="1.4" Data="M 1 1 L 9 9 M 9 1 L 1 9"/></Button>
                    </StackPanel>
                </Grid>
            </Border>
            <Grid Grid.Row="1"><Grid.ColumnDefinitions><ColumnDefinition x:Name="SidebarColumn" Width="210"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                <Border x:Name="SidebarPanel" Grid.Column="0" Background="{DynamicResource SidebarBrush}" BorderBrush="{DynamicResource BorderBrush}" BorderThickness="0,1,0,0" CornerRadius="0,0,0,17">
                    <Grid><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/></Grid.RowDefinitions>
                        <StackPanel Margin="20,26,16,24"><TextBlock Text="NeveAI" FontSize="21" FontWeight="Bold"/></StackPanel>
                        <StackPanel Grid.Row="1">
                            <Button x:Name="NavOverview" Style="{StaticResource NavigationButton}" Tag="active">
                                <StackPanel Orientation="Horizontal"><Viewbox Width="21" Height="21"><Path Width="24" Height="24" Fill="Transparent" Stroke="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" StrokeThickness="1.8" StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round" Data="M 12 3 L 12 15 M 7 10 L 12 15 L 17 10 M 5 15 L 5 19 A 2 2 0 0 0 7 21 L 17 21 A 2 2 0 0 0 19 19 L 19 15"/></Viewbox><TextBlock Margin="10,0,0,0" VerticalAlignment="Center" FontFamily="Segoe UI" FontSize="16" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" Text="Instalar"/></StackPanel>
                            </Button>
                            <Button x:Name="NavSettings" Style="{StaticResource NavigationButton}">
                                <StackPanel Orientation="Horizontal"><Viewbox Width="21" Height="21"><Path Width="24" Height="24" Fill="Transparent" Stroke="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" StrokeThickness="1.8" StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round" Data="M 14.7 6.3 A 1 1 0 0 0 14.7 7.7 L 16.3 9.3 A 1 1 0 0 0 17.7 9.3 L 21.47 5.53 A 6 6 0 0 1 13.53 13.47 L 6.62 20.38 A 2.12 2.12 0 0 1 3.62 17.38 L 10.53 10.47 A 6 6 0 0 1 18.47 2.53 Z"/></Viewbox><TextBlock Margin="10,0,0,0" VerticalAlignment="Center" FontFamily="Segoe UI" FontSize="16" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" Text="Atualizar"/></StackPanel>
                            </Button>
                            <Button x:Name="NavDiagnostics" Style="{StaticResource NavigationButton}">
                                <StackPanel Orientation="Horizontal"><Viewbox Width="21" Height="21"><Path Width="24" Height="24" Fill="Transparent" Stroke="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" StrokeThickness="1.8" StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round" Data="M 3 4 L 21 4 L 21 20 L 3 20 Z M 7 8 L 11 12 L 7 16 M 13 16 L 17 16"/></Viewbox><TextBlock Margin="10,0,0,0" VerticalAlignment="Center" FontFamily="Segoe UI" FontSize="16" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=Button}}" Text="Buildar"/></StackPanel>
                            </Button>
                        </StackPanel>
                    </Grid>
                </Border>
                <Border Grid.Column="1" Background="{DynamicResource BackgroundBrush}" CornerRadius="0,0,17,0">
                    <Grid><Grid.RowDefinitions><RowDefinition Height="70"/><RowDefinition Height="*"/><RowDefinition Height="0"/></Grid.RowDefinitions>
                        <Border Grid.Row="0" BorderBrush="{DynamicResource BorderBrush}" BorderThickness="0,1,0,1" Background="{DynamicResource BackgroundBrush}"><Grid Margin="28,0"><Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><StackPanel VerticalAlignment="Center"><TextBlock x:Name="LblPageContext" Text="Instalação" FontSize="15" FontWeight="SemiBold"/><TextBlock x:Name="LblPageSubtitle" Text="Detecte o hardware e instale tudo o que a NeveAI precisa." Margin="0,3,0,0" FontSize="13" Foreground="{DynamicResource TextSecondaryBrush}"/></StackPanel><Grid x:Name="HeaderActions" Grid.Column="1" VerticalAlignment="Center"><StackPanel x:Name="InstallActions" Orientation="Horizontal"><Button x:Name="BtnCancel" Style="{StaticResource CompletionActionBtn}" Content="Cancelar" Margin="0,0,10,0" Visibility="Collapsed"/><Button x:Name="BtnPrimary" Style="{StaticResource AccentActionBtn}" Content="Instalar"/></StackPanel></Grid></Grid></Border>
                        <Grid x:Name="InstallBodyHost" Grid.Row="1" Margin="32,24,32,24">

                <!-- WELCOME / CONFIG CARD -->
                <Grid x:Name="ConfigPanel">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Visibility="Collapsed"/>

                    <Border Grid.Row="1" Style="{StaticResource Section}" VerticalAlignment="Top">
                        <Grid VerticalAlignment="Center" Margin="0,24,0,24">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="220"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                            </Grid.RowDefinitions>

                            <TextBlock Grid.Row="0" Grid.Column="0" Text="GPU detectada:" FontSize="13" Foreground="{DynamicResource TextSecondaryBrush}" VerticalAlignment="Center" Margin="0,0,0,24"/>
                            <TextBlock Grid.Row="0" Grid.Column="1" x:Name="LblGpu" Text="Detectando..." FontSize="13" FontWeight="SemiBold" VerticalAlignment="Center" Margin="0,0,0,24" TextTrimming="CharacterEllipsis"/>

                            <TextBlock Grid.Row="1" Grid.Column="0" Text="Tipo de aceleração:" FontSize="13" Foreground="{DynamicResource TextSecondaryBrush}" VerticalAlignment="Center" Margin="0,0,0,12"/>
                            <ComboBox  Grid.Row="1" Grid.Column="1" x:Name="CmbBackend" Margin="0,0,0,12">
                                <ComboBoxItem Content="CPU (sem GPU)"/>
                                <ComboBoxItem Content="NVIDIA - RTX 50xx (Blackwell, CUDA 13.3)"/>
                                <ComboBoxItem Content="NVIDIA - RTX 40xx (Ada, CUDA 12.8)"/>
                                <ComboBoxItem Content="NVIDIA - RTX 30xx (Ampere, CUDA 12.8)"/>
                                <ComboBoxItem Content="NVIDIA - RTX 20xx (Turing, CUDA 12.6)"/>
                                <ComboBoxItem Content="NVIDIA - GTX 16xx (Turing, CUDA 12.4)"/>
                                <ComboBoxItem Content="NVIDIA - GTX 10xx ou anterior (Pascal)"/>
                                <ComboBoxItem Content="NVIDIA - Profissional (RTX A/Quadro/Tesla)"/>
                                <ComboBoxItem Content="AMD - HIP/ROCm 6.3"/>
                                <ComboBoxItem Content="AMD - Vulkan"/>
                            </ComboBox>

                            <TextBlock Grid.Row="2" Grid.Column="0" Text="VRAM (GB):" FontSize="13" Foreground="{DynamicResource TextSecondaryBrush}" VerticalAlignment="Center" Margin="0,0,0,12"/>
                            <ComboBox  Grid.Row="2" Grid.Column="1" x:Name="CmbVram" Margin="0,0,0,12">
                                <ComboBoxItem Content="Pular"/>
                                <ComboBoxItem Content="4 GB"/>
                                <ComboBoxItem Content="6 GB"/>
                                <ComboBoxItem Content="8 GB"/>
                                <ComboBoxItem Content="12 GB"/>
                                <ComboBoxItem Content="16 GB"/>
                                <ComboBoxItem Content="24 GB"/>
                                <ComboBoxItem Content="32 GB ou mais"/>
                            </ComboBox>

                            <CheckBox Grid.Row="3" Grid.Column="1" x:Name="ChkInstallPython" Content="Instalar Python 3.11" Style="{StaticResource OptionCheckBox}" Margin="0,5,0,14"/>
                            <CheckBox Grid.Row="4" Grid.Column="1" x:Name="ChkDesktopShortcut" Content="Adicionar ícone à área de trabalho" Style="{StaticResource OptionCheckBox}" Margin="0,0,0,0"/>
                        </Grid>
                    </Border>
                </Grid>

                <!-- INSTALL CARD -->
                <Grid x:Name="InstallPanel" Visibility="Collapsed">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0">
                        <TextBlock x:Name="LblStep" Text="Preparando…" FontSize="13" Foreground="{DynamicResource TextSecondaryBrush}" Margin="0,5,0,0" Visibility="Collapsed"/>
                    </StackPanel>

                    <Border Grid.Row="1" Style="{StaticResource Section}" Padding="16,14" Margin="0,0,0,14">
                        <StackPanel>
                            <Grid>
                                <TextBlock x:Name="LblProgressTxt" Text="0%" FontSize="12" Foreground="{DynamicResource TextSecondaryBrush}" HorizontalAlignment="Right"/>
                                <TextBlock x:Name="LblPhase" Text="Iniciando" FontSize="12" Foreground="{DynamicResource TextSecondaryBrush}"/>
                            </Grid>
                            <ProgressBar x:Name="Progress" Height="6" Minimum="0" Maximum="100" Value="0" Margin="0,8,0,0"
                                         Foreground="{DynamicResource AccentBrush}" Background="{DynamicResource SurfaceRaisedBrush}" BorderThickness="0"/>
                        </StackPanel>
                    </Border>

                    <Border Grid.Row="2" Background="#000000" BorderBrush="{DynamicResource BorderBrush}" BorderThickness="1" CornerRadius="8" Padding="14,12">
                        <ScrollViewer x:Name="LogScroll" VerticalScrollBarVisibility="Auto">
                            <TextBox x:Name="LogBox" Background="Transparent" Foreground="#D4D4D4" BorderThickness="0"
                                     IsReadOnly="True" FontFamily="Consolas" FontSize="11" TextWrapping="Wrap"
                                     AcceptsReturn="True" VerticalScrollBarVisibility="Disabled"/>
                        </ScrollViewer>
                    </Border>
                </Grid>

                <!-- DONE CARD -->
                <Grid x:Name="DonePanel" Visibility="Collapsed">
                    <Border Style="{StaticResource Section}" Padding="32" VerticalAlignment="Top">
                        <StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
                            <Border Width="56" Height="56" CornerRadius="28" Background="#10B981" Margin="0,0,0,18">
                                <TextBlock Text="OK" FontSize="20" FontWeight="Bold" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                            <TextBlock x:Name="LblDoneTitle" Text="Tudo pronto!" FontSize="22" FontWeight="SemiBold" HorizontalAlignment="Center"/>
                            <TextBlock x:Name="LblDoneSub" Text="Use iniciar.bat para iniciar o NeveAI." FontSize="13" Foreground="{DynamicResource TextSecondaryBrush}" HorizontalAlignment="Center" Margin="0,6,0,18"/>
                            <Border Background="{DynamicResource InputBrush}" BorderBrush="{DynamicResource BorderBrush}" BorderThickness="1" CornerRadius="7" Padding="14,12">
                                <TextBlock x:Name="LblSummary" FontFamily="Consolas" FontSize="11" Foreground="{DynamicResource TextSecondaryBrush}"/>
                            </Border>
                        </StackPanel>
                    </Border>
                </Grid>

                        </Grid>
                        <Border x:Name="InstallFooterHost" Grid.Row="2" Visibility="Collapsed"/>
                        <ContentControl x:Name="HubPageHost" Grid.Row="1" Grid.RowSpan="2" Visibility="Collapsed"/>
                    </Grid>
                </Border>
            </Grid>
        </Grid>
    </Border>
</Window>
"@

# =============================================================================
# Carregar XAML
# =============================================================================
$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)
$window.Tag = 'idle'

if (Test-Path -LiteralPath $WINDOW_ICON_PATH) {
    $window.Icon = [System.Windows.Media.Imaging.BitmapFrame]::Create([Uri]$WINDOW_ICON_PATH)
    $window.Add_SourceInitialized({
        $interop = New-Object System.Windows.Interop.WindowInteropHelper($window)
        [NeveInstallerWindowIdentity]::ApplyIcon($interop.Handle, $WINDOW_ICON_PATH)
    })
}

# Atalhos para controles
$ctl = @{}
foreach ($name in 'TitleBar','BtnMinimize','BtnMaximize','BtnClose','SidebarColumn','SidebarPanel','NavOverview','NavSettings','NavDiagnostics','LblPageContext','LblPageSubtitle','HeaderActions','InstallActions',
                  'LblGpu','CmbBackend','CmbVram','ChkInstallPython','ChkDesktopShortcut',
                  'ConfigPanel','InstallPanel','DonePanel',
                  'LblStep','LblPhase','LblProgressTxt','Progress','LogBox','LogScroll',
                  'LblDoneTitle','LblDoneSub','LblSummary',
                  'BtnCancel','BtnPrimary',
                  'InstallBodyHost','InstallFooterHost','HubPageHost') {
    $ctl[$name] = $window.FindName($name)
}

$script:InstallProcessList = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))
$script:InstallControl = [hashtable]::Synchronized(@{
    CancelRequested = $false
    Processes = $script:InstallProcessList
})
$script:PendingInstallCleanup = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))

$window.Dispatcher.add_UnhandledException({
    param($sender, $eventArgs)
    $msg = if ($eventArgs.Exception) { $eventArgs.Exception.Message } else { 'Falha inesperada no instalador.' }
    try { [System.IO.File]::WriteAllText($STATE_FILE, 'failed', [System.Text.UTF8Encoding]::new($false)) } catch {}
    try { Add-Content -LiteralPath $LOG -Value "[FATAL UI] $msg" -Encoding UTF8 } catch {}
    try {
        $ctl.LblStep.Text = 'Falha inesperada no instalador.'
        $ctl.LblPhase.Text = 'Falha inesperada no instalador.'
        $ctl.BtnPrimary.IsEnabled = $true
        $ctl.BtnPrimary.Content = 'Fechar'
        $ctl.BtnPrimary.Tag = 'done'
        $ctl.BtnCancel.Visibility = 'Collapsed'
        $ctl.BtnCancel.IsEnabled = $false
        $ctl.BtnClose.IsEnabled = $true
        $window.Tag = 'failed'
        $ctl.LogBox.AppendText("[FATAL UI] $msg`r`n")
        $ctl.LogScroll.ScrollToEnd()
    } catch {}
    [System.Windows.MessageBox]::Show("O instalador encontrou uma falha, mas a janela ficará aberta.`n`nVeja logs\install.log`n`n$msg", 'NeveAI - Instalador', 'OK', 'Error') | Out-Null
    $eventArgs.Handled = $true
})

# Drag da janela
$ctl.TitleBar.Add_MouseLeftButtonDown({
    param($s, $e)
    if ($e.ClickCount -eq 2) {
        $window.WindowState = if ($window.WindowState -eq 'Maximized') { 'Normal' } else { 'Maximized' }
        return
    }
    if ($e.ButtonState -eq 'Pressed') { try { $window.DragMove() } catch {} }
})

$window.Add_Loaded({
    try {
        $window.Topmost = $true
        [void]$window.Activate()
        $window.Topmost = $false
        [void]$window.Focus()
    } catch {}
})

function Stop-InstallerProcessTree([int]$ProcessId) {
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -EA SilentlyContinue)
        foreach ($child in $children) { Stop-InstallerProcessTree ([int]$child.ProcessId) }
    } catch {}
    try {
        $proc = Get-Process -Id $ProcessId -EA SilentlyContinue
        if ($proc -and -not $proc.HasExited) { Stop-Process -Id $ProcessId -Force -EA SilentlyContinue }
    } catch {}
}

function Stop-RegisteredInstallerProcesses {
    try {
        foreach ($proc in @($script:InstallControl.Processes)) {
            if ($proc -and -not $proc.HasExited) { Stop-InstallerProcessTree ([int]$proc.Id) }
        }
    } catch {}
}

$script:NeveAppCloseRequested = $false
function Stop-NeveRunningApp([string]$Reason = 'operação') {
    if ($script:NeveAppCloseRequested) { return }
    $script:NeveAppCloseRequested = $true

    try {
        Add-Content -LiteralPath $LOG -Value ("[INFO] Encerrando NeveAI antes de iniciar: {0}" -f $Reason) -Encoding UTF8
    } catch {}

    $targets = @()
    $browserProfile = ''
    try { $browserProfile = (Join-Path $ROOT 'logs\browser-app').ToLowerInvariant() } catch {}
    $browserProfileAlt = $browserProfile -replace '\\', '/'

    try {
        foreach ($proc in @(Get-CimInstance Win32_Process -EA SilentlyContinue)) {
            $processId = [int]$proc.ProcessId
            if ($processId -eq $PID) { continue }

            $name = if ($proc.Name) { [string]$proc.Name } else { '' }
            $cmd = if ($proc.CommandLine) { [string]$proc.CommandLine } else { '' }
            $nameLower = $name.ToLowerInvariant()
            $cmdLower = $cmd.ToLowerInvariant()

            if ($cmdLower.Contains('instalar.ps1') -or $cmdLower.Contains('install-launcher.log')) {
                continue
            }

            $isTarget = $false
            if ($nameLower -like 'llama-server*' -or $nameLower -like 'llama_server*') {
                $isTarget = $true
            }
            if ($cmdLower.Contains('neveai.main:app')) {
                $isTarget = $true
            }
            if ($cmdLower.Contains('neve_window.py')) {
                $isTarget = $true
            }
            if ($browserProfile -and ($cmdLower.Contains($browserProfile) -or $cmdLower.Contains($browserProfileAlt))) {
                $isTarget = $true
            }
            if ($cmdLower.Contains('--app=http://localhost:8080') -or $cmdLower.Contains('--app=http://127.0.0.1:8080')) {
                $isTarget = $true
            }

            if ($isTarget) { $targets += $processId }
        }
    } catch {}

    foreach ($targetPid in @($targets | Sort-Object -Unique)) {
        try { Stop-InstallerProcessTree ([int]$targetPid) } catch {}
    }

    if ($targets.Count -gt 0) {
        Start-Sleep -Milliseconds 600
    }
}

function Restore-InstallSelectionView {
    $ctl.InstallPanel.Visibility = 'Collapsed'
    $ctl.DonePanel.Visibility = 'Collapsed'
    $ctl.ConfigPanel.Visibility = 'Visible'
    $ctl.BtnCancel.Visibility = 'Collapsed'
    $ctl.BtnCancel.IsEnabled = $false
    $ctl.BtnCancel.Content = 'Cancelar'
    $ctl.BtnPrimary.Visibility = 'Visible'
    $ctl.BtnPrimary.IsEnabled = $true
    $ctl.BtnPrimary.Content = 'Instalar'
    $ctl.BtnPrimary.Tag = $null
    $ctl.Progress.Value = 0
    $ctl.LblProgressTxt.Text = '0%'
    $ctl.LblPhase.Text = 'Iniciando'
    $ctl.LogBox.Clear()
    $ctl.BtnClose.IsEnabled = $true
    $window.Tag = 'idle'
}

function Request-InstallCancel([bool]$CloseAfterCancel = $false) {
    if ($script:InstallControl.CancelRequested) { return }
    $script:InstallControl.CancelRequested = $true
    try { [System.IO.File]::WriteAllText($STATE_FILE, 'cancelled', [System.Text.UTF8Encoding]::new($false)) } catch {}
    try { Add-Content -LiteralPath $LOG -Value '[!] Instalação cancelada pelo usuário.' -Encoding UTF8 } catch {}

    try {
        $ctl.BtnCancel.IsEnabled = $false
        $ctl.BtnCancel.Content = 'Cancelando...'
        $ctl.LblStep.Text = 'Cancelando instalação...'
        $ctl.LblPhase.Text = 'Cancelando instalação...'
        $ctl.LogBox.AppendText("[!] Instalação cancelada pelo usuário.`r`n")
        $ctl.LogScroll.ScrollToEnd()
    } catch {}

    Stop-RegisteredInstallerProcesses

    $powerShellToStop = $script:InstallerPowerShell
    $runspaceToDispose = $script:InstallerRunspace
    $stopResult = $null
    try {
        if ($powerShellToStop) { $stopResult = $powerShellToStop.BeginStop($null, $null) }
    } catch {}
    if ($powerShellToStop -or $runspaceToDispose) {
        [void]$script:PendingInstallCleanup.Add([pscustomobject]@{
            PowerShell = $powerShellToStop
            Runspace = $runspaceToDispose
            StopResult = $stopResult
        })
    }

    $script:InstallerPowerShell = $null
    $script:InstallerRunspace = $null
    $script:InstallerAsyncResult = $null
    $script:InstallProcessList = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))
    $script:InstallControl = [hashtable]::Synchronized(@{
        CancelRequested = $false
        Processes = $script:InstallProcessList
    })
    $script:NeveAppCloseRequested = $false
    $window.Tag = 'cancelled'
    if ($CloseAfterCancel) {
        try { $window.Close() } catch {}
    } else {
        Restore-InstallSelectionView
    }
}

function Complete-PendingInstallCleanup {
    for ($index = $script:PendingInstallCleanup.Count - 1; $index -ge 0; $index--) {
        $pending = $script:PendingInstallCleanup[$index]
        $finished = $null -eq $pending.StopResult -or $pending.StopResult.IsCompleted
        if (-not $finished) { continue }
        try {
            if ($pending.PowerShell -and $pending.StopResult) {
                $pending.PowerShell.EndStop($pending.StopResult)
            }
        } catch {}
        try { if ($pending.PowerShell) { $pending.PowerShell.Dispose() } } catch {}
        try { if ($pending.Runspace) { $pending.Runspace.Dispose() } } catch {}
        $script:PendingInstallCleanup.RemoveAt($index)
    }
}

# Botoes basicos
$ctl.BtnMinimize.Add_Click({
    try { $window.WindowState = [System.Windows.WindowState]::Minimized } catch {}
})
$ctl.BtnMaximize.Add_Click({
    try {
        $window.WindowState = if ($window.WindowState -eq [System.Windows.WindowState]::Maximized) {
            [System.Windows.WindowState]::Normal
        } else {
            [System.Windows.WindowState]::Maximized
        }
    } catch {}
})
$ctl.BtnClose.Add_Click({
    if ([string]$window.Tag -eq 'installing') { Request-InstallCancel $true; return }
    $window.Close()
})
$ctl.BtnCancel.Add_Click({
    if ([string]$window.Tag -eq 'installing') { Request-InstallCancel $false; return }
    Restore-InstallSelectionView
})
$window.Add_Closing({
    param($sender, $eventArgs)
    if ([string]$window.Tag -eq 'installing') {
        Request-InstallCancel $false
    }
})

# =============================================================================
# Deteccao de hardware (executa antes de mostrar a janela)
# =============================================================================
$detected = @{
    Vendor    = 'CPU'
    Name      = ''
    Backend   = 0   # indice do CmbBackend
}

try {
    $nOut = nvidia-smi --query-gpu=name --format=csv,noheader 2>&1
    if ($LASTEXITCODE -eq 0 -and "$nOut" -notmatch 'failed|not found') {
        $detected.Vendor = 'NVIDIA'
        $detected.Name   = ("$nOut" -split "`n")[0].Trim()
    }
} catch {}

if ($detected.Vendor -eq 'CPU') {
    try {
        $gpus = Get-CimInstance Win32_VideoController -EA SilentlyContinue
        $amdGpu = $gpus | Where-Object { $_.Name -match 'AMD|Radeon|RX\s' } |
            Sort-Object @{ Expression = { if ($_.Name -match '\bRX\s*\d|Radeon\s+Pro\b') { 0 } elseif ($_.Name -match 'Vega\s*\d+\s*Graphics|Radeon(?:\(TM\))?\s+Graphics') { 2 } else { 1 } } },
                        @{ Expression = { [long]$_.AdapterRAM }; Descending = $true } | Select-Object -First 1
        if ($amdGpu) {
            $detected.Vendor = 'AMD'
            $detected.Name   = $amdGpu.Name.Trim()
        }
    } catch {}
}

# Mapear deteccao para indice do dropdown
if ($detected.Vendor -eq 'NVIDIA') {
    $n = $detected.Name
    if     ($n -match 'RTX\s*5\d{3}|50\d{2}')                      { $detected.Backend = 1 }
    elseif ($n -match 'RTX\s*4\d{3}|40\d{2}')                      { $detected.Backend = 2 }
    elseif ($n -match 'RTX\s*3\d{3}|30\d{2}')                      { $detected.Backend = 3 }
    elseif ($n -match 'RTX\s*2\d{3}|20\d{2}')                      { $detected.Backend = 4 }
    elseif ($n -match 'GTX\s*16\d{2}')                             { $detected.Backend = 5 }
    elseif ($n -match 'GTX\s*10\d{2}|GTX\s*9\d{2}|GTX\s*7\d{2}')   { $detected.Backend = 6 }
    elseif ($n -match 'RTX\s*A|Quadro|Tesla')                      { $detected.Backend = 7 }
    else                                                            { $detected.Backend = 2 }
} elseif ($detected.Vendor -eq 'AMD') {
    $detected.Backend = 9   # Vulkan default (mais compativel no Windows)
}

function Test-PythonLaunch([string]$exe, [string[]]$prefixArgs = @()) {
    try {
        if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) { return $null }
        $fullExe = (Resolve-Path -LiteralPath $exe).ProviderPath
        if ($fullExe -match '\\Microsoft\\WindowsApps\\python(3)?\.exe$') { return $null }

        $probe = 'import sys, venv, ensurepip; print(sys.executable); print(sys.version.split()[0])'
        $output = & $fullExe @prefixArgs -c $probe 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }

        $lines = @($output | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
        if ($lines.Count -lt 2) { return $null }

        $realExe = $lines[0]
        $version = $lines[-1]
        if (-not (Test-Path -LiteralPath $realExe)) { $realExe = $fullExe }

        $parts = $version -split '\.'
        if ($parts.Count -lt 2 -or $parts[0] -ne '3' -or @('11','12') -notcontains $parts[1]) {
            return $null
        }

        [pscustomobject]@{
            Executable = (Resolve-Path -LiteralPath $realExe).ProviderPath
            Version    = $version
        }
    } catch {
        return $null
    }
}

function Resolve-PythonLaunch {
    $candidates = @()

    foreach ($cmd in @(Get-Command py.exe -All -EA SilentlyContinue)) {
        foreach ($versionArg in @('-3.12', '-3.11')) {
            $candidates += [pscustomobject]@{ Exe = $cmd.Source; Args = @($versionArg) }
        }
    }

    foreach ($name in @('python.exe', 'python3.exe')) {
        foreach ($cmd in @(Get-Command $name -All -EA SilentlyContinue)) {
            $candidates += [pscustomobject]@{ Exe = $cmd.Source; Args = @() }
        }
    }

    $pythonRoots = @($env:LocalAppData, $env:ProgramFiles, ${env:ProgramFiles(x86)}, 'C:\') | Where-Object { $_ }
    foreach ($root in $pythonRoots) {
        foreach ($minor in @('312', '311')) {
            foreach ($relative in @("Programs\Python\Python$minor\python.exe", "Python$minor\python.exe")) {
                $path = Join-Path $root $relative
                if (Test-Path -LiteralPath $path) { $candidates += [pscustomobject]@{ Exe = $path; Args = @() } }
            }
        }
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        $key = "$($candidate.Exe)|$($candidate.Args -join ' ')"
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true

        $resolved = Test-PythonLaunch $candidate.Exe ([string[]]$candidate.Args)
        if ($resolved) { return $resolved }
    }

    return $null
}

function Test-NodeLaunch([string]$exe) {
    try {
        if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) { return $null }
        $fullExe = (Resolve-Path -LiteralPath $exe).ProviderPath
        if ($fullExe -match '\\Microsoft\\WindowsApps\\node\.exe$') { return $null }

        $versionOut = & $fullExe --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $version = (("$versionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        if ($version -notmatch '^v?(\d+)\.') { return $null }
        $major = [int]$matches[1]
        if ($major -lt 18 -or $major -gt 22) { return $null }

        [pscustomobject]@{
            Executable = $fullExe
            Version    = $version
        }
    } catch {
        return $null
    }
}

function Test-NpmLaunch([string]$exe) {
    try {
        if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) { return $null }
        $fullExe = (Resolve-Path -LiteralPath $exe).ProviderPath
        $versionOut = & $fullExe --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $version = (("$versionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        if (-not $version) { return $null }

        [pscustomobject]@{
            Executable = $fullExe
            Version    = $version
        }
    } catch {
        return $null
    }
}

function Resolve-NodeLaunch {
    $nodeCandidates = @()
    foreach ($cmd in @(Get-Command node.exe -All -EA SilentlyContinue)) {
        $nodeCandidates += $cmd.Source
    }

    foreach ($nodeBase in (@($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ })) {
        $path = Join-Path $nodeBase 'nodejs\node.exe'
        if (Test-Path -LiteralPath $path) { $nodeCandidates += $path }
    }

    $npmCandidates = @()
    foreach ($name in @('npm.cmd', 'npm.exe', 'npm')) {
        foreach ($cmd in @(Get-Command $name -All -EA SilentlyContinue)) {
            $npmCandidates += $cmd.Source
        }
    }

    foreach ($nodeCandidate in ($nodeCandidates | Select-Object -Unique)) {
        $nodeDir = Split-Path -Parent $nodeCandidate
        foreach ($npmName in @('npm.cmd', 'npm.exe')) {
            $npmPath = Join-Path $nodeDir $npmName
            if (Test-Path -LiteralPath $npmPath) { $npmCandidates += $npmPath }
        }
    }

    foreach ($nodeCandidate in ($nodeCandidates | Select-Object -Unique)) {
        $node = Test-NodeLaunch $nodeCandidate
        if (-not $node) { continue }

        foreach ($npmCandidate in ($npmCandidates | Select-Object -Unique)) {
            $npm = Test-NpmLaunch $npmCandidate
            if ($npm) {
                return [pscustomobject]@{
                    NodeExecutable = $node.Executable
                    NodeVersion    = $node.Version
                    NpmExecutable  = $npm.Executable
                    NpmVersion     = $npm.Version
                }
            }
        }
    }

    return $null
}

# Pre-checar Python e Node
$pythonLaunch = Resolve-PythonLaunch
$pyOk = $null -ne $pythonLaunch
$PYTHON_EXE = if ($pyOk) { $pythonLaunch.Executable } else { $null }
$pyVer = if ($pyOk) { "Python $($pythonLaunch.Version)" } else { '' }
$nodeLaunch = Resolve-NodeLaunch
$nodeOk = $null -ne $nodeLaunch
$NODE_EXE = if ($nodeOk) { $nodeLaunch.NodeExecutable } else { $null }
$NPM_EXE = if ($nodeOk) { $nodeLaunch.NpmExecutable } else { $null }
$nodeVer = if ($nodeOk) { "$($nodeLaunch.NodeVersion) / npm $($nodeLaunch.NpmVersion)" } else { '' }

if ($detected.Name) {
    $ctl.LblGpu.Text = $detected.Name
} else {
    $ctl.LblGpu.Text = "Nenhuma GPU detectada (modo CPU)"
}
$ctl.CmbBackend.SelectedIndex = $detected.Backend
$ctl.CmbVram.SelectedIndex    = 0
$ctl.ChkInstallPython.IsChecked = (-not $pyOk)
$ctl.ChkDesktopShortcut.IsChecked = $true

# Se faltar Python, o instalador ja deixa a instalacao automatica marcada.
# Node.js pode ser baixado em modo portatil pelo instalador.

# =============================================================================
# Funcoes auxiliares de UI (chamadas via Dispatcher)
# =============================================================================
function UI-Invoke([scriptblock]$sb) {
    $window.Dispatcher.Invoke([Action]$sb)
}

function UI-Log([string]$msg, [string]$kind='info') {
    UI-Invoke {
        $color = switch ($kind) {
            'ok'    { '[OK] ' }
            'warn'  { '[!]  ' }
            'err'   { '[X]  ' }
            'step'  { '==>  ' }
            default { '     ' }
        }
        $line = "$color$msg`r`n"
        $ctl.LogBox.AppendText($line)
        $ctl.LogScroll.ScrollToEnd()
    }
}

function UI-Progress([int]$val, [string]$phase) {
    UI-Invoke {
        $ctl.Progress.Value     = $val
        $ctl.LblProgressTxt.Text = "$val%"
        if ($phase) { $ctl.LblPhase.Text = $phase; $ctl.LblStep.Text = $phase }
    }
}

function ConvertTo-ProcessArgument([string]$arg) {
    if ($null -eq $arg) { throw 'Argumento nulo.' }
    if ($arg.Length -gt 0 -and $arg -notmatch '[\s"]') { return $arg }
    $escaped = [regex]::Replace($arg, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function New-NeveDesktopShortcut([string]$RootPath, [string]$LogPath) {
    try {
        $launcherPath = Join-Path $RootPath 'launchers\iniciar.vbs'
        if (-not (Test-Path -LiteralPath $launcherPath)) { throw "launchers\iniciar.vbs não encontrado em $RootPath" }

        $iconPath = Join-Path $RootPath 'static\static\favicon.ico'
        if (-not (Test-Path -LiteralPath $iconPath)) {
            $iconPath = Join-Path $RootPath 'static\favicon.ico'
        }

        $desktopPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
        if ([string]::IsNullOrWhiteSpace($desktopPath)) {
            $desktopPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
        }
        if ([string]::IsNullOrWhiteSpace($desktopPath) -or -not (Test-Path -LiteralPath $desktopPath)) {
            throw 'Não foi possível localizar a área de trabalho do usuário.'
        }

        $shortcutPath = Join-Path $desktopPath 'NeveAI.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $launcherPath
        $shortcut.Arguments = ''
        $shortcut.WorkingDirectory = $RootPath
        $shortcut.Description = 'NeveAI'
        $shortcut.WindowStyle = 1
        if (Test-Path -LiteralPath $iconPath) { $shortcut.IconLocation = $iconPath }
        $shortcut.Save()

        try { Add-Content -LiteralPath $LogPath -Value "[OK] Atalho criado na área de trabalho: $shortcutPath" -Encoding UTF8 } catch {}
        return $shortcutPath
    } catch {
        try { Add-Content -LiteralPath $LogPath -Value "[!] Não foi possível criar o atalho na área de trabalho: $($_.Exception.Message)" -Encoding UTF8 } catch {}
        return $null
    }
}

# =============================================================================
# Worker - executa em runspace separado
# =============================================================================
$ctl.BtnPrimary.Add_Click({
    if ($ctl.BtnPrimary.Tag -eq 'done') {
        $ctl.DonePanel.Visibility = 'Collapsed'
        $ctl.InstallPanel.Visibility = 'Collapsed'
        $ctl.ConfigPanel.Visibility = 'Visible'
        $ctl.BtnCancel.Visibility = 'Collapsed'
        $ctl.BtnPrimary.Content = 'Instalar'
        $ctl.BtnPrimary.Tag = $null
        $ctl.Progress.Value = 0
        $window.Tag = 'idle'
        return
    }
    $installPython311 = [bool]$ctl.ChkInstallPython.IsChecked
    $createDesktopShortcut = [bool]$ctl.ChkDesktopShortcut.IsChecked
    if ([string]::IsNullOrWhiteSpace($PYTHON_EXE) -or -not (Test-Path -LiteralPath $PYTHON_EXE)) {
        if ($installPython311) {
            $pythonLaunchRetry = Resolve-PythonLaunch
            if ($pythonLaunchRetry) {
                $script:PYTHON_EXE = $pythonLaunchRetry.Executable
                $PYTHON_EXE = $pythonLaunchRetry.Executable
            }
        }
    }
    if (([string]::IsNullOrWhiteSpace($PYTHON_EXE) -or -not (Test-Path -LiteralPath $PYTHON_EXE)) -and -not $installPython311) {
        [System.Windows.MessageBox]::Show(
            "Python 3.11/3.12 válido não encontrado.`n`nMarque `"Instalar Python 3.11 automaticamente`" ou instale o Python manualmente pelo python.org.",
            'NeveAI - Instalador', 'OK', 'Warning') | Out-Null
        return
    }
    # Coleta selecoes
    $backendIdx  = $ctl.CmbBackend.SelectedIndex
    $vramIdx     = $ctl.CmbVram.SelectedIndex

    $vramMap     = @(0,4,6,8,12,16,24,32)
    $vramGb      = $vramMap[$vramIdx]

    # Mapeia indice -> torchIndex / llamaAsset / cudaVer / useOnnxGpu
    $cfg = switch ($backendIdx) {
        0 { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='cpu';        cudaVer='CPU';                 useOnnxGpu=$false; vendor='CPU'    } }
        1 { @{ torchIndex='https://download.pytorch.org/whl/cu128'; llamaAsset='cuda-13.4'; cudaVer='CUDA 13.4 (Blackwell)'; useOnnxGpu=$true;  vendor='NVIDIA' } }
        2 { @{ torchIndex='https://download.pytorch.org/whl/cu128'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.8 (Ada)';        useOnnxGpu=$true;  vendor='NVIDIA' } }
        3 { @{ torchIndex='https://download.pytorch.org/whl/cu128'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.8 (Ampere)';     useOnnxGpu=$true;  vendor='NVIDIA' } }
        4 { @{ torchIndex='https://download.pytorch.org/whl/cu126'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.6 (Turing)';     useOnnxGpu=$true;  vendor='NVIDIA' } }
        5 { @{ torchIndex='https://download.pytorch.org/whl/cu124'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.4 (Turing)';     useOnnxGpu=$true;  vendor='NVIDIA' } }
        6 { @{ torchIndex='https://download.pytorch.org/whl/cu124'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.4 (Pascal)';     useOnnxGpu=$false; vendor='NVIDIA' } }
        7 { @{ torchIndex='https://download.pytorch.org/whl/cu128'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.8 (Profissional)'; useOnnxGpu=$true; vendor='NVIDIA' } }
        8 { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='hip-radeon'; cudaVer='AMD HIP/ROCm (PyTorch CPU no Windows)'; useOnnxGpu=$false; vendor='AMD'    } }
        9 { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='vulkan';         cudaVer='Vulkan';              useOnnxGpu=$false; vendor='AMD'    } }
        default { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='cpu'; cudaVer='CPU'; useOnnxGpu=$false; vendor='CPU' } }
    }

    # Trocar para a tela de instalacao
    $window.Tag = 'installing'
    $script:InstallControl.CancelRequested = $false
    try { $script:InstallControl.Processes.Clear() } catch {}
    try { [System.IO.File]::WriteAllText($STATE_FILE, 'running', [System.Text.UTF8Encoding]::new($false)) } catch {}
    $ctl.ConfigPanel.Visibility = 'Collapsed'
    $ctl.InstallPanel.Visibility = 'Visible'
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnCancel.Visibility = 'Visible'
    $ctl.BtnCancel.IsEnabled  = $true
    $ctl.BtnCancel.Content    = 'Cancelar'
    $ctl.BtnClose.IsEnabled = $false

    Stop-NeveRunningApp 'Instalar'

    # ---- Atalho: se TUDO ja esta instalado, marca como concluido
    $venvOk     = Test-Path $VENV_PY
    $torchOk    = $false
    if ($venvOk) {
        try {
            & $VENV_PY -c "import torch, fastapi, transformers" 2>&1 | Out-Null
            $torchOk = ($LASTEXITCODE -eq 0)
        } catch { $torchOk = $false }
    }
    $llamaOk    = (Get-ChildItem (Join-Path $ROOT 'llamacpp-server\bin') -Filter '*.exe' -EA SilentlyContinue | Measure-Object).Count -gt 0
    $nodeModsOk = Test-Path (Join-Path $ROOT 'node_modules')
    $frontendOk = Test-Path (Join-Path $BACKEND 'neveai\frontend\index.html')
    $envOk      = Test-Path (Join-Path $ROOT '.env')
    $python311Target = Join-Path $env:LocalAppData 'Programs\Python\Python311\python.exe'
    $needsPython311Install = $installPython311 -and -not (Test-PythonLaunch $python311Target)

    if ($venvOk -and $torchOk -and $llamaOk -and $nodeModsOk -and $frontendOk -and $envOk -and -not $needsPython311Install) {
        $ctl.LogBox.AppendText("[OK] Tudo já está instalado. Nada a fazer.`r`n")
        if ($createDesktopShortcut) {
            $shortcutPath = New-NeveDesktopShortcut $ROOT $LOG
            if ($shortcutPath) { $ctl.LogBox.AppendText("[OK] Atalho criado na área de trabalho.`r`n") }
        }
        $ctl.Progress.Value      = 100
        $ctl.LblProgressTxt.Text = '100%'
        $ctl.LblPhase.Text       = 'Concluído'
        $ctl.LblStep.Text        = 'Concluído'

        $summary = @()
        if (-not [string]::IsNullOrWhiteSpace($PYTHON_EXE) -and (Test-Path -LiteralPath $PYTHON_EXE)) {
            $summary += "Python:      $((& $PYTHON_EXE --version 2>&1))"
        } else {
            $summary += "Python:      venv existente"
        }
        if (-not [string]::IsNullOrWhiteSpace($NODE_EXE) -and (Test-Path -LiteralPath $NODE_EXE)) {
            $summary += "Node.js:     $((& $NODE_EXE --version 2>&1))"
        } else {
            $summary += "Node.js:     não verificado"
        }
        try {
            $tOut = & $VENV_PY -c "import torch; v=torch.__version__; cuda='(CUDA '+torch.version.cuda+')' if torch.cuda.is_available() else '(CPU)'; print('PyTorch '+v+' '+cuda)" 2>$null
            if ($tOut) { $summary += "PyTorch:     $tOut" }
        } catch {}
        if ($vramGb -gt 0) { $summary += "VRAM:        ${vramGb} GB ($($detected.Name))" }

        $ctl.InstallPanel.Visibility = 'Collapsed'
        $ctl.DonePanel.Visibility    = 'Visible'
        $ctl.LblDoneTitle.Text       = 'Já está tudo pronto!'
        $ctl.LblDoneSub.Text         = 'Nenhuma pendência detectada. Use iniciar.bat para iniciar o NeveAI.'
        $ctl.LblSummary.Text         = ($summary -join "`r`n")
        $ctl.BtnCancel.Visibility    = 'Collapsed'
        $ctl.BtnPrimary.IsEnabled    = $true
        $ctl.BtnPrimary.Content      = 'Concluir'
        $ctl.BtnPrimary.Tag          = 'done'
        $window.Tag = 'done'
        try { [System.IO.File]::WriteAllText($STATE_FILE, 'done', [System.Text.UTF8Encoding]::new($false)) } catch {}
        return
    }

    # Worker em runspace separado, usando as funcoes UI-* via $window
    $worker = {
        param($cfg, $installPython311, $createDesktopShortcut, $vramGb, $detected, $ROOT, $VENV_DIR, $VENV_PY, $BACKEND, $LOG, $STATE_FILE, $PYTHON_EXE, $NODE_EXE, $NPM_EXE, $INSTALLER_REVISION, $SCRIPT_PATH, $INSTALL_CONTROL)

        # Helpers (definidas dentro do runspace)
        function Log([string]$m, [string]$k='info') {
            $line = if ($null -eq $m) { '' } else { [string]$m }
            try {
                if ($script:Window -and $script:Ctl -and $script:Ctl.LogBox) {
                    $script:Window.Dispatcher.Invoke([Action]{
                        $script:Ctl.LogBox.AppendText("$line`r`n")
                        $script:Ctl.LogScroll.ScrollToEnd()
                    })
                }
            } catch {}
            Add-Content $LOG $line
        }
        function P([int]$v, [string]$phase) {
            try {
                if ($script:Window -and $script:Ctl) {
                    $script:Window.Dispatcher.Invoke([Action]{
                        $script:Ctl.Progress.Value = $v
                        $script:Ctl.LblProgressTxt.Text = "$v%"
                        if ($phase) { $script:Ctl.LblPhase.Text = $phase; $script:Ctl.LblStep.Text = $phase }
                    })
                }
            } catch {}
        }
        function Set-InstallState([string]$state) {
            try { [System.IO.File]::WriteAllText($STATE_FILE, $state, [System.Text.UTF8Encoding]::new($false)) } catch {}
        }
        function New-NeveDesktopShortcut([string]$RootPath) {
            try {
                $launcherPath = Join-Path $RootPath 'launchers\iniciar.vbs'
                if (-not (Test-Path -LiteralPath $launcherPath)) { throw "launchers\iniciar.vbs não encontrado em $RootPath" }

                $iconPath = Join-Path $RootPath 'static\static\favicon.ico'
                if (-not (Test-Path -LiteralPath $iconPath)) {
                    $iconPath = Join-Path $RootPath 'static\favicon.ico'
                }

                $desktopPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
                if ([string]::IsNullOrWhiteSpace($desktopPath)) {
                    $desktopPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
                }
                if ([string]::IsNullOrWhiteSpace($desktopPath) -or -not (Test-Path -LiteralPath $desktopPath)) {
                    throw 'Não foi possível localizar a área de trabalho do usuário.'
                }

                $shortcutPath = Join-Path $desktopPath 'NeveAI.lnk'
                $shell = New-Object -ComObject WScript.Shell
                $shortcut = $shell.CreateShortcut($shortcutPath)
                $shortcut.TargetPath = $launcherPath
                $shortcut.Arguments = ''
                $shortcut.WorkingDirectory = $RootPath
                $shortcut.Description = 'NeveAI'
                $shortcut.WindowStyle = 1
                if (Test-Path -LiteralPath $iconPath) { $shortcut.IconLocation = $iconPath }
                $shortcut.Save()

                Log "[OK] Atalho criado na área de trabalho: $shortcutPath"
                return $shortcutPath
            } catch {
                Log "[!] Não foi possível criar o atalho na área de trabalho: $($_.Exception.Message)" 'warn'
                return $null
            }
        }
        function Test-InstallCancelled {
            if ($INSTALL_CONTROL -and $INSTALL_CONTROL.CancelRequested) {
                Set-InstallState 'cancelled'
                throw [System.OperationCanceledException]::new('Instalação cancelada pelo usuário.')
            }
        }
        function Stop-ProcessTree([int]$ProcessId) {
            try {
                $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -EA SilentlyContinue)
                foreach ($child in $children) { Stop-ProcessTree ([int]$child.ProcessId) }
            } catch {}
            try {
                $proc = Get-Process -Id $ProcessId -EA SilentlyContinue
                if ($proc -and -not $proc.HasExited) { Stop-Process -Id $ProcessId -Force -EA SilentlyContinue }
            } catch {}
        }
        function ConvertTo-ProcessArgument([string]$arg) {
            if ($null -eq $arg) { throw 'Argumento nulo.' }
            if ($arg.Length -gt 0 -and $arg -notmatch '[\s"]') { return $arg }
            $escaped = [regex]::Replace($arg, '(\\*)"', '$1$1\"')
            $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
            return '"' + $escaped + '"'
        }
        function Run-NoPipe([string]$exe, [string[]]$argv, [string]$desc) {
            Test-InstallCancelled
            Log "==> $desc"
            if ([string]::IsNullOrWhiteSpace($exe)) { throw "Executável vazio ao executar '$desc'." }

            $safeArgs = @()
            foreach ($a in @($argv)) {
                if ($null -eq $a) { throw "Argumento nulo ao executar '$desc' com '$exe'." }
                $safeArgs += [string]$a
            }

            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $exe
            $psi.Arguments = (($safeArgs | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
            $psi.WorkingDirectory = $ROOT
            $psi.RedirectStandardOutput = $false
            $psi.RedirectStandardError = $false
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow = $true
            if ($script:FrontendNodeDir) {
                try {
                    $currentPath = $psi.EnvironmentVariables['PATH']
                    if ([string]::IsNullOrWhiteSpace($currentPath)) { $currentPath = $env:PATH }
                    $psi.EnvironmentVariables['PATH'] = "$script:FrontendNodeDir;$currentPath"
                } catch {
                    Log "[!] Não foi possível priorizar Node.js portátil para '$desc': $($_.Exception.Message)" 'warn'
                }
            }
            if ($script:CleanPipProcessEnv) {
                try {
                    $cleanVenvScripts = Join-Path $VENV_DIR 'Scripts'
                    $currentPath = $psi.EnvironmentVariables['PATH']
                    if ([string]::IsNullOrWhiteSpace($currentPath)) { $currentPath = $env:PATH }
                    if (Test-Path -LiteralPath $cleanVenvScripts) { $psi.EnvironmentVariables['PATH'] = "$cleanVenvScripts;$currentPath" }
                    if (Test-Path -LiteralPath $VENV_DIR) { $psi.EnvironmentVariables['VIRTUAL_ENV'] = $VENV_DIR }
                    $psi.EnvironmentVariables['PIP_CONFIG_FILE'] = 'NUL'
                    $psi.EnvironmentVariables['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
                    $psi.EnvironmentVariables['PIP_NO_INPUT'] = '1'
                    $psi.EnvironmentVariables['PIP_DEFAULT_TIMEOUT'] = '60'
                    $psi.EnvironmentVariables['PYTHONUNBUFFERED'] = '1'
                    foreach ($envName in @('PIP_REQUIRE_VIRTUALENV','PYTHONHOME','PYTHONPATH')) {
                        if ($psi.EnvironmentVariables.ContainsKey($envName)) { [void]$psi.EnvironmentVariables.Remove($envName) }
                    }
                } catch {
                    Log "[!] Não foi possível limpar todas as variáveis do processo para '$desc': $($_.Exception.Message)" 'warn'
                }
            }
            Log ("CMD: {0} {1}" -f $exe, ($safeArgs -join ' '))

            $p = $null
            try {
                $p = New-Object System.Diagnostics.Process
                $p.StartInfo = $psi
                [void]$p.Start()
                if ($INSTALL_CONTROL -and $INSTALL_CONTROL.Processes) { [void]$INSTALL_CONTROL.Processes.Add($p) }
                Log ("[pid {0}] {1} iniciado (sem pipes de stdout/stderr para evitar fechamento do WPF)" -f $p.Id, $desc)
            } catch {
                throw "Falha ao iniciar '$exe' para '$desc': $($_.Exception.Message)"
            }
            if ($null -eq $p) { throw "Falha ao iniciar '$exe' para '$desc': Process.Start retornou nulo." }

            try {
                $startedAt = Get-Date
                $lastHeartbeat = $startedAt
                while (-not $p.WaitForExit(1000)) {
                    if ($INSTALL_CONTROL -and $INSTALL_CONTROL.CancelRequested) {
                        Log ("[!] Cancelando {0} (pid {1})." -f $desc, $p.Id) 'warn'
                        Stop-ProcessTree ([int]$p.Id)
                        throw [System.OperationCanceledException]::new('Instalação cancelada pelo usuário.')
                    }
                    $now = Get-Date
                    if (($now - $lastHeartbeat).TotalSeconds -ge 10) {
                        $elapsedSec = [math]::Floor(($now - $startedAt).TotalSeconds)
                        Log ("... {0} ainda em andamento ({1}s)." -f $desc, $elapsedSec)
                        $lastHeartbeat = $now
                    }
                }
                $p.WaitForExit()
                $elapsed = (Get-Date) - $startedAt
                Log ("[exit {0}] {1} finalizado em {2:mm\:ss}" -f $p.ExitCode, $desc, $elapsed)
                return $p.ExitCode
            } finally {
                try { if ($INSTALL_CONTROL -and $INSTALL_CONTROL.Processes -and $p) { [void]$INSTALL_CONTROL.Processes.Remove($p) } } catch {}
                try { $p.Dispose() } catch {}
            }
        }
        function Run([string]$exe, [string[]]$argv, [string]$desc, [int]$timeoutSeconds = 3600) {
            return Run-NoPipe $exe $argv $desc
        }
        function Save-RemoteFile([string]$Url, [string]$Destination, [int]$TimeoutSec = 300) {
            Test-InstallCancelled
            $curl = Get-Command curl.exe -EA SilentlyContinue | Select-Object -First 1
            if ($curl) {
                try {
                    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Force -EA SilentlyContinue }
                    $rc = Run-NoPipe $curl.Source @(
                        '-L', '--fail', '--silent', '--show-error', '--compressed',
                        '--retry', '3', '--retry-delay', '2', '--connect-timeout', '30',
                        '--max-time', [string]$TimeoutSec,
                        '--output', $Destination, $Url
                    ) "baixar $Url"
                    if ($rc -eq 0 -and (Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -gt 0) {
                        return
                    }
                    Log "[!] curl não concluiu o download (exit $rc); usando fallback do PowerShell." 'warn'
                } catch {
                    Log "[!] curl falhou: $($_.Exception.Message); usando fallback do PowerShell." 'warn'
                }
            }

            if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Force -EA SilentlyContinue }
            Invoke-WebRequest $Url -OutFile $Destination -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Installer/3.0' } -TimeoutSec $TimeoutSec
            if (-not (Test-Path -LiteralPath $Destination) -or (Get-Item -LiteralPath $Destination).Length -le 0) {
                throw "Download vazio ou ausente: $Url"
            }
        }
        function Test-InstallerPythonLaunch([string]$exe, [string[]]$prefixArgs = @()) {
            try {
                if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) { return $null }
                $fullExe = (Resolve-Path -LiteralPath $exe).ProviderPath
                if ($fullExe -match '\\Microsoft\\WindowsApps\\python(3)?\.exe$') { return $null }

                $probe = 'import sys, venv, ensurepip; print(sys.executable); print(sys.version.split()[0])'
                $output = & $fullExe @prefixArgs -c $probe 2>&1
                if ($LASTEXITCODE -ne 0) { return $null }

                $lines = @($output | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
                if ($lines.Count -lt 2) { return $null }

                $realExe = $lines[0]
                $version = $lines[-1]
                if (-not (Test-Path -LiteralPath $realExe)) { $realExe = $fullExe }

                $parts = $version -split '\.'
                if ($parts.Count -lt 2 -or $parts[0] -ne '3' -or @('11','12') -notcontains $parts[1]) {
                    return $null
                }

                return [pscustomobject]@{
                    Executable = (Resolve-Path -LiteralPath $realExe).ProviderPath
                    Version    = $version
                }
            } catch {
                return $null
            }
        }
        function Resolve-InstallerPythonLaunch([string]$PreferredExe = $null, [switch]$PreferPython311) {
            $candidates = @()

            if ($PreferredExe) { $candidates += [pscustomobject]@{ Exe = $PreferredExe; Args = @() } }

            $localPython311 = Join-Path $env:LocalAppData 'Programs\Python\Python311\python.exe'
            $localPython312 = Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe'
            if ($PreferPython311) {
                if (Test-Path -LiteralPath $localPython311) { $candidates += [pscustomobject]@{ Exe = $localPython311; Args = @() } }
                if (Test-Path -LiteralPath $localPython312) { $candidates += [pscustomobject]@{ Exe = $localPython312; Args = @() } }
            } else {
                if (Test-Path -LiteralPath $localPython312) { $candidates += [pscustomobject]@{ Exe = $localPython312; Args = @() } }
                if (Test-Path -LiteralPath $localPython311) { $candidates += [pscustomobject]@{ Exe = $localPython311; Args = @() } }
            }

            foreach ($cmd in @(Get-Command py.exe -All -EA SilentlyContinue)) {
                $versionArgs = if ($PreferPython311) { @('-3.11', '-3.12') } else { @('-3.12', '-3.11') }
                foreach ($versionArg in $versionArgs) {
                    $candidates += [pscustomobject]@{ Exe = $cmd.Source; Args = @($versionArg) }
                }
            }

            foreach ($name in @('python.exe', 'python3.exe')) {
                foreach ($cmd in @(Get-Command $name -All -EA SilentlyContinue)) {
                    $candidates += [pscustomobject]@{ Exe = $cmd.Source; Args = @() }
                }
            }

            $pythonRoots = @($env:LocalAppData, $env:ProgramFiles, ${env:ProgramFiles(x86)}, 'C:\') | Where-Object { $_ }
            $minorOrder = if ($PreferPython311) { @('311', '312') } else { @('312', '311') }
            foreach ($root in $pythonRoots) {
                foreach ($minor in $minorOrder) {
                    foreach ($relative in @("Programs\Python\Python$minor\python.exe", "Python$minor\python.exe")) {
                        $path = Join-Path $root $relative
                        if (Test-Path -LiteralPath $path) { $candidates += [pscustomobject]@{ Exe = $path; Args = @() } }
                    }
                }
            }

            $seen = @{}
            foreach ($candidate in $candidates) {
                $key = "$($candidate.Exe)|$($candidate.Args -join ' ')"
                if ($seen.ContainsKey($key)) { continue }
                $seen[$key] = $true

                $resolved = Test-InstallerPythonLaunch $candidate.Exe ([string[]]$candidate.Args)
                if ($resolved) { return $resolved }
            }

            return $null
        }
        function Install-Python311IfNeeded([bool]$ShouldInstall) {
            $targetDir = Join-Path $env:LocalAppData 'Programs\Python\Python311'
            $targetPython = Join-Path $targetDir 'python.exe'

            if (-not $ShouldInstall) {
                $resolved = Resolve-InstallerPythonLaunch $PYTHON_EXE
                if ($resolved) { return $resolved }
                throw "Python 3.11/3.12 válido não encontrado. Marque a opção de instalar Python 3.11 automaticamente ou instale pelo python.org."
            }

            Set-InstallState 'installing_python311'
            P 5 'Instalando Python 3.11'

            $existing = Test-InstallerPythonLaunch $targetPython
            if ($existing) {
                $pythonDir = Split-Path -Parent $existing.Executable
                $scriptsDir = Join-Path $pythonDir 'Scripts'
                $env:PATH = "$pythonDir;$scriptsDir;$env:PATH"
                Log "[OK] Python 3.11 já disponível: $($existing.Executable)"
                return $existing
            }

            $installerUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
            $installerPath = Join-Path $env:TEMP 'neve_python_3.11.9_amd64.exe'

            try {
                if (Test-Path -LiteralPath $installerPath) { Remove-Item -LiteralPath $installerPath -Force -EA SilentlyContinue }
                Log "==> Baixando Python 3.11.9 oficial: $installerUrl"
                Save-RemoteFile $installerUrl $installerPath 300
                if (-not (Test-Path -LiteralPath $installerPath)) { throw 'O instalador do Python não foi baixado.' }

                $targetParent = Split-Path -Parent $targetDir
                if (-not (Test-Path -LiteralPath $targetParent)) { New-Item -ItemType Directory -Path $targetParent -Force | Out-Null }

                $args = @(
                    '/quiet',
                    'InstallAllUsers=0',
                    'PrependPath=1',
                    'Include_launcher=1',
                    'InstallLauncherAllUsers=0',
                    'Include_pip=1',
                    'Include_tcltk=0',
                    'Include_test=0',
                    'Include_doc=0',
                    'Include_debug=0',
                    'Shortcuts=0',
                    'AssociateFiles=0',
                    'SimpleInstall=1',
                    "TargetDir=$targetDir"
                )
                $rc = Run-NoPipe $installerPath $args 'Instalando Python 3.11 silenciosamente'
                if ($rc -notin @(0, 3010)) { throw "Falha ao instalar Python 3.11 (exit $rc)." }

                $pythonDir = Split-Path -Parent $targetPython
                $scriptsDir = Join-Path $pythonDir 'Scripts'
                $env:PATH = "$pythonDir;$scriptsDir;$env:PATH"

                $resolved = Resolve-InstallerPythonLaunch $targetPython -PreferPython311
                if (-not $resolved) { $resolved = Resolve-InstallerPythonLaunch $PYTHON_EXE -PreferPython311 }
                if (-not $resolved) { throw 'Python 3.11 foi instalado, mas não respondeu na validação com venv/ensurepip.' }

                Log "[OK] Python pronto: $($resolved.Executable) ($($resolved.Version))"
                return $resolved
            } finally {
                try { if (Test-Path -LiteralPath $installerPath) { Remove-Item -LiteralPath $installerPath -Force -EA SilentlyContinue } } catch {}
            }
        }
        function Get-NodeMajorFromVersion([string]$version) {
            if ([string]::IsNullOrWhiteSpace($version)) { return -1 }
            if ($version -notmatch '^v?(\d+)\.') { return -1 }
            return [int]$matches[1]
        }
        function Test-FrontendNodePair([string]$nodeExe, [string]$npmExe) {
            try {
                if ([string]::IsNullOrWhiteSpace($nodeExe) -or -not (Test-Path -LiteralPath $nodeExe)) { return $null }
                if ([string]::IsNullOrWhiteSpace($npmExe) -or -not (Test-Path -LiteralPath $npmExe)) { return $null }

                $nodePath = (Resolve-Path -LiteralPath $nodeExe).ProviderPath
                if ($nodePath -match '\\Microsoft\\WindowsApps\\node\.exe$') { return $null }

                $nodeVersionOut = & $nodePath --version 2>&1
                if ($LASTEXITCODE -ne 0) { return $null }
                $nodeVersion = (("$nodeVersionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
                $nodeMajor = Get-NodeMajorFromVersion $nodeVersion
                if ($nodeMajor -lt 18 -or $nodeMajor -gt 22) { return $null }

                $npmPath = (Resolve-Path -LiteralPath $npmExe).ProviderPath
                $npmCliPath = Join-Path (Split-Path -Parent $nodePath) 'node_modules\npm\bin\npm-cli.js'
                if (Test-Path -LiteralPath $npmCliPath) {
                    $npmVersionOut = & $nodePath $npmCliPath --version 2>&1
                } else {
                    $npmVersionOut = & $npmPath --version 2>&1
                }
                if ($LASTEXITCODE -ne 0) { return $null }
                $npmVersion = (("$npmVersionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
                if (-not $npmVersion) { return $null }

                return [pscustomobject]@{
                    NodeExecutable = $nodePath
                    NodeVersion    = $nodeVersion
                    NpmExecutable  = $npmPath
                    NpmVersion     = $npmVersion
                    NodeDir        = Split-Path -Parent $nodePath
                }
            } catch {
                return $null
            }
        }
        function Resolve-FrontendNodeLaunch {
            $nodeCandidates = @()
            $portableRoots = @(
                (Join-Path $ROOT 'tools'),
                (Join-Path $env:LocalAppData 'NeveAI\tools'),
                (Join-Path $env:TEMP 'NeveAI\tools')
            ) | Select-Object -Unique
            foreach ($portableRoot in $portableRoots) {
                $portableNode = Join-Path $portableRoot 'nodejs\node.exe'
                if (Test-Path -LiteralPath $portableNode) { $nodeCandidates += $portableNode }
                if (Test-Path -LiteralPath $portableRoot) {
                    $nodeCandidates += @(Get-ChildItem -LiteralPath $portableRoot -Directory -Filter 'nodejs-*' -EA SilentlyContinue |
                        ForEach-Object { Join-Path $_.FullName 'node.exe' } |
                        Where-Object { Test-Path -LiteralPath $_ })
                }
            }
            if ($NODE_EXE) { $nodeCandidates += $NODE_EXE }

            foreach ($cmd in @(Get-Command node.exe -All -EA SilentlyContinue)) {
                $nodeCandidates += $cmd.Source
            }
            foreach ($nodeBase in (@($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ })) {
                $path = Join-Path $nodeBase 'nodejs\node.exe'
                if (Test-Path -LiteralPath $path) { $nodeCandidates += $path }
            }

            foreach ($nodeCandidate in ($nodeCandidates | Select-Object -Unique)) {
                $nodeDir = Split-Path -Parent $nodeCandidate
                foreach ($npmName in @('npm.cmd','npm.exe')) {
                    $npmPath = Join-Path $nodeDir $npmName
                    $pair = Test-FrontendNodePair $nodeCandidate $npmPath
                    if ($pair) { return $pair }
                }
            }

            return $null
        }
        function Install-PortableNode22 {
            Set-InstallState 'installing_portable_node22'
            P 83 'Preparando Node.js 22 portátil'
            $toolsDir = Join-Path $ROOT 'tools'
            $nodeDir = Join-Path $toolsDir 'nodejs'
            $existing = Test-FrontendNodePair (Join-Path $nodeDir 'node.exe') (Join-Path $nodeDir 'npm.cmd')
            if ($existing) {
                Log "[OK] Node.js portátil já disponível: $($existing.NodeVersion) / npm $($existing.NpmVersion)"
                return $existing
            }

            if (-not (Test-Path -LiteralPath $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }
            Log '==> Baixando Node.js 22 LTS portátil porque o Node do sistema está ausente ou fora da faixa suportada (18-22)'

            $release = $null
            try {
                $index = Invoke-RestMethod 'https://nodejs.org/dist/index.json' -Headers @{ 'User-Agent' = 'Neve-Installer/3.0' } -TimeoutSec 60
                $release = $index | Where-Object { $_.version -match '^v22\.' -and $_.files -contains 'win-x64-zip' } | Select-Object -First 1
            } catch {
                Log "[!] Falha ao consultar versões do Node.js: $($_.Exception.Message)" 'warn'
            }
            if (-not $release) {
                $release = [pscustomobject]@{ version = 'v22.23.3'; files = @('win-x64-zip') }
                Log '[!] Índice do Node.js indisponível; usando a versão LTS de fallback v22.23.3.' 'warn'
            }

            $version = [string]$release.version
            $url = "https://nodejs.org/dist/$version/node-$version-win-x64.zip"
            $zipPath = Join-Path $env:TEMP "neve_node_$version-$([guid]::NewGuid().ToString('N')).zip"
            $stageParent = Join-Path $env:TEMP "neve_node_stage_$([guid]::NewGuid().ToString('N'))"
            try {
                if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue }
                New-Item -ItemType Directory -Path $stageParent -Force | Out-Null
                Log "==> Baixando $url"
                Save-RemoteFile $url $zipPath 300
                Expand-Archive $zipPath -DestinationPath $stageParent -Force
                $extracted = Get-ChildItem -LiteralPath $stageParent -Directory | Select-Object -First 1
                if (-not $extracted) { throw 'Arquivo do Node.js não extraiu a pasta esperada.' }
                $stagedPair = Test-FrontendNodePair (Join-Path $extracted.FullName 'node.exe') (Join-Path $extracted.FullName 'npm.cmd')
                if (-not $stagedPair) { throw 'Node.js portátil extraído não passou na validação.' }

                $installParents = @(
                    $toolsDir,
                    (Join-Path $env:LocalAppData 'NeveAI\tools'),
                    (Join-Path $env:TEMP 'NeveAI\tools')
                ) | Select-Object -Unique
                $installErrors = @()
                foreach ($installParent in $installParents) {
                    $candidateDir = Join-Path $installParent 'nodejs'
                    $createdCandidate = $false
                    try {
                        if (-not (Test-Path -LiteralPath $installParent)) {
                            New-Item -ItemType Directory -Path $installParent -Force -EA Stop | Out-Null
                        }
                        $candidateExisting = Test-FrontendNodePair (Join-Path $candidateDir 'node.exe') (Join-Path $candidateDir 'npm.cmd')
                        if ($candidateExisting) { return $candidateExisting }
                        if (Test-Path -LiteralPath $candidateDir) {
                            try { Remove-Item -LiteralPath $candidateDir -Recurse -Force -EA Stop } catch {}
                            if (Test-Path -LiteralPath $candidateDir) {
                                $candidateDir = Join-Path $installParent ("nodejs-{0}-{1}" -f $version.TrimStart('v'), [guid]::NewGuid().ToString('N').Substring(0, 8))
                            }
                        }
                        $createdCandidate = $true
                        Copy-Item -LiteralPath $extracted.FullName -Destination $candidateDir -Recurse -Force -EA Stop
                        Get-ChildItem -LiteralPath $candidateDir -Recurse -File -EA SilentlyContinue | Unblock-File -EA SilentlyContinue

                        $pair = $null
                        for ($attempt = 1; $attempt -le 10 -and -not $pair; $attempt++) {
                            $pair = Test-FrontendNodePair (Join-Path $candidateDir 'node.exe') (Join-Path $candidateDir 'npm.cmd')
                            if (-not $pair) { Start-Sleep -Milliseconds 500 }
                        }
                        if (-not $pair) { throw 'Os arquivos foram copiados, mas Node.js/npm não responderam.' }
                        if ($candidateDir -ne $nodeDir) {
                            Log "[!] Node.js portátil instalado no fallback: $candidateDir" 'warn'
                        }
                        Log "[OK] Node.js portátil pronto: $($pair.NodeVersion) / npm $($pair.NpmVersion)"
                        return $pair
                    } catch {
                        $installErrors += "$candidateDir -> $($_.Exception.Message)"
                        Log "[!] Não foi possível preparar Node.js em '$candidateDir': $($_.Exception.Message)" 'warn'
                        if ($createdCandidate) {
                            try { Remove-Item -LiteralPath $candidateDir -Recurse -Force -EA SilentlyContinue } catch {}
                        }
                    }
                }
                throw "Não foi possível preparar Node.js portátil em nenhum local permitido. $($installErrors -join ' | ')"
            } finally {
                try { if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue } } catch {}
                try { if (Test-Path -LiteralPath $stageParent) { Remove-Item -LiteralPath $stageParent -Recurse -Force -EA SilentlyContinue } } catch {}
            }
        }
        function Normalize-PythonPackageName([string]$name) {
            if ([string]::IsNullOrWhiteSpace($name)) { return '' }
            return (([string]$name).Trim().ToLowerInvariant() -replace '[-_.]+','-')
        }
        function Get-RequirementPackageName([string]$spec) {
            if ([string]::IsNullOrWhiteSpace($spec)) { return '' }
            $name = ([string]$spec).Trim()
            $name = ($name -split ';', 2)[0].Trim()
            if ($name.StartsWith('-')) { return '' }
            if ($name -match '^([^\s@]+)\s*@') { $name = $matches[1] }
            $name = ($name -split '(===|==|~=|!=|>=|<=|>|<)', 2)[0].Trim()
            $name = ($name -replace '\[.*?\]', '').Trim()
            return $name
        }
        function Get-UnpinnedRequirementSpec([string]$spec) {
            if ([string]::IsNullOrWhiteSpace($spec)) { return '' }
            $text = ([string]$spec).Trim()
            if (-not $text -or $text.StartsWith('-')) { return '' }

            $parts = $text -split ';', 2
            $requirement = $parts[0].Trim()
            if (-not $requirement -or $requirement.StartsWith('-')) { return '' }
            if ($requirement -match '\s@\s') { return '' }

            $base = ($requirement -split '\s*(===|==|~=|!=|>=|<=|>|<)\s*', 2)[0].Trim()
            if (-not $base -or $base -eq $requirement) { return '' }

            if ($parts.Count -gt 1) {
                $marker = $parts[1].Trim()
                if ($marker) { return ("{0}; {1}" -f $base, $marker) }
            }
            return $base
        }
        function Get-RequirementEntries([string]$path) {
            $entries = @()
            $lines = Get-Content -LiteralPath $path
            for ($i = 0; $i -lt $lines.Count; $i++) {
                $rawLine = ([string]$lines[$i]).Trim()
                $isOptional = $rawLine -match '#\s*optional\b'
                $line = $rawLine
                if (-not $line -or $line.StartsWith('#')) { continue }
                $line = [regex]::Replace($line, '\s+#.*$', '').Trim()
                if (-not $line) { continue }
                $entries += [pscustomobject]@{
                    Line = $i + 1
                    Spec = $line
                    Package = Get-RequirementPackageName $line
                    Optional = $isOptional
                }
            }
            return $entries
        }

        try {
            Test-InstallCancelled
            Set-Location -LiteralPath $ROOT
            Log "[OK] Instalador revisão: $INSTALLER_REVISION"
            Log "[OK] Script em execução: $SCRIPT_PATH"
            Log "[OK] Pasta de instalação: $ROOT"

            # ---- 1. Python opcional
            $pythonLaunchWorker = Install-Python311IfNeeded ([bool]$installPython311)
            $PYTHON_EXE = $pythonLaunchWorker.Executable

            # ---- 2. Estrutura de pastas
            P 8 'Criando estrutura de pastas'
            foreach ($d in @('logs','logs\webview2','logs\browser-app','models','mmproj',
                             'backend\data','backend\data\uploads','backend\data\vector_db',
                             'backend\data\cache','backend\data\cache\music_generation','backend\data\cache\video_generation','backend\data\tools',
                             'backend\neveai\frontend')) {
                $p = Join-Path $ROOT $d
                if (-not (Test-Path $p)) { New-Item $p -ItemType Directory -Force | Out-Null }
            }
            Log "[OK] Pastas garantidas"

            $requiredAppFiles = @(
                'package.json',
                'backend\requirements-runtime.txt',
                'backend\neveai\main.py',
                'backend\neveai\routers\music_generation.py',
                'backend\neveai\routers\video_generation.py',
                'backend\neveai\models\users.py',
                'backend\neveai\models\models.py',
                'backend\neveai\utils\auth.py'
            )
            $missingAppFiles = @()
            foreach ($relativeAppFile in $requiredAppFiles) {
                if (-not (Test-Path -LiteralPath (Join-Path $ROOT $relativeAppFile))) { $missingAppFiles += $relativeAppFile }
            }
            if ($missingAppFiles.Count -gt 0) {
                throw "Pacote local incompleto; faltam arquivos essenciais: $($missingAppFiles -join ', '). Baixe o release atualizado ou use a aba Atualizar para reparar."
            }
            Log "[OK] Arquivos essenciais do app validados"

            # ---- 3. .env padrao
            $envPath = Join-Path $ROOT '.env'
            if (-not (Test-Path -LiteralPath $envPath)) {
                $envText = @"
VITE_RELATIVE_CONFIG=True
VITE_NEVEAI_BACKEND_URL=http://localhost:8080
ENV=dev
PORT=8080
NEVE_SECRET_KEY=troque-esta-chave-por-algo-seguro
NEVE_AUTH=False
NEVE_NAME=NeveAI
ENABLE_OLLAMA_API=False
ENABLE_OPENAI_API=False
ENABLE_WEB_SEARCH=False
ENABLE_IMAGE_GENERATION=False
ENABLE_VIDEO_GENERATION=True
ENABLE_WEBSOCKET_SUPPORT=True
ENABLE_COMMUNITY_SHARING=False
ENABLE_MESSAGE_RATING=False
BYPASS_MODEL_ACCESS_CONTROL=True
ENABLE_SIGNUP=True
ENABLE_LOGIN_FORM=True
SAFE_MODE=False
CORS_ALLOW_ORIGIN=http://localhost:8080
USER_AGENT=NeveAI
"@
                [System.IO.File]::WriteAllText($envPath, $envText, [System.Text.UTF8Encoding]::new($false))
                Log "[OK] .env criado"
            } else {
                Log "[…] .env preservado"
            }

            # ---- 4. llama.cpp
            P 12 'Baixando llama.cpp'
            $llamaDir = Join-Path $ROOT 'llamacpp-server\bin'
            if (-not (Test-Path (Split-Path $llamaDir -Parent))) { New-Item (Split-Path $llamaDir -Parent) -ItemType Directory | Out-Null }
            if (-not (Test-Path $llamaDir)) { New-Item $llamaDir -ItemType Directory | Out-Null }
            $llamaServer = Join-Path $llamaDir 'llama-server.exe'
            $llamaVersionPath = Join-Path (Split-Path $llamaDir -Parent) 'version.txt'
            $llamaInstalled = $false
            try {
                $attempts = @($cfg.llamaAsset, 'cpu') | Where-Object { $_ } | Select-Object -Unique
                $releases = @((Invoke-RestMethod 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30' -Headers @{ 'User-Agent' = 'Neve-Installer/3.0'; 'Accept' = 'application/vnd.github+json' } -TimeoutSec 60))
                $rel = $releases | Where-Object {
                    if ($_.draft -or -not $_.tag_name) { return $false }
                    $releaseTag = [regex]::Escape([string]$_.tag_name)
                    foreach ($backendName in $attempts) {
                        $backendEsc = [regex]::Escape([string]$backendName)
                        if ($_.assets | Where-Object { $_.name -match "^llama-$releaseTag-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1) {
                            return $true
                        }
                    }
                    return $false
                } | Select-Object -First 1
                if (-not $rel) { throw 'Nenhuma release recente do llama.cpp contém binários Windows compatíveis.' }
                $tag = $rel.tag_name
                if (-not $tag) { throw 'Release do llama.cpp sem tag_name.' }

                if ((Test-Path -LiteralPath $llamaServer) -and (Test-Path -LiteralPath $llamaVersionPath)) {
                    $installedLlama = @(Get-Content -LiteralPath $llamaVersionPath -EA SilentlyContinue)
                    if ($installedLlama.Count -ge 2 -and $installedLlama[0] -eq $tag -and $installedLlama[1] -eq $cfg.llamaAsset) {
                        Log "[OK] llama.cpp $tag ($($cfg.llamaAsset)) já instalado; pulando download"
                        $llamaInstalled = $true
                    }
                }

                $attempts = if ($llamaInstalled) { @() } else { $attempts }
                foreach ($assetName in $attempts) {
                    $tmpFiles = @(); $stageDir = $null; $backupDir = $null
                    try {
                        $binName = "llama-$tag-bin-win-$assetName-x64.zip"
                        $binObj  = $rel.assets | Where-Object { $_.name -eq $binName } | Select-Object -First 1
                        if (-not $binObj) { throw "Asset $binName não encontrado." }

                        $stageDir = Join-Path $env:TEMP "neve_llama_stage_$([guid]::NewGuid().ToString('N'))"
                        New-Item $stageDir -ItemType Directory -Force | Out-Null

                        $sizeMB = [math]::Round($binObj.size/1MB,0)
                        Log "==> Baixando $binName ($sizeMB MB)"
                        $tmpBin = Join-Path $env:TEMP "neve_llama_bin_$([guid]::NewGuid().ToString('N')).zip"
                        $tmpFiles += $tmpBin
                        Save-RemoteFile $binObj.browser_download_url $tmpBin 300
                        Expand-Archive $tmpBin -DestinationPath $stageDir -Force

                        if ($assetName -match '^cuda-') {
                            P 18 'Baixando CUDA Runtime'
                            $dllName = "cudart-llama-bin-win-$assetName-x64.zip"
                            $dllObj  = $rel.assets | Where-Object { $_.name -eq $dllName } | Select-Object -First 1
                            if (-not $dllObj) { throw "Runtime CUDA $dllName não encontrado." }
                            $sizeMB = [math]::Round($dllObj.size/1MB,0)
                            Log "==> Baixando $dllName ($sizeMB MB)"
                            $tmpDll = Join-Path $env:TEMP "neve_cudart_$([guid]::NewGuid().ToString('N')).zip"
                            $tmpFiles += $tmpDll
                            Save-RemoteFile $dllObj.browser_download_url $tmpDll 300
                            Expand-Archive $tmpDll -DestinationPath $stageDir -Force
                        }

                        $serverExe = Get-ChildItem $stageDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1
                        if (-not $serverExe) { throw "O pacote $binName não contém llama-server.exe." }
                        $stagedFiles = @(Get-ChildItem $stageDir -Recurse -File)
                        if ($stagedFiles.Count -eq 0) { throw "O pacote $binName não extraiu arquivos." }

                        $backupDir = Join-Path $env:TEMP "neve_llama_backup_$([guid]::NewGuid().ToString('N'))"
                        New-Item $backupDir -ItemType Directory -Force | Out-Null
                        Get-ChildItem $llamaDir -Force -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $backupDir -Recurse -Force }

                        try {
                            Get-Process llama-server -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
                            Get-ChildItem $llamaDir -File -EA SilentlyContinue | Where-Object { $_.Extension -in '.exe','.dll','.pdb' } | Remove-Item -Force -EA Stop
                            foreach ($file in $stagedFiles) { Copy-Item $file.FullName $llamaDir -Force -EA Stop }
                            if (-not (Test-Path -LiteralPath $llamaServer)) { throw 'llama-server.exe não ficou disponível após a cópia.' }
                        } catch {
                            $applyError = $_
                            Log "[!] Falha ao aplicar llama.cpp; restaurando backup: $applyError" 'warn'
                            try {
                                Get-ChildItem $llamaDir -Force -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue
                                Get-ChildItem $backupDir -Force -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $llamaDir -Recurse -Force }
                            } catch {}
                            throw $applyError
                        }

                        Set-Content -Path (Join-Path (Split-Path $llamaDir -Parent) 'version.txt') -Value @($tag, $assetName, $binName) -Encoding UTF8
                        Log "[OK] llama.cpp $tag instalado ($assetName)"
                        $llamaInstalled = $true
                        break
                    } catch {
                        if ($assetName -ne 'cpu') { Log "[!] Falha ao instalar llama.cpp ${assetName}: $_. Tentando CPU." 'warn' } else { Log "[!] Falha ao instalar llama.cpp CPU: $_" 'warn' }
                    } finally {
                        foreach ($tmp in $tmpFiles) { try { Remove-Item $tmp -Force -EA SilentlyContinue } catch {} }
                        if ($stageDir) { try { Remove-Item $stageDir -Recurse -Force -EA SilentlyContinue } catch {} }
                        if ($backupDir) { try { Remove-Item $backupDir -Recurse -Force -EA SilentlyContinue } catch {} }
                    }
                }
            } catch {
                Log "[!] Falha ao consultar release do llama.cpp: $_" 'warn'
            }
            if (-not $llamaInstalled -and -not (Test-Path -LiteralPath $llamaServer)) {
                throw 'Não foi possível instalar o llama.cpp e nenhum llama-server.exe existente foi encontrado. Verifique a conexão com a internet e tente novamente.'
            }
            if (-not $llamaInstalled) { Log '[!] Usando llama.cpp existente porque o download novo não pôde ser concluído.' 'warn' }

            # ---- 5. Preparar venv
            P 25 'Preparando ambiente Python'
            if ([string]::IsNullOrWhiteSpace($PYTHON_EXE) -or -not (Test-Path -LiteralPath $PYTHON_EXE)) {
                throw "Python 3.11/3.12 válido não encontrado para criar o venv. Instale pelo python.org e desative aliases Python da Microsoft Store, se existirem."
            }
            Set-InstallState 'creating_venv'
            Log "[OK] Python selecionado: $PYTHON_EXE"
            $forceRecreateVenv = @('1','true','yes','sim') -contains ([string]$env:NEVE_RECREATE_VENV).ToLowerInvariant()
            if ((Test-Path -LiteralPath $VENV_PY) -and -not $forceRecreateVenv) {
                Log "[OK] venv existente preservado para retry incremental"
            } else {
                if (Test-Path $VENV_DIR) {
                    Log "==> Removendo venv antigo ou incompleto"
                    try { Remove-Item $VENV_DIR -Recurse -Force -EA Stop } catch {
                        Log "[X] Falha ao remover venv: $_" 'err'; throw
                    }
                }
                $venvParent = Split-Path -Parent $VENV_DIR
                if (-not (Test-Path -LiteralPath $venvParent)) { New-Item -ItemType Directory -Path $venvParent -Force | Out-Null }
                $rc = Run-NoPipe $PYTHON_EXE @('-m','venv',$VENV_DIR) 'Criando venv'
                if ($rc -ne 0) {
                    Log "[!] Criação padrão do venv falhou (exit $rc). Tentando novamente com --copies." 'warn'
                    if (Test-Path $VENV_DIR) { Remove-Item $VENV_DIR -Recurse -Force -EA SilentlyContinue }
                    $rc = Run-NoPipe $PYTHON_EXE @('-m','venv','--copies',$VENV_DIR) 'Criando venv (--copies)'
                }
                if ($rc -ne 0) { throw "Falha ao criar venv (exit $rc). Python usado: $PYTHON_EXE. Pasta alvo: $VENV_DIR" }
            }
            if (-not (Test-Path $VENV_PY)) {
                throw "O venv foi criado, mas o Python interno não foi encontrado em '$VENV_PY'. Verifique se o Python instalado suporta venv e se o antivírus não bloqueou a criação dos executáveis."
            }
            Set-InstallState 'venv_created'
            Log "[OK] venv pronto"

            # ---- 6. pip + PyTorch
            Set-InstallState 'installing_python_packages'
            Set-InstallState 'preparing_pip_environment'
            $venvScripts = Join-Path $VENV_DIR 'Scripts'
            $script:CleanPipProcessEnv = $true
            $env:VIRTUAL_ENV = $VENV_DIR
            $env:PATH = "$venvScripts;$env:PATH"
            try { Remove-Item Env:PIP_REQUIRE_VIRTUALENV -EA SilentlyContinue } catch {}
            $env:PIP_CONFIG_FILE = 'NUL'
            try { Remove-Item Env:PYTHONHOME -EA SilentlyContinue } catch {}
            try { Remove-Item Env:PYTHONPATH -EA SilentlyContinue } catch {}
            Log "[OK] Ambiente pip isolado para o venv (config global ignorada; PIP_REQUIRE_VIRTUALENV removido)"

            $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
            $env:PIP_NO_INPUT = '1'
            $env:PIP_DEFAULT_TIMEOUT = '60'
            # Build-isolation subprocesses inherit this value even when the parent
            # pip command receives --progress-bar explicitly.
            $env:PIP_PROGRESS_BAR = 'off'
            $env:PYTHONUNBUFFERED = '1'
            $pipLog = Join-Path (Split-Path -Parent $LOG) 'pip-install.log'
            try { [System.IO.File]::WriteAllText($pipLog, '', [System.Text.UTF8Encoding]::new($false)) } catch {}
            Log "[OK] Log detalhado do pip: $pipLog"
            $pipCommon = @('--isolated','--log',$pipLog)
            $pipInstallBase = @('install','--disable-pip-version-check','--no-input','--prefer-binary','--progress-bar','off','--retries','5','--timeout','60')
            $venvPipExe = Join-Path $venvScripts 'pip.exe'
            $venvPip3Exe = Join-Path $venvScripts 'pip3.exe'

            function Invoke-PipCommand {
                param([string[]]$PipArgs, [string]$Desc)

                $attempts = @()
                $attempts += [pscustomobject]@{ Exe = $VENV_PY; Args = (@('-I','-m','pip') + $pipCommon + $PipArgs); Desc = "$Desc [python -I -m pip]" }
                $attempts += [pscustomobject]@{ Exe = $VENV_PY; Args = (@('-m','pip') + $pipCommon + $PipArgs); Desc = "$Desc [python -m pip]" }
                foreach ($pipExe in @($venvPipExe, $venvPip3Exe) | Select-Object -Unique) {
                    if (Test-Path -LiteralPath $pipExe) {
                        $attempts += [pscustomobject]@{ Exe = $pipExe; Args = ($pipCommon + $PipArgs); Desc = "$Desc [$([System.IO.Path]::GetFileName($pipExe))]" }
                    }
                }

                $lastRc = 1
                $failures = @()
                foreach ($attempt in $attempts) {
                    $rc = Run $attempt.Exe $attempt.Args $attempt.Desc
                    if ($rc -eq 0) { return 0 }
                    $lastRc = $rc
                    $failures += ("{0}: exit {1}" -f $attempt.Desc, $rc)
                    if ($rc -eq 3) {
                        Log "[!] pip retornou exit 3 em '$($attempt.Desc)'. Tentando outra rota do pip no mesmo venv." 'warn'
                        continue
                    }
                    break
                }

                $script:LastPipFailures = $failures
                return $lastRc
            }

            function Invoke-PipInstall {
                param([string[]]$InstallArgs, [string]$Desc)
                return Invoke-PipCommand -PipArgs ($pipInstallBase + $InstallArgs) -Desc $Desc
            }

            function Save-GetPipScript {
                param([string]$Destination)
                $urls = @('https://bootstrap.pypa.io/get-pip.py')
                foreach ($url in $urls) {
                    try {
                        Log "==> Baixando get-pip.py com Invoke-WebRequest"
                        Invoke-WebRequest $url -OutFile $Destination -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Installer/3.0' } -TimeoutSec 120
                        if ((Test-Path -LiteralPath $Destination) -and ((Get-Item -LiteralPath $Destination).Length -gt 100000)) { return $true }
                    } catch { Log "[!] Invoke-WebRequest falhou para get-pip.py: $($_.Exception.Message)" 'warn' }

                    try {
                        Log "==> Baixando get-pip.py com WebClient"
                        $wc = New-Object System.Net.WebClient
                        $wc.Headers.Add('User-Agent', 'Neve-Installer/3.0')
                        $wc.DownloadFile($url, $Destination)
                        if ((Test-Path -LiteralPath $Destination) -and ((Get-Item -LiteralPath $Destination).Length -gt 100000)) { return $true }
                    } catch { Log "[!] WebClient falhou para get-pip.py: $($_.Exception.Message)" 'warn' }

                    $curl = Get-Command curl.exe -EA SilentlyContinue | Select-Object -First 1
                    if ($curl) {
                        Log "==> Baixando get-pip.py com curl.exe"
                        $rc = Run-NoPipe $curl.Source @('-L','--fail','--retry','3','--connect-timeout','30','-o',$Destination,$url) 'baixar get-pip.py com curl'
                        if ($rc -eq 0 -and (Test-Path -LiteralPath $Destination) -and ((Get-Item -LiteralPath $Destination).Length -gt 100000)) { return $true }
                    }
                }
                return $false
            }

            function Repair-PipBootstrap {
                Set-InstallState 'repairing_pip_bootstrap'
                $getPipPath = Join-Path (Split-Path -Parent $LOG) 'get-pip.py'
                try { if (Test-Path -LiteralPath $getPipPath) { Remove-Item -LiteralPath $getPipPath -Force -EA SilentlyContinue } } catch {}
                if (-not (Save-GetPipScript $getPipPath)) {
                    Log "[X] Não foi possível baixar get-pip.py para reparar o pip." 'err'
                    return 1
                }
                $rc = Run $VENV_PY @('-I',$getPipPath,'--no-warn-script-location','--force-reinstall','pip','setuptools','wheel') 'get-pip repair'
                return $rc
            }

            $installedPackagesPath = Join-Path (Split-Path -Parent $LOG) 'installed-python-packages.txt'
            $script:InstalledPythonPackages = @{}
            function Refresh-InstalledPackageCache {
                $code = @'
import importlib.metadata as metadata
import sys

def normalize(name: str) -> str:
    return name.strip().lower().replace('_', '-').replace('.', '-')

names = set()
for dist in metadata.distributions():
    name = dist.metadata.get('Name') or getattr(dist, 'name', '')
    if name:
        names.add(normalize(name))

with open(sys.argv[1], 'w', encoding='utf-8') as file:
    file.write('\n'.join(sorted(names)))
'@
                $rc = Run $VENV_PY @('-I','-c',$code,$installedPackagesPath) 'atualizar cache de pacotes Python instalados'
                $script:InstalledPythonPackages = @{}
                if ($rc -eq 0 -and (Test-Path -LiteralPath $installedPackagesPath)) {
                    foreach ($pkg in Get-Content -LiteralPath $installedPackagesPath -EA SilentlyContinue) {
                        $normalized = Normalize-PythonPackageName $pkg
                        if ($normalized) { $script:InstalledPythonPackages[$normalized] = $true }
                    }
                }
                return $rc
            }
            function Test-PythonPackageInstalled([string]$packageName) {
                $normalized = Normalize-PythonPackageName $packageName
                return ($normalized -and $script:InstalledPythonPackages.ContainsKey($normalized))
            }
            function Mark-PythonPackageInstalled([string]$packageName) {
                $normalized = Normalize-PythonPackageName $packageName
                if ($normalized) { $script:InstalledPythonPackages[$normalized] = $true }
            }
            function Test-TorchReady {
                $cudaRequired = if ($cfg.vendor -eq 'NVIDIA') { '1' } else { '0' }
                $code = 'import sys; import torch, torchvision; sys.exit(0 if (sys.argv[1] != "1" or torch.cuda.is_available()) else 1)'
                $rc = Run $VENV_PY @('-I','-c',$code,$cudaRequired) 'validar PyTorch existente'
                return ($rc -eq 0)
            }
            function Test-StableDiffusionCppReady([string]$expectedBackend = '') {
                $sdDir = Join-Path $BACKEND 'bin\stable-diffusion-cpp'
                $sdCli = Join-Path $sdDir 'sd-cli.exe'
                $sdDll = Join-Path $sdDir 'stable-diffusion.dll'
                if (-not ((Test-Path -LiteralPath $sdCli) -and (Test-Path -LiteralPath $sdDll))) { return $false }
                if (-not $expectedBackend) { return $true }
                $versionFile = Join-Path $sdDir 'version.txt'
                if (-not (Test-Path -LiteralPath $versionFile)) { return $false }
                $installedBackend = @(Get-Content -LiteralPath $versionFile -EA SilentlyContinue | Where-Object { $_ }) | Select-Object -Last 1
                return ([string]$installedBackend).Trim().ToLowerInvariant() -eq $expectedBackend.ToLowerInvariant()
            }

            function Install-StableDiffusionCpp {
                $sdBackend = if ($cfg.vendor -eq 'NVIDIA') { 'cuda12' } elseif ($cfg.vendor -eq 'AMD') { 'vulkan' } else { 'cpu' }
                if (Test-StableDiffusionCppReady $sdBackend) {
                    Log "[OK] stable-diffusion.cpp $sdBackend já disponível; pulando download"
                    return $true
                }

                $sdDir = Join-Path $BACKEND 'bin\stable-diffusion-cpp'
                if (-not (Test-Path -LiteralPath $sdDir)) { New-Item -ItemType Directory -Path $sdDir -Force | Out-Null }

                $stageDir = Join-Path $env:TEMP "neve_sdcpp_stage_$([guid]::NewGuid().ToString('N'))"
                $tmpFiles = @()
                try {
                    New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
                    $rel = Invoke-RestMethod 'https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest' -Headers @{ 'User-Agent' = 'Neve-Installer/3.0' } -TimeoutSec 60
                    $assetPattern = switch ($sdBackend) {
                        'cuda12' { 'sd-*-bin-win-cuda12-x64.zip' }
                        'vulkan' { 'sd-*-bin-win-vulkan-x64.zip' }
                        default  { 'sd-*-bin-win-cpu-x64.zip' }
                    }
                    $sdObj = $rel.assets | Where-Object { $_.name -like $assetPattern } | Select-Object -First 1
                    $dllObj = if ($sdBackend -eq 'cuda12') { $rel.assets | Where-Object { $_.name -eq 'cudart-sd-bin-win-cu12-x64.zip' } | Select-Object -First 1 } else { $null }
                    if (-not $sdObj -or ($sdBackend -eq 'cuda12' -and -not $dllObj)) { throw "Release do stable-diffusion.cpp sem binário Windows $sdBackend esperado." }

                    foreach ($asset in @($sdObj, $dllObj) | Where-Object { $_ }) {
                        $zipPath = Join-Path $env:TEMP ("neve_sdcpp_{0}_{1}.zip" -f ([guid]::NewGuid().ToString('N')), $asset.name)
                        $tmpFiles += $zipPath
                        $sizeMB = [math]::Round($asset.size / 1MB, 0)
                        Log "==> Baixando $($asset.name) ($sizeMB MB)"
                        Save-RemoteFile $asset.browser_download_url $zipPath 600
                        Expand-Archive $zipPath -DestinationPath $stageDir -Force
                    }

                    $stagedCli = Get-ChildItem -LiteralPath $stageDir -Recurse -File -Filter 'sd-cli.exe' | Select-Object -First 1
                    if (-not $stagedCli) { throw 'O pacote stable-diffusion.cpp não contém sd-cli.exe.' }

                    Get-ChildItem -LiteralPath $sdDir -Force -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue
                    Get-ChildItem -LiteralPath $stageDir -File -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $sdDir -Force }

                    Set-Content -Path (Join-Path $sdDir 'version.txt') -Value @($rel.tag_name, $sdBackend) -Encoding UTF8
                    if (-not (Test-StableDiffusionCppReady $sdBackend)) { throw 'sd-cli.exe foi copiado, mas não passou na validação.' }
                    Log "[OK] stable-diffusion.cpp $($rel.tag_name) $sdBackend instalado para Z-Image-Turbo"
                    return $true
                } catch {
                    Log "[!] stable-diffusion.cpp não pôde ser preparado agora: $_" 'warn'
                    return $false
                } finally {
                    foreach ($tmp in $tmpFiles) { try { Remove-Item $tmp -Force -EA SilentlyContinue } catch {} }
                    try { if (Test-Path -LiteralPath $stageDir) { Remove-Item $stageDir -Recurse -Force -EA SilentlyContinue } } catch {}
                }
            }

            P 31 'Validando pip do venv'
            Set-InstallState 'verifying_pip'
            $rc = Invoke-PipCommand -PipArgs @('--version') -Desc 'pip --version'
            if ($rc -ne 0) {
                Set-InstallState 'ensurepip_bootstrap'
                Log "[!] pip não respondeu; preparando pelo ensurepip do Python." 'warn'
                $rc = Run $VENV_PY @('-I','-m','ensurepip','--default-pip') 'ensurepip'
                if ($rc -ne 0) {
                    Log "[!] ensurepip falhou (exit $rc). Tentando reparar pip com get-pip.py oficial." 'warn'
                    $rc = Repair-PipBootstrap
                }
                if ($rc -eq 0) { $rc = Invoke-PipCommand -PipArgs @('--version') -Desc 'pip --version pós-bootstrap' }
                if ($rc -ne 0) { throw "pip do venv não respondeu após bootstrap e reparo (exit $rc). Tentativas: $($script:LastPipFailures -join '; '). Veja logs\pip-install.log." }
            } else {
                Log '[OK] pip existente preservado; bootstrap redundante ignorado'
            }

            P 33 'Preparando ferramentas de instalação'
            Set-InstallState 'pip_tooling'
            $rc = Invoke-PipInstall -InstallArgs @('--upgrade','pip','setuptools','wheel') -Desc 'pip/setuptools/wheel'
            if ($rc -ne 0) {
                Log "[!] Preparação de pip/setuptools/wheel falhou (exit $rc). Reparando pip e tentando novamente." 'warn'
                $repairRc = Repair-PipBootstrap
                if ($repairRc -eq 0) { $rc = Invoke-PipInstall -InstallArgs @('--upgrade','pip','setuptools','wheel') -Desc 'pip/setuptools/wheel pós-reparo' }
                if ($rc -ne 0) { throw "Falha ao preparar pip/setuptools/wheel após múltiplas rotas (exit $rc). Tentativas: $($script:LastPipFailures -join '; '). Veja logs\pip-install.log." }
            }
            [void](Refresh-InstalledPackageCache)

            P 38 "Instalando PyTorch ($($cfg.cudaVer))"
            Set-InstallState 'installing_torch'
            if ((Test-PythonPackageInstalled 'torch') -and (Test-PythonPackageInstalled 'torchvision') -and (Test-TorchReady)) {
                Log "[OK] PyTorch já instalado e válido; pulando"
            } else {
                $torchIndexes = @($cfg.torchIndex)
                if ($cfg.vendor -eq 'NVIDIA') {
                    $torchIndexes += @('https://download.pytorch.org/whl/cu128','https://download.pytorch.org/whl/cu126','https://download.pytorch.org/whl/cu124','https://download.pytorch.org/whl/cu121')
                }
                $torchIndexes = @($torchIndexes | Where-Object { $_ } | Select-Object -Unique)
                $torchInstalled = $false
                $torchFailures = @()
                foreach ($torchIndex in $torchIndexes) {
                    Set-InstallState ("installing_torch_{0}" -f (($torchIndex -replace '^https://download\.pytorch\.org/whl/','') -replace '[^A-Za-z0-9_\-]','_'))
                    $label = if ($torchIndex -match '/([^/]+)$') { $matches[1] } else { $torchIndex }
                    $rc = Invoke-PipInstall -InstallArgs @('torch','torchvision','--index-url',$torchIndex) -Desc "PyTorch + torchvision ($label)"
                    if ($rc -eq 0) {
                        $torchInstalled = $true
                        Mark-PythonPackageInstalled 'torch'
                        Mark-PythonPackageInstalled 'torchvision'
                        break
                    }
                    $torchFailures += ("{0}: exit {1}" -f $label, $rc)
                    if ($cfg.vendor -eq 'NVIDIA') {
                        Log "[!] PyTorch CUDA em $label falhou (exit $rc). Tentando outro índice CUDA compatível." 'warn'
                    }
                }
                if (-not $torchInstalled) { throw "Falha ao instalar PyTorch sem comprometer a aceleração escolhida. Tentativas: $($torchFailures -join '; '). Veja logs\pip-install.log." }
                [void](Refresh-InstalledPackageCache)
            }
            Log "[OK] PyTorch instalado"

            # ---- 7. stable-diffusion.cpp (Z-Image-Turbo)
            if ($cfg.vendor -in @('NVIDIA','AMD')) {
                P 55 'Preparando geração de imagem local'
                Set-InstallState 'installing_stable_diffusion_cpp'
                [void](Install-StableDiffusionCpp)
            } else {
                P 55 'Otimizando instalação para o hardware'
                Log "[OK] stable-diffusion.cpp ignorado para $($cfg.vendor)."
            }

            # ---- 8. requirements do backend
            P 60 'Instalando dependências do backend (~5-15 min)'
            Set-InstallState 'installing_backend_requirements'
            $runtimeReq = Join-Path $BACKEND 'requirements-runtime.txt'
            $fullReq = Join-Path $BACKEND 'requirements.txt'
            $useFullReq = @('1','true','yes','sim') -contains ([string]$env:NEVE_INSTALL_FULL_REQUIREMENTS).ToLowerInvariant()
            if ((-not $useFullReq) -and (Test-Path -LiteralPath $runtimeReq)) {
                $req = $runtimeReq
                Log "[OK] Usando requirements-runtime.txt (dependências essenciais do NeveAI)"
                Log "    Para instalar a lista completa antiga, defina NEVE_INSTALL_FULL_REQUIREMENTS=1 antes de abrir o instalador."
            } else {
                $req = $fullReq
                Log "[OK] Usando requirements.txt completo"
            }
            if (-not (Test-Path -LiteralPath $req)) {
                throw "Arquivo de dependências não encontrado em '$req'."
            }
            $reqName = Split-Path -Leaf $req
            $reqEntries = @(Get-RequirementEntries $req)
            $reqCount = $reqEntries.Count
            Log "[OK] $reqName encontrado: $reqCount entradas"
            $failedRequirements = @()
            $pythonDependencyFailures = @()
            Log "==> Instalando $reqName em lote para compartilhar resolução e downloads"
            Set-InstallState 'installing_backend_requirements_batch'
            $batchRc = Invoke-PipInstall -InstallArgs @('-r', $req) -Desc "$reqName em lote"
            if ($batchRc -eq 0) {
                Log "[OK] $reqName instalado em uma única resolução pip"
            } else {
                Log "[!] Instalação em lote falhou (exit $batchRc). Ativando recuperação incremental apenas para os pacotes pendentes." 'warn'
                [void](Refresh-InstalledPackageCache)
                for ($i = 0; $i -lt $reqEntries.Count; $i++) {
                $entry = $reqEntries[$i]
                $index = $i + 1
                $percent = 60 + [math]::Floor(($index / [math]::Max(1, $reqCount)) * 17)
                P $percent ("{0} {1}/{2}" -f $reqName, $index, $reqCount)
                Set-InstallState ("installing_requirement_{0}_of_{1}" -f $index, $reqCount)
                Log ("==> {0} [{1}/{2}] linha {3}: {4}" -f $reqName, $index, $reqCount, $entry.Line, $entry.Spec)

                if ($entry.Package -and (Test-PythonPackageInstalled $entry.Package)) {
                    Log ("[OK] {0} já instalado; pulando" -f $entry.Package)
                    continue
                }

                $rc = Invoke-PipInstall -InstallArgs @($entry.Spec) -Desc ("{0} {1}/{2}: {3}" -f $reqName, $index, $reqCount, $entry.Spec)
                if ($rc -ne 0) {
                    $fallbackSpec = Get-UnpinnedRequirementSpec $entry.Spec
                    if ($fallbackSpec) {
                        Log ("[!] Falha em {0} linha {1}: {2} (exit {3}); tentando sem versão: {4}" -f $reqName, $entry.Line, $entry.Spec, $rc, $fallbackSpec) 'warn'
                        $fallbackRc = Invoke-PipInstall -InstallArgs @($fallbackSpec) -Desc ("{0} {1}/{2} fallback sem versão: {3}" -f $reqName, $index, $reqCount, $fallbackSpec)
                        if ($fallbackRc -eq 0) {
                            Log ("[OK] Fallback sem versão instalado para linha {0}: {1}" -f $entry.Line, $fallbackSpec)
                            if ($entry.Package) { Mark-PythonPackageInstalled $entry.Package }
                            continue
                        }
                        $failedRequirements += ("linha {0}: {1} (exit {2}); fallback {3} (exit {4})" -f $entry.Line, $entry.Spec, $rc, $fallbackSpec, $fallbackRc)
                        Log ("[!] Fallback sem versão também falhou em {0} linha {1}: {2} (exit {3}); continuando com as demais" -f $reqName, $entry.Line, $fallbackSpec, $fallbackRc) 'warn'
                        continue
                    }

                    $failedRequirements += ("linha {0}: {1} (exit {2})" -f $entry.Line, $entry.Spec, $rc)
                    Log ("[!] Falha em {0} linha {1}: {2} (exit {3}); sem fallback aplicável, continuando com as demais" -f $reqName, $entry.Line, $entry.Spec, $rc) 'warn'
                    continue
                }
                if ($entry.Package) { Mark-PythonPackageInstalled $entry.Package }
                }
            }

            if ($failedRequirements.Count -gt 0) {
                $pythonDependencyFailures = @($failedRequirements)
                $pendingPath = Join-Path (Split-Path -Parent $LOG) 'python-dependencies-pending.txt'
                try { [System.IO.File]::WriteAllText($pendingPath, ($failedRequirements -join [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false)) } catch {}
                Log ("[!] Dependências pendentes: {0}" -f ($failedRequirements -join '; ')) 'warn'
                Log "[!] O instalador continuará. Ao executar de novo, pacotes já instalados serão pulados e estas pendências serão tentadas novamente." 'warn'
            } else {
                $pendingPath = Join-Path (Split-Path -Parent $LOG) 'python-dependencies-pending.txt'
                try { if (Test-Path -LiteralPath $pendingPath) { Remove-Item -LiteralPath $pendingPath -Force -EA SilentlyContinue } } catch {}
            }
            [void](Refresh-InstalledPackageCache)
            Log "[OK] Etapa de dependências do backend concluída"

            P 77 'Validando dependências Python'
            Set-InstallState 'pip_check'
            $rc = Invoke-PipCommand -PipArgs @('check') -Desc 'pip check'
            if ($rc -eq 0) { Log "[OK] pip check sem conflitos" } else { Log "[!] pip check encontrou conflitos; verifique o log acima se algo falhar ao iniciar" 'warn' }

            # ---- 9. onnxruntime-gpu (opcional)
            $installOnnxGpu = $cfg.useOnnxGpu -and (@('1','true','yes','sim') -contains ([string]$env:NEVE_INSTALL_ONNXRUNTIME_GPU).ToLowerInvariant())
            if ($installOnnxGpu) {
                P 78 'Instalando onnxruntime-gpu opcional'
                Set-InstallState 'installing_onnxruntime_gpu'
                if (Test-PythonPackageInstalled 'onnxruntime-gpu') {
                    Log "[OK] onnxruntime-gpu já instalado; pulando"
                } else {
                    [void](Invoke-PipCommand -PipArgs @('uninstall','onnxruntime','-y') -Desc 'remover onnxruntime CPU')
                    $rc = Invoke-PipInstall -InstallArgs @('onnxruntime-gpu') -Desc 'onnxruntime-gpu'
                    if ($rc -eq 0) {
                        Mark-PythonPackageInstalled 'onnxruntime-gpu'
                        Log "[OK] onnxruntime-gpu instalado"
                    } else {
                        Log "[!] onnxruntime-gpu falhou (exit $rc). Etapa opcional ignorada; sem fallback CPU silencioso." 'warn'
                    }
                }
            } elseif ($cfg.useOnnxGpu) {
                Log "[OK] onnxruntime-gpu opcional ignorado no runtime mínimo. Defina NEVE_INSTALL_ONNXRUNTIME_GPU=1 para instalar."
            }

            # ---- 10. npm install
            Set-InstallState 'installing_frontend'
            P 84 'Instalando pacotes npm'
            Set-Location -LiteralPath $ROOT
            $frontendNode = Resolve-FrontendNodeLaunch
            if (-not $frontendNode) {
                $frontendNode = Install-PortableNode22
            }
            if (-not $frontendNode) { throw 'Node.js 18-22 com npm não encontrado e o Node.js 22 portátil não pôde ser preparado.' }
            $NODE_EXE = $frontendNode.NodeExecutable
            $NPM_EXE = $frontendNode.NpmExecutable
            $script:FrontendNodeDir = $frontendNode.NodeDir
            Log "[OK] Node.js do frontend: $($frontendNode.NodeVersion) / npm $($frontendNode.NpmVersion) em $($frontendNode.NodeDir)"

            $packageLockPath = Join-Path $ROOT 'package-lock.json'
            $nodeModulesPath = Join-Path $ROOT 'node_modules'
            if ((Test-Path -LiteralPath $packageLockPath) -and -not (Test-Path -LiteralPath $nodeModulesPath)) {
                $rc = Run $NPM_EXE @('ci','--no-audit','--no-fund','--prefer-offline','--progress=false') 'npm ci'
                if ($rc -ne 0) { throw "Falha em npm ci (exit $rc)" }
            } else {
                $rc = Run $NPM_EXE @('install','--no-audit','--no-fund','--prefer-offline','--progress=false') 'npm install incremental'
                if ($rc -ne 0) { throw "Falha em npm install (exit $rc)" }
            }
            Log "[OK] Pacotes npm instalados"

            $previousOfficeCliSkipUpdate = $env:OFFICECLI_SKIP_UPDATE
            $previousOfficeCliNoAutoResident = $env:OFFICECLI_NO_AUTO_RESIDENT
            try {
                $env:OFFICECLI_SKIP_UPDATE = '1'
                $env:OFFICECLI_NO_AUTO_RESIDENT = '1'
                $officeCli = Join-Path $ROOT 'node_modules\@officecli\officecli\vendor\officecli.exe'
                if (-not (Test-Path -LiteralPath $officeCli)) {
                    Log "[!] Binário do OfficeCLI ausente após o npm install; executando a recuperação oficial." 'warn'
                    $rc = Run $NPM_EXE @('exec','--','officecli','--version') 'preparar OfficeCLI'
                    if ($rc -ne 0 -or -not (Test-Path -LiteralPath $officeCli)) {
                        throw 'Falha ao preparar o OfficeCLI para geração de DOCX, XLSX e PPTX.'
                    }
                }
                $rc = Run $officeCli @('--version') 'validar OfficeCLI'
                if ($rc -ne 0) { throw "OfficeCLI instalado, mas a validação falhou (exit $rc)." }
            } finally {
                if ($null -eq $previousOfficeCliSkipUpdate) { Remove-Item Env:\OFFICECLI_SKIP_UPDATE -ErrorAction SilentlyContinue } else { $env:OFFICECLI_SKIP_UPDATE = $previousOfficeCliSkipUpdate }
                if ($null -eq $previousOfficeCliNoAutoResident) { Remove-Item Env:\OFFICECLI_NO_AUTO_RESIDENT -ErrorAction SilentlyContinue } else { $env:OFFICECLI_NO_AUTO_RESIDENT = $previousOfficeCliNoAutoResident }
            }
            Log "[OK] OfficeCLI pronto para gerar DOCX, XLSX e PPTX"

            # ---- 11. npm run build
            P 92 'Compilando frontend (~2-5 min)'
            $rc = Run $NPM_EXE @('run','build','--','--logLevel','error') 'npm run build'
            if ($rc -ne 0) { throw "Falha no build do frontend (exit $rc)" }
            Log "[OK] Frontend compilado"

            # ---- 12. Deploy frontend para backend\neveai\frontend
            P 97 'Implantando frontend no backend'
            $frontDir = Join-Path $BACKEND 'neveai\frontend'
            if (Test-Path $frontDir) { Remove-Item $frontDir -Recurse -Force }
            New-Item $frontDir -ItemType Directory -Force | Out-Null
            Copy-Item (Join-Path $ROOT 'build\*') $frontDir -Recurse -Force
            Log "[OK] Frontend copiado para backend\neveai\frontend"

            # ---- Done
            Set-InstallState 'done'
            P 100 'Concluído'
            if ($createDesktopShortcut) { [void](New-NeveDesktopShortcut $ROOT) }

            # Resumo
            $summary = @()
            $summary += "Python:      $((& $PYTHON_EXE --version 2>&1))"
            $summary += "Node.js:     $((& $NODE_EXE --version 2>&1))"
            try {
                $tOut = & $VENV_PY -c "import torch; v=torch.__version__; cuda='(CUDA '+torch.version.cuda+')' if torch.cuda.is_available() else '(CPU)'; print('PyTorch '+v+' '+cuda)" 2>$null
                if ($tOut) { $summary += "PyTorch:     $tOut" }
            } catch {}
            $summary += "llama.cpp:   $($cfg.llamaAsset)"
            if (Test-StableDiffusionCppReady) {
                $sdBackendSummary = if ($cfg.vendor -eq 'AMD') { 'Vulkan' } elseif ($cfg.vendor -eq 'NVIDIA') { 'CUDA 12' } else { 'CPU' }
                $summary += "sd.cpp:      Z-Image-Turbo $sdBackendSummary"
            }
            if ($vramGb -gt 0) { $summary += "VRAM:        ${vramGb} GB ($($detected.Name))" }
            if ($pythonDependencyFailures.Count -gt 0) {
                $summary += "Pendências:  $($pythonDependencyFailures.Count) dependência(s) Python; rode instalar.bat novamente para tentar só o que faltou."
            }

            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.InstallPanel.Visibility = 'Collapsed'
                $script:Ctl.DonePanel.Visibility    = 'Visible'
                $script:Ctl.LblSummary.Text         = ($summary -join "`r`n")
                if ($pythonDependencyFailures.Count -gt 0) {
                    $script:Ctl.LblDoneTitle.Text = 'Concluído com pendências'
                    $script:Ctl.LblDoneSub.Text = 'O NeveAI tentou todas as dependências e registrou as pendências para retry incremental.'
                }
                $script:Ctl.BtnCancel.Visibility    = 'Collapsed'
                $script:Ctl.BtnPrimary.IsEnabled    = $true
                $script:Ctl.BtnPrimary.Content      = 'Concluir'
                $script:Ctl.BtnPrimary.Tag          = 'done'
                $script:Ctl.BtnClose.IsEnabled      = $true
                $script:Window.Tag = 'done'
            })
        } catch {
            if (($INSTALL_CONTROL -and $INSTALL_CONTROL.CancelRequested) -or ($_.Exception -is [System.OperationCanceledException])) {
                Set-InstallState 'cancelled'
                Log '[!] Instalação cancelada pelo usuário.' 'warn'
                return
            }
            $errMsg = "$($_.Exception.Message)"
            if (-not $errMsg) { $errMsg = "$_" }
            Set-InstallState 'failed'
            Log "[X] FALHA: $errMsg" 'err'
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LblStep.Text = "Falha durante a instalação."
                $script:Ctl.LblPhase.Text = "Falha durante a instalação."
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnPrimary.Content   = 'Fechar'
                $script:Ctl.BtnPrimary.Tag       = 'done'
                $script:Ctl.BtnCancel.Visibility = 'Collapsed'
                $script:Ctl.BtnCancel.IsEnabled  = $false
                $script:Ctl.BtnClose.IsEnabled   = $true
                $script:Window.Tag = 'failed'
                [System.Windows.MessageBox]::Show("A instalação falhou. A janela ficará aberta para você ler o log.`n`nVeja logs\install.log`n`n$errMsg", 'NeveAI', 'OK', 'Error') | Out-Null
            })
        }
    }

    # Cria runspace e injeta o que precisamos
    $runspace = [RunspaceFactory]::CreateRunspace()
    $runspace.ApartmentState = 'STA'
    $runspace.ThreadOptions  = 'ReuseThread'
    $runspace.Open()
    $runspace.SessionStateProxy.SetVariable('Window', $window)
    $runspace.SessionStateProxy.SetVariable('Ctl',    $ctl)

    $ps = [PowerShell]::Create()
    $ps.Runspace = $runspace
    $installControlForRun = $script:InstallControl
    [void]$ps.AddScript($worker).AddArgument($cfg).AddArgument($installPython311).AddArgument($createDesktopShortcut).AddArgument($vramGb).AddArgument($detected).AddArgument($ROOT).AddArgument($VENV_DIR).AddArgument($VENV_PY).AddArgument($BACKEND).AddArgument($LOG).AddArgument($STATE_FILE).AddArgument($PYTHON_EXE).AddArgument($NODE_EXE).AddArgument($NPM_EXE).AddArgument($INSTALLER_REVISION).AddArgument($SCRIPT_PATH).AddArgument($installControlForRun)
    $invocationStateHandler = {
        param($sender, $eventArgs)
        if ($eventArgs.InvocationStateInfo.State -eq 'Failed') {
            if ($installControlForRun -and $installControlForRun.CancelRequested) { return }
            $fatal = $eventArgs.InvocationStateInfo.Reason
            $msg = if ($fatal) { $fatal.Message } else { 'Falha fatal no processo de instalação.' }
            try { [System.IO.File]::WriteAllText($STATE_FILE, 'failed', [System.Text.UTF8Encoding]::new($false)) } catch {}
            try { Add-Content -LiteralPath $LOG -Value "[FATAL] $msg" -Encoding UTF8 } catch {}
            try {
                $window.Dispatcher.Invoke([Action]{
                    $ctl.LblStep.Text = 'Falha fatal durante a instalação.'
                    $ctl.LblPhase.Text = 'Falha fatal durante a instalação.'
                    $ctl.BtnPrimary.IsEnabled = $true
                    $ctl.BtnPrimary.Content = 'Fechar'
                    $ctl.BtnPrimary.Tag = 'done'
                    $ctl.BtnCancel.Visibility = 'Collapsed'
                    $ctl.BtnCancel.IsEnabled = $false
                    $ctl.BtnClose.IsEnabled = $true
                    $window.Tag = 'failed'
                    $ctl.LogBox.AppendText("[FATAL] $msg`r`n")
                    $ctl.LogScroll.ScrollToEnd()
                })
            } catch {}
        }
    }.GetNewClosure()
    [void]$ps.add_InvocationStateChanged($invocationStateHandler)
    $script:InstallerPowerShell = $ps
    $script:InstallerRunspace = $runspace
    $script:InstallerAsyncResult = $ps.BeginInvoke()
})


# =============================================================================
# Hub central: Atualizar e Buildar dentro da mesma janela WPF
# =============================================================================
$script:HubLegacyPages = @{}
$script:HubLegacyModules = @{}
$script:HubActionPanels = @{ install = $ctl.InstallActions }
$script:HubWindow = $window
$script:HubPageHost = $ctl.HubPageHost
$script:HubScriptPath = $SCRIPT_PATH
$script:HubActiveMode = 'home'

$script:UpdateLegacySource = @'
# NeveAI - Atualizador Grafico (WPF)
# Verifica a ultima release em github.com/Etamus/NeveAI, baixa, aplica e refaz o build.

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [Console]::OutputEncoding
$ErrorActionPreference    = 'Stop'

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

# =============================================================================
# Caminhos globais
# =============================================================================
$SCRIPT_PATH = if ($PSCommandPath) { $PSCommandPath } elseif ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { throw 'Não foi possível determinar o caminho do atualizador.' }
$LAUNCHER_DIR = (Resolve-Path -LiteralPath (Split-Path -Parent $SCRIPT_PATH)).ProviderPath
$ROOT         = (Resolve-Path -LiteralPath (Join-Path $LAUNCHER_DIR '..')).ProviderPath
Set-Location -LiteralPath $ROOT
$VENV_PY     = Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe'
$VERSION_FILE= Join-Path $ROOT 'version.txt'
$LOG_DIR     = Join-Path $ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) { New-Item $LOG_DIR -ItemType Directory | Out-Null }
$LOG = Join-Path $LOG_DIR 'update.log'
'' | Set-Content $LOG -Encoding UTF8

$REPO_OWNER  = 'Etamus'
$REPO_NAME   = 'NeveAI'
$API_LATEST  = "https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/releases/latest"
$LLAMA_API_RELEASES = 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30'
$UA          = 'Neve-Updater/1.0'

function Normalize-ReleaseTag([string]$tag) {
    return ([string]$tag).Trim().TrimStart('v', 'V')
}

function Get-VersionParts([string]$tag) {
    $normalized = Normalize-ReleaseTag $tag
    if ($normalized -match '^b(\d+)$') { return @([int]$matches[1]) }
    $core = ($normalized -split '[-+]', 2)[0]
    $matches = [regex]::Matches($core, '\d+')
    $parts = @()
    foreach ($match in $matches) { $parts += [int]$match.Value }
    return $parts
}

function Test-ReleaseTagNewer([string]$current, [string]$latest) {
    $currentNorm = Normalize-ReleaseTag $current
    $latestNorm = Normalize-ReleaseTag $latest
    if ([string]::IsNullOrWhiteSpace($currentNorm) -or [string]::IsNullOrWhiteSpace($latestNorm)) { return $false }
    if ($currentNorm -eq $latestNorm -or $currentNorm -eq '0.0.0') { return $false }

    $currentParts = @(Get-VersionParts $currentNorm)
    $latestParts = @(Get-VersionParts $latestNorm)
    if ($currentParts.Count -eq 0 -or $latestParts.Count -eq 0) { return $false }

    $max = [Math]::Max($currentParts.Count, $latestParts.Count)
    for ($i = 0; $i -lt $max; $i++) {
        $currentValue = if ($i -lt $currentParts.Count) { $currentParts[$i] } else { 0 }
        $latestValue = if ($i -lt $latestParts.Count) { $latestParts[$i] } else { 0 }
        if ($latestValue -gt $currentValue) { return $true }
        if ($latestValue -lt $currentValue) { return $false }
    }

    $semverPattern = '^\d+(?:\.\d+)*(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$'
    $currentMatch = [regex]::Match($currentNorm, $semverPattern)
    $latestMatch = [regex]::Match($latestNorm, $semverPattern)
    if (-not $currentMatch.Success -or -not $latestMatch.Success) { return $false }

    $currentPre = $currentMatch.Groups[1].Value
    $latestPre = $latestMatch.Groups[1].Value
    if ($currentPre -and -not $latestPre) { return $true }
    if (-not $currentPre -or -not $latestPre) { return $false }

    $currentIds = @($currentPre -split '\.')
    $latestIds = @($latestPre -split '\.')
    $count = [Math]::Max($currentIds.Count, $latestIds.Count)
    for ($i = 0; $i -lt $count; $i++) {
        if ($i -ge $currentIds.Count) { return $true }
        if ($i -ge $latestIds.Count) { return $false }
        $currentNumber = 0
        $latestNumber = 0
        $currentNumeric = [int]::TryParse($currentIds[$i], [ref]$currentNumber)
        $latestNumeric = [int]::TryParse($latestIds[$i], [ref]$latestNumber)
        if ($currentNumeric -and $latestNumeric) {
            if ($latestNumber -gt $currentNumber) { return $true }
            if ($latestNumber -lt $currentNumber) { return $false }
        } elseif ($currentNumeric -ne $latestNumeric) {
            return $currentNumeric
        } else {
            $comparison = [string]::CompareOrdinal($latestIds[$i], $currentIds[$i])
            if ($comparison -gt 0) { return $true }
            if ($comparison -lt 0) { return $false }
        }
    }

    return $false
}

function Get-FriendlyGitHubError($error) {
    $message = "$error"
    if ($message -match 'API rate limit exceeded|rate limit') {
        return 'Limite temporário do GitHub atingido. Aguarde alguns minutos e tente novamente, ou configure um token GitHub para aumentar o limite.'
    }
    return $message
}

function Get-GitHubLatestTagFromRedirect([string]$owner, [string]$repo) {
    $url = "https://github.com/$owner/$repo/releases/latest"
    foreach ($method in @('HEAD', 'GET')) {
        try {
            $request = [System.Net.HttpWebRequest]::Create($url)
            $request.Method = $method
            $request.AllowAutoRedirect = $false
            $request.UserAgent = $UA
            $request.Timeout = 20000
            $response = $request.GetResponse()
            try {
                $location = [string]$response.Headers['Location']
                if ($location -match '/releases/tag/([^/?#]+)') {
                    return [uri]::UnescapeDataString($matches[1])
                }
            } finally {
                $response.Close()
            }
        } catch [System.Net.WebException] {
            $response = $_.Exception.Response
            try {
                if ($response) {
                    $location = [string]$response.Headers['Location']
                    if ($location -match '/releases/tag/([^/?#]+)') {
                        return [uri]::UnescapeDataString($matches[1])
                    }
                }
            } finally {
                if ($response) { $response.Close() }
            }
        } catch {}
    }

    return $null
}

function New-GitHubReleaseFallbackObject([string]$owner, [string]$repo, [string]$tag) {
    [pscustomobject]@{
        tag_name = $tag
        body = 'Notas de release indisponíveis no momento porque o GitHub limitou a consulta pela API.'
        zipball_url = "https://github.com/$owner/$repo/archive/refs/tags/$([uri]::EscapeDataString($tag)).zip"
        assets = @()
        is_fallback = $true
    }
}

function Get-GitHubLatestRelease([string]$owner, [string]$repo) {
    $apiUrl = "https://api.github.com/repos/$owner/$repo/releases/latest"
    try {
        return Invoke-RestMethod $apiUrl -Headers @{ 'User-Agent' = $UA } -TimeoutSec 20
    } catch {
        $apiError = $_
        $tag = Get-GitHubLatestTagFromRedirect $owner $repo
        if ($tag) {
            return New-GitHubReleaseFallbackObject $owner $repo $tag
        }
        throw (Get-FriendlyGitHubError $apiError)
    }
}

function New-LlamaReleaseAssetReference([string]$tag, [string]$name) {
    [pscustomobject]@{
        name = $name
        size = 0
        browser_download_url = "https://github.com/ggml-org/llama.cpp/releases/download/$([uri]::EscapeDataString($tag))/$([uri]::EscapeDataString($name))"
    }
}

function Test-LlamaReleaseAssetReference([string]$url) {
    try {
        $request = [System.Net.HttpWebRequest]::Create($url)
        $request.Method = 'HEAD'
        $request.AllowAutoRedirect = $true
        $request.UserAgent = $UA
        $request.Timeout = 15000
        $response = $request.GetResponse()
        try {
            $statusCode = [int]$response.StatusCode
            return ($statusCode -ge 200 -and $statusCode -lt 400)
        } finally {
            $response.Close()
        }
    } catch {
        return $false
    }
}

function Test-LlamaBackendCompatible([string]$requested, [string]$available) {
    if ([string]::IsNullOrWhiteSpace($requested) -or [string]::IsNullOrWhiteSpace($available)) { return $false }
    if ($requested -eq $available) { return $true }

    $requestedCuda = [regex]::Match($requested, '^cuda(?:-cu)?-?(\d+)(?:\.\d+)?$')
    $availableCuda = [regex]::Match($available, '^cuda(?:-cu)?-?(\d+)(?:\.\d+)?$')
    return ($requestedCuda.Success -and $availableCuda.Success -and $requestedCuda.Groups[1].Value -eq $availableCuda.Groups[1].Value)
}

function Get-GitHubLatestLlamaRelease([string[]]$backends = @()) {
    $supportedBackends = @('cpu', 'cuda-12.4', 'cuda-13.4', 'cuda-13.3', 'cuda-cu12.4', 'cuda-cu13.4', 'cuda-cu13.3', 'vulkan')
    $wantedBackends = @($backends | Where-Object { $_ })
    if ($wantedBackends.Count -eq 0) { $wantedBackends = $supportedBackends }
    if ($wantedBackends -contains 'cuda-cu12.4') { $wantedBackends += 'cuda-12.4' }
    if ($wantedBackends -contains 'cuda-cu13.3') { $wantedBackends += 'cuda-13.3' }
    if ($wantedBackends -contains 'cuda-12.4') { $wantedBackends += 'cuda-cu12.4' }
    if ($wantedBackends -contains 'cuda-13.3') { $wantedBackends += 'cuda-cu13.3' }
    $wantedBackends = @($wantedBackends | Select-Object -Unique)

    $apiError = $null
    try {
        $releases = @((Invoke-RestMethod $LLAMA_API_RELEASES -Headers @{ 'User-Agent' = $UA; 'Accept' = 'application/vnd.github+json' } -TimeoutSec 30))
        foreach ($release in $releases) {
            if ($release.draft -or -not $release.tag_name) { continue }
            $tagEsc = [regex]::Escape([string]$release.tag_name)
            foreach ($asset in @($release.assets)) {
                $assetMatch = [regex]::Match([string]$asset.name, "^llama-$tagEsc-bin-win-(.+)-x64\.zip$")
                if (-not $assetMatch.Success) { continue }
                $availableBackend = $assetMatch.Groups[1].Value
                foreach ($backend in $wantedBackends) {
                    if (Test-LlamaBackendCompatible $backend $availableBackend) { return $release }
                }
            }
        }
        throw 'Nenhuma release recente do llama.cpp contém binários Windows compatíveis.'
    } catch {
        $apiError = $_
    }

    try {
        $feed = Invoke-WebRequest 'https://github.com/ggml-org/llama.cpp/releases.atom' -Headers @{ 'User-Agent' = $UA } -UseBasicParsing -TimeoutSec 30
        $seenTags = @{}
        foreach ($match in [regex]::Matches([string]$feed.Content, '/releases/tag/([^"<]+)')) {
            $tag = [uri]::UnescapeDataString($match.Groups[1].Value).Trim()
            if (-not $tag -or $seenTags.ContainsKey($tag)) { continue }
            $seenTags[$tag] = $true

            foreach ($backend in $wantedBackends) {
                $mainName = "llama-$tag-bin-win-$backend-x64.zip"
                $mainAsset = New-LlamaReleaseAssetReference $tag $mainName
                if (-not (Test-LlamaReleaseAssetReference $mainAsset.browser_download_url)) { continue }

                $assets = @($mainAsset)
                if ($backend -match '^cuda') {
                    $runtimeName = "cudart-llama-bin-win-$backend-x64.zip"
                    $runtimeAsset = New-LlamaReleaseAssetReference $tag $runtimeName
                    if (Test-LlamaReleaseAssetReference $runtimeAsset.browser_download_url) { $assets += $runtimeAsset }
                }

                return [pscustomobject]@{
                    tag_name = $tag
                    assets = $assets
                    prerelease = $true
                    draft = $false
                    is_fallback = $true
                }
            }
        }
    } catch {}

    throw (Get-FriendlyGitHubError $apiError)
}

# Logo (favicon do projeto)
$LOGO_PATH = Join-Path $ROOT 'static\favicon.png'
if (-not (Test-Path $LOGO_PATH)) { $LOGO_PATH = Join-Path $ROOT 'static\static\favicon.png' }

# =============================================================================
# XAML - Interface
# =============================================================================
[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="NeveAI - Atualizador"
        Width="780" Height="560"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize"
        WindowStyle="None"
        AllowsTransparency="True"
        Background="Transparent">
    <Window.Resources>
        <Style x:Key="PrimaryBtn" TargetType="Button">
            <Setter Property="Background" Value="#111111"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="Padding" Value="22,9"/>
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="FontWeight" Value="Medium"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#262626"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="bd" Property="Opacity" Value="0.4"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style x:Key="GhostBtn" TargetType="Button" BasedOn="{StaticResource PrimaryBtn}">
            <Setter Property="Background" Value="#F4F4F5"/>
            <Setter Property="Foreground" Value="#111111"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#E4E4E7"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style x:Key="AccentBtn" TargetType="Button" BasedOn="{StaticResource PrimaryBtn}">
            <Setter Property="Background" Value="#2563EB"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="Padding" Value="18,9"/>
            <Setter Property="MinWidth" Value="154"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#1D4ED8"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="bd" Property="Opacity" Value="0.45"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
    </Window.Resources>

    <Border CornerRadius="14" Background="#FAFAFA" BorderBrush="#E4E4E7" BorderThickness="1">
        <Grid>
            <Grid.RowDefinitions>
                <RowDefinition Height="56"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="68"/>
            </Grid.RowDefinitions>

            <!-- TITLE BAR -->
            <Grid Grid.Row="0" Background="Transparent">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>
                <StackPanel Grid.Column="0" Orientation="Horizontal" Margin="18,0,0,0" VerticalAlignment="Center">
                    <Image x:Name="LogoImg" Width="22" Height="22" Margin="0,0,10,0"/>
                    <TextBlock Text="NeveAI" FontSize="15" FontWeight="SemiBold" Foreground="#111111" VerticalAlignment="Center"/>
                    <TextBlock Text="  ·  Atualizador" FontSize="13" Foreground="#71717A" VerticalAlignment="Center"/>
                </StackPanel>
                <Button x:Name="BtnClose" Grid.Column="2" Width="44" Height="32" Margin="0,0,12,0"
                        Background="Transparent" BorderThickness="0" Cursor="Hand">
                    <Button.Template>
                        <ControlTemplate TargetType="Button">
                            <Border x:Name="bd" Background="Transparent" CornerRadius="6">
                                <TextBlock Text="×" FontSize="22" FontWeight="Medium" Foreground="#71717A" HorizontalAlignment="Center" VerticalAlignment="Center" Margin="0,-5,0,0"/>
                            </Border>
                            <ControlTemplate.Triggers>
                                <Trigger Property="IsMouseOver" Value="True">
                                    <Setter TargetName="bd" Property="Background" Value="#E4E4E7"/>
                                </Trigger>
                            </ControlTemplate.Triggers>
                        </ControlTemplate>
                    </Button.Template>
                </Button>
            </Grid>

            <!-- BODY -->
            <Grid Grid.Row="1" Margin="32,24,32,24">

                <!-- CHECK PANEL -->
                <Grid x:Name="CheckPanel">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,18">
                        <TextBlock x:Name="LblCheckTitle" Text="Verificando atualizações…" FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock x:Name="LblCheckSub" Text="Consultando GitHub…" FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="20,14" VerticalAlignment="Center" Margin="0,-86,0,16">
                        <Grid VerticalAlignment="Center">
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto"/>
                            </Grid.RowDefinitions>

                            <Grid Grid.Row="0" VerticalAlignment="Center">
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width="0.92*"/>
                                    <ColumnDefinition Width="1"/>
                                    <ColumnDefinition Width="1.08*"/>
                                </Grid.ColumnDefinitions>

                                <Grid Grid.Column="0" Margin="0,0,14,0">
                                    <Grid.RowDefinitions>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                    </Grid.RowDefinitions>
                                    <Grid.ColumnDefinitions>
                                        <ColumnDefinition Width="118"/>
                                        <ColumnDefinition Width="*"/>
                                    </Grid.ColumnDefinitions>

                                    <Grid Grid.Row="0" Grid.ColumnSpan="2" Margin="0,0,0,8">
                                        <TextBlock Text="NeveAI" FontSize="13" FontWeight="SemiBold" Foreground="#111111"/>
                                        <CheckBox x:Name="ChkUpdateNeve" HorizontalAlignment="Right" VerticalAlignment="Center" Visibility="Collapsed"/>
                                    </Grid>

                                    <TextBlock Grid.Row="1" Grid.Column="0" Text="Versão instalada:" FontSize="13" Foreground="#52525B" Margin="0,0,0,10"/>
                                    <TextBlock Grid.Row="1" Grid.Column="1" x:Name="LblCurrent" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,10" TextTrimming="CharacterEllipsis"/>

                                    <TextBlock Grid.Row="2" Grid.Column="0" Text="Última disponível:" FontSize="13" Foreground="#52525B" Margin="0,0,0,10"/>
                                    <TextBlock Grid.Row="2" Grid.Column="1" x:Name="LblLatest" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,10" TextTrimming="CharacterEllipsis"/>

                                    <TextBlock Grid.Row="3" Grid.Column="0" Text="Status:" FontSize="13" Foreground="#52525B" Margin="0,0,0,0"/>
                                    <TextBlock Grid.Row="3" Grid.Column="1" x:Name="LblStatus" Text="Aguardando…" FontSize="13" FontWeight="SemiBold" Foreground="#71717A" TextTrimming="CharacterEllipsis"/>
                                </Grid>

                                <Border Grid.Column="1" BorderBrush="#E4E4E7" BorderThickness="1,0,0,0"/>

                                <Grid Grid.Column="2" Margin="12,0,0,0">
                                    <Grid.RowDefinitions>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                    </Grid.RowDefinitions>
                                    <Grid.ColumnDefinitions>
                                        <ColumnDefinition Width="118"/>
                                        <ColumnDefinition Width="*"/>
                                    </Grid.ColumnDefinitions>

                                    <Grid Grid.Row="0" Grid.ColumnSpan="2" Margin="0,0,0,8">
                                        <TextBlock Text="llama.cpp" FontSize="13" FontWeight="SemiBold" Foreground="#111111"/>
                                        <CheckBox x:Name="ChkUpdateLlama" HorizontalAlignment="Right" VerticalAlignment="Center" Visibility="Collapsed"/>
                                    </Grid>

                                    <TextBlock Grid.Row="1" Grid.Column="0" Text="Versão instalada:" FontSize="13" Foreground="#52525B" Margin="0,0,0,10"/>
                                    <TextBlock Grid.Row="1" Grid.Column="1" x:Name="LblLlamaCurrent" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,10" TextTrimming="CharacterEllipsis"/>

                                    <TextBlock Grid.Row="2" Grid.Column="0" Text="Última disponível:" FontSize="13" Foreground="#52525B" Margin="0,0,0,10"/>
                                    <TextBlock Grid.Row="2" Grid.Column="1" x:Name="LblLlamaLatest" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,10" TextTrimming="CharacterEllipsis"/>

                                    <TextBlock Grid.Row="3" Grid.Column="0" Text="Status:" FontSize="13" Foreground="#52525B" Margin="0,0,0,0"/>
                                    <TextBlock Grid.Row="3" Grid.Column="1" x:Name="LblLlamaStatus" Text="Aguardando…" FontSize="13" FontWeight="SemiBold" Foreground="#71717A" TextTrimming="CharacterEllipsis"/>
                                </Grid>
                            </Grid>
                        </Grid>
                    </Border>
                </Grid>

                <!-- UPDATE PANEL -->
                <Grid x:Name="UpdatePanel" Visibility="Collapsed">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0">
                        <TextBlock x:Name="LblStep" Text="Preparando…" FontSize="13" Foreground="#71717A" Margin="0,4,0,0" Visibility="Collapsed"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="16,14" Margin="0,0,0,14">
                        <StackPanel>
                            <Grid>
                                <TextBlock x:Name="LblProgressTxt" Text="0%" FontSize="12" Foreground="#52525B" HorizontalAlignment="Right"/>
                                <TextBlock x:Name="LblPhase" Text="Iniciando" FontSize="12" Foreground="#52525B"/>
                            </Grid>
                            <ProgressBar x:Name="Progress" Height="6" Minimum="0" Maximum="100" Value="0" Margin="0,8,0,0"
                                         Foreground="#111111" Background="#F4F4F5" BorderThickness="0"/>
                        </StackPanel>
                    </Border>

                    <Border Grid.Row="2" Background="#0A0A0A" BorderBrush="#E4E4E7" BorderThickness="1" CornerRadius="10" Padding="14,12">
                        <ScrollViewer x:Name="LogScroll" VerticalScrollBarVisibility="Auto">
                            <TextBox x:Name="LogBox" Background="Transparent" Foreground="#D4D4D4" BorderThickness="0"
                                     IsReadOnly="True" FontFamily="Consolas" FontSize="11" TextWrapping="Wrap"
                                     AcceptsReturn="True" VerticalScrollBarVisibility="Disabled"/>
                        </ScrollViewer>
                    </Border>
                </Grid>

                <!-- DONE PANEL -->
                <Grid x:Name="DonePanel" Visibility="Collapsed">
                    <Border Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="32">
                        <StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
                            <Border Width="56" Height="56" CornerRadius="28" Background="#10B981" Margin="0,0,0,18">
                                <TextBlock Text="OK" FontSize="20" FontWeight="Bold" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                            <TextBlock x:Name="LblDoneTitle" Text="Atualização concluída!" FontSize="22" FontWeight="SemiBold" Foreground="#111111" HorizontalAlignment="Center"/>
                            <TextBlock x:Name="LblDoneSub" Text="Use iniciar.bat para iniciar a NeveAI." FontSize="13" Foreground="#71717A" HorizontalAlignment="Center" Margin="0,6,0,18"/>
                            <Border Background="#FAFAFA" CornerRadius="8" Padding="14,12">
                                <TextBlock x:Name="LblSummary" FontFamily="Consolas" FontSize="11" Foreground="#52525B"/>
                            </Border>
                        </StackPanel>
                    </Border>
                </Grid>

            </Grid>

            <!-- FOOTER -->
            <Border Grid.Row="2" BorderBrush="#EEEEEE" BorderThickness="0,1,0,0" Padding="32,0,32,0">
                <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" VerticalAlignment="Center">
                    <Button x:Name="BtnLlama" Style="{StaticResource AccentBtn}" Content="Atualizar llama.cpp" Margin="0,0,10,0" ToolTip="Atualização opcional, separada do NeveAI" Visibility="Collapsed"/>
                    <Button x:Name="BtnCancel" Style="{StaticResource GhostBtn}" Content="Cancelar" Margin="0,0,10,0" Visibility="Collapsed"/>
                    <Button x:Name="BtnPrimary" Style="{StaticResource PrimaryBtn}" Content="Atualizar" IsEnabled="False" Visibility="Collapsed"/>
                </StackPanel>
            </Border>
        </Grid>
    </Border>
</Window>
"@

# =============================================================================
# Carregar XAML
# =============================================================================
$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)

$ctl = @{}
foreach ($name in 'LogoImg','BtnClose',
                  'CheckPanel','UpdatePanel','DonePanel',
                  'LblCheckTitle','LblCheckSub','LblCurrent','LblLatest','LblStatus',
                  'LblLlamaCurrent','LblLlamaLatest','LblLlamaStatus',
                  'ChkUpdateNeve','ChkUpdateLlama',
                  'LblStep','LblPhase','LblProgressTxt','Progress','LogBox','LogScroll',
                  'LblDoneTitle','LblDoneSub','LblSummary',
                  'BtnLlama','BtnCancel','BtnPrimary') {
    $ctl[$name] = $window.FindName($name)
}

function Test-ReleaseTagValid([string]$tag) {
    $normalized = Normalize-ReleaseTag $tag
    return -not [string]::IsNullOrWhiteSpace($normalized) -and
        [regex]::IsMatch($normalized, '^\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?$')
}

$script:UpdateProcessList = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))
$script:UpdateControl = [hashtable]::Synchronized(@{
    CancelRequested = $false
    Processes = $script:UpdateProcessList
})
$script:UpdatePowerShell = $null
$script:UpdateRunspace = $null
$script:PendingUpdateCleanup = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))
$script:UpdateSelectedNeve = $false
$script:UpdateSelectedLlama = $false

# Logo
if (Test-Path $LOGO_PATH) {
    try {
        $bmp = New-Object System.Windows.Media.Imaging.BitmapImage
        $bmp.BeginInit()
        $bmp.UriSource = New-Object System.Uri($LOGO_PATH, [System.UriKind]::Absolute)
        $bmp.CacheOption = [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad
        $bmp.EndInit()
        $ctl.LogoImg.Source = $bmp
    } catch {}
}

$window.Add_MouseLeftButtonDown({
    param($s, $e)
    if ($e.ButtonState -eq 'Pressed') { try { $window.DragMove() } catch {} }
})

$script:ExitCode = 0
$window.Add_Closing({
    if ($ctl.BtnPrimary.Tag -eq 'error') { $script:ExitCode = 1 }
})
$ctl.BtnClose.Add_Click({
    if ($ctl.BtnPrimary.Tag -eq 'error') { $script:ExitCode = 1 }
    $window.Close()
})
$ctl.BtnCancel.Add_Click({ Request-UpdateCancel })

# =============================================================================
# Helpers de UI (chamáveis fora da thread principal via Dispatcher)
# =============================================================================
function Set-UI([scriptblock]$sb) { $window.Dispatcher.Invoke([Action]$sb) }

function Append-Log([string]$msg, [string]$kind = 'info') {
    $ts = (Get-Date).ToString('HH:mm:ss')
    $line = "[$ts] $msg"
    Add-Content -Path $LOG -Value $line -Encoding UTF8
    Set-UI {
        $ctl.LogBox.AppendText($line + "`r`n")
        $ctl.LogScroll.ScrollToEnd()
    }
}

function Set-Progress([int]$pct, [string]$phase) {
    Set-UI {
        $ctl.Progress.Value = $pct
        $ctl.LblProgressTxt.Text = "$pct%"
        if ($phase) { $ctl.LblPhase.Text = $phase; $ctl.LblStep.Text = $phase }
    }
}

function Test-NeveAppIntegrity([string]$root) {
    $required = @(
        @{ Path = 'instalar.bat'; Label = 'instalar.bat' },
        @{ Path = 'launchers\instalar.ps1'; Label = 'launchers\instalar.ps1' },
        @{ Path = 'launchers\instalar.vbs'; Label = 'launchers\instalar.vbs' },
        @{ Path = 'launchers\iniciar.ps1'; Label = 'launchers\iniciar.ps1' },
        @{ Path = 'launchers\iniciar.vbs'; Label = 'launchers\iniciar.vbs' },
        @{ Path = 'backend\neveai\__init__.py'; Label = 'pacote backend' },
        @{ Path = 'backend\neveai\main.py'; Label = 'backend main.py' },
        @{ Path = 'backend\neveai\routers\music_generation.py'; Label = 'geração musical' },
        @{ Path = 'backend\neveai\routers\video_generation.py'; Label = 'geração de vídeo' },
        @{ Path = 'backend\neveai\models\users.py'; Label = 'backend\neveai\models\users.py' },
        @{ Path = 'backend\neveai\models\models.py'; Label = 'backend\neveai\models\models.py' },
        @{ Path = 'backend\neveai\models\auths.py'; Label = 'backend\neveai\models\auths.py' },
        @{ Path = 'backend\neveai\routers\auths.py'; Label = 'backend\neveai\routers' },
        @{ Path = 'backend\neveai\utils\auth.py'; Label = 'backend\neveai\utils' }
    )

    $missing = @()
    foreach ($item in $required) {
        $path = Join-Path $root $item.Path
        if (-not (Test-Path -LiteralPath $path)) { $missing += $item.Label }
    }

    [pscustomobject]@{
        Ok      = $missing.Count -eq 0
        Missing = $missing
    }
}

function Update-PrimaryButtonState {
    $hasSelection = [bool]$ctl.ChkUpdateNeve.IsChecked -or [bool]$ctl.ChkUpdateLlama.IsChecked
    if ($hasSelection) {
        $ctl.BtnPrimary.Content = 'Atualizar'
        $ctl.BtnPrimary.Tag = 'update'
        $ctl.BtnPrimary.IsEnabled = $true
        $ctl.BtnPrimary.Visibility = 'Visible'
    } else {
        $ctl.BtnPrimary.IsEnabled = $false
        $ctl.BtnPrimary.Visibility = 'Collapsed'
    }
}

function Reset-UpdateSelectionView([bool]$completed) {
    $completedNeve = $completed -and [bool]$ctl.ChkUpdateNeve.IsChecked
    $completedLlama = $completed -and [bool]$ctl.ChkUpdateLlama.IsChecked

    if ($completedNeve) {
        $ctl.LblCurrent.Text = $ctl.LblLatest.Text
        $ctl.LblStatus.Text = 'Atualizado'
        $ctl.LblStatus.Foreground = '#10B981'
        $ctl.ChkUpdateNeve.Visibility = 'Collapsed'
    }
    if ($completedLlama) {
        $ctl.LblLlamaCurrent.Text = $ctl.LblLlamaLatest.Text
        $ctl.LblLlamaStatus.Text = 'Atualizado'
        $ctl.LblLlamaStatus.Foreground = '#10B981'
        $ctl.ChkUpdateLlama.Visibility = 'Collapsed'
    }

    $ctl.ChkUpdateNeve.IsChecked = $false
    $ctl.ChkUpdateLlama.IsChecked = $false
    $ctl.ChkUpdateNeve.IsEnabled = $true
    $ctl.ChkUpdateLlama.IsEnabled = $true
    $ctl.BtnLlama.IsEnabled = $true
    $ctl.BtnCancel.IsEnabled = $false
    $ctl.BtnCancel.Visibility = 'Collapsed'
    $ctl.DonePanel.Visibility = 'Collapsed'
    $ctl.UpdatePanel.Visibility = 'Collapsed'
    $ctl.CheckPanel.Visibility = 'Visible'

    $available = @($ctl.ChkUpdateNeve, $ctl.ChkUpdateLlama) |
        Where-Object { $_.Visibility -eq 'Visible' }
    if ($available.Count -eq 0) {
        $ctl.LblCheckTitle.Text = 'Você já está atualizado'
        $ctl.LblCheckSub.Text = 'Nenhuma atualização pendente para a NeveAI ou llama.cpp.'
    } else {
        $ctl.LblCheckTitle.Text = if ($available.Count -gt 1) { 'Atualizações disponíveis' } else { 'Atualização disponível' }
        $ctl.LblCheckSub.Text = if ($available.Count -gt 1) {
            'Marque uma ou mais atualizações para continuar.'
        } else {
            'Uma nova versão está pronta para ser instalada.'
        }
    }

    $ctl.BtnPrimary.Tag = $null
    Update-PrimaryButtonState
}

function Stop-RegisteredUpdateProcesses {
    foreach ($process in @($script:UpdateControl.Processes)) {
        try {
            if ($process -and -not $process.HasExited) { $process.Kill() }
        } catch {}
    }
    try { $script:UpdateControl.Processes.Clear() } catch {}
}

function Request-UpdateCancel {
    if ($ctl.UpdatePanel.Visibility -ne 'Visible') {
        Reset-UpdateSelectionView $false
        return
    }

    $restoreNeve = $script:UpdateSelectedNeve
    $restoreLlama = $script:UpdateSelectedLlama
    $script:UpdateControl.CancelRequested = $true
    $ctl.BtnCancel.IsEnabled = $false
    $ctl.BtnCancel.Content = 'Cancelando...'
    Stop-RegisteredUpdateProcesses
    $powerShellToStop = $script:UpdatePowerShell
    $runspaceToDispose = $script:UpdateRunspace
    $stopResult = $null
    try { if ($powerShellToStop) { $stopResult = $powerShellToStop.BeginStop($null, $null) } } catch {}
    if ($powerShellToStop -or $runspaceToDispose) {
        [void]$script:PendingUpdateCleanup.Add([pscustomobject]@{
            PowerShell = $powerShellToStop
            Runspace = $runspaceToDispose
            StopResult = $stopResult
        })
    }
    $script:UpdatePowerShell = $null
    $script:UpdateRunspace = $null
    $script:UpdateProcessList = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))
    $script:UpdateControl = [hashtable]::Synchronized(@{
        CancelRequested = $false
        Processes = $script:UpdateProcessList
    })
    $script:NeveAppCloseRequested = $false
    $ctl.BtnCancel.Content = 'Cancelar'
    Reset-UpdateSelectionView $false
    if ($restoreNeve -and $ctl.ChkUpdateNeve.Visibility -eq 'Visible') {
        $ctl.ChkUpdateNeve.IsChecked = $true
    }
    if ($restoreLlama -and $ctl.ChkUpdateLlama.Visibility -eq 'Visible') {
        $ctl.ChkUpdateLlama.IsChecked = $true
    }
    Update-PrimaryButtonState
}

function Complete-PendingUpdateCleanup {
    for ($index = $script:PendingUpdateCleanup.Count - 1; $index -ge 0; $index--) {
        $pending = $script:PendingUpdateCleanup[$index]
        $finished = $null -eq $pending.StopResult -or $pending.StopResult.IsCompleted
        if (-not $finished) { continue }
        try {
            if ($pending.PowerShell -and $pending.StopResult) {
                $pending.PowerShell.EndStop($pending.StopResult)
            }
        } catch {}
        try { if ($pending.PowerShell) { $pending.PowerShell.Dispose() } } catch {}
        try { if ($pending.Runspace) { $pending.Runspace.Dispose() } } catch {}
        $script:PendingUpdateCleanup.RemoveAt($index)
    }
}

$ctl.ChkUpdateNeve.Add_Checked({ Update-PrimaryButtonState })
$ctl.ChkUpdateNeve.Add_Unchecked({ Update-PrimaryButtonState })
$ctl.ChkUpdateLlama.Add_Checked({ Update-PrimaryButtonState })
$ctl.ChkUpdateLlama.Add_Unchecked({ Update-PrimaryButtonState })

# =============================================================================
# Worker separado: atualizacao opcional do llama.cpp
# =============================================================================
$ctl.BtnLlama.Add_Click({
    $script:UpdateSelectedNeve = [bool]$ctl.ChkUpdateNeve.IsChecked
    $script:UpdateSelectedLlama = [bool]$ctl.ChkUpdateLlama.IsChecked
    $script:UpdateControl.CancelRequested = $false
    try { $script:UpdateControl.Processes.Clear() } catch {}
    $ctl.CheckPanel.Visibility  = 'Collapsed'
    $ctl.DonePanel.Visibility   = 'Collapsed'
    $ctl.UpdatePanel.Visibility = 'Visible'
    $ctl.LogBox.Clear()
    $ctl.Progress.Value = 0
    $ctl.LblProgressTxt.Text = '0%'
    $ctl.LblPhase.Text = 'Preparando'
    $ctl.LblStep.Text = 'Preparando atualização do llama.cpp...'
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnLlama.IsEnabled   = $false
    $ctl.BtnCancel.Visibility = 'Visible'
    $ctl.BtnCancel.IsEnabled  = $true
    $ctl.BtnCancel.Content    = 'Cancelar'

    Stop-NeveRunningApp 'Atualizar llama.cpp'

    $argRoot      = $ROOT
    $argLog       = $LOG
    $argLlamaApi  = $LLAMA_API_RELEASES
    $argUa        = $UA

    $worker = {
        param($ROOT, $LOG, $LLAMA_API_RELEASES, $UA, $UPDATE_CONTROL)

        Set-Location -LiteralPath $ROOT

        function L([string]$m, [string]$k='info') {
            $ts = (Get-Date).ToString('HH:mm:ss')
            $line = "[$ts] $m"
            Add-Content -Path $LOG -Value $line -Encoding UTF8
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LogBox.AppendText($line + "`r`n")
                $script:Ctl.LogScroll.ScrollToEnd()
            })
        }
        function P([int]$v, [string]$phase) {
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.Progress.Value = $v
                $script:Ctl.LblProgressTxt.Text = "$v%"
                if ($phase) { $script:Ctl.LblPhase.Text = $phase; $script:Ctl.LblStep.Text = $phase }
            })
        }
        function Test-LlamaBackendCompatible([string]$requested, [string]$available) {
            if ([string]::IsNullOrWhiteSpace($requested) -or [string]::IsNullOrWhiteSpace($available)) { return $false }
            if ($requested -eq $available) { return $true }
            $requestedCuda = [regex]::Match($requested, '^cuda(?:-cu)?-?(\d+)(?:\.\d+)?$')
            $availableCuda = [regex]::Match($available, '^cuda(?:-cu)?-?(\d+)(?:\.\d+)?$')
            return ($requestedCuda.Success -and $availableCuda.Success -and $requestedCuda.Groups[1].Value -eq $availableCuda.Groups[1].Value)
        }
        function Get-LatestLlamaRelease([string[]]$backends) {
            $apiError = $null
            try {
                $releases = @((Invoke-RestMethod $LLAMA_API_RELEASES -Headers @{ 'User-Agent' = $UA; 'Accept' = 'application/vnd.github+json' } -TimeoutSec 30))
                foreach ($release in $releases) {
                    if ($release.draft -or -not $release.tag_name) { continue }
                    $tagEsc = [regex]::Escape([string]$release.tag_name)
                    foreach ($asset in @($release.assets)) {
                        $assetMatch = [regex]::Match([string]$asset.name, "^llama-$tagEsc-bin-win-(.+)-x64\.zip$")
                        if (-not $assetMatch.Success) { continue }
                        $availableBackend = $assetMatch.Groups[1].Value
                        foreach ($backend in $backends) {
                            if (Test-LlamaBackendCompatible $backend $availableBackend) { return $release }
                        }
                    }
                }
                throw 'Nenhuma release recente do llama.cpp contém os binários Windows necessários.'
            } catch {
                $apiError = $_
            }

            try {
                $feed = Invoke-WebRequest 'https://github.com/ggml-org/llama.cpp/releases.atom' -Headers @{ 'User-Agent' = $UA } -UseBasicParsing -TimeoutSec 30
                $seenTags = @{}
                foreach ($match in [regex]::Matches([string]$feed.Content, '/releases/tag/([^"<]+)')) {
                    $tag = [uri]::UnescapeDataString($match.Groups[1].Value).Trim()
                    if (-not $tag -or $seenTags.ContainsKey($tag)) { continue }
                    $seenTags[$tag] = $true

                    foreach ($backend in $backends) {
                        $mainAsset = New-LlamaReleaseAsset $tag "llama-$tag-bin-win-$backend-x64.zip"
                        if (-not (Test-ReleaseAssetUrl $mainAsset.browser_download_url)) { continue }

                        $assets = @($mainAsset)
                        if ($backend -match '^cuda') {
                            $runtimeAsset = New-LlamaReleaseAsset $tag "cudart-llama-bin-win-$backend-x64.zip"
                            if (Test-ReleaseAssetUrl $runtimeAsset.browser_download_url) { $assets += $runtimeAsset }
                        }

                        L '[!] GitHub API limitada; usando o feed de releases compatíveis.' 'warn'
                        return [pscustomobject]@{ tag_name = $tag; assets = $assets; prerelease = $true; draft = $false; is_fallback = $true }
                    }
                }
            } catch {}

            throw "Não foi possível localizar uma release compatível do llama.cpp: $apiError"
        }
        function New-LlamaReleaseAsset([string]$tag, [string]$name) {
            [pscustomobject]@{
                name = $name
                size = 0
                browser_download_url = "https://github.com/ggml-org/llama.cpp/releases/download/$([uri]::EscapeDataString($tag))/$([uri]::EscapeDataString($name))"
            }
        }
        function Test-ReleaseAssetUrl([string]$url) {
            try {
                $request = [System.Net.HttpWebRequest]::Create($url)
                $request.Method = 'HEAD'
                $request.AllowAutoRedirect = $true
                $request.UserAgent = $UA
                $request.Timeout = 15000
                $response = $request.GetResponse()
                try {
                    $statusCode = [int]$response.StatusCode
                    return ($statusCode -ge 200 -and $statusCode -lt 400)
                } finally {
                    $response.Close()
                }
            } catch {
                return $false
            }
        }
        function New-LlamaTarget([string]$vendor, [string]$name, [string]$label, [string[]]$backends, [string]$reason) {
            [pscustomobject]@{
                Vendor   = $vendor
                Name     = $name
                Label    = $label
                Backends = $backends
                Reason   = $reason
            }
        }
        function Convert-ToInvariantDouble([string]$value) {
            if ([string]::IsNullOrWhiteSpace($value)) { return $null }
            try {
                return [double]::Parse(($value.Trim() -replace ',', '.'), [System.Globalization.CultureInfo]::InvariantCulture)
            } catch {
                return $null
            }
        }
        function Get-LlamaHardwareTarget {
            $nvidiaLine = $null
            try {
                $nvidiaOut = nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader 2>&1
                if ($LASTEXITCODE -eq 0 -and "$nvidiaOut" -notmatch 'failed|not found|invalid') {
                    $nvidiaLine = ("$nvidiaOut" -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
                }
            } catch {}

            if (-not $nvidiaLine) {
                try {
                    $nvidiaOut = nvidia-smi --query-gpu=name --format=csv,noheader 2>&1
                    if ($LASTEXITCODE -eq 0 -and "$nvidiaOut" -notmatch 'failed|not found|invalid') {
                        $nameOnly = ("$nvidiaOut" -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
                        if ($nameOnly) { $nvidiaLine = $nameOnly }
                    }
                } catch {}
            }

            if ($nvidiaLine) {
                $parts = $nvidiaLine -split ','
                $name = $parts[0].Trim()
                $computeCap = $null
                if ($parts.Count -gt 1) { $computeCap = Convert-ToInvariantDouble $parts[1] }

                if ($computeCap -ne $null -and $computeCap -lt 5.0) {
                    return New-LlamaTarget 'CPU' $name 'CPU (GPU NVIDIA sem suporte CUDA moderno)' @('cpu') "GPU NVIDIA detectada ($name), mas compute capability $computeCap não é suportada pelos binários CUDA atuais."
                }

                if ($name -match 'RTX\s*5\d{3}|50\d{2}|Blackwell' -or ($computeCap -ne $null -and $computeCap -ge 12.0)) {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 13' @('cuda-13.4','cuda-cu13.4','cuda-13.3','cuda-cu13.3') "GPU NVIDIA Blackwell detectada: $name."
                }

                if ($computeCap -ne $null -and $computeCap -ge 5.0) {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 12.4' @('cuda-12.4','cuda-cu12.4') "GPU NVIDIA compatível com CUDA 12 detectada: $name."
                }

                if ($name -match 'RTX\s*[234]\d{3}|[234]0\d{2}|GTX\s*16\d{2}|GTX\s*10\d{2}|GTX\s*9\d{2}|Quadro|Tesla|RTX\s*A') {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 12.4' @('cuda-12.4','cuda-cu12.4') "GPU NVIDIA reconhecida por geração: $name."
                }

                throw "GPU NVIDIA detectada ($name), mas não foi possível determinar com segurança o binário CUDA correto. Nada foi instalado."
            }

            try {
                $gpus = Get-CimInstance Win32_VideoController -EA SilentlyContinue
                $amdGpu = $gpus | Where-Object { $_.Name -match 'AMD|Radeon|RX\s' } |
                    Sort-Object @{ Expression = { if ($_.Name -match '\bRX\s*\d|Radeon\s+Pro\b') { 0 } elseif ($_.Name -match 'Vega\s*\d+\s*Graphics|Radeon(?:\(TM\))?\s+Graphics') { 2 } else { 1 } } },
                                @{ Expression = { [long]$_.AdapterRAM }; Descending = $true } | Select-Object -First 1
                if ($amdGpu) {
                    return New-LlamaTarget 'AMD' $amdGpu.Name.Trim() 'AMD Vulkan' @('vulkan') "GPU AMD detectada: $($amdGpu.Name.Trim())."
                }
            } catch {}

            return New-LlamaTarget 'CPU' '' 'CPU' @('cpu') 'Nenhuma GPU NVIDIA/AMD compatível foi detectada.'
        }
        function Find-LlamaBinAsset($assets, [string]$tag, [string[]]$backends) {
            $tagEsc = [regex]::Escape($tag)
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^llama-$tagEsc-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^llama-.+-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($asset in @($assets)) {
                $assetMatch = [regex]::Match([string]$asset.name, '^llama-.+-bin-win-(.+)-x64\.zip$')
                if (-not $assetMatch.Success) { continue }
                foreach ($backend in $backends) {
                    if (Test-LlamaBackendCompatible $backend $assetMatch.Groups[1].Value) { return $asset }
                }
            }
            foreach ($backend in $backends) {
                $asset = New-LlamaReleaseAsset $tag "llama-$tag-bin-win-$backend-x64.zip"
                if (Test-ReleaseAssetUrl $asset.browser_download_url) { return $asset }
            }
            return $null
        }
        function Find-CudaRuntimeAsset($assets, [string]$tag, [string[]]$backends) {
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^cudart-llama-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($asset in @($assets)) {
                $assetMatch = [regex]::Match([string]$asset.name, '^cudart-llama-bin-win-(.+)-x64\.zip$')
                if (-not $assetMatch.Success) { continue }
                foreach ($backend in $backends) {
                    if (Test-LlamaBackendCompatible $backend $assetMatch.Groups[1].Value) { return $asset }
                }
            }
            foreach ($backend in $backends) {
                $asset = New-LlamaReleaseAsset $tag "cudart-llama-bin-win-$backend-x64.zip"
                if (Test-ReleaseAssetUrl $asset.browser_download_url) { return $asset }
            }
            return $null
        }
        function Get-InstalledLlamaInfo([string]$root) {
            $versionPath = Join-Path $root 'llamacpp-server\version.txt'
            $tag = ''
            $backend = ''
            $asset = ''
            if (Test-Path $versionPath) {
                $lines = @(Get-Content $versionPath -EA SilentlyContinue)
                if ($lines.Count -gt 0) { $tag = $lines[0].Trim() }
                if ($lines.Count -gt 1) { $backend = $lines[1].Trim() }
                if ($lines.Count -gt 2) { $asset = $lines[2].Trim() }
            }
            [pscustomobject]@{
                Tag = $tag
                Backend = $backend
                Asset = $asset
            }
        }

        $tmpFiles = @()
        $stageDir = $null
        $backupDir = $null
        try {
            P 5 'Detectando hardware'
            $target = Get-LlamaHardwareTarget
            L "[OK] Alvo selecionado: $($target.Label)"
            if ($target.Name) { L "    Hardware: $($target.Name)" }
            if ($target.Reason) { L "    $($target.Reason)" }

            P 10 'Consultando releases do llama.cpp'
            $rel = Get-LatestLlamaRelease ([string[]]$target.Backends)
            $tag = $rel.tag_name
            if (-not $tag) { throw 'Release do llama.cpp sem tag_name.' }
            L "[OK] Última release compatível: $tag"

            $installed = Get-InstalledLlamaInfo $ROOT
            if ($installed.Tag -and $installed.Tag -eq $tag) {
                P 100 'llama.cpp atualizado'
                L "[OK] llama.cpp já está na última release ($tag). Nenhum download necessário."

                $summary = "Release instalada: $($installed.Tag)`r`nÚltima disponível: $tag`r`nStatus: atualizado"
                if ($installed.Backend) { $summary += "`r`nBackend: $($installed.Backend)" }
                if ($installed.Asset) { $summary += "`r`nAsset:   $($installed.Asset)" }

                $script:Window.Dispatcher.Invoke([Action]{
                    $script:Ctl.UpdatePanel.Visibility = 'Collapsed'
                    $script:Ctl.DonePanel.Visibility   = 'Visible'
                    $script:Ctl.LblDoneTitle.Text = 'llama.cpp já está atualizado'
                    $script:Ctl.LblDoneSub.Text   = 'A versão instalada já é a última release disponível.'
                    $script:Ctl.LblSummary.Text   = $summary
                    $script:Ctl.BtnPrimary.Content   = 'Concluir'
                    $script:Ctl.BtnPrimary.Tag       = 'done'
                    $script:Ctl.BtnPrimary.IsEnabled = $true
                    $script:Ctl.BtnLlama.IsEnabled   = $false
                    $script:Ctl.BtnCancel.Visibility = 'Collapsed'
                    $script:Ctl.BtnCancel.IsEnabled  = $false
                })
                return
            }

            $mainAsset = Find-LlamaBinAsset $rel.assets $tag ([string[]]$target.Backends)
            if (-not $mainAsset) {
                throw "O release $tag não contém um asset Windows x64 para $($target.Label). Nada foi instalado."
            }

            $isCuda = (@($target.Backends) | Where-Object { $_ -match '^cuda' } | Select-Object -First 1) -ne $null
            $runtimeAsset = $null
            if ($isCuda) { $runtimeAsset = Find-CudaRuntimeAsset $rel.assets $tag ([string[]]$target.Backends) }

            P 28 'Baixando binários'
            $tmpMain = Join-Path $env:TEMP "neve_llama_$([guid]::NewGuid().ToString('N')).zip"
            $tmpFiles += $tmpMain
            $sizeMB = [math]::Round($mainAsset.size / 1MB, 1)
            L "==> Baixando $($mainAsset.name) ($sizeMB MB)"
            Invoke-WebRequest $mainAsset.browser_download_url -OutFile $tmpMain -UseBasicParsing -Headers @{ 'User-Agent' = $UA }

            $tmpRuntime = $null
            if ($runtimeAsset) {
                $tmpRuntime = Join-Path $env:TEMP "neve_llama_cudart_$([guid]::NewGuid().ToString('N')).zip"
                $tmpFiles += $tmpRuntime
                $runtimeMB = [math]::Round($runtimeAsset.size / 1MB, 1)
                L "==> Baixando $($runtimeAsset.name) ($runtimeMB MB)"
                Invoke-WebRequest $runtimeAsset.browser_download_url -OutFile $tmpRuntime -UseBasicParsing -Headers @{ 'User-Agent' = $UA }
            } elseif ($isCuda) {
                L '[!] Runtime CUDA separado não encontrado no release; prosseguindo apenas com o pacote principal.' 'warn'
            }

            P 45 'Extraindo e validando'
            $stageDir = Join-Path $env:TEMP "neve_llama_stage_$([guid]::NewGuid().ToString('N'))"
            New-Item $stageDir -ItemType Directory -Force | Out-Null
            Expand-Archive $tmpMain -DestinationPath $stageDir -Force
            if ($tmpRuntime) { Expand-Archive $tmpRuntime -DestinationPath $stageDir -Force }
            $serverExe = Get-ChildItem $stageDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1
            if (-not $serverExe) { throw 'O pacote baixado não contém llama-server.exe.' }
            $stagedFiles = Get-ChildItem $stageDir -Recurse -File
            if (-not $stagedFiles) { throw 'Nenhum arquivo extraído do pacote do llama.cpp.' }
            L "[OK] Pacote validado ($($stagedFiles.Count) arquivos)"

            P 62 'Preparando troca segura'
            $llamaRoot = Join-Path $ROOT 'llamacpp-server'
            $llamaDir = Join-Path $llamaRoot 'bin'
            if (-not (Test-Path $llamaRoot)) { New-Item $llamaRoot -ItemType Directory -Force | Out-Null }
            if (-not (Test-Path $llamaDir)) { New-Item $llamaDir -ItemType Directory -Force | Out-Null }
            $backupDir = Join-Path $env:TEMP "neve_llama_backup_$([guid]::NewGuid().ToString('N'))"
            New-Item $backupDir -ItemType Directory -Force | Out-Null
            Get-ChildItem $llamaDir -Force -EA SilentlyContinue | ForEach-Object {
                Copy-Item $_.FullName $backupDir -Recurse -Force
            }
            L '[OK] Backup temporário criado'

            try {
                Get-Process llama-server -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
                Get-ChildItem $llamaDir -File -EA SilentlyContinue |
                    Where-Object { $_.Extension -in '.exe','.dll','.pdb' } |
                    Remove-Item -Force -EA Stop

                foreach ($file in $stagedFiles) {
                    Copy-Item $file.FullName $llamaDir -Force -EA Stop
                }

                if (-not (Test-Path (Join-Path $llamaDir 'llama-server.exe'))) {
                    throw 'llama-server.exe não ficou disponível após a cópia.'
                }
            } catch {
                $replaceError = $_
                L "[!] Falha ao aplicar binários; restaurando backup: $replaceError" 'warn'
                try {
                    Get-ChildItem $llamaDir -Force -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue
                    Get-ChildItem $backupDir -Force -EA SilentlyContinue | ForEach-Object {
                        Copy-Item $_.FullName $llamaDir -Recurse -Force
                    }
                    L '[OK] Backup restaurado'
                } catch {
                    L "[!] Falha ao restaurar backup automaticamente: $_" 'warn'
                }
                throw $replaceError
            }

            P 90 'Registrando versão'
            Set-Content -Path (Join-Path $llamaRoot 'version.txt') -Value @(
                $tag,
                $target.Label,
                $mainAsset.name
            ) -Encoding UTF8

            P 100 'llama.cpp atualizado'
            L "[OK] llama.cpp $tag instalado em llamacpp-server\bin"

            $summary = "Release: $tag`r`nBackend: $($target.Label)`r`nAsset:   $($mainAsset.name)"
            if ($runtimeAsset) { $summary += "`r`nRuntime: $($runtimeAsset.name)" }
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.UpdatePanel.Visibility = 'Collapsed'
                $script:Ctl.DonePanel.Visibility   = 'Visible'
                $script:Ctl.LblDoneTitle.Text = 'llama.cpp atualizado!'
                $script:Ctl.LblDoneSub.Text   = 'Atualização opcional concluída sem alterar o projeto principal.'
                $script:Ctl.LblSummary.Text   = $summary
                $script:Ctl.BtnPrimary.Content   = 'Concluir'
                $script:Ctl.BtnPrimary.Tag       = 'done'
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnLlama.IsEnabled   = $false
                $script:Ctl.BtnCancel.Visibility = 'Collapsed'
                $script:Ctl.BtnCancel.IsEnabled  = $false
            })
        } catch {
            if ($UPDATE_CONTROL -and $UPDATE_CONTROL.CancelRequested) { return }
            $errMsg = "$_"
            L "[X] FALHA: $errMsg" 'err'
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LblStep.Text = 'Falha ao atualizar llama.cpp.'
                $script:Ctl.BtnPrimary.Content   = 'Fechar'
                $script:Ctl.BtnPrimary.Tag       = 'error'
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnLlama.IsEnabled   = $true
                $script:Ctl.BtnCancel.Visibility = 'Collapsed'
                $script:Ctl.BtnCancel.IsEnabled  = $false
                [System.Windows.MessageBox]::Show(
                    "A atualização do llama.cpp falhou.`r`n`r`nVeja o log em logs\update.log`r`n`r`n$errMsg",
                    'NeveAI - Atualizador',
                    [System.Windows.MessageBoxButton]::OK,
                    [System.Windows.MessageBoxImage]::Error) | Out-Null
            })
        } finally {
            foreach ($tmp in $tmpFiles) { try { Remove-Item $tmp -Force -EA SilentlyContinue } catch {} }
            if ($stageDir) { try { Remove-Item $stageDir -Recurse -Force -EA SilentlyContinue } catch {} }
            if ($backupDir) { try { Remove-Item $backupDir -Recurse -Force -EA SilentlyContinue } catch {} }
        }
    }

    $rs = [RunspaceFactory]::CreateRunspace()
    $rs.ApartmentState = 'STA'
    $rs.ThreadOptions  = 'ReuseThread'
    $rs.Open()
    $rs.SessionStateProxy.SetVariable('Window', $window)
    $rs.SessionStateProxy.SetVariable('Ctl',    $ctl)

    $ps = [PowerShell]::Create()
    $ps.Runspace = $rs
    [void]$ps.AddScript($worker)
    [void]$ps.AddArgument($argRoot)
    [void]$ps.AddArgument($argLog)
    [void]$ps.AddArgument($argLlamaApi)
    [void]$ps.AddArgument($argUa)
    [void]$ps.AddArgument($script:UpdateControl)
    $script:UpdatePowerShell = $ps
    $script:UpdateRunspace = $rs
    [void]$ps.BeginInvoke()
})

# =============================================================================
# Versão instalada
# =============================================================================
$currentVersion = 'desconhecida'
if (Test-Path $VERSION_FILE) {
    $currentVersion = (Get-Content $VERSION_FILE -Raw).Trim()
    if (-not $currentVersion) { $currentVersion = 'desconhecida' }
}

$llamaVersionFile = Join-Path $ROOT 'llamacpp-server\version.txt'
$llamaInstalledTag = ''
$llamaInstalledBackend = ''
$llamaInstalledAsset = ''
if (Test-Path $llamaVersionFile) {
    $llamaLines = @(Get-Content $llamaVersionFile -EA SilentlyContinue)
    if ($llamaLines.Count -gt 0) { $llamaInstalledTag = $llamaLines[0].Trim() }
    if ($llamaLines.Count -gt 1) { $llamaInstalledBackend = $llamaLines[1].Trim() }
    if ($llamaLines.Count -gt 2) { $llamaInstalledAsset = $llamaLines[2].Trim() }
}

$llamaCurrentDisplay = 'Não instalado'
if ($llamaInstalledTag) {
    $llamaCurrentDisplay = $llamaInstalledTag
    if ($llamaInstalledBackend) { $llamaCurrentDisplay = "$llamaInstalledTag ($llamaInstalledBackend)" }
}

# =============================================================================
# Consulta a release mais recente (síncrono, antes de mostrar)
# =============================================================================
$latestTag   = $null
$releaseObj  = $null
$checkError  = $null
$llamaLatestTag = $null
$llamaReleaseObj = $null
$llamaCheckError = $null
try {
    $releaseObj = Get-GitHubLatestRelease $REPO_OWNER $REPO_NAME
    $latestTag  = $releaseObj.tag_name
    if (-not (Test-ReleaseTagValid $latestTag)) {
        throw "O GitHub retornou uma versão inválida: '$latestTag'."
    }
} catch {
    $checkError = Get-FriendlyGitHubError $_
}
try {
    $llamaPreferredBackends = @()
    if ($llamaInstalledAsset -match '-bin-win-(.+)-x64\.zip$') {
        $llamaPreferredBackends = @($matches[1])
    } elseif ($llamaInstalledBackend -in @('cpu', 'cuda-12.4', 'cuda-13.3', 'cuda-13.4', 'cuda-cu12.4', 'cuda-cu13.3', 'cuda-cu13.4', 'vulkan')) {
        $llamaPreferredBackends = @($llamaInstalledBackend)
    }
    $llamaReleaseObj = Get-GitHubLatestLlamaRelease ([string[]]$llamaPreferredBackends)
    $llamaLatestTag  = $llamaReleaseObj.tag_name
} catch {
    $llamaCheckError = Get-FriendlyGitHubError $_
}

$appIntegrity = Test-NeveAppIntegrity $ROOT

$ctl.LblCurrent.Text = $currentVersion
if ($checkError) {
    $ctl.LblCheckTitle.Text = 'Falha ao verificar atualizações'
    $ctl.LblCheckSub.Text   = $checkError
    $ctl.LblLatest.Text     = '—'
    $ctl.LblStatus.Text     = 'Erro de rede'
    $ctl.LblStatus.Foreground = '#DC2626'
    $ctl.ChkUpdateNeve.Visibility = 'Collapsed'
} else {
    $ctl.LblLatest.Text = $latestTag
    $notes = $releaseObj.body
    if ([string]::IsNullOrWhiteSpace($notes)) { $notes = '(sem notas de release)' }
    if (-not $appIntegrity.Ok) {
        $notes = "Instalação local incompleta. O atualizador vai reparar a partir do release do GitHub.`r`nFaltando: $($appIntegrity.Missing -join ', ')`r`n`r`n$notes"
    }
    $currentVersionValid = Test-ReleaseTagValid $currentVersion
    $sameNeveVersion = $currentVersionValid -and (Normalize-ReleaseTag $currentVersion) -eq (Normalize-ReleaseTag $latestTag)
    $hasNeveUpdate = (-not $currentVersionValid) -or (Test-ReleaseTagNewer $currentVersion $latestTag)
    if ($sameNeveVersion -and $appIntegrity.Ok) {
        $ctl.LblStatus.Text     = 'Atualizado'
        $ctl.LblStatus.Foreground = '#10B981'
        $ctl.ChkUpdateNeve.Visibility = 'Collapsed'
    } elseif ($sameNeveVersion -and -not $appIntegrity.Ok) {
        $ctl.LblStatus.Text     = 'Reparo necessário'
        $ctl.LblStatus.Foreground = '#D97706'
        $ctl.ChkUpdateNeve.Visibility = 'Visible'
        $ctl.ChkUpdateNeve.IsChecked = $true
    } elseif ($hasNeveUpdate -or -not $appIntegrity.Ok) {
        $ctl.LblStatus.Text     = 'Pendente'
        $ctl.LblStatus.Foreground = '#D97706'
        $ctl.ChkUpdateNeve.Visibility = 'Visible'
        $ctl.ChkUpdateNeve.IsChecked = $false
    } else {
        $ctl.LblStatus.Text     = 'Atualizado'
        $ctl.LblStatus.Foreground = '#10B981'
        $ctl.ChkUpdateNeve.Visibility = 'Collapsed'
    }
}

$ctl.LblLlamaCurrent.Text = $llamaCurrentDisplay
if ($llamaCheckError) {
    $ctl.LblLlamaLatest.Text = '—'
    $ctl.LblLlamaStatus.Text = 'Erro ao verificar'
    $ctl.LblLlamaStatus.Foreground = '#DC2626'
    $ctl.ChkUpdateLlama.Visibility = 'Collapsed'
} else {
    $ctl.LblLlamaLatest.Text = $llamaLatestTag
    if ($llamaInstalledTag -and ((Normalize-ReleaseTag $llamaInstalledTag) -eq (Normalize-ReleaseTag $llamaLatestTag))) {
        $ctl.LblLlamaStatus.Text = 'Atualizado'
        $ctl.LblLlamaStatus.Foreground = '#10B981'
        $ctl.ChkUpdateLlama.Visibility = 'Collapsed'
    } elseif ($llamaInstalledTag -and (Test-ReleaseTagNewer $llamaInstalledTag $llamaLatestTag)) {
        $ctl.LblLlamaStatus.Text = 'Pendente'
        $ctl.LblLlamaStatus.Foreground = '#D97706'
        $ctl.ChkUpdateLlama.Visibility = 'Visible'
        $ctl.ChkUpdateLlama.IsChecked = $false
    } elseif ($llamaInstalledTag) {
        $ctl.LblLlamaStatus.Text = 'Atualizado'
        $ctl.LblLlamaStatus.Foreground = '#10B981'
        $ctl.ChkUpdateLlama.Visibility = 'Collapsed'
    } else {
        $ctl.LblLlamaStatus.Text = 'Não instalado'
        $ctl.LblLlamaStatus.Foreground = '#D97706'
        $ctl.ChkUpdateLlama.Visibility = 'Visible'
        $ctl.ChkUpdateLlama.IsChecked = $false
    }
}

if ($ctl.ChkUpdateNeve.Visibility -eq 'Visible' -and $ctl.ChkUpdateLlama.Visibility -eq 'Visible') {
    $ctl.LblCheckTitle.Text = 'Atualizações disponíveis'
    $ctl.LblCheckSub.Text = 'Marque uma ou mais atualizações para continuar.'
} elseif ($ctl.ChkUpdateNeve.Visibility -eq 'Visible') {
    if (((Normalize-ReleaseTag $currentVersion) -eq (Normalize-ReleaseTag $latestTag)) -and -not $appIntegrity.Ok) {
        $ctl.LblCheckTitle.Text = 'Reparo disponível'
        $ctl.LblCheckSub.Text = 'Arquivos locais estão faltando; o release do GitHub será reaplicado.'
    } else {
        $ctl.LblCheckTitle.Text = 'Atualização disponível'
        $ctl.LblCheckSub.Text = 'Uma nova versão está pronta para ser instalada.'
    }
} elseif ($ctl.ChkUpdateLlama.Visibility -eq 'Visible') {
    $ctl.LblCheckTitle.Text = 'Atualização disponível'
    $ctl.LblCheckSub.Text = 'Uma nova versão está pronta para ser instalada.'
} elseif (-not $checkError -and -not $llamaCheckError) {
    $ctl.LblCheckTitle.Text = 'Você já está atualizado'
    $ctl.LblCheckSub.Text = 'Nenhuma atualização pendente para a NeveAI ou llama.cpp.'
}

Update-PrimaryButtonState

# =============================================================================
# Worker da atualização combinada (NeveAI -> llama.cpp)
# =============================================================================
$ctl.BtnPrimary.Add_Click({
    $tag = $ctl.BtnPrimary.Tag
    if ($tag -in @('error', 'close', 'done')) {
        Reset-UpdateSelectionView ($tag -eq 'done')
        return
    }
    if ($tag -ne 'update') { return }

    $updateNeve  = [bool]$ctl.ChkUpdateNeve.IsChecked
    $updateLlama = [bool]$ctl.ChkUpdateLlama.IsChecked
    if (-not $updateNeve -and -not $updateLlama) { return }

    $script:UpdateSelectedNeve = $updateNeve
    $script:UpdateSelectedLlama = $updateLlama
    $script:UpdateControl.CancelRequested = $false
    try { $script:UpdateControl.Processes.Clear() } catch {}
    $ctl.CheckPanel.Visibility   = 'Collapsed'
    $ctl.UpdatePanel.Visibility  = 'Visible'
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnLlama.IsEnabled   = $false
    $ctl.BtnCancel.Visibility = 'Visible'
    $ctl.BtnCancel.IsEnabled  = $true
    $ctl.BtnCancel.Content    = 'Cancelar'
    $ctl.ChkUpdateNeve.IsEnabled = $false
    $ctl.ChkUpdateLlama.IsEnabled = $false

    Stop-NeveRunningApp 'Atualizar'

    $argUpdateNeve   = $updateNeve
    $argUpdateLlama  = $updateLlama
    $argLatestTag    = $latestTag
    $argZipUrl       = if ($releaseObj) { $releaseObj.zipball_url } else { $null }
    $argRoot         = $ROOT
    $argLog          = $LOG
    $argVersionFile  = $VERSION_FILE
    $argCurrent      = $currentVersion
    $argLlamaApi     = $LLAMA_API_RELEASES
    $argUa           = $UA

    $worker = {
        param($updateNeve, $updateLlama, $latestTag, $zipUrl, $ROOT, $LOG, $VERSION_FILE, $currentVersion, $LLAMA_API_RELEASES, $UA, $UPDATE_CONTROL)

        Set-Location -LiteralPath $ROOT

        function L([string]$m, [string]$k='info') {
            $ts = (Get-Date).ToString('HH:mm:ss')
            $line = "[$ts] $m"
            Add-Content -Path $LOG -Value $line -Encoding UTF8
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LogBox.AppendText($line + "`r`n")
                $script:Ctl.LogScroll.ScrollToEnd()
            })
        }
        function P([int]$v, [string]$phase) {
            if ($v -lt 0) { $v = 0 }
            if ($v -gt 100) { $v = 100 }
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.Progress.Value = $v
                $script:Ctl.LblProgressTxt.Text = "$v%"
                if ($phase) { $script:Ctl.LblPhase.Text = $phase; $script:Ctl.LblStep.Text = $phase }
            })
        }
        function PN([int]$v, [string]$phase) {
            if ($updateLlama) { P ([int][math]::Round($v * 0.70)) $phase } else { P $v $phase }
        }
        function PL([int]$v, [string]$phase) {
            if ($updateNeve) { P (70 + [int][math]::Round($v * 0.30)) $phase } else { P $v $phase }
        }
        function Test-LlamaBackendCompatible([string]$requested, [string]$available) {
            if ([string]::IsNullOrWhiteSpace($requested) -or [string]::IsNullOrWhiteSpace($available)) { return $false }
            if ($requested -eq $available) { return $true }
            $requestedCuda = [regex]::Match($requested, '^cuda(?:-cu)?-?(\d+)(?:\.\d+)?$')
            $availableCuda = [regex]::Match($available, '^cuda(?:-cu)?-?(\d+)(?:\.\d+)?$')
            return ($requestedCuda.Success -and $availableCuda.Success -and $requestedCuda.Groups[1].Value -eq $availableCuda.Groups[1].Value)
        }
        function Get-LatestLlamaRelease([string[]]$backends) {
            $apiError = $null
            try {
                $releases = @((Invoke-RestMethod $LLAMA_API_RELEASES -Headers @{ 'User-Agent' = $UA; 'Accept' = 'application/vnd.github+json' } -TimeoutSec 30))
                foreach ($release in $releases) {
                    if ($release.draft -or -not $release.tag_name) { continue }
                    $tagEsc = [regex]::Escape([string]$release.tag_name)
                    foreach ($asset in @($release.assets)) {
                        $assetMatch = [regex]::Match([string]$asset.name, "^llama-$tagEsc-bin-win-(.+)-x64\.zip$")
                        if (-not $assetMatch.Success) { continue }
                        $availableBackend = $assetMatch.Groups[1].Value
                        foreach ($backend in $backends) {
                            if (Test-LlamaBackendCompatible $backend $availableBackend) { return $release }
                        }
                    }
                }
                throw 'Nenhuma release recente do llama.cpp contém os binários Windows necessários.'
            } catch {
                $apiError = $_
            }

            try {
                $feed = Invoke-WebRequest 'https://github.com/ggml-org/llama.cpp/releases.atom' -Headers @{ 'User-Agent' = $UA } -UseBasicParsing -TimeoutSec 30
                $seenTags = @{}
                foreach ($match in [regex]::Matches([string]$feed.Content, '/releases/tag/([^"<]+)')) {
                    $tag = [uri]::UnescapeDataString($match.Groups[1].Value).Trim()
                    if (-not $tag -or $seenTags.ContainsKey($tag)) { continue }
                    $seenTags[$tag] = $true

                    foreach ($backend in $backends) {
                        $mainAsset = New-LlamaReleaseAsset $tag "llama-$tag-bin-win-$backend-x64.zip"
                        if (-not (Test-ReleaseAssetUrl $mainAsset.browser_download_url)) { continue }

                        $assets = @($mainAsset)
                        if ($backend -match '^cuda') {
                            $runtimeAsset = New-LlamaReleaseAsset $tag "cudart-llama-bin-win-$backend-x64.zip"
                            if (Test-ReleaseAssetUrl $runtimeAsset.browser_download_url) { $assets += $runtimeAsset }
                        }

                        L '[!] GitHub API limitada; usando o feed de releases compatíveis.' 'warn'
                        return [pscustomobject]@{ tag_name = $tag; assets = $assets; prerelease = $true; draft = $false; is_fallback = $true }
                    }
                }
            } catch {}

            throw "Não foi possível localizar uma release compatível do llama.cpp: $apiError"
        }
        function New-LlamaReleaseAsset([string]$tag, [string]$name) {
            [pscustomobject]@{
                name = $name
                size = 0
                browser_download_url = "https://github.com/ggml-org/llama.cpp/releases/download/$([uri]::EscapeDataString($tag))/$([uri]::EscapeDataString($name))"
            }
        }
        function Test-ReleaseAssetUrl([string]$url) {
            try {
                $request = [System.Net.HttpWebRequest]::Create($url)
                $request.Method = 'HEAD'
                $request.AllowAutoRedirect = $true
                $request.UserAgent = $UA
                $request.Timeout = 15000
                $response = $request.GetResponse()
                try {
                    $statusCode = [int]$response.StatusCode
                    return ($statusCode -ge 200 -and $statusCode -lt 400)
                } finally {
                    $response.Close()
                }
            } catch {
                return $false
            }
        }
        function ConvertTo-ProcessArgument([string]$arg) {
            if ($null -eq $arg) { throw 'Argumento nulo.' }
            if ($arg.Length -gt 0 -and $arg -notmatch '[\s"]') { return $arg }
            $escaped = [regex]::Replace($arg, '(\\*)"', '$1$1\"')
            $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
            return '"' + $escaped + '"'
        }
        function Run([string]$exe, [string[]]$argv, [string]$desc) {
            L "==> $desc"
            if ([string]::IsNullOrWhiteSpace($exe)) { throw "Executável vazio ao executar '$desc'." }
            $safeArgs = @()
            foreach ($a in @($argv)) {
                if ($null -eq $a) { throw "Argumento nulo ao executar '$desc' com '$exe'." }
                $safeArgs += [string]$a
            }
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $exe
            $psi.Arguments = (($safeArgs | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
            $psi.WorkingDirectory = $ROOT
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError  = $true
            $psi.UseShellExecute        = $false
            $psi.CreateNoWindow         = $true
            $npmCache = Join-Path $ROOT 'tools\npm-cache'
            if (-not (Test-Path -LiteralPath $npmCache)) { New-Item -ItemType Directory -Path $npmCache -Force | Out-Null }
            $psi.EnvironmentVariables['npm_config_cache'] = $npmCache
            $psi.EnvironmentVariables['npm_config_audit'] = 'false'
            $psi.EnvironmentVariables['npm_config_fund'] = 'false'
            $psi.EnvironmentVariables['npm_config_update_notifier'] = 'false'
            if ($script:FrontendNodeDir) {
                try {
                    $currentPath = $psi.EnvironmentVariables['PATH']
                    if ([string]::IsNullOrWhiteSpace($currentPath)) { $currentPath = $env:PATH }
                    $psi.EnvironmentVariables['PATH'] = "$script:FrontendNodeDir;$currentPath"
                } catch {
                    L "[!] Não foi possível priorizar Node.js portátil para '$desc': $($_.Exception.Message)" 'warn'
                }
            }
            L ("> {0} {1}" -f $exe, ($safeArgs -join ' '))
            $p = $null
            try {
                $p = [System.Diagnostics.Process]::Start($psi)
            } catch {
                throw "Falha ao iniciar '$exe' para '$desc': $($_.Exception.Message)"
            }
            if ($null -eq $p) { throw "Falha ao iniciar '$exe' para '$desc': Process.Start retornou nulo." }
            if ($UPDATE_CONTROL -and $UPDATE_CONTROL.Processes) {
                [void]$UPDATE_CONTROL.Processes.Add($p)
            }

            # stdout e stderr precisam ser drenados ao mesmo tempo. Vite/Svelte escreve
            # muitos avisos em stderr durante "transforming..." e enche o pipe se apenas
            # stdout for lido, bloqueando tanto o build quanto o atualizador.
            $stdoutDone = $false
            $stderrDone = $false
            $stdoutTask = $p.StandardOutput.ReadLineAsync()
            $stderrTask = $p.StandardError.ReadLineAsync()
            $lastActivity = Get-Date
            $startedAt = Get-Date

            while (-not ($stdoutDone -and $stderrDone)) {
                if ($UPDATE_CONTROL -and $UPDATE_CONTROL.CancelRequested) {
                    try { if (-not $p.HasExited) { $p.Kill() } } catch {}
                    throw [System.OperationCanceledException]::new('Atualização cancelada pelo usuário.')
                }
                $readLine = $false

                if (-not $stdoutDone -and $stdoutTask.IsCompleted) {
                    $line = $stdoutTask.GetAwaiter().GetResult()
                    if ($null -eq $line) {
                        $stdoutDone = $true
                        $stdoutTask = $null
                    } else {
                        if (-not [string]::IsNullOrWhiteSpace($line)) { L "    $line" }
                        $lastActivity = Get-Date
                        $stdoutTask = $p.StandardOutput.ReadLineAsync()
                    }
                    $readLine = $true
                }

                if (-not $stderrDone -and $stderrTask.IsCompleted) {
                    $line = $stderrTask.GetAwaiter().GetResult()
                    if ($null -eq $line) {
                        $stderrDone = $true
                        $stderrTask = $null
                    } else {
                        if (-not [string]::IsNullOrWhiteSpace($line)) { L "    $line" 'warn' }
                        $lastActivity = Get-Date
                        $stderrTask = $p.StandardError.ReadLineAsync()
                    }
                    $readLine = $true
                }

                $now = Get-Date
                if (-not $p.HasExited -and $timeoutSeconds -gt 0 -and ($now - $startedAt).TotalSeconds -ge $timeoutSeconds) {
                    try { $p.Kill() } catch {}
                    try { $p.WaitForExit(5000) | Out-Null } catch {}
                    try { $p.Dispose() } catch {}
                    throw "Tempo limite excedido em '$desc' após $timeoutSeconds segundos. A atualização será restaurada."
                }
                if (-not $p.HasExited -and ($now - $lastActivity).TotalSeconds -ge 10) {
                    L "    ... $desc ainda em andamento."
                    $lastActivity = $now
                }

                if (-not $readLine) { Start-Sleep -Milliseconds 25 }
            }

            $p.WaitForExit()
            $exitCode = $p.ExitCode
            if ($UPDATE_CONTROL -and $UPDATE_CONTROL.Processes) {
                [void]$UPDATE_CONTROL.Processes.Remove($p)
            }
            $p.Dispose()
            return $exitCode
        }
        function Get-NodeMajorFromVersion([string]$version) {
            if ([string]::IsNullOrWhiteSpace($version)) { return -1 }
            if ($version -notmatch '^v?(\d+)\.') { return -1 }
            return [int]$matches[1]
        }
        function Test-FrontendNodePair([string]$nodeExe, [string]$npmExe) {
            try {
                if ([string]::IsNullOrWhiteSpace($nodeExe) -or -not (Test-Path -LiteralPath $nodeExe)) { return $null }
                if ([string]::IsNullOrWhiteSpace($npmExe) -or -not (Test-Path -LiteralPath $npmExe)) { return $null }

                $nodePath = (Resolve-Path -LiteralPath $nodeExe).ProviderPath
                if ($nodePath -match '\\Microsoft\\WindowsApps\\node\.exe$') { return $null }

                $nodeVersionOut = & $nodePath --version 2>&1
                if ($LASTEXITCODE -ne 0) { return $null }
                $nodeVersion = (("$nodeVersionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
                $nodeMajor = Get-NodeMajorFromVersion $nodeVersion
                if ($nodeMajor -lt 18 -or $nodeMajor -gt 22) { return $null }

                $npmPath = (Resolve-Path -LiteralPath $npmExe).ProviderPath
                $npmCliPath = Join-Path (Split-Path -Parent $nodePath) 'node_modules\npm\bin\npm-cli.js'
                if (Test-Path -LiteralPath $npmCliPath) {
                    $npmVersionOut = & $nodePath $npmCliPath --version 2>&1
                } else {
                    $npmVersionOut = & $npmPath --version 2>&1
                }
                if ($LASTEXITCODE -ne 0) { return $null }
                $npmVersion = (("$npmVersionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
                if (-not $npmVersion) { return $null }

                return [pscustomobject]@{
                    NodeExecutable = $nodePath
                    NodeVersion    = $nodeVersion
                    NpmExecutable  = $npmPath
                    NpmVersion     = $npmVersion
                    NodeDir        = Split-Path -Parent $nodePath
                }
            } catch {
                return $null
            }
        }
        function Resolve-FrontendNodeLaunch {
            $nodeCandidates = @()
            $portableRoots = @(
                (Join-Path $ROOT 'tools'),
                (Join-Path $env:LocalAppData 'NeveAI\tools'),
                (Join-Path $env:TEMP 'NeveAI\tools')
            ) | Select-Object -Unique
            foreach ($portableRoot in $portableRoots) {
                $portableNode = Join-Path $portableRoot 'nodejs\node.exe'
                if (Test-Path -LiteralPath $portableNode) { $nodeCandidates += $portableNode }
                if (Test-Path -LiteralPath $portableRoot) {
                    $nodeCandidates += @(Get-ChildItem -LiteralPath $portableRoot -Directory -Filter 'nodejs-*' -EA SilentlyContinue |
                        ForEach-Object { Join-Path $_.FullName 'node.exe' } |
                        Where-Object { Test-Path -LiteralPath $_ })
                }
            }
            if ($env:NODE_EXE) { $nodeCandidates += $env:NODE_EXE }

            foreach ($cmd in @(Get-Command node.exe -All -EA SilentlyContinue)) {
                $nodeCandidates += $cmd.Source
            }
            foreach ($nodeBase in (@($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ })) {
                $path = Join-Path $nodeBase 'nodejs\node.exe'
                if (Test-Path -LiteralPath $path) { $nodeCandidates += $path }
            }

            foreach ($nodeCandidate in ($nodeCandidates | Select-Object -Unique)) {
                $nodeDir = Split-Path -Parent $nodeCandidate
                foreach ($npmName in @('npm.cmd','npm.exe')) {
                    $npmPath = Join-Path $nodeDir $npmName
                    $pair = Test-FrontendNodePair $nodeCandidate $npmPath
                    if ($pair) { return $pair }
                }
            }

            return $null
        }
        function Install-PortableNode22 {
            P 52 'Preparando Node.js 22 portátil'
            $toolsDir = Join-Path $ROOT 'tools'
            $nodeDir = Join-Path $toolsDir 'nodejs'
            $existing = Test-FrontendNodePair (Join-Path $nodeDir 'node.exe') (Join-Path $nodeDir 'npm.cmd')
            if ($existing) {
                L "[OK] Node.js portátil já disponível: $($existing.NodeVersion) / npm $($existing.NpmVersion)"
                return $existing
            }

            if (-not (Test-Path -LiteralPath $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }
            L '==> Baixando Node.js 22 LTS portátil porque o Node do sistema está ausente ou fora da faixa suportada (18-22)'

            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
            } catch {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            }

            $release = $null
            try {
                $index = Invoke-RestMethod 'https://nodejs.org/dist/index.json' -Headers @{ 'User-Agent' = $UA } -TimeoutSec 60
                $release = $index | Where-Object { $_.version -match '^v22\.' -and $_.files -contains 'win-x64-zip' } | Select-Object -First 1
            } catch {
                L "[!] Falha ao consultar versões do Node.js: $($_.Exception.Message)" 'warn'
            }
            if (-not $release) {
                $release = [pscustomobject]@{ version = 'v22.23.3'; files = @('win-x64-zip') }
                L '[!] Índice do Node.js indisponível; usando a versão LTS de fallback v22.23.3.' 'warn'
            }

            $version = [string]$release.version
            $url = "https://nodejs.org/dist/$version/node-$version-win-x64.zip"
            $zipPath = Join-Path $env:TEMP "neve_node_$version-$([guid]::NewGuid().ToString('N')).zip"
            $stageParent = Join-Path $env:TEMP "neve_node_stage_$([guid]::NewGuid().ToString('N'))"
            try {
                if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue }
                New-Item -ItemType Directory -Path $stageParent -Force | Out-Null
                L "==> Baixando $url"
                try {
                    Invoke-WebRequest $url -OutFile $zipPath -UseBasicParsing -Headers @{ 'User-Agent' = $UA } -TimeoutSec 300
                } catch {
                    L "[!] Download pelo PowerShell falhou: $($_.Exception.Message). Tentando curl." 'warn'
                    $curl = Get-Command curl.exe -EA SilentlyContinue | Select-Object -First 1
                    if (-not $curl) { throw }
                    $rc = Run $curl.Source @('-L','--fail','--silent','--show-error','--compressed','--retry','3','--retry-delay','2','--connect-timeout','30','--max-time','300','--output',$zipPath,$url) 'Baixando Node.js com curl'
                    if ($rc -ne 0 -or -not (Test-Path -LiteralPath $zipPath) -or (Get-Item -LiteralPath $zipPath).Length -le 0) {
                        throw "curl não conseguiu baixar Node.js (exit $rc)."
                    }
                }
                Expand-Archive $zipPath -DestinationPath $stageParent -Force
                $extracted = Get-ChildItem -LiteralPath $stageParent -Directory | Select-Object -First 1
                if (-not $extracted) { throw 'Arquivo do Node.js não extraiu a pasta esperada.' }
                $stagedPair = Test-FrontendNodePair (Join-Path $extracted.FullName 'node.exe') (Join-Path $extracted.FullName 'npm.cmd')
                if (-not $stagedPair) { throw 'Node.js portátil extraído não passou na validação.' }

                $installParents = @(
                    $toolsDir,
                    (Join-Path $env:LocalAppData 'NeveAI\tools'),
                    (Join-Path $env:TEMP 'NeveAI\tools')
                ) | Select-Object -Unique
                $installErrors = @()
                foreach ($installParent in $installParents) {
                    $candidateDir = Join-Path $installParent 'nodejs'
                    $createdCandidate = $false
                    try {
                        if (-not (Test-Path -LiteralPath $installParent)) {
                            New-Item -ItemType Directory -Path $installParent -Force -EA Stop | Out-Null
                        }
                        $candidateExisting = Test-FrontendNodePair (Join-Path $candidateDir 'node.exe') (Join-Path $candidateDir 'npm.cmd')
                        if ($candidateExisting) { return $candidateExisting }
                        if (Test-Path -LiteralPath $candidateDir) {
                            try { Remove-Item -LiteralPath $candidateDir -Recurse -Force -EA Stop } catch {}
                            if (Test-Path -LiteralPath $candidateDir) {
                                $candidateDir = Join-Path $installParent ("nodejs-{0}-{1}" -f $version.TrimStart('v'), [guid]::NewGuid().ToString('N').Substring(0, 8))
                            }
                        }
                        $createdCandidate = $true
                        Copy-Item -LiteralPath $extracted.FullName -Destination $candidateDir -Recurse -Force -EA Stop
                        Get-ChildItem -LiteralPath $candidateDir -Recurse -File -EA SilentlyContinue | Unblock-File -EA SilentlyContinue

                        $pair = $null
                        for ($attempt = 1; $attempt -le 10 -and -not $pair; $attempt++) {
                            $pair = Test-FrontendNodePair (Join-Path $candidateDir 'node.exe') (Join-Path $candidateDir 'npm.cmd')
                            if (-not $pair) { Start-Sleep -Milliseconds 500 }
                        }
                        if (-not $pair) { throw 'Os arquivos foram copiados, mas Node.js/npm não responderam.' }
                        if ($candidateDir -ne $nodeDir) { L "[!] Node.js portátil instalado no fallback: $candidateDir" 'warn' }
                        L "[OK] Node.js portátil pronto: $($pair.NodeVersion) / npm $($pair.NpmVersion)"
                        return $pair
                    } catch {
                        $installErrors += "$candidateDir -> $($_.Exception.Message)"
                        L "[!] Não foi possível preparar Node.js em '$candidateDir': $($_.Exception.Message)" 'warn'
                        if ($createdCandidate) {
                            try { Remove-Item -LiteralPath $candidateDir -Recurse -Force -EA SilentlyContinue } catch {}
                        }
                    }
                }
                throw "Não foi possível preparar Node.js portátil em nenhum local permitido. $($installErrors -join ' | ')"
            } finally {
                try { if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue } } catch {}
                try { if (Test-Path -LiteralPath $stageParent) { Remove-Item -LiteralPath $stageParent -Recurse -Force -EA SilentlyContinue } } catch {}
            }
        }
        function Test-NeveAppIntegrity([string]$root) {
            $required = @(
                @{ Path = 'instalar.bat'; Label = 'instalar.bat' },
                @{ Path = 'launchers\instalar.ps1'; Label = 'launchers\instalar.ps1' },
                @{ Path = 'launchers\instalar.vbs'; Label = 'launchers\instalar.vbs' },
                @{ Path = 'launchers\iniciar.ps1'; Label = 'launchers\iniciar.ps1' },
                @{ Path = 'launchers\iniciar.vbs'; Label = 'launchers\iniciar.vbs' },
                @{ Path = 'backend\neveai\__init__.py'; Label = 'pacote backend' },
                @{ Path = 'backend\neveai\main.py'; Label = 'backend main.py' },
                @{ Path = 'backend\neveai\routers\music_generation.py'; Label = 'geração musical' },
                @{ Path = 'backend\neveai\routers\video_generation.py'; Label = 'geração de vídeo' },
                @{ Path = 'backend\neveai\models\users.py'; Label = 'backend\neveai\models\users.py' },
                @{ Path = 'backend\neveai\models\models.py'; Label = 'backend\neveai\models\models.py' },
                @{ Path = 'backend\neveai\models\auths.py'; Label = 'backend\neveai\models\auths.py' },
                @{ Path = 'backend\neveai\routers\auths.py'; Label = 'backend\neveai\routers' },
                @{ Path = 'backend\neveai\utils\auth.py'; Label = 'backend\neveai\utils' }
            )
            $missing = @()
            foreach ($item in $required) {
                $path = Join-Path $root $item.Path
                if (-not (Test-Path -LiteralPath $path)) { $missing += $item.Label }
            }
            [pscustomobject]@{ Ok = $missing.Count -eq 0; Missing = $missing }
        }
        function Copy-ReleaseInstallerFiles([string]$sourceRoot, [string]$destinationRoot) {
            $relativeFiles = @(
                'instalar.bat',
                'launchers\instalar.ps1',
                'launchers\instalar.vbs',
                'launchers\iniciar.ps1',
                'launchers\iniciar.vbs'
            )
            foreach ($relativePath in $relativeFiles) {
                if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $relativePath))) {
                    throw "Release do GitHub não contém $relativePath; atualização abortada antes de alterar os launchers atuais."
                }
            }

            $transactionRoot = Join-Path $env:TEMP "neve_launcher_tx_$([guid]::NewGuid().ToString('N'))"
            $backupRoot = Join-Path $transactionRoot 'backup'
            $stageRoot = Join-Path $transactionRoot 'stage'
            New-Item -ItemType Directory -Path $backupRoot,$stageRoot -Force | Out-Null
            $committed = @()
            try {
                foreach ($relativePath in $relativeFiles) {
                    $sourceFile = Join-Path $sourceRoot $relativePath
                    $destinationFile = Join-Path $destinationRoot $relativePath
                    $stageFile = Join-Path $stageRoot $relativePath
                    $backupFile = Join-Path $backupRoot $relativePath
                    New-Item -ItemType Directory -Path (Split-Path -Parent $stageFile) -Force | Out-Null
                    Copy-Item -LiteralPath $sourceFile -Destination $stageFile -Force -EA Stop
                    if (Test-Path -LiteralPath $destinationFile) {
                        New-Item -ItemType Directory -Path (Split-Path -Parent $backupFile) -Force | Out-Null
                        Copy-Item -LiteralPath $destinationFile -Destination $backupFile -Force -EA Stop
                    }
                }

                foreach ($relativePath in $relativeFiles) {
                    $stageFile = Join-Path $stageRoot $relativePath
                    $destinationFile = Join-Path $destinationRoot $relativePath
                    $destinationDir = Split-Path -Parent $destinationFile
                    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
                    $pendingFile = "$destinationFile.neve-new-$([guid]::NewGuid().ToString('N'))"
                    Copy-Item -LiteralPath $stageFile -Destination $pendingFile -Force -EA Stop
                    try {
                        if (Test-Path -LiteralPath $destinationFile) {
                            try {
                                [System.IO.File]::Replace($pendingFile, $destinationFile, $null, $true)
                            } catch {
                                Move-Item -LiteralPath $pendingFile -Destination $destinationFile -Force -EA Stop
                            }
                        } else {
                            Move-Item -LiteralPath $pendingFile -Destination $destinationFile -Force -EA Stop
                        }
                    } finally {
                        Remove-Item -LiteralPath $pendingFile -Force -EA SilentlyContinue
                    }
                    $committed += $relativePath
                    L "[OK] $relativePath atualizado a partir do release do GitHub"
                }
            } catch {
                $commitError = $_
                foreach ($relativePath in $committed) {
                    $destinationFile = Join-Path $destinationRoot $relativePath
                    $backupFile = Join-Path $backupRoot $relativePath
                    try {
                        if (Test-Path -LiteralPath $backupFile) {
                            Copy-Item -LiteralPath $backupFile -Destination $destinationFile -Force -EA Stop
                        } else {
                            Remove-Item -LiteralPath $destinationFile -Force -EA SilentlyContinue
                        }
                    } catch {}
                }
                throw "Falha ao trocar os launchers; os anteriores foram restaurados: $($commitError.Exception.Message)"
            } finally {
                Remove-Item -LiteralPath $transactionRoot -Recurse -Force -EA SilentlyContinue
            }
        }
        function Get-RelativePath([string]$basePath, [string]$path) {
            $baseFull = [System.IO.Path]::GetFullPath($basePath).TrimEnd('\', '/')
            $pathFull = [System.IO.Path]::GetFullPath($path)
            if ($pathFull.Length -le $baseFull.Length) { return '' }
            return $pathFull.Substring($baseFull.Length).TrimStart('\', '/')
        }
        function Test-ReleaseExcluded([string]$relativePath, [bool]$isDirectory, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            $normalized = ($relativePath -replace '/', '\').TrimStart('\')
            if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }

            foreach ($dir in $excludeDirs) {
                $excludedDir = ($dir -replace '/', '\').Trim('\')
                if (
                    $normalized.Equals($excludedDir, [System.StringComparison]::OrdinalIgnoreCase) -or
                    $normalized.StartsWith($excludedDir + '\', [System.StringComparison]::OrdinalIgnoreCase)
                ) {
                    return $true
                }
            }

            if (-not $isDirectory) {
                $leaf = Split-Path -Path $normalized -Leaf
                foreach ($file in $excludeFiles) {
                    if ($leaf.Equals($file, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
                }
            }

            return $false
        }
        function Test-ReleaseProtectedDescendant([string]$relativePath, [string]$directoryPath, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            $normalized = ($relativePath -replace '/', '\').Trim('\')
            if ([string]::IsNullOrWhiteSpace($normalized)) { return $true }

            foreach ($dir in $excludeDirs) {
                $excludedDir = ($dir -replace '/', '\').Trim('\')
                if ($excludedDir.StartsWith($normalized + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
                    return $true
                }
            }

            foreach ($file in $excludeFiles) {
                try {
                    $match = Get-ChildItem -LiteralPath $directoryPath -Filter $file -File -Recurse -Force -EA SilentlyContinue | Select-Object -First 1
                    if ($match) { return $true }
                } catch {}
            }

            return $false
        }
        function Remove-ReleaseItem([System.IO.FileSystemInfo]$item) {
            try {
                Remove-Item -LiteralPath $item.FullName -Recurse -Force -EA Stop
                $script:RemovedReleaseItems++
            } catch {
                throw "Falha ao remover item antigo '$($item.FullName)': $($_.Exception.Message)"
            }
        }
        function Remove-ReleaseOrphans([string]$destinationPath, [string]$sourceRoot, [string]$destinationRoot, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            if (-not (Test-Path -LiteralPath $destinationPath)) { return }

            $children = @(Get-ChildItem -LiteralPath $destinationPath -Force -EA SilentlyContinue)
            foreach ($child in $children) {
                $relativePath = Get-RelativePath $destinationRoot $child.FullName

                if (Test-ReleaseExcluded $relativePath $child.PSIsContainer $excludeDirs $excludeFiles) {
                    $script:SkippedReleaseItems++
                    continue
                }

                $sourcePath = Join-Path $sourceRoot $relativePath
                if (Test-Path -LiteralPath $sourcePath) {
                    $sourceItem = Get-Item -LiteralPath $sourcePath -Force
                    if ($child.PSIsContainer -and $sourceItem.PSIsContainer) {
                        Remove-ReleaseOrphans $child.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                    } elseif ($child.PSIsContainer -ne $sourceItem.PSIsContainer) {
                        if ($child.PSIsContainer -and (Test-ReleaseProtectedDescendant $relativePath $child.FullName $excludeDirs $excludeFiles)) {
                            Remove-ReleaseOrphans $child.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                        } else {
                            Remove-ReleaseItem $child
                        }
                    }
                    continue
                }

                if ($child.PSIsContainer -and (Test-ReleaseProtectedDescendant $relativePath $child.FullName $excludeDirs $excludeFiles)) {
                    Remove-ReleaseOrphans $child.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                    continue
                }

                Remove-ReleaseItem $child
            }
        }
        function Copy-ReleaseTree([string]$sourcePath, [string]$sourceRoot, [string]$destinationRoot, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            $item = Get-Item -LiteralPath $sourcePath -Force
            $relativePath = Get-RelativePath $sourceRoot $item.FullName

            if (Test-ReleaseExcluded $relativePath $item.PSIsContainer $excludeDirs $excludeFiles) {
                $script:SkippedReleaseItems++
                return
            }

            $destinationPath = Join-Path $destinationRoot $relativePath
            if ($item.PSIsContainer) {
                if (-not (Test-Path -LiteralPath $destinationPath)) {
                    [System.IO.Directory]::CreateDirectory($destinationPath) | Out-Null
                }
                Get-ChildItem -LiteralPath $item.FullName -Force | ForEach-Object {
                    Copy-ReleaseTree $_.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                }
                return
            }

            $destinationParent = Split-Path -Parent $destinationPath
            if (-not (Test-Path -LiteralPath $destinationParent)) {
                [System.IO.Directory]::CreateDirectory($destinationParent) | Out-Null
            }
            [System.IO.File]::Copy($item.FullName, $destinationPath, $true)
            $script:CopiedReleaseFiles++
        }
        function Invoke-ReleaseDownload([string]$uri, [string]$destination) {
            $lastError = $null
            for ($attempt = 1; $attempt -le 4; $attempt++) {
                try {
                    Remove-Item -LiteralPath $destination -Force -EA SilentlyContinue
                    Invoke-WebRequest $uri -OutFile $destination -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Updater/2.0'; 'Accept' = 'application/octet-stream' } -TimeoutSec 600 -EA Stop
                    if (-not (Test-Path -LiteralPath $destination)) { throw 'O download não criou o arquivo esperado.' }
                    if ((Get-Item -LiteralPath $destination).Length -lt 1KB) { throw 'O pacote baixado está vazio ou incompleto.' }
                    return
                } catch {
                    $lastError = $_
                    Remove-Item -LiteralPath $destination -Force -EA SilentlyContinue
                    if ($attempt -lt 4) {
                        L "[!] Download interrompido (tentativa $attempt/4). Tentando novamente..." 'warn'
                        Start-Sleep -Seconds ([math]::Min(8, [math]::Pow(2, $attempt)))
                    }
                }
            }
            throw "Não foi possível baixar a release após 4 tentativas: $($lastError.Exception.Message)"
        }
        function New-ReleaseRollbackSnapshot([string]$sourceRoot, [string]$snapshotRoot, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            New-Item -ItemType Directory -Path $snapshotRoot -Force | Out-Null
            $savedCopied = $script:CopiedReleaseFiles
            $savedSkipped = $script:SkippedReleaseItems
            try {
                foreach ($item in @(Get-ChildItem -LiteralPath $sourceRoot -Force -EA Stop)) {
                    Copy-ReleaseTree $item.FullName $sourceRoot $snapshotRoot $excludeDirs $excludeFiles
                }
            } finally {
                $script:CopiedReleaseFiles = $savedCopied
                $script:SkippedReleaseItems = $savedSkipped
            }
        }
        function Restore-ReleaseRollbackSnapshot([string]$snapshotRoot, [string]$destinationRoot, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            if (-not (Test-Path -LiteralPath $snapshotRoot)) { throw 'Snapshot de restauração não encontrado.' }
            $savedCopied = $script:CopiedReleaseFiles
            $savedRemoved = $script:RemovedReleaseItems
            $savedSkipped = $script:SkippedReleaseItems
            try {
                Remove-ReleaseOrphans $destinationRoot $snapshotRoot $destinationRoot $excludeDirs $excludeFiles
                foreach ($item in @(Get-ChildItem -LiteralPath $snapshotRoot -Force -EA Stop)) {
                    Copy-ReleaseTree $item.FullName $snapshotRoot $destinationRoot $excludeDirs $excludeFiles
                }
            } finally {
                $script:CopiedReleaseFiles = $savedCopied
                $script:RemovedReleaseItems = $savedRemoved
                $script:SkippedReleaseItems = $savedSkipped
            }
        }
        function Publish-FrontendAtomically([string]$sourceDir, [string]$destinationDir) {
            if (-not (Test-Path -LiteralPath (Join-Path $sourceDir 'index.html'))) {
                throw 'O build novo não contém index.html; o frontend atual foi mantido.'
            }
            $parent = Split-Path -Parent $destinationDir
            $suffix = [guid]::NewGuid().ToString('N')
            $stagedDir = Join-Path $parent "frontend.neve-new-$suffix"
            $backupDir = Join-Path $parent "frontend.neve-old-$suffix"
            $hadExisting = Test-Path -LiteralPath $destinationDir
            New-Item -ItemType Directory -Path $stagedDir -Force | Out-Null
            try {
                Get-ChildItem -LiteralPath $sourceDir -Force | Copy-Item -Destination $stagedDir -Recurse -Force -EA Stop
                if ($hadExisting) {
                    Move-Item -LiteralPath $destinationDir -Destination $backupDir -Force -EA Stop
                }
                try {
                    Move-Item -LiteralPath $stagedDir -Destination $destinationDir -Force -EA Stop
                } catch {
                    if (Test-Path -LiteralPath $backupDir) {
                        Move-Item -LiteralPath $backupDir -Destination $destinationDir -Force -EA SilentlyContinue
                    }
                    throw
                }
                return [pscustomobject]@{
                    Destination = $destinationDir
                    Backup      = if ($hadExisting) { $backupDir } else { $null }
                    HadExisting = $hadExisting
                }
            } finally {
                Remove-Item -LiteralPath $stagedDir -Recurse -Force -EA SilentlyContinue
                if ((Test-Path -LiteralPath $backupDir) -and -not (Test-Path -LiteralPath $destinationDir)) {
                    Move-Item -LiteralPath $backupDir -Destination $destinationDir -Force -EA SilentlyContinue
                }
            }
        }
        function Test-NeveInstallState([string]$root) {
            $required = @(
                @{ Path = '.env'; Label = '.env' },
                @{ Path = 'backend\neveai\venv\Scripts\python.exe'; Label = 'venv Python' },
                @{ Path = 'node_modules'; Label = 'node_modules' },
                @{ Path = 'backend\neveai\frontend\index.html'; Label = 'frontend publicado' }
            )
            $missing = @()
            foreach ($item in $required) {
                $path = Join-Path $root $item.Path
                if (-not (Test-Path -LiteralPath $path)) { $missing += $item.Label }
            }

            [pscustomobject]@{
                Installed = $missing.Count -eq 0
                Missing   = $missing
            }
        }
        function New-LlamaTarget([string]$vendor, [string]$name, [string]$label, [string[]]$backends, [string]$reason) {
            [pscustomobject]@{ Vendor=$vendor; Name=$name; Label=$label; Backends=$backends; Reason=$reason }
        }
        function Convert-ToInvariantDouble([string]$value) {
            if ([string]::IsNullOrWhiteSpace($value)) { return $null }
            try { return [double]::Parse(($value.Trim() -replace ',', '.'), [System.Globalization.CultureInfo]::InvariantCulture) } catch { return $null }
        }
        function Get-InstalledLlamaInfo([string]$root) {
            $versionPath = Join-Path $root 'llamacpp-server\version.txt'
            $tag = ''; $backend = ''; $asset = ''
            if (Test-Path $versionPath) {
                $lines = @(Get-Content $versionPath -EA SilentlyContinue)
                if ($lines.Count -gt 0) { $tag = $lines[0].Trim() }
                if ($lines.Count -gt 1) { $backend = $lines[1].Trim() }
                if ($lines.Count -gt 2) { $asset = $lines[2].Trim() }
            }
            [pscustomobject]@{ Tag=$tag; Backend=$backend; Asset=$asset }
        }
        function Get-LlamaHardwareTarget {
            $nvidiaLine = $null
            try {
                $nvidiaOut = nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader 2>&1
                if ($LASTEXITCODE -eq 0 -and "$nvidiaOut" -notmatch 'failed|not found|invalid') {
                    $nvidiaLine = ("$nvidiaOut" -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
                }
            } catch {}
            if (-not $nvidiaLine) {
                try {
                    $nvidiaOut = nvidia-smi --query-gpu=name --format=csv,noheader 2>&1
                    if ($LASTEXITCODE -eq 0 -and "$nvidiaOut" -notmatch 'failed|not found|invalid') {
                        $nameOnly = ("$nvidiaOut" -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
                        if ($nameOnly) { $nvidiaLine = $nameOnly }
                    }
                } catch {}
            }
            if ($nvidiaLine) {
                $parts = $nvidiaLine -split ','
                $name = $parts[0].Trim()
                $computeCap = $null
                if ($parts.Count -gt 1) { $computeCap = Convert-ToInvariantDouble $parts[1] }
                if ($computeCap -ne $null -and $computeCap -lt 5.0) {
                    return New-LlamaTarget 'CPU' $name 'CPU (GPU NVIDIA sem suporte CUDA moderno)' @('cpu') "GPU NVIDIA detectada ($name), mas compute capability $computeCap não é suportada pelos binários CUDA atuais."
                }
                if ($name -match 'RTX\s*5\d{3}|50\d{2}|Blackwell' -or ($computeCap -ne $null -and $computeCap -ge 12.0)) {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 13' @('cuda-13.4','cuda-cu13.4','cuda-13.3','cuda-cu13.3') "GPU NVIDIA Blackwell detectada: $name."
                }
                if ($computeCap -ne $null -and $computeCap -ge 5.0) {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 12.4' @('cuda-12.4','cuda-cu12.4') "GPU NVIDIA compatível com CUDA 12 detectada: $name."
                }
                if ($name -match 'RTX\s*[234]\d{3}|[234]0\d{2}|GTX\s*16\d{2}|GTX\s*10\d{2}|GTX\s*9\d{2}|Quadro|Tesla|RTX\s*A') {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 12.4' @('cuda-12.4','cuda-cu12.4') "GPU NVIDIA reconhecida por geração: $name."
                }
                throw "GPU NVIDIA detectada ($name), mas não foi possível determinar com segurança o binário CUDA correto. Nada foi instalado."
            }
            try {
                $gpus = Get-CimInstance Win32_VideoController -EA SilentlyContinue
                $amdGpu = $gpus | Where-Object { $_.Name -match 'AMD|Radeon|RX\s' } |
                    Sort-Object @{ Expression = { if ($_.Name -match '\bRX\s*\d|Radeon\s+Pro\b') { 0 } elseif ($_.Name -match 'Vega\s*\d+\s*Graphics|Radeon(?:\(TM\))?\s+Graphics') { 2 } else { 1 } } },
                                @{ Expression = { [long]$_.AdapterRAM }; Descending = $true } | Select-Object -First 1
                if ($amdGpu) { return New-LlamaTarget 'AMD' $amdGpu.Name.Trim() 'AMD Vulkan' @('vulkan') "GPU AMD detectada: $($amdGpu.Name.Trim())." }
            } catch {}
            return New-LlamaTarget 'CPU' '' 'CPU' @('cpu') 'Nenhuma GPU NVIDIA/AMD compatível foi detectada.'
        }
        function Find-LlamaBinAsset($assets, [string]$tag, [string[]]$backends) {
            $tagEsc = [regex]::Escape($tag)
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^llama-$tagEsc-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^llama-.+-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($asset in @($assets)) {
                $assetMatch = [regex]::Match([string]$asset.name, '^llama-.+-bin-win-(.+)-x64\.zip$')
                if (-not $assetMatch.Success) { continue }
                foreach ($backend in $backends) {
                    if (Test-LlamaBackendCompatible $backend $assetMatch.Groups[1].Value) { return $asset }
                }
            }
            foreach ($backend in $backends) {
                $asset = New-LlamaReleaseAsset $tag "llama-$tag-bin-win-$backend-x64.zip"
                if (Test-ReleaseAssetUrl $asset.browser_download_url) { return $asset }
            }
            return $null
        }
        function Find-CudaRuntimeAsset($assets, [string]$tag, [string[]]$backends) {
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^cudart-llama-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($asset in @($assets)) {
                $assetMatch = [regex]::Match([string]$asset.name, '^cudart-llama-bin-win-(.+)-x64\.zip$')
                if (-not $assetMatch.Success) { continue }
                foreach ($backend in $backends) {
                    if (Test-LlamaBackendCompatible $backend $assetMatch.Groups[1].Value) { return $asset }
                }
            }
            foreach ($backend in $backends) {
                $asset = New-LlamaReleaseAsset $tag "cudart-llama-bin-win-$backend-x64.zip"
                if (Test-ReleaseAssetUrl $asset.browser_download_url) { return $asset }
            }
            return $null
        }
        function Update-NeveAI {
            Set-Location -LiteralPath $ROOT
            if (-not $latestTag -or -not $zipUrl) { throw 'Release do NeveAI indisponível para atualização.' }
            $installState = Test-NeveInstallState $ROOT
            $canBuildAndDeploy = [bool]$installState.Installed
            if (-not $canBuildAndDeploy) {
                L "[!] Instalação incompleta detectada. Build/deploy serão pulados." 'warn'
                L "    Faltando: $($installState.Missing -join ', ')" 'warn'
                L "    Rode instalar.bat para concluir a instalação antes de gerar frontend." 'warn'
            }

            $operationId = [guid]::NewGuid().ToString('N')
            $tmpZip = Join-Path $env:TEMP "neve_update_$operationId.zip"
            $tmpExt = Join-Path $env:TEMP "neve_update_ext_$operationId"
            $rollbackRoot = Join-Path $env:TEMP "neve_update_rollback_$operationId"
            $envFile = Join-Path $ROOT '.env'
            $envBackup = $null
            $mutationStarted = $false
            $frontendTransaction = $null
            $backendDependenciesChanged = $false
            $rollbackRequirement = $null
            $versionExisted = Test-Path -LiteralPath $VERSION_FILE
            $previousVersion = if ($versionExisted) { Get-Content -LiteralPath $VERSION_FILE -Raw -EA SilentlyContinue } else { $null }
            $excludeDirs = @('backend\neveai\venv','backend\neveai\frontend','backend\neveai\data','backend\data','backend\__pycache__','models','mmproj','llamacpp-server','node_modules','build','logs','tools\nodejs','.git','.vscode','.svelte-kit')
            $excludeFiles = @('.env', 'version.txt', 'instalar.bat', 'instalar.ps1', 'instalar.vbs', 'iniciar.ps1', 'iniciar.vbs')

            try {
                PN 5 "Baixando NeveAI $latestTag"
                L "==> Download $zipUrl"
                Invoke-ReleaseDownload $zipUrl $tmpZip
                $sizeMB = [math]::Round((Get-Item -LiteralPath $tmpZip).Length / 1MB, 1)
                L "[OK] NeveAI baixado ($sizeMB MB)"

                PN 18 'Extraindo e validando NeveAI'
                New-Item $tmpExt -ItemType Directory -Force | Out-Null
                Expand-Archive $tmpZip -DestinationPath $tmpExt -Force -EA Stop
                $inner = Get-ChildItem -LiteralPath $tmpExt -Directory | Select-Object -First 1
                if (-not $inner) { throw 'Estrutura inesperada do zip da release.' }
                $sourceRoot = (Resolve-Path -LiteralPath $inner.FullName).ProviderPath
                $destinationRoot = (Resolve-Path -LiteralPath $ROOT).ProviderPath
                if ($sourceRoot.Equals($destinationRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                    throw 'A pasta fonte da release é igual à pasta de instalação; atualização abortada.'
                }
                $releaseIntegrity = Test-NeveAppIntegrity $sourceRoot
                if (-not $releaseIntegrity.Ok) {
                    throw "Release incompleta; nenhum arquivo local foi alterado. Faltando: $($releaseIntegrity.Missing -join ', ')."
                }
                L "[OK] Pasta da instalação: $destinationRoot"
                L "[OK] Pasta da release validada: $sourceRoot"

                PN 27 'Preservando dados e estado atual'
                if (Test-Path -LiteralPath $envFile) {
                    $envBackup = Join-Path $env:TEMP "neve_update_env_$operationId.bak"
                    Copy-Item -LiteralPath $envFile -Destination $envBackup -Force -EA Stop
                    L '[OK] .env preservado'
                }
                New-ReleaseRollbackSnapshot $destinationRoot $rollbackRoot $excludeDirs $excludeFiles
                L '[OK] Ponto de restauração criado'

                PN 38 'Aplicando arquivos do NeveAI'
                $mutationStarted = $true
                $script:CopiedReleaseFiles = 0
                $script:RemovedReleaseItems = 0
                $script:SkippedReleaseItems = 0
                Remove-ReleaseOrphans $destinationRoot $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                foreach ($item in @(Get-ChildItem -LiteralPath $sourceRoot -Force -EA Stop)) {
                    Copy-ReleaseTree $item.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                }
                L "[OK] Arquivos de release aplicados ($script:CopiedReleaseFiles arquivos, $script:RemovedReleaseItems órfãos removidos, $script:SkippedReleaseItems itens preservados)"

                $integrity = Test-NeveAppIntegrity $ROOT
                if (-not $integrity.Ok) {
                    throw "Release aplicada sem arquivos essenciais: $($integrity.Missing -join ', ')."
                }
                if ($envBackup -and -not (Test-Path -LiteralPath $envFile)) {
                    Copy-Item -LiteralPath $envBackup -Destination $envFile -Force -EA Stop
                }
                L '[OK] Integridade dos arquivos essenciais validada'

                if ($canBuildAndDeploy) {
                    $requirementRelative = if (Test-Path -LiteralPath (Join-Path $ROOT 'backend\requirements-runtime.txt')) { 'backend\requirements-runtime.txt' } else { 'backend\requirements.txt' }
                    $activeRequirement = Join-Path $ROOT $requirementRelative
                    $rollbackRequirement = Join-Path $rollbackRoot $requirementRelative
                    if (-not (Test-Path -LiteralPath $activeRequirement)) { throw 'A release não contém a lista de dependências do backend.' }
                    $backendDependenciesChanged = -not (Test-Path -LiteralPath $rollbackRequirement)
                    if (-not $backendDependenciesChanged) {
                        $backendDependenciesChanged = (Get-FileHash -LiteralPath $activeRequirement -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $rollbackRequirement -Algorithm SHA256).Hash
                    }
                    if ($backendDependenciesChanged) {
                        PN 48 'Atualizando dependências do backend'
                        $venvPython = Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe'
                        if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Python do ambiente virtual não encontrado para atualizar as dependências do backend.' }
                        $rc = Run $venvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $activeRequirement) 'dependências do backend' 3600
                        if ($rc -ne 0) { throw "Atualização das dependências do backend falhou (código $rc)" }
                        L '[OK] Dependências do backend sincronizadas'
                    }
                }

                if ($canBuildAndDeploy) {
                    PN 55 'Instalando dependências do frontend'
                    $frontendNode = Resolve-FrontendNodeLaunch
                    if (-not $frontendNode) { $frontendNode = Install-PortableNode22 }
                    if (-not $frontendNode) { throw 'Node.js 18-22 com npm não encontrado e o Node.js 22 portátil não pôde ser preparado.' }
                    $script:FrontendNodeDir = $frontendNode.NodeDir
                    $npmExe = $frontendNode.NpmExecutable
                    L "[OK] Node.js do frontend: $($frontendNode.NodeVersion) / npm $($frontendNode.NpmVersion) em $($frontendNode.NodeDir)"
                    $rc = Run $npmExe @('install', '--no-audit', '--no-fund') 'npm install' 2700
                    if ($rc -ne 0) { throw "npm install falhou (código $rc)" }

                    $previousOfficeCliSkipUpdate = $env:OFFICECLI_SKIP_UPDATE
                    $previousOfficeCliNoAutoResident = $env:OFFICECLI_NO_AUTO_RESIDENT
                    try {
                        $env:OFFICECLI_SKIP_UPDATE = '1'
                        $env:OFFICECLI_NO_AUTO_RESIDENT = '1'
                        $officeCli = Join-Path $ROOT 'node_modules\@officecli\officecli\vendor\officecli.exe'
                        if (-not (Test-Path -LiteralPath $officeCli)) {
                            $rc = Run $npmExe @('exec', '--', 'officecli', '--version') 'preparar OfficeCLI'
                            if ($rc -ne 0 -or -not (Test-Path -LiteralPath $officeCli)) {
                                throw 'Falha ao preparar o OfficeCLI para geração de DOCX, XLSX e PPTX.'
                            }
                        }
                        $rc = Run $officeCli @('--version') 'validar OfficeCLI'
                        if ($rc -ne 0) { throw "OfficeCLI instalado, mas a validação falhou (código $rc)." }
                    } finally {
                        if ($null -eq $previousOfficeCliSkipUpdate) { Remove-Item Env:\OFFICECLI_SKIP_UPDATE -ErrorAction SilentlyContinue } else { $env:OFFICECLI_SKIP_UPDATE = $previousOfficeCliSkipUpdate }
                        if ($null -eq $previousOfficeCliNoAutoResident) { Remove-Item Env:\OFFICECLI_NO_AUTO_RESIDENT -ErrorAction SilentlyContinue } else { $env:OFFICECLI_NO_AUTO_RESIDENT = $previousOfficeCliNoAutoResident }
                    }
                    L '[OK] OfficeCLI pronto para gerar DOCX, XLSX e PPTX'

                    PN 76 'Gerando build do frontend'
                    Remove-Item -LiteralPath (Join-Path $ROOT 'build') -Recurse -Force -EA SilentlyContinue
                    $rc = Run $npmExe @('run', 'build', '--', '--logLevel', 'error') 'npm run build' 1800
                    if ($rc -ne 0) { throw "npm run build falhou (código $rc)" }

                    PN 91 'Publicando frontend'
                    $buildDir = Join-Path $ROOT 'build'
                    $deployDir = Join-Path $ROOT 'backend\neveai\frontend'
                    $frontendTransaction = Publish-FrontendAtomically $buildDir $deployDir
                    L '[OK] Frontend novo publicado de forma transacional'
                } else {
                    PN 91 'Pulando build/deploy'
                    L '[OK] Build e deploy pulados porque o projeto ainda não foi instalado.'
                }

                PN 96 'Finalizando atualização'
                [System.IO.File]::WriteAllText($VERSION_FILE, $latestTag, [System.Text.UTF8Encoding]::new($false))
                Copy-ReleaseInstallerFiles $sourceRoot $destinationRoot
                $mutationStarted = $false
                if ($frontendTransaction -and $frontendTransaction.Backup) {
                    Remove-Item -LiteralPath $frontendTransaction.Backup -Recurse -Force -EA SilentlyContinue
                }
                try { L "[OK] NeveAI atualizado para $latestTag" } catch {}
                if ($canBuildAndDeploy) { return "NeveAI: $currentVersion -> $latestTag" }
                return "NeveAI: $currentVersion -> $latestTag (build/deploy pulados; instalação incompleta)"
            } catch {
                $updateError = $_
                if ($mutationStarted) {
                    L '[!] A atualização não foi concluída; restaurando a instalação anterior...' 'warn'
                    try {
                        if ($frontendTransaction) {
                            Remove-Item -LiteralPath $frontendTransaction.Destination -Recurse -Force -EA SilentlyContinue
                            if ($frontendTransaction.HadExisting -and (Test-Path -LiteralPath $frontendTransaction.Backup)) {
                                Move-Item -LiteralPath $frontendTransaction.Backup -Destination $frontendTransaction.Destination -Force -EA Stop
                            }
                        }
                        Restore-ReleaseRollbackSnapshot $rollbackRoot $ROOT $excludeDirs $excludeFiles
                        if ($backendDependenciesChanged -and $rollbackRequirement -and (Test-Path -LiteralPath $rollbackRequirement)) {
                            $venvPython = Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe'
                            if (Test-Path -LiteralPath $venvPython) {
                                $restoreRc = Run $venvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $rollbackRequirement) 'restauração das dependências do backend' 3600
                                if ($restoreRc -ne 0) { L '[!] Não foi possível ressincronizar todas as dependências antigas; os arquivos do projeto foram restaurados.' 'warn' }
                            }
                        }
                        if ($envBackup -and (Test-Path -LiteralPath $envBackup)) {
                            Copy-Item -LiteralPath $envBackup -Destination $envFile -Force -EA Stop
                        }
                        if ($versionExisted) {
                            [System.IO.File]::WriteAllText($VERSION_FILE, [string]$previousVersion, [System.Text.UTF8Encoding]::new($false))
                        } else {
                            Remove-Item -LiteralPath $VERSION_FILE -Force -EA SilentlyContinue
                        }
                        L '[OK] Instalação anterior restaurada.'
                    } catch {
                        throw "A atualização falhou e a restauração automática também encontrou um erro: $($_.Exception.Message). Erro original: $($updateError.Exception.Message)"
                    }
                }
                throw $updateError
            } finally {
                Remove-Item -LiteralPath $tmpZip -Force -EA SilentlyContinue
                Remove-Item -LiteralPath $tmpExt -Recurse -Force -EA SilentlyContinue
                Remove-Item -LiteralPath $rollbackRoot -Recurse -Force -EA SilentlyContinue
                if ($envBackup) { Remove-Item -LiteralPath $envBackup -Force -EA SilentlyContinue }
            }
        }
        function Update-LlamaCpp {
            $tmpFiles = @(); $stageDir = $null; $backupDir = $null
            try {
                PL 5 'Detectando hardware para llama.cpp'
                $target = Get-LlamaHardwareTarget
                L "[OK] Alvo llama.cpp: $($target.Label)"
                if ($target.Name) { L "    Hardware: $($target.Name)" }

                PL 10 'Consultando releases do llama.cpp'
                $rel = Get-LatestLlamaRelease ([string[]]$target.Backends)
                $tag = $rel.tag_name
                if (-not $tag) { throw 'Release do llama.cpp sem tag_name.' }
                $installed = Get-InstalledLlamaInfo $ROOT
                if ($installed.Tag -and $installed.Tag -eq $tag) {
                    L "[OK] llama.cpp já está na última release ($tag). Nenhum download necessário."
                    return "llama.cpp: já atualizado ($tag)"
                }

                $mainAsset = Find-LlamaBinAsset $rel.assets $tag ([string[]]$target.Backends)
                if (-not $mainAsset) { throw "O release $tag não contém um asset Windows x64 para $($target.Label). Nada foi instalado." }
                $isCuda = (@($target.Backends) | Where-Object { $_ -match '^cuda' } | Select-Object -First 1) -ne $null
                $runtimeAsset = $null
                if ($isCuda) { $runtimeAsset = Find-CudaRuntimeAsset $rel.assets $tag ([string[]]$target.Backends) }

                PL 28 'Baixando llama.cpp'
                $tmpMain = Join-Path $env:TEMP "neve_llama_$([guid]::NewGuid().ToString('N')).zip"
                $tmpFiles += $tmpMain
                Invoke-WebRequest $mainAsset.browser_download_url -OutFile $tmpMain -UseBasicParsing -Headers @{ 'User-Agent' = $UA }
                $tmpRuntime = $null
                if ($runtimeAsset) {
                    $tmpRuntime = Join-Path $env:TEMP "neve_llama_cudart_$([guid]::NewGuid().ToString('N')).zip"
                    $tmpFiles += $tmpRuntime
                    Invoke-WebRequest $runtimeAsset.browser_download_url -OutFile $tmpRuntime -UseBasicParsing -Headers @{ 'User-Agent' = $UA }
                }

                PL 45 'Extraindo e validando llama.cpp'
                $stageDir = Join-Path $env:TEMP "neve_llama_stage_$([guid]::NewGuid().ToString('N'))"
                New-Item $stageDir -ItemType Directory -Force | Out-Null
                Expand-Archive $tmpMain -DestinationPath $stageDir -Force
                if ($tmpRuntime) { Expand-Archive $tmpRuntime -DestinationPath $stageDir -Force }
                $serverExe = Get-ChildItem $stageDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1
                if (-not $serverExe) { throw 'O pacote baixado não contém llama-server.exe.' }
                $stagedFiles = Get-ChildItem $stageDir -Recurse -File
                if (-not $stagedFiles) { throw 'Nenhum arquivo extraído do pacote do llama.cpp.' }

                PL 62 'Instalando llama.cpp'
                $llamaRoot = Join-Path $ROOT 'llamacpp-server'
                $llamaDir = Join-Path $llamaRoot 'bin'
                if (-not (Test-Path $llamaRoot)) { New-Item $llamaRoot -ItemType Directory -Force | Out-Null }
                if (-not (Test-Path $llamaDir)) { New-Item $llamaDir -ItemType Directory -Force | Out-Null }
                $backupDir = Join-Path $env:TEMP "neve_llama_backup_$([guid]::NewGuid().ToString('N'))"
                New-Item $backupDir -ItemType Directory -Force | Out-Null
                Get-ChildItem $llamaDir -Force -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $backupDir -Recurse -Force }
                try {
                    Get-Process llama-server -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
                    Get-ChildItem $llamaDir -File -EA SilentlyContinue | Where-Object { $_.Extension -in '.exe','.dll','.pdb' } | Remove-Item -Force -EA Stop
                    foreach ($file in $stagedFiles) { Copy-Item $file.FullName $llamaDir -Force -EA Stop }
                    if (-not (Test-Path (Join-Path $llamaDir 'llama-server.exe'))) { throw 'llama-server.exe não ficou disponível após a cópia.' }
                } catch {
                    $replaceError = $_
                    L "[!] Falha ao aplicar llama.cpp; restaurando backup: $replaceError" 'warn'
                    try {
                        Get-ChildItem $llamaDir -Force -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue
                        Get-ChildItem $backupDir -Force -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $llamaDir -Recurse -Force }
                    } catch {}
                    throw $replaceError
                }

                PL 90 'Registrando versão do llama.cpp'
                Set-Content -Path (Join-Path $llamaRoot 'version.txt') -Value @($tag, $target.Label, $mainAsset.name) -Encoding UTF8
                L "[OK] llama.cpp $tag instalado"
                return "llama.cpp: $($installed.Tag -replace '^$','não instalado') -> $tag ($($target.Label))"
            } finally {
                foreach ($tmp in $tmpFiles) { try { Remove-Item $tmp -Force -EA SilentlyContinue } catch {} }
                if ($stageDir) { try { Remove-Item $stageDir -Recurse -Force -EA SilentlyContinue } catch {} }
                if ($backupDir) { try { Remove-Item $backupDir -Recurse -Force -EA SilentlyContinue } catch {} }
            }
        }

        try {
            $summary = @()
            if ($updateNeve) { $summary += Update-NeveAI }
            if ($updateLlama) { $summary += Update-LlamaCpp }
            P 100 'Concluído'
            L '[OK] Atualização concluída.'

            $doneTitle = if ($updateNeve -and $updateLlama) { 'Atualizações concluídas!' } elseif ($updateNeve) { 'NeveAI atualizado!' } else { 'llama.cpp atualizado!' }
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.UpdatePanel.Visibility = 'Collapsed'
                $script:Ctl.DonePanel.Visibility   = 'Visible'
                $script:Ctl.LblDoneTitle.Text = $doneTitle
                $script:Ctl.LblDoneSub.Text   = 'Use iniciar.bat para iniciar a NeveAI.'
                $script:Ctl.LblSummary.Text   = ($summary -join "`r`n")
                $script:Ctl.BtnPrimary.Content   = 'Concluir'
                $script:Ctl.BtnPrimary.Tag       = 'done'
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnPrimary.Visibility = 'Visible'
                $script:Ctl.BtnCancel.Visibility = 'Collapsed'
                $script:Ctl.BtnCancel.IsEnabled  = $false
            })
        } catch {
            if ($UPDATE_CONTROL -and $UPDATE_CONTROL.CancelRequested) { return }
            $errMsg = "$_"
            L "[X] FALHA: $errMsg" 'err'
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LblStep.Text = 'Falha durante a atualização.'
                $script:Ctl.BtnPrimary.Content   = 'Fechar'
                $script:Ctl.BtnPrimary.Tag       = 'error'
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnPrimary.Visibility = 'Visible'
                $script:Ctl.BtnCancel.Visibility = 'Collapsed'
                $script:Ctl.BtnCancel.IsEnabled = $false
                [System.Windows.MessageBox]::Show(
                    "A atualização falhou.`r`n`r`nVeja o log em logs\update.log`r`n`r`n$errMsg",
                    'NeveAI - Atualizador',
                    [System.Windows.MessageBoxButton]::OK,
                    [System.Windows.MessageBoxImage]::Error) | Out-Null
            })
        }
    }

    $rs = [RunspaceFactory]::CreateRunspace()
    $rs.ApartmentState = 'STA'
    $rs.ThreadOptions  = 'ReuseThread'
    $rs.Open()
    $rs.SessionStateProxy.SetVariable('Window', $window)
    $rs.SessionStateProxy.SetVariable('Ctl',    $ctl)

    $ps = [PowerShell]::Create()
    $ps.Runspace = $rs
    [void]$ps.AddScript($worker)
    [void]$ps.AddArgument($argUpdateNeve)
    [void]$ps.AddArgument($argUpdateLlama)
    [void]$ps.AddArgument($argLatestTag)
    [void]$ps.AddArgument($argZipUrl)
    [void]$ps.AddArgument($argRoot)
    [void]$ps.AddArgument($argLog)
    [void]$ps.AddArgument($argVersionFile)
    [void]$ps.AddArgument($argCurrent)
    [void]$ps.AddArgument($argLlamaApi)
    [void]$ps.AddArgument($argUa)
    [void]$ps.AddArgument($script:UpdateControl)
    $script:UpdatePowerShell = $ps
    $script:UpdateRunspace = $rs
    [void]$ps.BeginInvoke()
})

# =============================================================================
# Mostra a janela
# =============================================================================
[void]$window.ShowDialog()
exit $script:ExitCode

'@

$script:BuildLegacySource = @'
# NeveAI - Buildar Grafico (WPF)
# Faz build limpo, publica em backend\neveai\frontend e valida o hash do index.html.

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

# =============================================================================
# Caminhos globais
# =============================================================================
$SCRIPT_PATH = if ($PSCommandPath) { $PSCommandPath } elseif ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { throw 'NÃ£o foi possÃ­vel determinar o caminho do build.' }
$LAUNCHER_DIR = (Resolve-Path -LiteralPath (Split-Path -Parent $SCRIPT_PATH)).ProviderPath
$ROOT = (Resolve-Path -LiteralPath (Join-Path $LAUNCHER_DIR '..')).ProviderPath
Set-Location -LiteralPath $ROOT
$BUILD_DIR = Join-Path $ROOT 'build'
$DEPLOY_DIR = Join-Path $ROOT 'backend\neveai\frontend'
$LOG_DIR = Join-Path $ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) { New-Item $LOG_DIR -ItemType Directory | Out-Null }
$LOG = Join-Path $LOG_DIR 'build.log'
'' | Set-Content $LOG -Encoding UTF8

$LOGO_PATH = Join-Path $ROOT 'static\favicon.png'
if (-not (Test-Path $LOGO_PATH)) {
    $LOGO_PATH = Join-Path $ROOT 'static\static\favicon.png'
}

# =============================================================================
# XAML - Interface
# =============================================================================
[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="NeveAI - Buildar"
        Width="780" Height="560"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize"
        WindowStyle="None"
        AllowsTransparency="True"
        Background="Transparent">
    <Window.Resources>
        <Style x:Key="PrimaryBtn" TargetType="Button">
            <Setter Property="Background" Value="#111111"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="Padding" Value="22,9"/>
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="FontWeight" Value="Medium"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#262626"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="bd" Property="Opacity" Value="0.4"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style x:Key="GhostBtn" TargetType="Button" BasedOn="{StaticResource PrimaryBtn}">
            <Setter Property="Background" Value="#F4F4F5"/>
            <Setter Property="Foreground" Value="#111111"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#E4E4E7"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="bd" Property="Opacity" Value="0.5"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
    </Window.Resources>

    <Border CornerRadius="14" Background="#FAFAFA" BorderBrush="#E4E4E7" BorderThickness="1">
        <Grid>
            <Grid.RowDefinitions>
                <RowDefinition Height="56"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="68"/>
            </Grid.RowDefinitions>

            <Grid Grid.Row="0" Background="Transparent">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>
                <StackPanel Grid.Column="0" Orientation="Horizontal" Margin="18,0,0,0" VerticalAlignment="Center">
                    <Image x:Name="LogoImg" Width="22" Height="22" Margin="0,0,10,0"/>
                    <TextBlock Text="NeveAI" FontSize="15" FontWeight="SemiBold" Foreground="#111111" VerticalAlignment="Center"/>
                    <TextBlock Text="  -  Buildar" FontSize="13" Foreground="#71717A" VerticalAlignment="Center"/>
                </StackPanel>
                <Button x:Name="BtnClose" Grid.Column="2" Width="44" Height="32" Margin="0,0,12,0"
                        Background="Transparent" BorderThickness="0" Cursor="Hand">
                    <Button.Template>
                        <ControlTemplate TargetType="Button">
                            <Border x:Name="bd" Background="Transparent" CornerRadius="6">
                                <TextBlock Text="×" FontSize="22" FontWeight="Medium" Foreground="#71717A" HorizontalAlignment="Center" VerticalAlignment="Center" Margin="0,-5,0,0"/>
                            </Border>
                            <ControlTemplate.Triggers>
                                <Trigger Property="IsMouseOver" Value="True">
                                    <Setter TargetName="bd" Property="Background" Value="#E4E4E7"/>
                                </Trigger>
                            </ControlTemplate.Triggers>
                        </ControlTemplate>
                    </Button.Template>
                </Button>
            </Grid>

            <Grid Grid.Row="1" Margin="32,8,32,0">
                <Grid x:Name="IntroPanel">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,18">
                        <TextBlock Text="Realizar build do projeto" FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock Text="Compila e publica a pasta build no backend da NeveAI."
                                   FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="20">
                        <Grid>
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                            </Grid.RowDefinitions>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="170"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>

                            <TextBlock Grid.Row="0" Grid.Column="0" Text="Build:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <TextBlock Grid.Row="0" Grid.Column="1" x:Name="LblBuildPath" Text="build" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,12" TextTrimming="CharacterEllipsis"/>

                            <TextBlock Grid.Row="1" Grid.Column="0" Text="Destino:" FontSize="13" Foreground="#52525B"/>
                            <TextBlock Grid.Row="1" Grid.Column="1" x:Name="LblDeployPath" Text="backend\neveai\frontend" FontSize="13" FontWeight="SemiBold" Foreground="#111111" TextTrimming="CharacterEllipsis"/>

                        </Grid>
                    </Border>
                </Grid>

                <Grid x:Name="WorkPanel" Visibility="Collapsed">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,12">
                        <TextBlock Text="Buildando..." FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock x:Name="LblStep" Text="Preparando..." FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="16,14" Margin="0,0,0,14">
                        <StackPanel>
                            <Grid>
                                <TextBlock x:Name="LblProgressTxt" Text="0%" FontSize="12" Foreground="#52525B" HorizontalAlignment="Right"/>
                                <TextBlock x:Name="LblPhase" Text="Iniciando" FontSize="12" Foreground="#52525B"/>
                            </Grid>
                            <ProgressBar x:Name="Progress" Height="6" Minimum="0" Maximum="100" Value="0" Margin="0,8,0,0"
                                         Foreground="#111111" Background="#F4F4F5" BorderThickness="0"/>
                        </StackPanel>
                    </Border>

                    <Border Grid.Row="2" Background="#0A0A0A" CornerRadius="10" Padding="14,12">
                        <ScrollViewer x:Name="LogScroll" VerticalScrollBarVisibility="Auto">
                            <TextBox x:Name="LogBox" Background="Transparent" Foreground="#D4D4D4" BorderThickness="0"
                                     IsReadOnly="True" FontFamily="Consolas" FontSize="11" TextWrapping="Wrap"
                                     AcceptsReturn="True" VerticalScrollBarVisibility="Disabled"/>
                        </ScrollViewer>
                    </Border>
                </Grid>

                <Grid x:Name="DonePanel" Visibility="Collapsed">
                    <Border Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="32">
                        <StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
                            <Border x:Name="StatusBadge" Width="56" Height="56" CornerRadius="28" Background="#10B981" Margin="0,0,0,18">
                                <TextBlock x:Name="LblBadge" Text="OK" FontSize="20" FontWeight="Bold" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                            <TextBlock x:Name="LblDoneTitle" Text="Build publicado!" FontSize="22" FontWeight="SemiBold" Foreground="#111111" HorizontalAlignment="Center"/>
                            <TextBlock x:Name="LblDoneSub" Text="O frontend do backend esta atualizado." FontSize="13" Foreground="#71717A" HorizontalAlignment="Center" Margin="0,6,0,18"/>
                            <Border Background="#FAFAFA" CornerRadius="8" Padding="14,12" MaxWidth="620">
                                <TextBlock x:Name="LblSummary" FontFamily="Consolas" FontSize="11" Foreground="#52525B" TextWrapping="Wrap"/>
                            </Border>
                        </StackPanel>
                    </Border>
                </Grid>
            </Grid>

            <Border Grid.Row="2" BorderBrush="#EEEEEE" BorderThickness="0,1,0,0" Padding="32,0,32,0">
                <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" VerticalAlignment="Center">
                    <Button x:Name="BtnCancel" Style="{StaticResource GhostBtn}" Content="Cancelar" Margin="0,0,10,0" Visibility="Collapsed"/>
                    <Button x:Name="BtnPrimary" Style="{StaticResource PrimaryBtn}" Content="Publicar"/>
                </StackPanel>
            </Border>
        </Grid>
    </Border>
</Window>
"@

# =============================================================================
# Carregar XAML
# =============================================================================
$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)

$ctl = @{}
foreach ($name in 'LogoImg','BtnClose','IntroPanel','WorkPanel','DonePanel',
                  'LblBuildPath','LblDeployPath','LblStep','LblPhase','LblProgressTxt',
                  'Progress','LogBox','LogScroll','StatusBadge','LblBadge','LblDoneTitle',
                  'LblDoneSub','LblSummary','BtnCancel','BtnPrimary') {
    $ctl[$name] = $window.FindName($name)
}

$ctl.LblBuildPath.Text = $BUILD_DIR
$ctl.LblDeployPath.Text = $DEPLOY_DIR

if (Test-Path $LOGO_PATH) {
    try {
        $bmp = New-Object System.Windows.Media.Imaging.BitmapImage
        $bmp.BeginInit()
        $bmp.UriSource = New-Object System.Uri($LOGO_PATH, [System.UriKind]::Absolute)
        $bmp.CacheOption = [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad
        $bmp.EndInit()
        $ctl.LogoImg.Source = $bmp
    } catch {}
}

$window.Add_MouseLeftButtonDown({
    param($s, $e)
    if ($e.ButtonState -eq 'Pressed') { try { $window.DragMove() } catch {} }
})

$script:IsRunning = $false
$script:ExitCode = 0

function Set-UI([scriptblock]$sb) {
    [void]$window.Dispatcher.Invoke([Action]$sb)
}

function Append-Log([string]$msg, [string]$kind = 'info') {
    $ts = (Get-Date).ToString('HH:mm:ss')
    $prefix = switch ($kind) {
        'ok'    { '[OK] ' }
        'warn'  { '[!]  ' }
        'err'   { '[X]  ' }
        'step'  { '==>  ' }
        default { '     ' }
    }
    $line = "[$ts] $prefix$msg"
    Add-Content -Path $LOG -Value $line -Encoding UTF8
    Set-UI {
        $ctl.LogBox.AppendText($line + "`r`n")
        $ctl.LogScroll.ScrollToEnd()
    }
}

function Set-Progress([int]$pct, [string]$phase) {
    Set-UI {
        $ctl.Progress.Value = $pct
        $ctl.LblProgressTxt.Text = "$pct%"
        if ($phase) {
            $ctl.LblPhase.Text = $phase
            $ctl.LblStep.Text = $phase
        }
    }
}

function ConvertTo-ProcessArgument([string]$arg) {
    if ($null -eq $arg) { return '""' }
    if ($arg -notmatch '[\s"]') { return $arg }
    return '"' + ($arg -replace '"', '\"') + '"'
}

function Invoke-LoggedProcess([string]$fileName, [string[]]$arguments, [string]$description) {
    Append-Log $description 'step'
    Append-Log ("> " + $fileName + ' ' + ($arguments -join ' '))

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $fileName
    $psi.Arguments = ($arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $psi.WorkingDirectory = $ROOT
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $npmCache = Join-Path $ROOT 'tools\npm-cache'
    if (-not (Test-Path -LiteralPath $npmCache)) { New-Item -ItemType Directory -Path $npmCache -Force | Out-Null }
    $psi.EnvironmentVariables['npm_config_cache'] = $npmCache
    $psi.EnvironmentVariables['npm_config_audit'] = 'false'
    $psi.EnvironmentVariables['npm_config_fund'] = 'false'
    $psi.EnvironmentVariables['npm_config_update_notifier'] = 'false'

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi

    try {
        [void]$proc.Start()
    } catch {
        throw "Falha ao iniciar '$fileName' para '$description': $($_.Exception.Message)"
    }

    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $proc.WaitForExit()

    $stdoutText = ''
    $stderrText = ''
    try { $stdoutText = $stdoutTask.GetAwaiter().GetResult() } catch {
        Append-Log "Nao foi possivel ler toda a saida de ${description}: $($_.Exception.Message)" 'warn'
    }
    try { $stderrText = $stderrTask.GetAwaiter().GetResult() } catch {
        Append-Log "Nao foi possivel ler toda a saida de erro de ${description}: $($_.Exception.Message)" 'warn'
    }

    # Process output can contain thousands of Vite asset lines. Persist it in one
    # operation and update WPF in one batch so the log control cannot interrupt a
    # successful build while repeatedly repainting itself.
    $processLines = New-Object System.Collections.Generic.List[string]
    $ansiPattern = ([string][char]27) + '\[[0-9;?]*[ -/]*[@-~]'
    foreach ($entry in @(@($stdoutText, 'info'), @($stderrText, 'warn'))) {
        $text = [string]$entry[0]
        $kind = [string]$entry[1]
        $prefix = if ($kind -eq 'warn') { '[!]  ' } else { '     ' }
        foreach ($rawLine in [regex]::Split($text, "\r?\n")) {
            if ([string]::IsNullOrWhiteSpace($rawLine)) { continue }
            $cleanLine = [regex]::Replace($rawLine, $ansiPattern, '')
            [void]$processLines.Add("[$((Get-Date).ToString('HH:mm:ss'))] $prefix$cleanLine")
        }
    }

    if ($processLines.Count -gt 0) {
        Add-Content -LiteralPath $LOG -Value $processLines.ToArray() -Encoding UTF8
        $visibleLines = if ($processLines.Count -gt 240) {
            @("[... $($processLines.Count - 240) linhas mantidas somente em logs\build.log ...]") + $processLines.GetRange($processLines.Count - 240, 240).ToArray()
        } else {
            $processLines.ToArray()
        }
        try {
            Set-UI {
                $ctl.LogBox.AppendText(($visibleLines -join "`r`n") + "`r`n")
                $ctl.LogScroll.ScrollToEnd()
            }
        } catch {
            # A falha de pintura do log nao pode invalidar um processo concluido.
            Add-Content -LiteralPath $LOG -Value "[WARN] Falha apenas ao atualizar o log visual: $($_.Exception.Message)" -Encoding UTF8
        }
    }

    if ($proc.ExitCode -eq 0) {
        Append-Log "$description concluido" 'ok'
    } else {
        Append-Log "$description falhou com codigo $($proc.ExitCode)" 'err'
    }

    return $proc.ExitCode
}

function Get-NodeMajorFromVersion([string]$version) {
    if ([string]::IsNullOrWhiteSpace($version)) { return -1 }
    if ($version -notmatch '^v?(\d+)\.') { return -1 }
    return [int]$matches[1]
}

function Test-FrontendNodePair([string]$nodeExe, [string]$npmExe) {
    try {
        if ([string]::IsNullOrWhiteSpace($nodeExe) -or -not (Test-Path -LiteralPath $nodeExe)) { return $null }
        if ([string]::IsNullOrWhiteSpace($npmExe) -or -not (Test-Path -LiteralPath $npmExe)) { return $null }

        $nodePath = (Resolve-Path -LiteralPath $nodeExe).ProviderPath
        if ($nodePath -match '\\Microsoft\\WindowsApps\\node\.exe$') { return $null }

        $nodeVersionOut = & $nodePath --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $nodeVersion = (("$nodeVersionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        $nodeMajor = Get-NodeMajorFromVersion $nodeVersion
        if ($nodeMajor -lt 18 -or $nodeMajor -gt 22) { return $null }

        $npmPath = (Resolve-Path -LiteralPath $npmExe).ProviderPath
        $npmCliPath = Join-Path (Split-Path -Parent $nodePath) 'node_modules\npm\bin\npm-cli.js'
        if (Test-Path -LiteralPath $npmCliPath) {
            $npmVersionOut = & $nodePath $npmCliPath --version 2>&1
        } else {
            $npmVersionOut = & $npmPath --version 2>&1
        }
        if ($LASTEXITCODE -ne 0) { return $null }
        $npmVersion = (("$npmVersionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        if (-not $npmVersion) { return $null }

        return [pscustomobject]@{
            NodeExecutable = $nodePath
            NodeVersion    = $nodeVersion
            NpmExecutable  = $npmPath
            NpmVersion     = $npmVersion
            NodeDir        = Split-Path -Parent $nodePath
        }
    } catch {
        return $null
    }
}

function Resolve-FrontendNodeLaunch {
    $nodeCandidates = @()
    $portableRoots = @(
        (Join-Path $ROOT 'tools'),
        (Join-Path $env:LocalAppData 'NeveAI\tools'),
        (Join-Path $env:TEMP 'NeveAI\tools')
    ) | Select-Object -Unique
    foreach ($portableRoot in $portableRoots) {
        $portableNode = Join-Path $portableRoot 'nodejs\node.exe'
        if (Test-Path -LiteralPath $portableNode) { $nodeCandidates += $portableNode }
        if (Test-Path -LiteralPath $portableRoot) {
            $nodeCandidates += @(Get-ChildItem -LiteralPath $portableRoot -Directory -Filter 'nodejs-*' -EA SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName 'node.exe' } |
                Where-Object { Test-Path -LiteralPath $_ })
        }
    }
    if ($env:NODE_EXE) { $nodeCandidates += $env:NODE_EXE }

    foreach ($cmd in @(Get-Command node.exe -All -EA SilentlyContinue)) {
        $nodeCandidates += $cmd.Source
    }

    foreach ($nodeBase in (@($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ })) {
        $path = Join-Path $nodeBase 'nodejs\node.exe'
        if (Test-Path -LiteralPath $path) { $nodeCandidates += $path }
    }

    foreach ($nodeCandidate in ($nodeCandidates | Select-Object -Unique)) {
        $nodeDir = Split-Path -Parent $nodeCandidate
        foreach ($npmName in @('npm.cmd', 'npm.exe')) {
            $npmPath = Join-Path $nodeDir $npmName
            $pair = Test-FrontendNodePair $nodeCandidate $npmPath
            if ($pair) { return $pair }
        }
    }

    return $null
}

function Install-PortableNode22 {
    Set-Progress 8 'Preparando Node.js portatil'
    $toolsDir = Join-Path $ROOT 'tools'
    $nodeDir = Join-Path $toolsDir 'nodejs'

    $existing = Test-FrontendNodePair (Join-Path $nodeDir 'node.exe') (Join-Path $nodeDir 'npm.cmd')
    if ($existing) {
        Append-Log "Node.js portatil ja disponivel: $($existing.NodeVersion) / npm $($existing.NpmVersion)" 'ok'
        return $existing
    }

    if (-not (Test-Path -LiteralPath $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }
    Append-Log 'Baixando Node.js 22 LTS portatil porque nenhum Node.js 18-22 valido foi encontrado' 'step'

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
    } catch {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    }

    $release = $null
    try {
        $index = Invoke-RestMethod 'https://nodejs.org/dist/index.json' -Headers @{ 'User-Agent' = 'Neve-Buildar/1.0' } -TimeoutSec 60
        $release = $index | Where-Object { $_.version -match '^v22\.' -and $_.files -contains 'win-x64-zip' } | Select-Object -First 1
    } catch {
        Append-Log "Falha ao consultar versoes do Node.js: $($_.Exception.Message)" 'warn'
    }

    if (-not $release) {
        $release = [pscustomobject]@{ version = 'v22.23.3'; files = @('win-x64-zip') }
        Append-Log 'Indice do Node.js indisponivel; usando a versao LTS de fallback v22.23.3.' 'warn'
    }

    $version = [string]$release.version
    $url = "https://nodejs.org/dist/$version/node-$version-win-x64.zip"
    $zipPath = Join-Path $env:TEMP "neve_node_$version-$([guid]::NewGuid().ToString('N')).zip"
    $stageParent = Join-Path $env:TEMP "neve_node_stage_$([guid]::NewGuid().ToString('N'))"

    try {
        if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue }
        New-Item -ItemType Directory -Path $stageParent -Force | Out-Null
        Append-Log "Baixando $url"
        try {
            Invoke-WebRequest $url -OutFile $zipPath -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Buildar/1.0' } -TimeoutSec 300
        } catch {
            Append-Log "Download pelo PowerShell falhou: $($_.Exception.Message). Tentando curl." 'warn'
            $curl = Get-Command curl.exe -EA SilentlyContinue | Select-Object -First 1
            if (-not $curl) { throw }
            & $curl.Source -L --fail --silent --show-error --compressed --retry 3 --retry-delay 2 --connect-timeout 30 --max-time 300 --output $zipPath $url
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $zipPath) -or (Get-Item -LiteralPath $zipPath).Length -le 0) {
                throw "curl nao conseguiu baixar Node.js (exit $LASTEXITCODE)."
            }
        }

        Append-Log 'Extraindo Node.js portatil'
        Expand-Archive $zipPath -DestinationPath $stageParent -Force
        $extracted = Get-ChildItem -LiteralPath $stageParent -Directory | Select-Object -First 1
        if (-not $extracted) { throw 'Arquivo do Node.js nao extraiu a pasta esperada.' }
        $stagedPair = Test-FrontendNodePair (Join-Path $extracted.FullName 'node.exe') (Join-Path $extracted.FullName 'npm.cmd')
        if (-not $stagedPair) { throw 'Node.js portatil extraido nao passou na validacao.' }

        $installParents = @(
            $toolsDir,
            (Join-Path $env:LocalAppData 'NeveAI\tools'),
            (Join-Path $env:TEMP 'NeveAI\tools')
        ) | Select-Object -Unique
        $installErrors = @()
        foreach ($installParent in $installParents) {
            $candidateDir = Join-Path $installParent 'nodejs'
            $createdCandidate = $false
            try {
                if (-not (Test-Path -LiteralPath $installParent)) {
                    New-Item -ItemType Directory -Path $installParent -Force -EA Stop | Out-Null
                }
                $candidateExisting = Test-FrontendNodePair (Join-Path $candidateDir 'node.exe') (Join-Path $candidateDir 'npm.cmd')
                if ($candidateExisting) { return $candidateExisting }
                if (Test-Path -LiteralPath $candidateDir) {
                    try { Remove-Item -LiteralPath $candidateDir -Recurse -Force -EA Stop } catch {}
                    if (Test-Path -LiteralPath $candidateDir) {
                        $candidateDir = Join-Path $installParent ("nodejs-{0}-{1}" -f $version.TrimStart('v'), [guid]::NewGuid().ToString('N').Substring(0, 8))
                    }
                }
                $createdCandidate = $true
                Copy-Item -LiteralPath $extracted.FullName -Destination $candidateDir -Recurse -Force -EA Stop
                Get-ChildItem -LiteralPath $candidateDir -Recurse -File -EA SilentlyContinue | Unblock-File -EA SilentlyContinue

                $pair = $null
                for ($attempt = 1; $attempt -le 10 -and -not $pair; $attempt++) {
                    $pair = Test-FrontendNodePair (Join-Path $candidateDir 'node.exe') (Join-Path $candidateDir 'npm.cmd')
                    if (-not $pair) { Start-Sleep -Milliseconds 500 }
                }
                if (-not $pair) { throw 'Os arquivos foram copiados, mas Node.js/npm nao responderam.' }
                if ($candidateDir -ne $nodeDir) { Append-Log "Node.js portatil instalado no fallback: $candidateDir" 'warn' }
                Append-Log "Node.js portatil pronto: $($pair.NodeVersion) / npm $($pair.NpmVersion)" 'ok'
                return $pair
            } catch {
                $installErrors += "$candidateDir -> $($_.Exception.Message)"
                Append-Log "Nao foi possivel preparar Node.js em '$candidateDir': $($_.Exception.Message)" 'warn'
                if ($createdCandidate) {
                    try { Remove-Item -LiteralPath $candidateDir -Recurse -Force -EA SilentlyContinue } catch {}
                }
            }
        }
        throw "Nao foi possivel preparar Node.js portatil em nenhum local permitido. $($installErrors -join ' | ')"
    } finally {
        try { if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue } } catch {}
        try { if (Test-Path -LiteralPath $stageParent) { Remove-Item -LiteralPath $stageParent -Recurse -Force -EA SilentlyContinue } } catch {}
    }
}

function Resolve-OrInstallFrontendNode {
    $frontendNode = Resolve-FrontendNodeLaunch
    if (-not $frontendNode) { $frontendNode = Install-PortableNode22 }
    if (-not $frontendNode) { throw 'Node.js 18-22 com npm nao encontrado e o Node.js 22 portatil nao pode ser preparado.' }

    $env:PATH = "$($frontendNode.NodeDir);$env:PATH"
    $env:npm_config_cache = Join-Path $ROOT 'tools\npm-cache'
    $env:npm_config_audit = 'false'
    $env:npm_config_fund = 'false'
    $env:npm_config_update_notifier = 'false'

    Append-Log "Node.js do build: $($frontendNode.NodeVersion) / npm $($frontendNode.NpmVersion) em $($frontendNode.NodeDir)" 'ok'
    return $frontendNode
}

function Test-FrontendDependencies {
    $vite = Join-Path $ROOT 'node_modules\vite\bin\vite.js'
    $svelteKit = Join-Path $ROOT 'node_modules\@sveltejs\kit\package.json'
    return ((Test-Path -LiteralPath $vite) -and (Test-Path -LiteralPath $svelteKit))
}

function Ensure-FrontendDependencies([string]$npmExe) {
    if (Test-FrontendDependencies) {
        Append-Log 'Pacotes npm ja estao presentes' 'ok'
        return
    }

    Set-Progress 15 'Instalando pacotes npm'
    $rc = Invoke-LoggedProcess $npmExe @('install', '--no-audit', '--no-fund') 'npm install'
    if ($rc -ne 0) { throw "npm install falhou (codigo $rc)." }
}

function Ensure-OfficeCLI([string]$npmExe) {
    $previousOfficeCliSkipUpdate = $env:OFFICECLI_SKIP_UPDATE
    $previousOfficeCliNoAutoResident = $env:OFFICECLI_NO_AUTO_RESIDENT
    try {
        $env:OFFICECLI_SKIP_UPDATE = '1'
        $env:OFFICECLI_NO_AUTO_RESIDENT = '1'
        $officeCli = Join-Path $ROOT 'node_modules\@officecli\officecli\vendor\officecli.exe'
        $officeCliLauncher = Join-Path $ROOT 'node_modules\@officecli\officecli\officecli.js'
        if (-not (Test-Path -LiteralPath $officeCliLauncher)) {
            $rc = Invoke-LoggedProcess $npmExe @('install', '--no-audit', '--no-fund', '--prefer-offline', '--progress=false') 'instalar OfficeCLI'
            if ($rc -ne 0) { throw "npm install do OfficeCLI falhou (codigo $rc)." }
        }
        if (-not (Test-Path -LiteralPath $officeCli)) {
            $rc = Invoke-LoggedProcess $npmExe @('exec', '--', 'officecli', '--version') 'preparar OfficeCLI'
            if ($rc -ne 0 -or -not (Test-Path -LiteralPath $officeCli)) {
                throw 'Falha ao preparar o OfficeCLI para geracao de DOCX, XLSX e PPTX.'
            }
        }
        $rc = Invoke-LoggedProcess $officeCli @('--version') 'validar OfficeCLI'
        if ($rc -ne 0) { throw "OfficeCLI instalado, mas a validacao falhou (codigo $rc)." }
    } finally {
        if ($null -eq $previousOfficeCliSkipUpdate) { Remove-Item Env:\OFFICECLI_SKIP_UPDATE -ErrorAction SilentlyContinue } else { $env:OFFICECLI_SKIP_UPDATE = $previousOfficeCliSkipUpdate }
        if ($null -eq $previousOfficeCliNoAutoResident) { Remove-Item Env:\OFFICECLI_NO_AUTO_RESIDENT -ErrorAction SilentlyContinue } else { $env:OFFICECLI_NO_AUTO_RESIDENT = $previousOfficeCliNoAutoResident }
    }
    Append-Log 'OfficeCLI pronto para gerar DOCX, XLSX e PPTX' 'ok'
}

function Set-Done([bool]$ok, [string]$summary) {
    $script:ExitCode = if ($ok) { 0 } else { 1 }

    Set-UI {
        $ctl.IntroPanel.Visibility = 'Collapsed'
        $ctl.WorkPanel.Visibility = 'Collapsed'
        $ctl.DonePanel.Visibility = 'Visible'
        $ctl.BtnCancel.Visibility = 'Collapsed'
        $ctl.BtnPrimary.Tag = 'close'
        $ctl.BtnPrimary.Content = 'Fechar'
        $ctl.BtnPrimary.IsEnabled = $true

        if ($ok) {
            $ctl.StatusBadge.Background = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.ColorConverter]::ConvertFromString('#10B981'))
            $ctl.LblBadge.Text = 'OK'
            $ctl.LblDoneTitle.Text = 'Build publicado!'
            $ctl.LblDoneSub.Text = 'O frontend do backend esta atualizado.'
        } else {
            $ctl.StatusBadge.Background = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.ColorConverter]::ConvertFromString('#EF4444'))
            $ctl.LblBadge.Text = 'X'
            $ctl.LblDoneTitle.Text = 'Build falhou'
            $ctl.LblDoneSub.Text = 'Confira o log para ver o ponto da falha.'
        }

        $ctl.LblSummary.Text = $summary
    }
}

function Start-BuildDeploy {
    if ($script:IsRunning) { return }
    $script:IsRunning = $true

    Set-UI {
        $ctl.IntroPanel.Visibility = 'Collapsed'
        $ctl.DonePanel.Visibility = 'Collapsed'
        $ctl.WorkPanel.Visibility = 'Visible'
        $ctl.LogBox.Clear()
        $ctl.Progress.Value = 0
        $ctl.LblProgressTxt.Text = '0%'
        $ctl.LblPhase.Text = 'Preparando'
        $ctl.LblStep.Text = 'Preparando build...'
        $ctl.BtnPrimary.IsEnabled = $false
        $ctl.BtnCancel.Visibility = 'Collapsed'
        $ctl.BtnCancel.IsEnabled = $false
    }

    try {
        Stop-NeveRunningApp 'Buildar'

        Set-Location -LiteralPath $ROOT
        Append-Log "Pasta do build: $ROOT" 'ok'

        Set-Progress 5 'Preparando Node.js/npm'
        $frontendNode = Resolve-OrInstallFrontendNode
        $npmExe = $frontendNode.NpmExecutable

        Ensure-FrontendDependencies $npmExe
        Ensure-OfficeCLI $npmExe

        Set-Progress 22 'Limpando build antigo'
        if (Test-Path $BUILD_DIR) {
            Remove-Item $BUILD_DIR -Recurse -Force
            Append-Log 'Pasta build antiga removida' 'ok'
        } else {
            Append-Log 'Nenhuma pasta build antiga encontrada'
        }

        Set-Progress 32 'Executando npm run build'
        $rc = Invoke-LoggedProcess $npmExe @('run', 'build', '--', '--logLevel', 'error') 'npm run build'
        if ($rc -ne 0) { throw "npm run build falhou (codigo $rc)." }

        $srcIndex = Join-Path $BUILD_DIR 'index.html'
        if (-not (Test-Path $srcIndex)) { throw 'build\index.html nao foi gerado.' }

        Set-Progress 82 'Limpando destino do backend'
        if (Test-Path $DEPLOY_DIR) {
            Get-ChildItem -LiteralPath $DEPLOY_DIR -Force | Remove-Item -Recurse -Force
            Append-Log 'Destino backend\neveai\frontend limpo' 'ok'
        } else {
            New-Item $DEPLOY_DIR -ItemType Directory -Force | Out-Null
            Append-Log 'Destino backend\neveai\frontend criado' 'ok'
        }

        Set-Progress 88 'Copiando build para o backend'
        Copy-Item -Path (Join-Path $BUILD_DIR '*') -Destination $DEPLOY_DIR -Recurse -Force
        Append-Log 'Arquivos copiados para backend\neveai\frontend' 'ok'

        Set-Progress 94 'Verificando hash do deploy'
        $dstIndex = Join-Path $DEPLOY_DIR 'index.html'
        if (-not (Test-Path $dstIndex)) { throw 'backend\neveai\frontend\index.html nao foi publicado.' }
        $srcHash = Get-FileHash $srcIndex -Algorithm SHA256
        $dstHash = Get-FileHash $dstIndex -Algorithm SHA256
        if ($srcHash.Hash -ne $dstHash.Hash) { throw 'Hash do index.html nao bate entre build e deploy.' }
        Append-Log 'deploy hash match' 'ok'

        $fileCount = (Get-ChildItem -LiteralPath $DEPLOY_DIR -Recurse -File | Measure-Object).Count
        Set-Progress 100 'Concluido'

        $script:IsRunning = $false
        Set-Done $true "Build:  $BUILD_DIR`nDeploy: $DEPLOY_DIR`nArquivos publicados: $fileCount`nSHA256 index.html: $($srcHash.Hash)"
    } catch {
        Append-Log $_.Exception.Message 'err'
        $script:IsRunning = $false
        Set-Done $false "Erro: $($_.Exception.Message)`nLog:  $LOG"
    }
}

$ctl.BtnClose.Add_Click({ if (-not $script:IsRunning) { $window.Close() } })
$ctl.BtnCancel.Add_Click({ if (-not $script:IsRunning) { $window.Close() } })
$ctl.BtnPrimary.Add_Click({
    if ($ctl.BtnPrimary.Tag -eq 'close') {
        $ctl.DonePanel.Visibility = 'Collapsed'
        $ctl.WorkPanel.Visibility = 'Collapsed'
        $ctl.IntroPanel.Visibility = 'Visible'
        $ctl.BtnCancel.Visibility = 'Collapsed'
        $ctl.BtnPrimary.Tag = $null
        $ctl.BtnPrimary.Content = 'Publicar'
    } else {
        Start-BuildDeploy
    }
})

[void]$window.ShowDialog()
exit $script:ExitCode

'@

function Convert-LegacyWindowXamlToHubPage([string]$legacyXaml) {
	$openWindow = [regex]::new('(?s)^\s*<Window\b.*?>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
	$pageXaml = $openWindow.Replace(
		$legacyXaml,
		'<UserControl xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Background="Transparent">',
		1
	)
	$pageXaml = $pageXaml.Replace('</Window>', '</UserControl>')
	$pageXaml = $pageXaml.Replace('<Window.Resources>', '<UserControl.Resources>')
	$pageXaml = $pageXaml.Replace('</Window.Resources>', '</UserControl.Resources>')
	$pageXaml = $pageXaml.Replace('<Border CornerRadius="14" Background="#FAFAFA" BorderBrush="#E4E4E7" BorderThickness="1">', '<Border Background="#000000" CornerRadius="0,0,17,0" ClipToBounds="True">')
	$rowRegex = [regex]::new('<RowDefinition Height="56"/>')
	$pageXaml = $rowRegex.Replace($pageXaml, '<RowDefinition Height="0"/>', 1)
	$footerRowRegex = [regex]::new('<RowDefinition Height="68"/>')
	$pageXaml = $footerRowRegex.Replace($pageXaml, '<RowDefinition Height="0"/>', 1)
	# As telas antigas continuam com toda a lógica original, mas herdam a mesma
	# paleta escura e geometria visual da nova moldura.
	$pageXaml = $pageXaml.Replace('Background="#FAFAFA"', 'Background="#000000"')
	$pageXaml = $pageXaml.Replace('Background="White"', 'Background="#171717"')
	$pageXaml = $pageXaml.Replace('<Setter Property="Background" Value="#111111"/>', '<Setter Property="Background" Value="#202020"/>')
	$pageXaml = $pageXaml.Replace('<Setter Property="Foreground" Value="White"/>', '<Setter Property="Foreground" Value="#F3F5F7"/>')
	$pageXaml = $pageXaml.Replace('<Setter Property="Background" Value="#2563EB"/>', '<Setter Property="Background" Value="#202020"/>')
	$pageXaml = $pageXaml.Replace('<Setter TargetName="bd" Property="Background" Value="#1D4ED8"/>', '<Setter TargetName="bd" Property="Background" Value="#292929"/>')
	$pageXaml = $pageXaml.Replace('<Setter TargetName="bd" Property="Background" Value="#262626"/>', '<Setter TargetName="bd" Property="Background" Value="#292929"/>')
	$pageXaml = $pageXaml.Replace('Background="#F4F4F5"', 'Background="#202020"')
	$pageXaml = $pageXaml.Replace('Background="#0A0A0A"', 'Background="#000000"')
	$pageXaml = $pageXaml.Replace('BorderBrush="#E4E4E7"', 'BorderBrush="#303030"')
	$pageXaml = $pageXaml.Replace('BorderBrush="#EEEEEE"', 'BorderBrush="#303030"')
	$pageXaml = $pageXaml.Replace('BorderBrush="#D4D4D8"', 'BorderBrush="#484848"')
	$pageXaml = $pageXaml.Replace('Foreground="#111111"', 'Foreground="#F3F5F7"')
	$pageXaml = $pageXaml.Replace('Foreground="#52525B"', 'Foreground="#A9B1BC"')
	$pageXaml = $pageXaml.Replace('Foreground="#71717A"', 'Foreground="#8B8B8B"')
	$pageXaml = $pageXaml.Replace('CornerRadius="10"', 'CornerRadius="8"')
	$pageXaml = $pageXaml.Replace('CornerRadius="14"', 'CornerRadius="8"')
	return $pageXaml
}

function Convert-LegacyScriptToHubModule([string]$source, [string]$mode) {
	$xamlRegex = [regex]::new('(?s)\[xml\]\$xaml = @"\r?\n(.*?)\r?\n"@', [System.Text.RegularExpressions.RegexOptions]::Singleline)
	$match = $xamlRegex.Match($source)
	if (-not $match.Success) { throw "Nao foi possivel localizar o XAML legado de $mode." }

	$pageXaml = Convert-LegacyWindowXamlToHubPage $match.Groups[1].Value
	$replacement = "[xml]`$xaml = @'`r`n$pageXaml`r`n'@"
	$modified = $source.Remove($match.Index, $match.Length).Insert($match.Index, $replacement)

	$scriptPathRegex = [regex]::new('(?m)^\$SCRIPT_PATH\s*=.*$')
	$modified = $scriptPathRegex.Replace($modified, '$SCRIPT_PATH = $script:HubScriptPath', 1)

	$modified = $modified.Replace(
		'$window = [Windows.Markup.XamlReader]::Load($reader)',
		'$legacyPage = [Windows.Markup.XamlReader]::Load($reader); $window = $script:HubWindow; $script:HubPageRegistry[$script:HubMode] = $legacyPage; $script:HubPageHost.Content = $legacyPage'
	)
	$modified = $modified.Replace('$ctl[$name] = $window.FindName($name)', '$ctl[$name] = $legacyPage.FindName($name)')
	$modified = [regex]::Replace($modified, '(?m)^\[void\]\$window\.ShowDialog\(\)\s*$', '')
	$modified = [regex]::Replace($modified, '(?m)^exit \$script:ExitCode\s*$', '')

	$sharedHelpers = @'
$script:NeveAppCloseRequested = $false
function Stop-HubNeveProcessTree([int]$ProcessId) {
	if ($ProcessId -eq $PID) { return }
	try {
		$children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -EA SilentlyContinue)
		foreach ($child in $children) { Stop-HubNeveProcessTree ([int]$child.ProcessId) }
	} catch {}
	try {
		$proc = Get-Process -Id $ProcessId -EA SilentlyContinue
		if ($proc -and -not $proc.HasExited) { Stop-Process -Id $ProcessId -Force -EA SilentlyContinue }
	} catch {}
}

function Stop-NeveRunningApp([string]$Reason = 'operação') {
	if ($script:NeveAppCloseRequested) { return }
	$script:NeveAppCloseRequested = $true

	try {
		Add-Content -LiteralPath $LOG -Value ("[INFO] Encerrando NeveAI antes de iniciar: {0}" -f $Reason) -Encoding UTF8
	} catch {}

	$targets = @()
	$browserProfile = ''
	try { $browserProfile = (Join-Path $ROOT 'logs\browser-app').ToLowerInvariant() } catch {}
	$browserProfileAlt = $browserProfile -replace '\\', '/'

	try {
		foreach ($proc in @(Get-CimInstance Win32_Process -EA SilentlyContinue)) {
			$processId = [int]$proc.ProcessId
			if ($processId -eq $PID) { continue }

			$name = if ($proc.Name) { [string]$proc.Name } else { '' }
			$cmd = if ($proc.CommandLine) { [string]$proc.CommandLine } else { '' }
			$nameLower = $name.ToLowerInvariant()
			$cmdLower = $cmd.ToLowerInvariant()

			if ($cmdLower.Contains('instalar.ps1') -or $cmdLower.Contains('install-launcher.log')) {
				continue
			}

			$isTarget = $false
			if ($nameLower -like 'llama-server*' -or $nameLower -like 'llama_server*') {
				$isTarget = $true
			}
			if ($cmdLower.Contains('neveai.main:app')) {
				$isTarget = $true
			}
			if ($cmdLower.Contains('neve_window.py')) {
				$isTarget = $true
			}
			if ($browserProfile -and ($cmdLower.Contains($browserProfile) -or $cmdLower.Contains($browserProfileAlt))) {
				$isTarget = $true
			}
			if ($cmdLower.Contains('--app=http://localhost:8080') -or $cmdLower.Contains('--app=http://127.0.0.1:8080')) {
				$isTarget = $true
			}

			if ($isTarget) { $targets += $processId }
		}
	} catch {}

	foreach ($targetPid in @($targets | Sort-Object -Unique)) {
		try { Stop-HubNeveProcessTree ([int]$targetPid) } catch {}
	}

	if ($targets.Count -gt 0) {
		Start-Sleep -Milliseconds 600
	}
}
'@

	return @"
param(`$HubWindowParam, `$HubPageHostParam, `$HubPageRegistryParam, `$HubModeParam, `$HubScriptPathParam)
`$script:HubWindow = `$HubWindowParam
`$script:HubPageHost = `$HubPageHostParam
`$script:HubPageRegistry = `$HubPageRegistryParam
`$script:HubMode = `$HubModeParam
`$script:HubScriptPath = `$HubScriptPathParam
$sharedHelpers
$modified
"@
}

function Initialize-HubLegacyPage([string]$mode) {
	if ($script:HubLegacyPages.ContainsKey($mode)) {
		$ctl.HubPageHost.Content = $script:HubLegacyPages[$mode]
		return
	}

	$source = switch ($mode) {
		'update' { $script:UpdateLegacySource }
		'build' { $script:BuildLegacySource }
		default { throw "Pagina de hub desconhecida: $mode" }
	}

	$moduleSource = Convert-LegacyScriptToHubModule $source $mode
	$module = New-Module -Name "NeveHub_$mode" -ScriptBlock ([scriptblock]::Create($moduleSource)) -ArgumentList $window, $ctl.HubPageHost, $script:HubLegacyPages, $mode, $SCRIPT_PATH
	$script:HubLegacyModules[$mode] = $module

	$actionPanel = New-Object System.Windows.Controls.StackPanel
	$actionPanel.Orientation = [System.Windows.Controls.Orientation]::Horizontal
	$actionPanel.VerticalAlignment = [System.Windows.VerticalAlignment]::Center
	$actionPanel.Visibility = [System.Windows.Visibility]::Collapsed
	$actionNames = if ($mode -eq 'update') { @('BtnLlama', 'BtnCancel', 'BtnPrimary') } else { @('BtnCancel', 'BtnPrimary') }
	foreach ($actionName in $actionNames) {
		$button = $script:HubLegacyPages[$mode].FindName($actionName)
		if (-not $button) { continue }
		$parent = $button.Parent
		if ($parent -is [System.Windows.Controls.Panel]) { [void]$parent.Children.Remove($button) }
		$button.Style = $window.FindResource('PrimaryBtn')
		$button.Margin = New-Object System.Windows.Thickness(0, 0, 10, 0)
		$originMode = $mode
		$button.Add_Click({
			if (-not (Test-HubActivePageBusy)) { Select-HubPage $originMode }
		}.GetNewClosure())
		[void]$actionPanel.Children.Add($button)
	}
	if ($actionPanel.Children.Count -gt 0) {
		$actionPanel.Children[$actionPanel.Children.Count - 1].Margin = New-Object System.Windows.Thickness(0)
	}
	[void]$ctl.HeaderActions.Children.Add($actionPanel)
	$script:HubActionPanels[$mode] = $actionPanel

	# Os títulos das páginas agora vivem no cabeçalho persistente da moldura.
	try {
		$page = $script:HubLegacyPages[$mode]
		if ($mode -eq 'update') {
			$title = $page.FindName('LblCheckTitle')
			if ($title -and $title.Parent) { $title.Parent.Visibility = 'Collapsed' }
			foreach ($panelName in @('CheckPanel', 'DonePanel')) {
				$panel = $page.FindName($panelName)
				if ($panel -and $panel.Children.Count -gt 0) {
					$card = $panel.Children[$panel.Children.Count - 1]
					$card.VerticalAlignment = 'Top'
					$card.Margin = New-Object System.Windows.Thickness(0, 16, 0, 0)
				}
			}
			foreach ($checkName in @('ChkUpdateNeve', 'ChkUpdateLlama')) {
				$check = $page.FindName($checkName)
				if ($check) { $check.Style = $window.FindResource('OptionCheckBox') }
			}
		} elseif ($mode -eq 'build') {
			$intro = $page.FindName('IntroPanel')
			if ($intro -and $intro.Children.Count -gt 0) {
				$intro.Children[0].Visibility = 'Collapsed'
				$card = $intro.Children[$intro.Children.Count - 1]
				$card.VerticalAlignment = 'Top'
				$card.Margin = New-Object System.Windows.Thickness(0, 16, 0, 0)
			}
			$done = $page.FindName('DonePanel')
			if ($done -and $done.Children.Count -gt 0) {
				$card = $done.Children[$done.Children.Count - 1]
				$card.VerticalAlignment = 'Top'
				$card.Margin = New-Object System.Windows.Thickness(0, 16, 0, 0)
			}
		}
	} catch {}
}

function Show-HubActionPanel([string]$mode) {
	foreach ($entry in $script:HubActionPanels.GetEnumerator()) {
		$entry.Value.Visibility = if ($entry.Key -eq $mode) { 'Visible' } else { 'Collapsed' }
	}
}

function Update-HubActionButtonStyles {
	$accentStyle = $window.FindResource('AccentActionBtn')
	$regularStyle = $window.FindResource('PrimaryBtn')
	$completionStyle = $window.FindResource('CompletionActionBtn')
	foreach ($panel in $script:HubActionPanels.Values) {
		foreach ($button in $panel.Children) {
			if (-not ($button -is [System.Windows.Controls.Button])) { continue }
			$label = [string]$button.Content
			$targetStyle = if ($label -in @('Instalar', 'Atualizar', 'Publicar')) {
				$accentStyle
			} elseif ($label -in @('Cancelar', 'Concluir', 'Fechar')) {
				$completionStyle
			} else {
				$regularStyle
			}
			if ($button.Style -ne $targetStyle) { $button.Style = $targetStyle }
		}
	}
}

function Set-HubHeaderState([string]$mode) {
	$ctl.LblPageContext.Text = switch ($mode) {
		'install' { 'Instalação' }
		'update' { 'Atualização' }
		'build' { 'Publicação' }
		default { 'Instalação' }
	}
	$ctl.LblPageSubtitle.Text = switch ($mode) {
		'install' { 'Detecte o hardware e instale tudo o que a NeveAI precisa.' }
		'update' { 'Verifique e instale novas versões da NeveAI e do llama.cpp.' }
		'build' { 'Compile e publique o projeto na pasta do backend.' }
		default { 'Detecte o hardware e instale tudo o que a NeveAI precisa.' }
	}
	$ctl.NavOverview.Tag = if ($mode -eq 'install') { 'active' } else { $null }
	$ctl.NavSettings.Tag = if ($mode -eq 'update') { 'active' } else { $null }
	$ctl.NavDiagnostics.Tag = if ($mode -eq 'build') { 'active' } else { $null }
}

function Get-HubLegacyPageControl([string]$mode, [string]$name) {
	try {
		if (-not $script:HubLegacyPages.ContainsKey($mode)) { return $null }
		$page = $script:HubLegacyPages[$mode]
		if (-not $page) { return $null }
		return $page.FindName($name)
	} catch {
		return $null
	}
}

function Test-HubActivePageBusy {
	switch ($script:HubActiveMode) {
		'install' {
			return ([string]$window.Tag -eq 'installing')
		}
		'update' {
			$updatePanel = Get-HubLegacyPageControl 'update' 'UpdatePanel'
			return ($updatePanel -and $updatePanel.Visibility -eq 'Visible')
		}
		'build' {
			$workPanel = Get-HubLegacyPageControl 'build' 'WorkPanel'
			return ($workPanel -and $workPanel.Visibility -eq 'Visible')
		}
		default {
			return $false
		}
    }
}

function Test-HubProjectInstalled {
    $requiredPaths = @(
        (Join-Path $ROOT '.env'),
        (Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe'),
        (Join-Path $ROOT 'node_modules'),
        (Join-Path $ROOT 'backend\neveai\frontend\index.html')
    )
    foreach ($path in $requiredPaths) {
        if (-not (Test-Path -LiteralPath $path)) { return $false }
    }
    return $true
}

function Select-HubPage([string]$mode) {
    if (Test-HubActivePageBusy) { return }
    if ($mode -eq 'home') { $mode = 'install' }
    if ($mode -in @('update', 'build') -and -not (Test-HubProjectInstalled)) {
        $mode = 'install'
    }

	$script:HubActiveMode = $mode
	Set-HubHeaderState $mode

	if ($mode -eq 'install') {
		$ctl.HubPageHost.Visibility = 'Collapsed'
		$ctl.InstallBodyHost.Visibility = 'Visible'
		$ctl.InstallFooterHost.Visibility = 'Collapsed'
		Show-HubActionPanel 'install'
		return
	}

	$ctl.InstallBodyHost.Visibility = 'Collapsed'
	$ctl.InstallFooterHost.Visibility = 'Collapsed'
	$ctl.HubPageHost.Visibility = 'Visible'

	try {
		Initialize-HubLegacyPage $mode
		Show-HubActionPanel $mode
	} catch {
		[System.Windows.MessageBox]::Show(
			"Falha ao abrir a pagina '$mode'.`r`n`r`n$($_.Exception.Message)",
			'NeveAI - Hub',
			[System.Windows.MessageBoxButton]::OK,
			[System.Windows.MessageBoxImage]::Error
		) | Out-Null
		Select-HubPage 'install'
	}
}

$script:HubBusyMonitorTimer = New-Object Windows.Threading.DispatcherTimer
$script:HubBusyMonitorTimer.Interval = [TimeSpan]::FromMilliseconds(150)
$script:HubBusyMonitorTimer.Add_Tick({
	Complete-PendingInstallCleanup
	if ($script:HubLegacyModules.ContainsKey('update')) {
		try { & $script:HubLegacyModules['update'] { Complete-PendingUpdateCleanup } } catch {}
	}
	$busy = Test-HubActivePageBusy
	$installed = Test-HubProjectInstalled
	Update-HubActionButtonStyles
	$ctl.NavOverview.IsEnabled = (-not $busy) -or $script:HubActiveMode -eq 'install'
	$ctl.NavSettings.IsEnabled = $installed -and ((-not $busy) -or $script:HubActiveMode -eq 'update')
	$ctl.NavDiagnostics.IsEnabled = $installed -and ((-not $busy) -or $script:HubActiveMode -eq 'build')
	$blockedHint = if ($installed) { $null } else { 'Conclua a instalação antes de acessar esta aba.' }
	$ctl.NavSettings.ToolTip = $blockedHint
	$ctl.NavDiagnostics.ToolTip = $blockedHint
})
$script:HubBusyMonitorTimer.Start()
$window.Add_Closed({ try { $script:HubBusyMonitorTimer.Stop() } catch {} })

$ctl.NavOverview.Add_Click({ Select-HubPage 'install' })
$ctl.NavSettings.Add_Click({ Select-HubPage 'update' })
$ctl.NavDiagnostics.Add_Click({ Select-HubPage 'build' })
Select-HubPage $(if ($StartPage -eq 'home') { 'install' } else { $StartPage })

# =============================================================================
# Mostrar a janela
# =============================================================================
[void]$window.ShowDialog()
