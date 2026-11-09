import { describe, expect, it } from 'vitest';
import { normalizeLearningRequestFeatures } from './guidedLearning';

describe('guided learning request exclusivity', () => {
	it('disables document tools in conflicting restored or queued features without mutating them', () => {
		const features = { file_generation: true, guided_learning: true, voice: true };
		expect(normalizeLearningRequestFeatures(features)).toEqual({
			file_generation: false, guided_learning: true, voice: true
		});
		expect(features.file_generation).toBe(true);
	});

	it('preserves document tools when Learn is off or absent', () => {
		for (const features of [{ file_generation: true }, { file_generation: true, guided_learning: false }]) {
			expect(normalizeLearningRequestFeatures(features)).toEqual(features);
		}
	});

	it('keeps Learn enabled when document tools were already off', () => {
		expect(normalizeLearningRequestFeatures({ guided_learning: true, file_generation: false }))
			.toEqual({ guided_learning: true, file_generation: false });
	});
});
