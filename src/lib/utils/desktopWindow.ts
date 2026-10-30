type DesktopWindow = Window & {
	__NEVE_WEBVIEW2__?: boolean;
	chrome?: { webview?: { postMessage: (message: { type: string }) => void } };
};

export async function notifyDesktopReady() {
	const host = window as DesktopWindow;
	if (host.__NEVE_WEBVIEW2__ !== true) return;
	await document.fonts?.ready;
	await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
	host.chrome?.webview?.postMessage({ type: 'neve:ready' });
}
