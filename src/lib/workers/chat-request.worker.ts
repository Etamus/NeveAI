import { unpackInlineImages } from '$lib/utils/inlineImageTransfer';

self.onmessage = async ({ data }: MessageEvent<unknown>) => {
	try {
		self.postMessage({ body: new Blob([JSON.stringify(await unpackInlineImages(data))], { type: 'application/json' }) });
	} catch {
		self.postMessage({ failed: true });
	}
};
