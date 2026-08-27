import type { LocalModel, LocalVramInfo } from '$lib/apis/llamacpp';

export interface UnifiedModelsPreload {
	loaded: boolean;
	localModels: LocalModel[];
	mmProjFiles: string[];
	adminModels: any[];
	workspaceModels: any[];
	baseModels: any[];
	vramInfo: LocalVramInfo | null;
}

export const buildUnifiedAdminModels = (
	localModels: LocalModel[] = [],
	baseModels: any[] = [],
	workspaceModels: any[] = []
) => {
	const localIds = new Set(localModels.map((model) => model.id).filter(Boolean));
	const currentBaseModels = baseModels.filter((model: any) => {
		const isLocalLlamaCppModel = model?.owned_by === 'llamacpp' || Boolean(model?.llamacpp);
		return !isLocalLlamaCppModel || localIds.has(model.id);
	});
	const baseIds = new Set(currentBaseModels.map((model: any) => model.id));
	const validIds = new Set([
		...baseIds,
		...workspaceModels
			.filter((model: any) => baseIds.has(model.id) || localIds.has(model.id))
			.map((model: any) => model.id)
	]);

	let adminModels = [...validIds]
		.map((id: string) => {
			const base = currentBaseModels.find((model: any) => model.id === id);
			const workspace = workspaceModels.find((model: any) => model.id === id);
			if (base && workspace) return { ...base, ...workspace };
			if (workspace) return { ...workspace };
			if (base) return { ...base, is_active: true };
			return null;
		})
		.filter((model): model is any => model !== null);

	const registeredIds = new Set(adminModels.map((model: any) => model.id));
	adminModels = [
		...adminModels,
		...localModels
			.filter((model) => model.id && !registeredIds.has(model.id))
			.map((model) => ({
				id: model.id,
				name: model.filename.replace(/\.gguf$/i, ''),
				meta: {},
				params: {},
				is_active: true
			}))
	];

	return adminModels;
};
