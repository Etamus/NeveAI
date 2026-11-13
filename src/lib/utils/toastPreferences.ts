export type ToastCategory = 'runtime' | 'downloads' | 'errors';
export const interfaceNotificationsEnabled = (settings: Record<string, any> | null | undefined) =>
	settings?.enableInterfaceNotifications !== false;
const keys = {
	runtime: 'showModelRuntimeToasts',
	downloads: 'showModelDownloadToasts',
	errors: 'showErrorToasts'
} as const;
export const toastCategoryEnabled = (
	settings: Record<string, any> | null | undefined,
	category: ToastCategory
) => interfaceNotificationsEnabled(settings) && settings?.[keys[category]] !== false;
