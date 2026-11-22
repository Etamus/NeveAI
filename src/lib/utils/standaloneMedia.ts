const names = { stable_diffusion: 'Neve Image', video_generation: 'Neve Video', model3d_generation: 'Pixal3D' };

// A request identity, never a selectable or loadable chat model.
export function standaloneMedia(features?: Record<string, unknown> | null) {
	const active = Object.entries(names).filter(([key]) => features?.[key] === true);
	if (active.length !== 1) return null;
	const [key,name] = active[0];
	return { id:'neve-media/'+key, name, info: { meta: {capabilities: {vision:true}} } };
}
