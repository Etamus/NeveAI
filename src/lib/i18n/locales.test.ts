import { describe, expect, it } from 'vitest';
import i18next from 'i18next';
import ptBR from './locales/pt-BR/translation.json';
import enUS from './locales/en-US/translation.json';

const resources = {
	'pt-BR': { translation: ptBR },
	'en-US': { translation: enUS }
};

describe('Interface translations after cleanup', () => {
	it('preserves the current Portuguese labels', async () => {
		const instance = i18next.createInstance();
		await instance.init({ lng: 'pt-BR', resources, returnEmptyString: false, fallbackLng: false });
		const labels = {
			Theme: 'Tema',
			Language: 'Idioma',
			Settings: 'Configura\u00e7\u00f5es',
			About: 'Sobre',
			'Data Controls': 'Dados',
			'New Chat': 'Novo chat',
			'Web Search': 'Busca na web',
			'Deep Search': 'Pesquisa profunda',
			'Upload Files': 'Anexar arquivos',
			'Send a Message': 'Envie uma mensagem...',
			Tools: 'Ferramentas'
		};
		for (const [key, text] of Object.entries(labels)) expect(instance.t(key)).toBe(text);
	});

	it('preserves the customized English labels and normal fallback', async () => {
		const instance = i18next.createInstance();
		await instance.init({ lng: 'en-US', resources, returnEmptyString: false, fallbackLng: false });
		const labels = {
			Theme: 'Theme',
			Settings: 'Settings',
			'Data Controls': 'Data',
			'New Chat': 'New chat',
			'Web Search': 'Web search',
			'Deep Search': 'Deep search',
			'Upload Files': 'Upload files',
			'Search Models': 'Search...',
			'Configura\u00e7\u00f5es globais': 'Global settings',
			'Par\u00e2metros avan\u00e7ados': 'Advanced parameters',
			Continuar: 'Continue',
			'Uso de tokens': 'Tokens usage',
			Contexto: 'Context',
			'Send a Message': 'Send a message...'
		};
		for (const [key, text] of Object.entries(labels)) expect(instance.t(key)).toBe(text);
	});

	it('keeps dynamic date, status, and interpolation labels', () => {
		for (const locale of [ptBR, enUS]) {
			for (const key of ['Today', 'Yesterday', 'January', 'Enabled', 'Disabled', '{{COUNT}} Sources']) {
				expect(Object.hasOwn(locale, key), key).toBe(true);
			}
		}
	});

	it('does not carry translations for removed community and collaboration screens', () => {
		for (const locale of [ptBR, enUS]) {
			for (const key of [
				'A collaboration channel where people join as members',
				'Account Activation Pending',
				'Share to Neve Community'
			]) expect(Object.hasOwn(locale, key), key).toBe(false);
		}
	});
});
