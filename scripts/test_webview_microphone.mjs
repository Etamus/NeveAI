import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, readFile, copyFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { once } from 'node:events';

const root = process.cwd();
const state = JSON.parse(await readFile('.desktop/installed.json', 'utf8'));
const profile = await mkdtemp(path.join(tmpdir(), 'neve-test-mic-'));
// Fixed WebView2 uses the host's explicit browser options. Inject only the fake
// capture device in the test build, never auto-grant microphone permission.
const host = path.join(profile,'MicFixture.exe');
const libs = ['Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll'];
for (const name of [...libs,'WebView2Loader.dll'])
	await copyFile(path.join(root,'.desktop',path.dirname(state.host),name),path.join(profile,name));
const source = await readFile('desktop/NeveWindow.cs','utf8');
assert(source.includes('"--disable-backgrounding-occluded-windows"'));
await writeFile(path.join(profile,'MicFixture.cs'),source.replace('"--disable-backgrounding-occluded-windows"','"--disable-backgrounding-occluded-windows --use-fake-device-for-media-stream"'));
await promisify(execFile)(path.join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319/csc.exe'),
	['/nologo','/target:winexe','/platform:x64','/out:'+host,...['System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll','System.Xaml.dll',...['WindowsBase.dll','PresentationCore.dll','PresentationFramework.dll'].map(n=>path.join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319/WPF',n)),...libs.map(n=>path.join(profile,n))].map(n=>'/r:'+n),path.join(profile,'MicFixture.cs')],{windowsHide:true});
let report;
const server = createServer((req, res) => {
	if (req.url.startsWith('/result/')) {
		console.log('Device result:',decodeURIComponent(req.url.slice(8))); report?.(req.url.slice(8)); res.end(); return;
	}
	res.setHeader('Content-Type', 'text/html; charset=utf-8');
	res.end(`<!doctype html><html lang="pt-BR" class="dark" style="font-size:115%;background:#171717"><body><script>
		chrome.webview.postMessage({type:'neve:theme', dark:true, lang:'pt-BR'});
		chrome.webview.postMessage({type:'neve:ready'});
		navigator.mediaDevices.getUserMedia({audio:true}).then(stream=>{
			const label=stream.getAudioTracks()[0]?.label;
			stream.getTracks().forEach(track=>track.stop());
			fetch('/result/'+encodeURIComponent(label));
		},err=>fetch('/result/'+err.name));
	</script></body></html>`);
});
server.listen(0, '127.0.0.1'); await once(server, 'listening');
try {
	for (const action of ['deny','escape','outside','allow']) {
		const allow = action === 'allow';
		const result = new Promise(resolve => { report = resolve; });
		const child = spawn(host, [
			'--root',root,'--runtime',path.join(root,'.desktop',state.runtime),
			'--profile',path.join(profile,action,'profile'),'--url','http://127.0.0.1:'+server.address().port
		], {windowsHide:true,env:{...process.env,NEVE_WEBVIEW2_TEST_MODE:'1'}});
		let timer;
		try {
			// Invoke only a button in our isolated host's consent window.
			const script = `$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$ae=[Windows.Automation.AutomationElement]
$owner=[Windows.Automation.PropertyCondition]::new($ae::ProcessIdProperty,[int]${child.pid})
$name=[Windows.Automation.PropertyCondition]::new($ae::NameProperty,'${allow?'Permitir':'Agora não'}')
$english=[Windows.Automation.PropertyCondition]::new($ae::NameProperty,'${allow?'Allow':'Not now'}')
$names=[Windows.Automation.OrCondition]::new($name,$english)
$condition=[Windows.Automation.AndCondition]::new($owner,$names)
$deadline=[DateTime]::UtcNow.AddSeconds(20)
do {
 $button=$ae::RootElement.FindFirst([Windows.Automation.TreeScope]::Descendants,$condition)
 if ($button -and $button.Current.IsEnabled) {
  if ($env:NEVE_MIC_SCREENSHOT -and ${action==='deny'?'$true':'$false'}) {
   Add-Type -AssemblyName System.Drawing
   Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class CaptureDpi { [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context); }'
   [void][CaptureDpi]::SetThreadDpiAwarenessContext([IntPtr](-4))
   $headingName=[Windows.Automation.PropertyCondition]::new($ae::NameProperty,'Permitir acesso ao microfone?')
   $type=[Windows.Automation.PropertyCondition]::new($ae::ControlTypeProperty,[Windows.Automation.ControlType]::Text)
   $heading=$ae::RootElement.FindFirst([Windows.Automation.TreeScope]::Descendants,[Windows.Automation.AndCondition]::new($owner,$headingName,$type))
   $top=$heading.Current.BoundingRectangle
   $bottom=$button.Current.BoundingRectangle
   $unit=$bottom.Height/28
   $margin=[Math]::Ceiling(41*$unit)
   $y=[int]($top.Y-37*$unit)
   $bitmap=New-Object Drawing.Bitmap ([int]($top.Width+2*$margin)),([int]($bottom.Bottom+37*$unit-$y))
   $graphics=[Drawing.Graphics]::FromImage($bitmap)
   try {
    $graphics.CopyFromScreen([int]($top.X-$margin),$y,0,0,$bitmap.Size)
    $bitmap.Save($env:NEVE_MIC_SCREENSHOT,[Drawing.Imaging.ImageFormat]::Png)
   } finally {$graphics.Dispose(); $bitmap.Dispose()}
  }
  if ('${action}' -in 'escape','outside') {
   Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class DialogInput { [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr window, uint message, IntPtr w, IntPtr l); [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y); }'
   $hwnd=[DialogInput]::GetForegroundWindow()
   $window=$ae::FromHandle($hwnd)
   if ($window.Current.ProcessId -ne ${child.pid} -or $window.Current.Name -notin 'Permitir acesso ao microfone?','Allow microphone access?') {throw 'Unexpected active window'}
   if ('${action}' -eq 'escape') {
    [void][DialogInput]::PostMessage($hwnd,256,[IntPtr]27,[IntPtr]0)
   } else {
    $bounds=$window.Current.BoundingRectangle
    [void][DialogInput]::SetCursorPos([int]$bounds.Left+8,[int]$bounds.Top+8)
    [void][DialogInput]::PostMessage($hwnd,513,[IntPtr]1,[IntPtr]524296)
    [void][DialogInput]::PostMessage($hwnd,514,[IntPtr]0,[IntPtr]524296)
   }
  } else { $button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke() }
  exit 0
 }
 Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)
throw 'Microphone permission button missing'`;
			await promisify(execFile)('powershell.exe',['-NoProfile','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')],{windowsHide:true,timeout:25000});
			const answer = decodeURIComponent(await Promise.race([result,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('No permission result')),10000);})]));
			if (allow) assert.match(answer,/fake/i); else assert.equal(answer,'NotAllowedError');
			console.log('PASS: native permission',action);
		} finally { clearTimeout(timer); const closed=once(child,'exit'); child.kill(); if(child.exitCode===null) await closed; }
	}
} finally { server.closeAllConnections(); server.close(); }
