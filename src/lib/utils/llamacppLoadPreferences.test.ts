import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
	getLocalModelLoadPreferences,
	getLocalModelAccelerationMode,
	setLocalModelAccelerationMode,
	setResponseSpeed,
	setLocalModelTokenPredictionPreference,
	setLocalModelSpeculativePreference,
	setLocalModelContextShiftPreference,
	setLocalModelContextPreference,
	setLocalModelVisionPreference,
	setLocalModelCachePreference,
	RESPONSE_SPEED_CHANGED
} from './llamacppLoadPreferences';

beforeEach(() => {
	const values = new Map<string, string>();
	vi.stubGlobal('localStorage', {
		getItem: (key: string) => values.get(key) ?? null,
		setItem: (key: string, value: string) => values.set(key, String(value)),
		removeItem: (key: string) => values.delete(key)
	});
	vi.stubGlobal('window', { dispatchEvent: vi.fn() });
});

describe('Independent acceleration controls', () => {
	it('defaults speed to normal', () => {
		expect(getLocalModelAccelerationMode()).toBe('normal');
	});
	it('switches speed modes atomically without changing context or cache', () => {
		setLocalModelContextPreference(8192);
		setLocalModelCachePreference('q8_0');
		const observed: unknown[] = [];
		vi.mocked(window.dispatchEvent).mockImplementation(() => {
			observed.push(getLocalModelLoadPreferences());
			return true;
		});
		for (const mode of ['de', 'mtp', 'de', 'normal', 'mtp', 'normal'] as const) {
			setLocalModelAccelerationMode(mode);
			expect(getLocalModelAccelerationMode()).toBe(mode);
			expect(getLocalModelLoadPreferences()).toMatchObject({
				context: 8192, cache: 'q8_0',
				speculative: mode === 'de' ? 'high' : 'off',
				tokenPrediction: mode === 'mtp' ? 'on' : 'off'
			});
		}
		expect(observed).toHaveLength(6);
	});
	it.each(['normal', 'de', 'mtp'] as const)('context shift blocks speed %s', (mode) => {
		setLocalModelAccelerationMode('de');
		setLocalModelContextShiftPreference('on');
		setLocalModelAccelerationMode(mode);
		expect(getLocalModelAccelerationMode()).toBe('normal');
		expect(getLocalModelLoadPreferences()).toMatchObject({speculative: 'off', tokenPrediction: 'off'});
		setLocalModelContextShiftPreference('off');
		expect(getLocalModelAccelerationMode()).toBe('de');
	});
	it.each(['normal', 'de', 'mtp'] as const)('restores %s across repeated context-shift cycles', (mode) => {
		setLocalModelAccelerationMode(mode);
		for (const unlock of ['off', 'default'] as const) {
			setLocalModelContextShiftPreference('on');
			setLocalModelContextShiftPreference('on');
			expect(getLocalModelAccelerationMode()).toBe('normal');
			setLocalModelAccelerationMode('normal');
			setLocalModelAccelerationMode('de');
			setLocalModelAccelerationMode('mtp');
			setLocalModelTokenPredictionPreference('default');
			setLocalModelContextShiftPreference(unlock);
			expect(getLocalModelAccelerationMode()).toBe(mode);
		}
	});
	it('migrates legacy low to DE and keeps legacy MTP priority', () => {
		localStorage.setItem('llamacpp_speculative_decoding', 'low');
		expect(getLocalModelLoadPreferences().speculative).toBe('high');
		expect(getLocalModelAccelerationMode()).toBe('de');
		localStorage.setItem('neveai.responseSpeed', 'fast');
		expect(getLocalModelAccelerationMode()).toBe('mtp');
	});
	it.each([null, 'ask', 'auto', 'invalid'])('uses automatic context for %s', (value) => {
		if (value !== null) localStorage.setItem('llamacpp_load_context', value);
		expect(getLocalModelLoadPreferences().context).toBe('auto');
	});
	it('keeps manual context choices and can reset to auto', () => {
		setLocalModelContextPreference(32768);
		expect(getLocalModelLoadPreferences().context).toBe(32768);
		setLocalModelContextPreference('auto');
		expect(getLocalModelLoadPreferences().context).toBe('auto');
	});
	it.each([null, 'ask', 'invalid', 'yes'])('enables vision by default for %s', (value) => {
		if (value !== null) localStorage.setItem('llamacpp_load_vision', value);
		expect(getLocalModelLoadPreferences().vision).toBe('yes');
	});
	it('preserves disabled vision and supports only yes/no', () => {
		setLocalModelVisionPreference('no');
		expect(getLocalModelLoadPreferences().vision).toBe('no');
		setLocalModelVisionPreference('yes');
		expect(getLocalModelLoadPreferences().vision).toBe('yes');
	});
	it('uses enabled vision without browser storage', () => {
		vi.stubGlobal('localStorage', undefined);
		expect(getLocalModelLoadPreferences().vision).toBe('yes');
	});
	it('preserves the explicit default prediction setting while changing load controls', () => {
		setLocalModelTokenPredictionPreference('default');
		setLocalModelContextPreference(8192);
		setLocalModelVisionPreference('yes');
		setLocalModelCachePreference('q8_0');
		expect(getLocalModelLoadPreferences().tokenPrediction).toBe('default');
		setLocalModelTokenPredictionPreference('on');
		expect(getLocalModelLoadPreferences().tokenPrediction).toBe('on');
		setLocalModelTokenPredictionPreference('off');
		expect(getLocalModelLoadPreferences().tokenPrediction).toBe('off');
		setLocalModelTokenPredictionPreference('default');
		setLocalModelContextShiftPreference('on');
		setLocalModelTokenPredictionPreference('default');
		expect(getLocalModelLoadPreferences().tokenPrediction).toBe('off');
	});
	it('defaults prediction and speculative acceleration to inactive', () => {
		expect(getLocalModelLoadPreferences()).toMatchObject({
			tokenPrediction: 'off',
			speculative: 'default'
		});
	});
	it('prediction switches speculation off and prevents reactivation', () => {
		setLocalModelSpeculativePreference('high');
		setResponseSpeed('fast');
		setLocalModelSpeculativePreference('high');
		expect(getLocalModelLoadPreferences()).toMatchObject({
			tokenPrediction: 'on',
			speculative: 'off'
		});
		expect(localStorage.getItem('llamacpp_speculative_decoding')).toBe('off');
		setResponseSpeed('normal');
		expect(getLocalModelLoadPreferences().speculative).toBe('off');
		setLocalModelSpeculativePreference('high');
		expect(getLocalModelLoadPreferences().speculative).toBe('high');
	});
	it.each(['prediction', 'speculative'])('context shift masks and preserves %s', (mode) => {
		if (mode === 'prediction') setResponseSpeed('fast');
		else setLocalModelSpeculativePreference('high');
		setLocalModelContextShiftPreference('on');
		setResponseSpeed('fast');
		setLocalModelSpeculativePreference('high');
		expect(getLocalModelLoadPreferences()).toMatchObject({
			contextShift: 'on',
			tokenPrediction: 'off',
			speculative: 'off'
		});
		expect(localStorage.getItem('neveai.responseSpeed')).toBe(mode === 'prediction' ? 'fast' : null);
		expect(localStorage.getItem('llamacpp_speculative_decoding')).toBe(mode === 'prediction' ? 'off' : 'high');
	});
	it.each(['off', 'default'] as const)(
		'context shift %s restores saved prediction',
		(mode) => {
			setResponseSpeed('fast');
			setLocalModelContextShiftPreference('on');
			setLocalModelContextShiftPreference(mode);
			expect(getLocalModelLoadPreferences()).toMatchObject({
				tokenPrediction: 'on',
				speculative: 'off'
			});
			expect(window.dispatchEvent).toHaveBeenLastCalledWith(
				expect.objectContaining({ type: RESPONSE_SPEED_CHANGED })
			);
			setResponseSpeed('normal');
			setLocalModelSpeculativePreference('high');
			expect(getLocalModelLoadPreferences().speculative).toBe('high');
		}
	);
	it('masks conflicting legacy state on read', () => {
		localStorage.setItem('neveai.responseSpeed', 'fast');
		localStorage.setItem('llamacpp_speculative_decoding', 'high');
		expect(getLocalModelLoadPreferences().speculative).toBe('off');
		localStorage.setItem('llamacpp_context_shift', 'on');
		expect(getLocalModelLoadPreferences()).toMatchObject({
			tokenPrediction: 'off',
			speculative: 'off'
		});
	});
	it('load controls do not own speculation', () => {
		setLocalModelSpeculativePreference('high');
		setLocalModelContextPreference(8192);
		setLocalModelCachePreference('f16');
		localStorage.setItem(
			'llamacpp_load_preference_user_snapshot',
			'{"speculative":"high","tokenPrediction":"on"}'
		);
		expect(getLocalModelLoadPreferences()).toMatchObject({
			speculative: 'high',
			tokenPrediction: 'off'
		});
		setLocalModelSpeculativePreference('off');
		expect(getLocalModelLoadPreferences().context).toBe(8192);
	});
	it.each(['on', 'off'] as const)('load controls leave context shift %s untouched', (state) => {
		setLocalModelContextShiftPreference(state);
		setLocalModelContextPreference(32768);
		setLocalModelVisionPreference('no');
		setLocalModelCachePreference('q4_0');
		expect(getLocalModelLoadPreferences().contextShift).toBe(state);
		localStorage.setItem(
			'llamacpp_load_preference_user_snapshot',
			JSON.stringify({ contextShift: state === 'on' ? 'off' : 'on' })
		);
		expect(getLocalModelLoadPreferences().contextShift).toBe(state);
	});
});
