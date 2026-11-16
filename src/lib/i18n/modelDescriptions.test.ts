import { describe, expect, it } from 'vitest';
import i18next from 'i18next';
import english from './locales/en-US/translation.json';
import portuguese from './locales/pt-BR/translation.json';

describe('Neve catalog descriptions', () => {
	it('switches every catalog description between Portuguese and English', async () => {
		const descriptions = Object.keys(english).filter((key) => key.startsWith('Modelo de '));
		expect(descriptions.length).toBeGreaterThanOrEqual(7);
		const instance = i18next.createInstance();
		await instance.init({
			lng: 'pt-BR',
			fallbackLng: 'en-US',
			keySeparator: false,
			resources: {
				'en-US': { translation: english },
				'pt-BR': { translation: portuguese }
			}
		});
		for (const description of descriptions) expect(instance.t(description)).toBe(description);
		await instance.changeLanguage('en-US');
		for (const description of descriptions) {
			expect(instance.t(description)).toBe(english[description as keyof typeof english]);
			expect(instance.t(description)).not.toBe(description);
		}
		await instance.changeLanguage('pt-BR');
		for (const description of descriptions) expect(instance.t(description)).toBe(description);
	});
});
