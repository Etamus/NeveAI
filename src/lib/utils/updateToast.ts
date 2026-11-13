import { interfaceNotificationsEnabled } from './toastPreferences';
type UpdateNotificationSettings =
	{ showUpdateToast?: boolean; enableInterfaceNotifications?: boolean } | null | undefined;

export const getUpdateToastSummary = (version: string) => {
	const targets = version
		.split(' • ')
		.map((target) => target.trim())
		.filter(Boolean);
	return { primary: targets[0] ?? '', additional: Math.max(0, targets.length - 1) };
};

export const updateNotificationsEnabled = (settings: UpdateNotificationSettings) =>
	interfaceNotificationsEnabled(settings) && settings?.showUpdateToast !== false;

// Keep pending updates separate from notification visibility and manual dismissal.
export const createUpdateToastManager = () => {
	let enabled = true;
	let dismissed = false;
	let pendingVersion = '';

	return {
		setSettings(settings: UpdateNotificationSettings) {
			const nextEnabled = updateNotificationsEnabled(settings);
			if (nextEnabled && !enabled) dismissed = false;
			enabled = nextEnabled;
		},
		setVersion(version: string) {
			pendingVersion = version;
		},
		dismiss() {
			dismissed = true;
		},
		visibleVersion(contextVisible: boolean) {
			return enabled && !dismissed && contextVisible ? pendingVersion : '';
		}
	};
};
