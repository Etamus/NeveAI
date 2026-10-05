export function normalizeModelFavorites<T extends Record<string, any>>(ui: T): T & { favoriteModels: string[] } {
	const { pinnedModels, ...rest } = ui;
	const source = Array.isArray(ui.favoriteModels) ? ui.favoriteModels : pinnedModels;
	return {
		...rest,
		favoriteModels: [...new Set((Array.isArray(source) ? source : []).filter(
			(id): id is string => typeof id === 'string' && id.length > 0
		))]
	} as T & { favoriteModels: string[] };
}

export function isNeveModel(model: any): boolean {
	const meta = model?.info?.meta ?? model?.meta;
	return meta?.managed_by === 'neve_download' &&
		typeof meta.neve_catalog_id === 'string' && meta.neve_catalog_id.trim().length > 0;
}
