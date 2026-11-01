export const videoGenerationModels = [
	{ id: 'minimax_h3', label: 'Neve Video 1' },
	{ id: 'vdn_h3', label: 'Neve Video 1.5' }
] as const;

export type VideoGenerationModel = (typeof videoGenerationModels)[number]['id'];

export const normalizeVideoGenerationModel = (value: unknown): VideoGenerationModel =>
	value === 'vdn_h3' ? 'vdn_h3' : 'minimax_h3';

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
