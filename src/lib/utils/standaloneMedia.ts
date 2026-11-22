const names = { stable_diffusion: 'Neve Image', video_generation: 'Neve Video', model3d_generation: 'Pixal3D' };
export const isStandaloneMediaId = (id: unknown) => Object.keys(names).some(key => id === 'neve-media/' + key);

export function staleMeshCompletionError(message: any) {
	return message?.model === 'neve-media/model3d_generation' && message?.error?.content === 'Model not found' &&
		message.files?.some(file => file.type === 'model3d' && file.id) &&
		message.statusHistory?.some(s => s.action === 'model3d_generation' && s.done && !s.error);
}

// A request identity, never a selectable or loadable chat model.
export function standaloneMedia(features?: Record<string, unknown> | null) {
	const active = Object.entries(names).filter(([key]) => features?.[key] === true);
	if (active.length !== 1) return null;
	const [key,name] = active[0];
	return { id:'neve-media/'+key, name, info: { meta: {capabilities: {vision:true}} } };
}
