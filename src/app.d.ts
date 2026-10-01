// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	type NeveI18nStore = import('svelte/store').Writable<import('i18next').i18n>;
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface Platform {}
	}
}

declare module 'svelte' {
	export function getContext(key: 'i18n'): NeveI18nStore;
}

export {};
