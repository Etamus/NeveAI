import { afterEach, describe, expect, it, vi } from 'vitest';
import { notifyDesktopReady } from './desktopWindow';

afterEach(() => { vi.unstubAllGlobals(); });
describe('desktop window readiness', () => {
	it('does nothing in normal browsers', async () => {
		vi.stubGlobal('window', {});
		await expect(notifyDesktopReady()).resolves.toBeUndefined();
	});
	it('does not send native messages from a browser with only a chrome object', async () => {
		const postMessage = vi.fn();
		vi.stubGlobal('window', { chrome: { webview: { postMessage } } });
		await notifyDesktopReady();
		expect(postMessage).not.toHaveBeenCalled();
	});
	it('notifies only the explicit WebView2 host after fonts and paint', async () => {
		const postMessage = vi.fn();
		vi.stubGlobal('window', { __NEVE_WEBVIEW2__: true, chrome: { webview: { postMessage } } });
		vi.stubGlobal('document', { fonts: { ready: Promise.resolve() } });
		vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { callback(); return 1; });
		await notifyDesktopReady();
		expect(postMessage).toHaveBeenCalledWith({ type: 'neve:ready' });
	});
	it('tolerates an unavailable bridge', async () => {
		vi.stubGlobal('window', { __NEVE_WEBVIEW2__: true });
		vi.stubGlobal('document', {});
		vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { callback(); return 1; });
		await expect(notifyDesktopReady()).resolves.toBeUndefined();
	});
	it('waits for fonts and both animation frames before revealing the native window', async () => {
		let fontsReady: () => void;
		const fonts = new Promise<void>((resolve) => { fontsReady = resolve; });
		const frames: (() => void)[] = [];
		const postMessage = vi.fn();
		vi.stubGlobal('window', { __NEVE_WEBVIEW2__: true, chrome: { webview: { postMessage } } });
		vi.stubGlobal('document', { fonts: { ready: fonts } });
		vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { frames.push(callback); return frames.length; });
		const pending = notifyDesktopReady();
		expect(frames).toHaveLength(0);
		fontsReady!();
		await Promise.resolve();
		frames.shift()!();
		expect(postMessage).not.toHaveBeenCalled();
		frames.shift()!();
		await pending;
		expect(postMessage).toHaveBeenCalledTimes(1);
	});
});
