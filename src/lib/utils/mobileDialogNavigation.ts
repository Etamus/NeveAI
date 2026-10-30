import { get } from 'svelte/store';
import { page } from '$app/stores';
import { pushState } from '$app/navigation';
import { createMobileDialogHistory } from './mobileDialogHistory';

export const MOBILE_DIALOG_STATE = 'neveMobileDialog';
export const mobileDialogHistory = createMobileDialogHistory({
	push: id => pushState('', { ...get(page).state, [MOBILE_DIALOG_STATE]: id }),
	current: () => get(page).url.href === window.location.href
		? (get(page).state as Record<string, string>)[MOBILE_DIALOG_STATE] : undefined,
	back: () => window.history.back()
});
