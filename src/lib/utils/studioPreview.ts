const retries = new WeakMap<HTMLMediaElement,(time:number)=>boolean>();
export function retryStudioPreview(node: HTMLMediaElement, time:number) {
	return retries.get(node)?.(time) ?? false;
}

// Compatible MP4s use native byte ranges. Only the segmented preview needs a player.
export function studioPreview(node: HTMLMediaElement, initial: string) {
	let revision = 0;
	let failed = false;
	const onError = () => { failed=true; };
	node.addEventListener('error',onError);
	let player: import('hls.js').default | undefined;
	async function attach(url: string, time?:number) {
		const current = ++revision;
		player?.destroy(); player = undefined;
		failed=false;
		node.dataset.previewUrl = url;
		const nativeHls=node.canPlayType('application/vnd.apple.mpegurl');
		if (!url.includes('/preview.m3u8') || (nativeHls && time===undefined)) {
			node.src = url;
			return;
		}
		try {
			const {default: Hls} = await import('hls.js');
			if (current !== revision) return;
			if (!Hls.isSupported()) throw new Error('No MediaSource');
			player = new Hls({startPosition:time??-1,maxBufferLength: 12, maxMaxBufferLength: 16, backBufferLength: 8});
			player.on(Hls.Events.ERROR, (_, data) => { if (data.fatal && current===revision && !failed) node.dispatchEvent(new Event('error')); });
			player.attachMedia(node);
			player.loadSource(url);
		} catch {
			if (current === revision) node.src = nativeHls ? url : url.replace('/preview.m3u8', '');
		}
	}
	retries.set(node,time=>{
		const url=node.dataset.previewUrl;
		if(!url || !(failed || node.error)) return false;
		void attach(url,time);
		return true;
	});
	void attach(initial);
	return {update(url: string) { if (url !== node.dataset.previewUrl) void attach(url); },
		destroy() { revision++; retries.delete(node); node.removeEventListener('error',onError);
			player?.destroy(); node.pause(); node.removeAttribute('src'); node.load(); }};
}
