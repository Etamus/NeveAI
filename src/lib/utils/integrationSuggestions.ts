import { get, writable } from 'svelte/store';

export const suggestionIntegrationIds = ['stable_diffusion', 'guided_learning', 'web_search', 'video_generation', 'music_generation', 'model3d_generation'] as const;
export type SuggestionIntegration = typeof suggestionIntegrationIds[number];
const defaults: SuggestionIntegration[] = ['stable_diffusion', 'guided_learning', 'web_search'];
const storageKey = (userId: string) => `neveai.integration-suggestions.v1:${encodeURIComponent(userId)}`;

export const integrationSuggestionUsage = writable<Record<string, SuggestionIntegration[]>>({});
export const dismissedSuggestions = writable<Record<string, SuggestionIntegration[]>>({});
const dismissedKey = (userId: string) => storageKey(userId) + ':dismissed';

function normalize(value: unknown): SuggestionIntegration[] {
	if (!Array.isArray(value)) return [];
	return [...new Set(value.filter((item): item is SuggestionIntegration => suggestionIntegrationIds.includes(item)))];
}

export function getIntegrationSuggestions(recent: unknown, allowed: readonly SuggestionIntegration[] = suggestionIntegrationIds, dismissed: readonly SuggestionIntegration[] = []): SuggestionIntegration[] {
	return normalize([...normalize(recent), ...defaults, ...suggestionIntegrationIds]).filter(id => allowed.includes(id)).slice(0, 3).filter(id => !dismissed.includes(id));
}

export function loadIntegrationSuggestionUsage(userId: string | undefined) {
	if (!userId || typeof localStorage === 'undefined' || get(integrationSuggestionUsage)[userId]) return;
	let recent: SuggestionIntegration[] = [];
	try { recent = normalize(JSON.parse(localStorage.getItem(storageKey(userId)) ?? '[]')); } catch { /* An unavailable or invalid cache uses the default order. */ }
	let dismissed: SuggestionIntegration[] = [];
	try { dismissed = normalize(JSON.parse(localStorage.getItem(dismissedKey(userId)) ?? '[]')); } catch { /* No saved dismissals. */ }
	dismissedSuggestions.update(users => ({ ...users, [userId]: dismissed }));
	integrationSuggestionUsage.update(users => ({ ...users, [userId]: recent }));
}

function setDismissed(userId: string, ids: SuggestionIntegration[]) {
	dismissedSuggestions.update(users => ({ ...users, [userId]: ids }));
	try { localStorage.setItem(dismissedKey(userId), JSON.stringify(ids)); } catch { /* Session-only storage. */ }
}

export function dismissSuggestion(userId: string | undefined, id: SuggestionIntegration) {
	if (!userId) return;
	loadIntegrationSuggestionUsage(userId);
	const ids = get(dismissedSuggestions)[userId] ?? [];
	if (!ids.includes(id)) setDismissed(userId, [...ids, id]);
}

export function recordIntegrationUse(userId: string | undefined, features: Record<string, unknown>) {
	if (!userId || features.deep_search) return;
	const integration = suggestionIntegrationIds.find(id => features[id] === true);
	if (!integration) return;
	loadIntegrationSuggestionUsage(userId);
	if (get(dismissedSuggestions)[userId]?.length) setDismissed(userId, []);
	const recent = get(integrationSuggestionUsage)[userId] ?? [];
	if (recent[0] === integration) return;
	const next = [integration, ...recent.filter(id => id !== integration)];
	integrationSuggestionUsage.update(users => ({ ...users, [userId]: next }));
	try { localStorage.setItem(storageKey(userId), JSON.stringify(next)); } catch { /* Keep this session working if storage is unavailable. */ }
}
