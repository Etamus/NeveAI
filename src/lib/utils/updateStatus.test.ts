import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { get } from 'svelte/store';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getAvailableUpdateTargets, versionUpdateStatus } from './updateAvailability';

const apiSource = readFileSync('src/lib/apis/index.ts', 'utf8');
const aboutSource = readFileSync('src/lib/components/chat/Settings/About.svelte', 'utf8');
const response = (json: unknown, ok = true) => ({ ok, json: async () => json });
const available = {current_tag: 'v3.1.01', latest_tag: 'v3.1.02', neve_update_available: true};

function api(fetch: ReturnType<typeof vi.fn>) {
	const arrow = apiSource.match(/export const getVersionUpdates = ([\s\S]*?)\n};/)?.[1];
	expect(arrow).toBeTruthy();
	return runInNewContext(ts.transpile(`let versionUpdateRequest = 0;
		const check = ${arrow}\n}; check;`, {target: ts.ScriptTarget.ES2022}), {
		fetch, versionUpdateStatus, NEVEAI_BASE_URL: '', console: {error() {}}
	});
}

afterEach(() => versionUpdateStatus.set(null));

describe('Shared update status for immediate About availability', () => {
	it('starts unknown instead of assuming an update exists', () => {
		expect(get(versionUpdateStatus)).toBeNull();
		expect(getAvailableUpdateTargets(get(versionUpdateStatus), 'v3.1.01')).toEqual([]);
	});
	it('publishes successful startup checks for synchronous reads before About mounts', async () => {
		const fetch = vi.fn().mockResolvedValue(response(available));
		await api(fetch)('fixture');
		expect(getAvailableUpdateTargets(get(versionUpdateStatus), 'v3.1.01')).toEqual(['NeveAI v3.1.02']);
		expect(fetch.mock.calls[0][1].cache).toBe('no-store');
	});
	it('keeps the known result while refreshing, then removes a resolved update', async () => {
		versionUpdateStatus.set(available);
		let resolve!: (value: unknown) => void;
		const check = api(vi.fn(() => new Promise(done => {resolve = done;})));
		const pending = check('fixture');
		expect(get(versionUpdateStatus)).toEqual(available);
		resolve(response({...available, latest_tag: 'v3.1.01', neve_update_available: false}));
		await pending;
		expect(getAvailableUpdateTargets(get(versionUpdateStatus), 'v3.1.01')).toEqual([]);
	});
	it('does not let an older request restore an update after a newer check resolved it', async () => {
		const resolvers: Array<(value: unknown) => void> = [];
		const check = api(vi.fn(() => new Promise(resolve => resolvers.push(resolve))));
		const older = check('fixture');
		const newer = check('fixture');
		resolvers[1](response({...available, latest_tag: 'v3.1.01', neve_update_available: false}));
		await newer;
		resolvers[0](response(available));
		await older;
		expect(getAvailableUpdateTargets(get(versionUpdateStatus), 'v3.1.01')).toEqual([]);
	});
	it('clears a result on an API failure without claiming that an update is available', async () => {
		versionUpdateStatus.set(available);
		await expect(api(vi.fn().mockResolvedValue(response({detail: 'offline'}, false)))('fixture')).rejects.toEqual({detail: 'offline'});
		expect(get(versionUpdateStatus)).toBeNull();
	});
	it('About derives visibility from shared availability and preserves the admin restriction', () => {
		expect(aboutSource).toContain('getAvailableUpdateTargets($versionUpdateStatus, projectVersion)');
		expect(aboutSource).toContain("$user?.role === 'admin' && (updateAvailable || startingUpdater)");
	});
});
