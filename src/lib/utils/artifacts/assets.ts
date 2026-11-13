import { base } from '$app/paths';

declare const __NEVE_ARTIFACT_VERSION__: string;

export function artifactAssetBase(): string {
	const version = typeof __NEVE_ARTIFACT_VERSION__ === 'string' ? __NEVE_ARTIFACT_VERSION__ : 'dev';
	return new URL(`${base}/artifacts/${version}`, location.origin).href;
}
