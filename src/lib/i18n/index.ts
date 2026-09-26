import i18next from 'i18next';
import type { i18n as i18nType } from 'i18next';
import { writable, type Writable } from 'svelte/store';

export type I18nStore = Writable<i18nType>;
import ptBR from './locales/pt-BR/translation.json';
import enUS from './locales/en-US/translation.json';
import dayjs from '$lib/dayjs';

const supportedLocales = ['pt-BR', 'en-US'] as const;
type SupportedLocale = (typeof supportedLocales)[number];
const isSupportedLocale = (locale: string | null | undefined): locale is SupportedLocale =>
	supportedLocales.includes(locale as SupportedLocale);

const createI18nStore = (i18n: i18nType) => {
	const i18nWritable = writable(i18n);

	i18n.on('initialized', () => {
		i18nWritable.set(i18n);
	});
	i18n.on('loaded', () => {
		i18nWritable.set(i18n);
	});
	i18n.on('added', () => i18nWritable.set(i18n));
	i18n.on('languageChanged', () => {
		i18nWritable.set(i18n);
	});
	return i18nWritable;
};

const createIsLoadingStore = (i18n: i18nType) => {
	const isLoading = writable(false);

	// if loaded resources are empty || {}, set loading to true
	i18n.on('loaded', (resources) => {
		// console.log('loaded:', resources);
		isLoading.set(Object.keys(resources).length === 0);
	});

	// if resources failed loading, set loading to true
	i18n.on('failedLoading', () => {
		isLoading.set(true);
	});

	return isLoading;
};

export const initI18n = (defaultLocale?: string | undefined) => {
	const storedLocale = typeof localStorage !== 'undefined' ? localStorage.getItem('neveai.language') : null;
	const locale = isSupportedLocale(storedLocale)
		? storedLocale
		: isSupportedLocale(defaultLocale)
			? defaultLocale
			: 'pt-BR';

	if (i18next.isInitialized) {
		document.documentElement.setAttribute('lang', i18next.language);
		dayjs.locale(i18next.language === 'pt-BR' ? 'pt-br' : 'en');
		return;
	}

	i18next
		.init({
			debug: false,
			lng: locale,
			fallbackLng: false,
			supportedLngs: [...supportedLocales],
			resources: {
				'pt-BR': { translation: ptBR },
				'en-US': { translation: enUS }
			},
			initImmediate: false,
			ns: 'translation',
			returnEmptyString: false,
			interpolation: {
				escapeValue: false // not needed for svelte as it escapes by default
			}
		});

	document.documentElement.setAttribute('lang', locale);
	dayjs.locale(locale === 'pt-BR' ? 'pt-br' : 'en');
};

const i18n = createI18nStore(i18next);
const isLoadingStore = createIsLoadingStore(i18next);

export const getLanguages = async () => {
	return [
		{ code: 'pt-BR', title: 'Português (Brasil)' },
		{ code: 'en-US', title: 'English' }
	];
};
export const changeLanguage = (lang: string) => {
	if (!isSupportedLocale(lang)) return;
	localStorage.setItem('neveai.language', lang);
	document.documentElement.setAttribute('lang', lang);
	dayjs.locale(lang === 'pt-BR' ? 'pt-br' : 'en');
	void i18next.changeLanguage(lang);
};

export default i18n;
export const isLoading = isLoadingStore;
