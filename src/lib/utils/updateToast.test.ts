import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { getAvailableUpdateTargets } from './updateAvailability';
import { createUpdateToastManager, getUpdateToastSummary, updateNotificationsEnabled } from './updateToast';

const generalSource = readFileSync('src/lib/components/chat/Settings/General.svelte', 'utf8');
const layoutSource = readFileSync('src/routes/(app)/+layout.svelte', 'utf8').replace(/\r\n/g, '\n');
const settingsModalSource = readFileSync('src/lib/components/chat/SettingsModal.svelte', 'utf8');

describe('Update notification preference', () => {
	it.each([
		['', '', 0],
		['NeveAI v3.1.83', 'NeveAI v3.1.83', 0],
		['llama.cpp b12167', 'llama.cpp b12167', 0],
		['NeveAI v3.1.83 • llama.cpp b12167', 'NeveAI v3.1.83', 1],
		['NeveAI v3.1.83 • llama.cpp b12167 • engine', 'NeveAI v3.1.83', 2]
	])('summarizes only the visible toast label: %s', (version, primary, additional) => {
		expect(getUpdateToastSummary(version as string)).toEqual({ primary, additional });
	});
	it.each([undefined, null, {}, { showUpdateToast: true }])('defaults enabled for %j', (settings) => {
		expect(updateNotificationsEnabled(settings)).toBe(true);
		const manager = createUpdateToastManager();
		manager.setSettings(settings);
		manager.setVersion('NeveAI v3.0.21');
		expect(manager.visibleVersion(true)).toBe('NeveAI v3.0.21');
	});

	it.each([
		{ latest: 'v3.0.21', current: 'v3.0.20' },
		{ llama_cpp: { current: 'b11719', latest: 'b11857', update_available: true } },
		{ latest: 'v3.0.21', current: 'v3.0.20',
			llama_cpp: { current: 'b11719', latest: 'b11857', update_available: true } }
	])('hides a visible update immediately and restores pending targets: %j', (response) => {
		const manager = createUpdateToastManager();
		const version = getAvailableUpdateTargets(response, 'v3.0.20').join(' • ');
		manager.setVersion(version);
		expect(manager.visibleVersion(true)).toBe(version);
		manager.setSettings({ showUpdateToast: false });
		expect(manager.visibleVersion(true)).toBe('');
		manager.setSettings({ showUpdateToast: true });
		expect(manager.visibleVersion(true)).toBe(version);
	});

	it('retains the newest check while disabled and respects route/modal visibility on reenable', () => {
		const manager = createUpdateToastManager();
		manager.setVersion('NeveAI v3.0.21');
		manager.setSettings({ showUpdateToast: false });
		manager.setVersion('llama.cpp b11857');
		expect(manager.visibleVersion(true)).toBe('');
		manager.setSettings({ showUpdateToast: true });
		expect(manager.visibleVersion(false)).toBe('');
		expect(manager.visibleVersion(true)).toBe('llama.cpp b11857');
	});

	it('does not restore a resolved update', () => {
		const manager = createUpdateToastManager();
		manager.setVersion('NeveAI v3.0.21');
		manager.setSettings({ showUpdateToast: false });
		manager.setVersion('');
		manager.setSettings({ showUpdateToast: true });
		expect(manager.visibleVersion(true)).toBe('');
	});

	it('applies a saved disabled preference arriving after initial subscription', () => {
		const settings = writable<{ showUpdateToast?: boolean }>({});
		const manager = createUpdateToastManager();
		const unsubscribe = settings.subscribe((value) => manager.setSettings(value));
		try {
			manager.setVersion('NeveAI v3.0.21');
			expect(manager.visibleVersion(true)).toBe('NeveAI v3.0.21');
			settings.set({ showUpdateToast: false });
			expect(updateNotificationsEnabled({ showUpdateToast: false })).toBe(false);
			expect(manager.visibleVersion(true)).toBe('');
		} finally {
			unsubscribe();
		}
	});

	it('preserves manual dismissal across unrelated saves, but allows explicit reenabling', () => {
		const manager = createUpdateToastManager();
		manager.setVersion('NeveAI v3.0.21');
		manager.dismiss();
		manager.setSettings({});
		expect(manager.visibleVersion(true)).toBe('');
		manager.setSettings({ showUpdateToast: false });
		manager.setSettings({ showUpdateToast: true });
		expect(manager.visibleVersion(true)).toBe('NeveAI v3.0.21');
	});

	it.each([false, true])('persists %s through the existing saver and reloads it', async (enabled) => {
		// Execute the existing SettingsModal saver with stores/API dependencies isolated.
		const body = settingsModalSource.match(/const saveSettings = async \(updated\) => \{([\s\S]*?)\n\t\};/)?.[1];
		expect(body).toBeTruthy();
		const settings = writable({ theme: 'dark' });
		let persisted = '';
		const updateUserSettings = vi.fn(async (_token, payload) => {
			persisted = JSON.stringify(payload);
		});
		const saveSettings = new Function('settings', 'models', 'getModels', 'updateUserSettings', 'localStorage', `
			let $settings;
			const unsubscribe = settings.subscribe(value => { $settings = value; });
			return async (updated) => {
				try { ${body} } finally { unsubscribe(); }
			};
		`)(settings, writable([]), vi.fn(async () => []), updateUserSettings, { token: 'test' });

		await saveSettings({ showUpdateToast: enabled });
		expect(updateUserSettings).toHaveBeenCalledWith('test', {
			ui: { theme: 'dark', showUpdateToast: enabled }
		});
		const reloadedSettings = JSON.parse(persisted).ui;
		expect(updateNotificationsEnabled(reloadedSettings)).toBe(enabled);
		const reloadedManager = createUpdateToastManager();
		reloadedManager.setSettings(reloadedSettings);
		reloadedManager.setVersion('llama.cpp b11857');
		expect(reloadedManager.visibleVersion(true)).toBe(enabled ? 'llama.cpp b11857' : '');
	});

	it('moves the notification switch to Updates and uses the existing saver', () => {
		expect(generalSource).not.toContain('update-notifications-label');
		const updates = readFileSync('src/lib/components/chat/Settings/Updates.svelte', 'utf8');
		expect(updates).toContain('updateNotificationsEnabled($settings)');
		expect(updates).toMatch(/saveSettings\(\{\s*showUpdateToast:\s*event.detail\s*\}\)/);
		const portuguese = JSON.parse(readFileSync('src/lib/i18n/locales/pt-BR/translation.json', 'utf8'));
		expect(portuguese['Notify about new updates']).toBe('Notificar sobre novas atualizações');
		expect(portuguese['Stream response']).toBe('Exibir respostas em tempo real');
	});

	it('subscribes to preference changes, cleans up, and never gates checks or About availability', () => {
		expect(layoutSource).toContain('unsubscribeUpdatePreferences = settings.subscribe((value) => {');
		expect(layoutSource).toContain('updateToastManager.setSettings(value);\n\t\t\t\tsyncUpdateToast();');
		expect(layoutSource).toContain('unsubscribeUpdatePreferences?.()');
		const checkBody = layoutSource.split('const checkForVersionUpdates = async () => {')[1].split('\n\t};')[0];
		expect(checkBody).toContain('await getVersionUpdates(');
		expect(checkBody).not.toMatch(/showUpdateToast|updateNotificationsEnabled|setSettings/);
		const aboutSource = readFileSync('src/lib/components/chat/Settings/Updates.svelte', 'utf8');
		expect(aboutSource).toContain('getAvailableUpdateTargets');
		expect(aboutSource).not.toContain('updateToastManager');
	});
});
