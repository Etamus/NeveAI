import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getReasoningLevel, getReasoningState, setReasoningLevel, usesReasoningEffort } from './reasoningModes';
import {
	getLocalModelLoadPreferences,
	getResponseSpeed,
	setResponseSpeed
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

describe('Reasoning and independent speed', () => {
	it.each([0, 1, 2, 3] as const)('maps and persists level %i without changing speed', (level) => {
		setResponseSpeed('fast');
		setReasoningLevel(level);
		expect(getReasoningLevel()).toBe(level);
		expect(getReasoningState(level)).toEqual({
			enabled: level > 0,
			extended: level >= 2,
			unlimited: level === 3
		});
		expect(getResponseSpeed()).toBe('fast');
	});
	it('starts at normal even when legacy profiles enabled prediction', () => {
		localStorage.setItem('llamacpp_token_prediction', 'on');
		expect(getResponseSpeed()).toBe('normal');
		expect(getLocalModelLoadPreferences().tokenPrediction).toBe('off');
	});
	it('preserves the reasoning level when speed changes', () => {
		setReasoningLevel(3);
		setResponseSpeed('fast');
		setResponseSpeed('normal');
		expect(getReasoningLevel()).toBe(3);
	});
	it('migrates both legacy reasoning switches and invalid values', () => {
		localStorage.setItem('neveai.globalThinkingEnabled', 'false');
		expect(getReasoningLevel()).toBe(0);
		localStorage.setItem('neveai.globalThinkingEnabled', 'true');
		localStorage.setItem('neveai.thinkingExtendedEnabled', 'false');
		expect(getReasoningLevel()).toBe(1);
		localStorage.setItem('neveai.reasoningLevel', 'invalid');
		localStorage.setItem('neveai.thinkingExtendedEnabled', 'true');
		expect(getReasoningLevel()).toBe(2);
	});
});

describe('reasoning effort models', () => {
	it.each([
		{ id: 'gpt-oss:20b' },
		{ name: 'Custom', llamacpp: { filename: 'GPT_OSS-120B-Q4.gguf' } },
		{ name: 'Neve Sense' },
		{ llamacpp: { filename: 'Neve-Sense2-20B-Q4.gguf' } },
		{ info: { meta: { neve_catalog_id: 'neve-sense' } } },
		{ llamacpp: { reasoning_control: 'effort' } }
	])('recognizes effort-based identity %j', (model) => {
		expect(usesReasoningEffort(model)).toBe(true);
	});
	it.each([undefined, {}, { name: 'Qwen3.5' }, { name: 'Neve Strata S' }])('preserves instantaneous mode for %j', (model) => {
		expect(usesReasoningEffort(model)).toBe(false);
	});
	it('keeps both upper levels extended, with only the last level unlimited', () => {
		expect(getReasoningState(2)).toEqual({ enabled: true, extended: true, unlimited: false });
		expect(getReasoningState(3)).toEqual({ enabled: true, extended: true, unlimited: true });
	});
});
