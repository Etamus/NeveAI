import { describe, expect, it } from 'vitest';
import { getAvailableUpdateTargets } from './updateAvailability';

describe('About update availability', () => {
	it.each([
		['same version', 'v2.8.82', '2.8.82'],
		['older release', '2.8.81', 'v2.8.82'],
		['unknown installed version', 'v2.8.83', ''],
		['invalid version', 'unknown', '2.8.82'],
		['development version', '2.8.83', '0.0.0']
	])('does not show a button for %s even if flagged true', (_name, latest, current) => {
		expect(getAvailableUpdateTargets({ latest_tag: latest, current_tag: current, neve_update_available: true }, '')).toEqual([]);
	});
	it('shows a real project update', () => {
		expect(getAvailableUpdateTargets({ latest_tag: 'v2.8.83', current: '2.8.82', neve_update_available: true }, '')).toEqual(['NeveAI v2.8.83']);
	});
	it('respects an explicitly disabled check', () => {
		expect(getAvailableUpdateTargets({ latest: '2.8.83', current: '2.8.82', neve_update_available: false }, '')).toEqual([]);
	});
	it('supports legacy project payloads and the installed version fallback', () => {
		expect(getAvailableUpdateTargets({ latest: '2.8.83' }, 'v2.8.82')).toEqual(['NeveAI 2.8.83']);
	});
	it.each(['b11716', 'b11715'])('rejects equal or older llama.cpp %s', (latest) => {
		expect(getAvailableUpdateTargets({ llama_cpp: { current_tag: '\uFEFFb11716', latest_tag: latest, update_available: true } }, '')).toEqual([]);
	});
	it('requires a compatible llama.cpp update confirmed by the backend', () => {
		expect(getAvailableUpdateTargets({ llama_cpp: { current: 'b11716', latest: 'b11717', update_available: false } }, '')).toEqual([]);
		expect(getAvailableUpdateTargets({ llama_cpp: { current: 'b11716', latest: 'b11717', update_available: true } }, '')).toEqual(['llama.cpp b11717']);
	});
	it('clears the old result when the next check is up to date or fails', () => {
		expect(getAvailableUpdateTargets({ latest: '2.8.83', current: '2.8.82' }, '')).toHaveLength(1);
		expect(getAvailableUpdateTargets({ latest: '2.8.83', current: '2.8.83' }, '')).toEqual([]);
		expect(getAvailableUpdateTargets(null, '')).toEqual([]);
	});
});
