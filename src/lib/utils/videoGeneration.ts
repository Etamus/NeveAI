export const videoGenerationModels = [
	{ id: 'minimax_h3', label: 'Neve Video 1' },
	{ id: 'vdn_h3', label: 'Neve Video 1.5' }
] as const;

export type VideoGenerationModel = (typeof videoGenerationModels)[number]['id'];

export const normalizeVideoGenerationModel = (value: unknown): VideoGenerationModel =>
	value === 'vdn_h3' ? 'vdn_h3' : 'minimax_h3';

// Match the server's latent-patch dimensions so the first status does not resize the preview.
export function pendingVideoGenerationStatus(message: any, parent?: any): {
	action: string; done: boolean; progress: number; width: number; height: number;
	resolution: string; duration: string; aspect_ratio: string; referenceDimensions: boolean; error?: boolean; quality?: string;
} | null {
	const features = message?.video_generation_features;
	if (message?.done || message?.error || !features?.video_generation) return null;
	const resolution = features.video_generation_resolution === '672p' ? '672p' : '480p';
	let [width, height] = resolution === '672p' ? [1184, 672] : [864, 480];
	if (features.video_generation_aspect_ratio === '9:16') [width, height] = [height, width];
	const image = parent?.files?.find((file: any) => file.type === 'image' || file.content_type?.startsWith('image/'));
	const sourceWidth = Number(image?.image_width), sourceHeight = Number(image?.image_height);
	const referenceDimensions = sourceWidth > 0 && sourceHeight > 0 && Number.isFinite(sourceWidth + sourceHeight);
	if (referenceDimensions) {
		const scale = (resolution === '672p' ? 672 : 480) / Math.min(sourceWidth, sourceHeight);
		let w = sourceWidth * scale, h = sourceHeight * scale;
		const maximum = 768 * 1344;
		if (w * h > maximum) { const ratio = Math.sqrt(maximum / (w * h)); w *= ratio; h *= ratio; }
		width = Math.max(32, Math.floor((Math.round(w) + 16) / 32) * 32);
		height = Math.max(32, Math.floor((Math.round(h) + 16) / 32) * 32);
		while (width * height > maximum) { if (width >= height) width -= 32; else height -= 32; }
	}
	return { action: 'video_generation', done: false, progress: 0, width, height,
		resolution, referenceDimensions, duration: features.video_generation_duration ?? '5s',
		aspect_ratio: features.video_generation_aspect_ratio ?? '16:9' };
}

export function snapshotVideoRequestFeatures(features: Record<string, any>, mobile = false) {
	const snapshot = structuredClone(features);
	if (snapshot.video_generation) {
		snapshot.video_generation_model = normalizeVideoGenerationModel(snapshot.video_generation_model);
		if (mobile) {
			snapshot.video_generation_resolution = '480p';
			snapshot.video_generation_duration = '5s';
		}
	}
	return snapshot;
}

// Persisted request options also cover failures before a generation status arrives.
export function getVideoGenerationFeatures(message: any, responses: any[] = []) {
	const messages = [message, ...responses];
	const saved = messages.find((item) => item?.video_generation_features?.video_generation)
		?.video_generation_features;
	if (saved) return snapshotVideoRequestFeatures(saved);
	const status = messages.flatMap((item) => item?.statusHistory ?? [])
		.find((item) => item?.action === 'video_generation');
	if (!status) return null;
	return {
		video_generation: true,
		video_generation_model: normalizeVideoGenerationModel(status.video_generation_model ?? status.model),
		video_generation_resolution: status.resolution ?? '480p',
		video_generation_duration: status.duration ?? '5s',
		video_generation_aspect_ratio: status.aspect_ratio ?? '16:9'
	};
}
