using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal sealed class NeveWindow : Form
{
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hwnd, int command);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, IntPtr process);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint current, uint foreground, bool attach);
    [DllImport("user32.dll")] static extern bool IsHungAppWindow(IntPtr hwnd);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr context);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern int SetCurrentProcessExplicitAppUserModelID(string id);
    delegate bool WindowCallback(IntPtr hwnd, IntPtr data);
    [DllImport("user32.dll")] static extern bool EnumWindows(WindowCallback callback, IntPtr data);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr GetProp(IntPtr hwnd, string name);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern bool SetProp(IntPtr hwnd, string name, IntPtr value);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr RemoveProp(IntPtr hwnd, string name);

    readonly WebView2 view = new WebView2();
    readonly JavaScriptSerializer json = new JavaScriptSerializer();
    readonly string root, runtime, profile, readyFile, stateFile;
    readonly Uri appUri;
    readonly EventWaitHandle readiness;
    bool ready, initializing, dark = true;
    System.Windows.Forms.Timer startup;
    readonly System.Windows.Forms.Timer stateTimer = new System.Windows.Forms.Timer();
    Rectangle lastNormalBounds;
    bool lastMaximized;
    CoreWebView2Environment environment;
    readonly List<Form> popups = new List<Form>();

    NeveWindow(Dictionary<string, string> args, EventWaitHandle signal)
    {
        readiness = signal;
        json.MaxJsonLength = 64 * 1024 * 1024;
        root = Path.GetFullPath(args["root"]);
        runtime = Path.GetFullPath(args["runtime"]);
        profile = Path.GetFullPath(args["profile"]);
        readyFile = args.ContainsKey("ready-file") ? args["ready-file"] : "";
        appUri = new Uri(args.ContainsKey("url") ? args["url"] : "http://localhost:8080/?neve-desktop=1");
        if (appUri.Scheme != "http" || !appUri.IsLoopback ||
            (appUri.Port != 8080 && Environment.GetEnvironmentVariable("NEVE_WEBVIEW2_TEST_MODE") != "1"))
            throw new ArgumentException("A janela aceita somente o servidor local do NeveAI.");
        stateFile = Path.Combine(Path.GetDirectoryName(profile), "window-state.json");
        Directory.CreateDirectory(profile);
        Text = "";
        ShowIcon = false;
        Icon = new Icon(Path.Combine(root, "static", "static", "faviconbar.ico"));
        MinimumSize = new Size(480, 320);
        StartPosition = FormStartPosition.Manual;
        Bounds = new Rectangle(160, 80, 1280, 820);
        BackColor = Color.Black;
        Opacity = 0;
        view.Dock = DockStyle.Fill;
        view.DefaultBackgroundColor = Color.Black;
        Controls.Add(view);
        RestoreState();
        lastNormalBounds = Bounds;
        lastMaximized = WindowState == FormWindowState.Maximized;
        stateTimer.Interval = 300;
        stateTimer.Tick += delegate { stateTimer.Stop(); if (ready) SaveState(); };
        Move += delegate { RememberBounds(); };
        Resize += delegate { RememberBounds(); };
        Shown += async delegate { await Initialize(); };
        FormClosing += delegate { if (ready) SaveState(); };
        FormClosed += delegate { if (startup != null) startup.Dispose(); stateTimer.Dispose(); foreach (Form popup in popups.ToArray()) popup.Close(); view.Dispose(); };
    }

    void Log(string message)
    {
        try { File.AppendAllText(Path.Combine(root, "logs", "webview2-window.log"),
            DateTime.UtcNow.ToString("o") + " " + message + Environment.NewLine); } catch { }
    }

    void Theme(bool isDark)
    {
        dark = isDark;
        BackColor = dark ? Color.Black : Color.White;
        view.DefaultBackgroundColor = BackColor;
        int mode = dark ? 1 : 0, backdrop = 1;
        try {
            DwmSetWindowAttribute(Handle, 20, ref mode, 4);
            DwmSetWindowAttribute(Handle, 38, ref backdrop, 4);
        } catch (DllNotFoundException) { }
    }

    async Task Initialize()
    {
        if (initializing) return;
        initializing = true;
        try {
            if (!File.Exists(Path.Combine(runtime, "msedgewebview2.exe")))
                throw new FileNotFoundException("WebView2 Fixed ausente. Execute instalar.bat.");
            var options = new CoreWebView2EnvironmentOptions();
            options.AdditionalBrowserArguments = "--disable-backgrounding-occluded-windows";
            int debugPort;
            if (Int32.TryParse(Environment.GetEnvironmentVariable("NEVE_WEBVIEW2_DEBUG_PORT"), out debugPort) && debugPort >= 1024 && debugPort <= 65535)
                options.AdditionalBrowserArguments += " --remote-debugging-address=127.0.0.1 --remote-debugging-port=" + debugPort;
            environment = await CoreWebView2Environment.CreateAsync(runtime, profile, options);
            await view.EnsureCoreWebView2Async(environment);
            var core = view.CoreWebView2;
            if (Environment.GetEnvironmentVariable("NEVE_WEBVIEW2_TEST_MODE") == "1") {
                string downloads = Path.Combine(Path.GetDirectoryName(profile), "downloads");
                Directory.CreateDirectory(downloads);
                core.Profile.DefaultDownloadFolderPath = downloads;
            }
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.AreDevToolsEnabled = debugPort != 0;
            core.Settings.IsSwipeNavigationEnabled = false;
            core.WebMessageReceived += OnMessage;
            core.NewWindowRequested += OpenPopup;
            core.WindowCloseRequested += delegate { Close(); };
            core.PermissionRequested += delegate(object sender, CoreWebView2PermissionRequestedEventArgs e) {
                Uri source;
                if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out source) || source.GetLeftPart(UriPartial.Authority) != appUri.GetLeftPart(UriPartial.Authority)) {
                    e.State = CoreWebView2PermissionState.Deny; return;
                }
                if (e.PermissionKind == CoreWebView2PermissionKind.Microphone || e.PermissionKind == CoreWebView2PermissionKind.Camera) {
                    string device = e.PermissionKind == CoreWebView2PermissionKind.Camera ? "camera" : "microfone";
                    e.State = MessageBox.Show(this, "Permitir que o NeveAI use o " + device + "?", "NeveAI", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes ? CoreWebView2PermissionState.Allow : CoreWebView2PermissionState.Deny;
                }
            };
            core.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e) {
                Uri target;
                if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out target) || target.GetLeftPart(UriPartial.Authority) != appUri.GetLeftPart(UriPartial.Authority)) {
                    e.Cancel = true;
                    if (target != null) OpenLink(target);
                }
            };
            core.NavigationCompleted += delegate(object sender, CoreWebView2NavigationCompletedEventArgs e) {
                if (!e.IsSuccess && !ready) Fail("Nao foi possivel abrir o servidor local: " + e.WebErrorStatus);
            };
            core.ProcessFailed += delegate(object sender, CoreWebView2ProcessFailedEventArgs e) {
                Log("process_failed " + e.ProcessFailedKind);
                if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited || e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited)
                    Fail("O processo da interface foi encerrado. Reabra o NeveAI; os dados do servidor foram preservados.");
            };
            // This bridge accepts only UI lifecycle messages, never native commands.
            await core.AddScriptToExecuteOnDocumentCreatedAsync(@"(() => {
                if (window.top !== window || location.origin !== '" + appUri.GetLeftPart(UriPartial.Authority) + @"') return;
                window.__NEVE_WEBVIEW2__ = true;
                const theme = () => chrome.webview.postMessage({type:'neve:theme',dark:document.documentElement.classList.contains('dark')});
                const watch = () => { theme(); new MutationObserver(theme).observe(document.documentElement,{attributes:true,attributeFilter:['class']}); };
                if(document.documentElement) watch(); else addEventListener('DOMContentLoaded',watch,{once:true});
            })();");
            var migration = Path.Combine(Path.GetDirectoryName(profile), "local-storage-migration.json");
            if (File.Exists(migration)) {
                var data = File.ReadAllText(migration);
                // Deserialize/re-serialize so file contents cannot become executable script.
                var values = json.Deserialize<Dictionary<string, string>>(data);
                string literal = json.Serialize(values);
                await core.AddScriptToExecuteOnDocumentCreatedAsync(@"if(window.top===window && location.origin==='" + appUri.GetLeftPart(UriPartial.Authority) + @"' && !localStorage.getItem('neveai.webview2.migrated')) {
                    const values=" + literal + @"; for(const key of Object.keys(values)) if(localStorage.getItem(key)===null) localStorage.setItem(key,values[key]);
                    localStorage.setItem('neveai.webview2.migrated','1'); }");
            }
            Theme(true);
            startup = new System.Windows.Forms.Timer();
            startup.Interval = 60000;
            startup.Tick += delegate { if (!ready) Fail("A interface nao concluiu a abertura. Consulte logs/webview2-window.log."); };
            startup.Start();
            core.Navigate(appUri.AbsoluteUri);
            Log("runtime " + environment.BrowserVersionString);
        } catch (Exception error) { Fail(error.ToString()); }
    }

    void OnMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        Uri source;
        if (!Uri.TryCreate(e.Source, UriKind.Absolute, out source) || source.GetLeftPart(UriPartial.Authority) != appUri.GetLeftPart(UriPartial.Authority)) return;
        try {
            var message = json.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
            if (message.ContainsKey("type") && (string)message["type"] == "neve:theme" && message.ContainsKey("dark") && message["dark"] is bool)
                Theme((bool)message["dark"]);
            else if (message.ContainsKey("type") && (string)message["type"] == "neve:ready" && !ready) {
                ready = true;
                if (startup != null) startup.Stop();
                Opacity = 1;
                PresentWindow(Handle);
                view.Focus();
                string migration = Path.Combine(Path.GetDirectoryName(profile), "local-storage-migration.json");
                if (File.Exists(migration)) File.Delete(migration);
                File.WriteAllText(Path.Combine(Path.GetDirectoryName(profile), "migration-complete"), "complete");
                WriteReady(readyFile);
                readiness.Set();
                RememberBounds();
                Log("ready");
            }
        } catch (Exception error) { Log("message " + error.GetType().Name); }
    }

    static void OpenLink(Uri target)
    {
        if (target.Scheme == "http" || target.Scheme == "https" || target.Scheme == "mailto") {
            try { Process.Start(new ProcessStartInfo(target.AbsoluteUri) { UseShellExecute = true }); } catch { }
        }
    }

    async void OpenPopup(object sender, CoreWebView2NewWindowRequestedEventArgs e)
    {
        Uri target;
        if (Uri.TryCreate(e.Uri, UriKind.Absolute, out target) && (target.Scheme == "mailto" || ((target.Scheme == "http" || target.Scheme == "https") && !target.IsLoopback))) {
            e.Handled = true;
            OpenLink(target);
            return;
        }
        if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out target) || !new[] { "http", "https", "blob", "about" }.Contains(target.Scheme)) { e.Handled = true; return; }
        var deferral = e.GetDeferral();
        Form popup = null;
        try {
            popup = new Form { Text = "NeveAI", Icon = Icon, Size = new Size(1100, 800), BackColor = BackColor, Opacity = 0 };
            var preview = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = BackColor };
            popup.Controls.Add(preview);
            popups.Add(popup);
            Form owned = popup;
            popup.FormClosed += delegate { popups.Remove(owned); preview.Dispose(); };
            popup.Show(this);
            await preview.EnsureCoreWebView2Async(environment);
            preview.CoreWebView2.Settings.AreDevToolsEnabled = view.CoreWebView2.Settings.AreDevToolsEnabled;
            preview.CoreWebView2.Settings.IsStatusBarEnabled = false;
            preview.CoreWebView2.NavigationCompleted += delegate { owned.Opacity = 1; };
            preview.CoreWebView2.NewWindowRequested += OpenPopup;
            preview.CoreWebView2.WindowCloseRequested += delegate { owned.Close(); };
            e.NewWindow = preview.CoreWebView2;
            e.Handled = true;
        } catch (Exception error) { Log("popup " + error.GetType().Name); e.Handled = true; if (popup != null) popup.Close(); }
        finally { deferral.Complete(); }
    }

    void Fail(string message)
    {
        if (IsDisposed || Disposing) return;
        Log(message);
        if (startup != null) startup.Stop();
        MessageBox.Show(message, "NeveAI", MessageBoxButtons.OK, MessageBoxIcon.Error);
        Close();
        Environment.ExitCode = 1;
    }

    void RestoreState()
    {
        try {
            string path = File.Exists(stateFile) ? stateFile : Path.Combine(root, "logs", "browser-app", "window-state.json");
            var state = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path));
            var rect = (Dictionary<string, object>)state["normal_rect"];
            var bounds = Rectangle.FromLTRB(Convert.ToInt32(rect["left"]), Convert.ToInt32(rect["top"]), Convert.ToInt32(rect["right"]), Convert.ToInt32(rect["bottom"]));
            if (bounds.Width >= 480 && bounds.Height >= 320 && Array.Exists(Screen.AllScreens, s => Rectangle.Intersect(s.WorkingArea, bounds).Width >= 100 && Rectangle.Intersect(s.WorkingArea, bounds).Height >= 100)) Bounds = bounds;
            if (state.ContainsKey("maximized") && (bool)state["maximized"]) WindowState = FormWindowState.Maximized;
        } catch { }
    }

    void RememberBounds()
    {
        if (!ready || WindowState == FormWindowState.Minimized) return;
        Rectangle candidate = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
        if (candidate.Width >= 480 && candidate.Height >= 320 && Array.Exists(Screen.AllScreens, screen => Rectangle.Intersect(screen.WorkingArea, candidate).Width >= 100)) {
            lastNormalBounds = candidate;
            lastMaximized = WindowState == FormWindowState.Maximized;
        }
        stateTimer.Stop();
        stateTimer.Start();
    }

    void SaveState()
    {
        try {
            Rectangle bounds = WindowState == FormWindowState.Minimized ? lastNormalBounds : WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            string value = json.Serialize(new { maximized = WindowState == FormWindowState.Minimized ? lastMaximized : WindowState == FormWindowState.Maximized,
                normal_rect = new { left = bounds.Left, top = bounds.Top, right = bounds.Right, bottom = bounds.Bottom } });
            string temporary = stateFile + ".tmp";
            Directory.CreateDirectory(Path.GetDirectoryName(stateFile));
            File.WriteAllText(temporary, value);
            if (File.Exists(stateFile)) File.Replace(temporary, stateFile, null);
            else File.Move(temporary, stateFile);
        } catch (Exception error) { Log("state " + error.GetType().Name); }
    }

    static void WriteReady(string path)
    {
        if (!String.IsNullOrEmpty(path)) { Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))); File.WriteAllText(path, "ready"); }
    }

    static void PresentWindow(IntPtr hwnd)
    {
        // Restore once on launch; never keep the application above other windows.
        IntPtr foreground = GetForegroundWindow();
        uint current = GetCurrentThreadId();
        uint other = GetWindowThreadProcessId(foreground, IntPtr.Zero);
        bool attached = foreground != IntPtr.Zero && other != 0 && other != current &&
            !IsHungAppWindow(foreground) && AttachThreadInput(current, other, true);
        try {
            ShowWindow(hwnd, IsIconic(hwnd) ? 9 : 5);
            SetWindowPos(hwnd, IntPtr.Zero, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040);
            SetForegroundWindow(hwnd);
        } finally { if (attached) AttachThreadInput(current, other, false); }
    }

    [STAThread]
    static int Main(string[] arguments)
    {
        try {
            var args = new Dictionary<string, string>();
            for (int index = 0; index < arguments.Length; index += 2) args.Add(arguments[index].TrimStart('-'), arguments[index + 1]);
            string key;
            using (var hash = SHA256.Create()) key = BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(Path.GetFullPath(args["profile"]).ToLowerInvariant()))).Replace("-", "");
            bool owns;
            using (var mutex = new Mutex(true, "Local\\NeveAI.WebView2." + key, out owns)) {
              using (var signal = new EventWaitHandle(false, EventResetMode.ManualReset, "Local\\NeveAI.WebView2.Ready." + key)) {
                if (!owns) {
                    if (!signal.WaitOne(TimeSpan.FromSeconds(60))) throw new TimeoutException("A primeira janela ainda nao concluiu a abertura.");
                    IntPtr existing = IntPtr.Zero;
                    EnumWindows(delegate(IntPtr hwnd, IntPtr data) { if (GetProp(hwnd, "NeveAI." + key) != IntPtr.Zero) { existing = hwnd; return false; } return true; }, IntPtr.Zero);
                    if (existing == IntPtr.Zero) throw new InvalidOperationException("A janela anterior nao foi localizada.");
                    PresentWindow(existing);
                    WriteReady(args.ContainsKey("ready-file") ? args["ready-file"] : "");
                    return 0;
                }
                signal.Reset();
                try { SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch (EntryPointNotFoundException) { }
                SetCurrentProcessExplicitAppUserModelID("NeveAI.Desktop");
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                var window = new NeveWindow(args, signal);
                IntPtr handle = window.Handle;
                SetProp(handle, "NeveAI." + key, new IntPtr(1));
                try { Application.Run(window); }
                finally { RemoveProp(handle, "NeveAI." + key); }
                return Environment.ExitCode;
              }
            }
        } catch (Exception error) { MessageBox.Show(error.ToString(), "NeveAI", MessageBoxButtons.OK, MessageBoxIcon.Error); return 1; }
    }
}
