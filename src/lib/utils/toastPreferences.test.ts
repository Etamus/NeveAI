import {expect, it} from 'vitest';
import {toastCategoryEnabled,interfaceNotificationsEnabled} from './toastPreferences';
import {createUpdateToastManager,updateNotificationsEnabled} from './updateToast';
it('enables all categories by default and keeps them independent', () => {
	for(const category of ['runtime','downloads','errors'] as const) expect(toastCategoryEnabled(undefined,category)).toBe(true);
	expect(toastCategoryEnabled({showErrorToasts:false},'errors')).toBe(false);
	expect(toastCategoryEnabled({showErrorToasts:false},'runtime')).toBe(true);
	expect(toastCategoryEnabled({showModelDownloadToasts:false},'downloads')).toBe(false);
});
it('masks every category and update alerts without changing individual choices',()=>{
	const settings={enableInterfaceNotifications:false,showModelRuntimeToasts:true,showModelDownloadToasts:true,showErrorToasts:false,showUpdateToast:true};
	expect(interfaceNotificationsEnabled(undefined)).toBe(true);
	for(const category of ['runtime','downloads','errors'] as const)expect(toastCategoryEnabled(settings,category)).toBe(false);
	expect(updateNotificationsEnabled(settings)).toBe(false);
	const manager=createUpdateToastManager();manager.setVersion('NeveAI v9');manager.setSettings(settings);
	expect(manager.visibleVersion(true)).toBe('');
	const enabled={...settings,enableInterfaceNotifications:true};manager.setSettings(enabled);
	expect(manager.visibleVersion(true)).toBe('NeveAI v9');
	expect(toastCategoryEnabled(enabled,'runtime')).toBe(true);
	expect(toastCategoryEnabled(enabled,'downloads')).toBe(true);
	expect(toastCategoryEnabled(enabled,'errors')).toBe(false);
	expect(settings.showModelRuntimeToasts).toBe(true);
});
