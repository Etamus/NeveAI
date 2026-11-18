type FileSource = Response | Blob;
type SaveWindow = Window & { __NEVE_WEBVIEW2__?: boolean; __NEVE_NATIVE_DOWNLOADS__?: boolean; showSaveFilePicker?: (options: { suggestedName: string }) => Promise<FileSystemFileHandle> };

export async function downloadChatFile(name: string, source: () => FileSource | Promise<FileSource>) {
	try { await saveChatFile(name, source); }
	catch (error) { (await import('svelte-sonner')).toast.error(String((error as Error).message ?? error)); }
}

/** Older desktop hosts need the picker; current hosts prompt in DownloadStarting. */
export async function saveChatFile(name: string, source: () => FileSource | Promise<FileSource>) {
	const host = window as SaveWindow;
	let handle: FileSystemFileHandle | undefined;
	if (host.__NEVE_WEBVIEW2__ && !host.__NEVE_NATIVE_DOWNLOADS__ && host.showSaveFilePicker) {
		try { handle = await host.showSaveFilePicker({ suggestedName: name.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_') }); }
		catch (error) { if ((error as Error).name === 'AbortError') return; throw error; }
	}
	const file = await source();
	if (file instanceof Response && !file.ok) throw new Error('Download: HTTP ' + file.status);
	if (handle) {
		const stream = file instanceof Blob ? file.stream() : file.body;
		if (!stream) throw new Error('Empty download response');
		await stream.pipeTo(await handle.createWritable());
		return;
	}
	const blob = file instanceof Blob ? file : await file.blob();
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = name;
	document.body.appendChild(link);
	link.click();
	link.remove();
	setTimeout(() => URL.revokeObjectURL(url), 30000);
}
