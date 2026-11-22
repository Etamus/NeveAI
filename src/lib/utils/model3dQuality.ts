export const model3dProfiles = [
	{ id: 'standard', label: 'Default' }, { id: 'draft', label: 'Draft' }, { id: 'high', label: 'High quality' }
] as const;
export type Model3dQuality = (typeof model3dProfiles)[number]['id'];
export const normalizeModel3dQuality = (value: unknown): Model3dQuality =>
	value === 'draft' || value === 'high' ? value : 'standard';
