type UpdateNotificationSettings = { showUpdateToast?: boolean } | null | undefined;

export const updateNotificationsEnabled = (settings: UpdateNotificationSettings) =>
	settings?.showUpdateToast !== false;

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
