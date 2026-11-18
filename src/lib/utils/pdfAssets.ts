import { base } from '$app/paths';

// PDF.js fetches only the resources required by the open document.
export function pdfAssets(version: string) {
	const root = new URL(base + '/pdfjs/' + version + '/', window.location.origin).href;
	return { cMapUrl: root + 'cmaps/', cMapPacked: true, standardFontDataUrl: root + 'standard_fonts/',
		wasmUrl: root + 'wasm/', iccUrl: root + 'iccs/' };
}
