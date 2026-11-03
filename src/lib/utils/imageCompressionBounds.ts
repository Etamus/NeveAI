export function imageCompressionBounds(settings: any = {}, config: any = {}) {
	const enabled = settings?.imageCompression ?? false;
	let width = enabled ? (settings?.imageCompressionSize?.width ?? null) : null;
	let height = enabled ? (settings?.imageCompressionSize?.height ?? null) : null;
	const configWidth = config?.file?.image_compression?.width ?? null;
	const configHeight = config?.file?.image_compression?.height ?? null;
	if (configWidth && (width === null || width > configWidth)) width = configWidth;
	if (configHeight && (height === null || height > configHeight)) height = configHeight;
	return { width, height };
}
