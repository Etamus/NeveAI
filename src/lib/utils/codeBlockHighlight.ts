import hljs from 'highlight.js';

// One-entry cache per block; never retain code from other chats globally.
export function createCodeBlockHighlighter() {
	let previousCode: string | undefined;
	let previousLanguage: string | undefined;
	let html = '';
	return (code: string, language: string) => {
		if (code === previousCode && language === previousLanguage) return html;
		const known = hljs.getLanguage(language);
		const result = known
			? hljs.highlight(code, { language, ignoreIllegals: true })
			: hljs.highlightAuto(code);
		previousCode = code;
		previousLanguage = language;
		html = result.value;
		return html;
	};
}
