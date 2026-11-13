import { Marked } from 'marked';
import { removeDetails } from '$lib/utils';
import { isWithinCodeBlock } from 'remend';
import { normalizeArtifactPath } from './path';
export { normalizeArtifactPath } from './path';

export type ArtifactFile = { path: string; language: string; content: string };
const lexer = new Marked();
const aliases: Record<string, string> = {
	javascript: 'js',
	typescript: 'ts',
	react: 'jsx',
	htm: 'html'
};
const supported = new Set(['html', 'css', 'js', 'jsx', 'ts', 'tsx', 'json']);

export function visibleArtifactSource(content: string): string {
	const visible = removeDetails(content, ['reasoning', 'code_interpreter', 'tool_calls']);
	for (const match of visible.matchAll(
		/<details\b[^>]*\btype=["'](?:reasoning|code_interpreter|tool_calls)["'][^>]*>/gi
	)) {
		if (!isWithinCodeBlock(visible, match.index!)) return visible.slice(0, match.index);
	}
	return visible;
}

export function artifactFiles(content: string, unfinished = false): ArtifactFile[] {
	const files: ArtifactFile[] = [];
	let preceding = '';
	for (const token of lexer.lexer(visibleArtifactSource(content))) {
		if (token.type !== 'code') {
			if (token.type !== 'space') preceding = token.raw;
			continue;
		}
		const fence = token.raw.match(/^ {0,3}(`{3,}|~{3,})/);
		if (!fence) continue;
		const closing = new RegExp(`\\n {0,3}${fence[1][0]}{${fence[1].length},}[ \\t]*(?:\\r?\\n)?$`);
		if (!unfinished && !closing.test(token.raw)) continue;
		const info = token.lang ?? '';
		const first = info.split(/\s+/)[0].toLowerCase();
		let language = aliases[first] ?? first;
		const named =
			info.match(/(?:[\w@./-]+\.(?:html?|css|[cm]?js|jsx|tsx?|json))\b/i)?.[0] ??
			preceding.match(/(?:^|[\s`])([\w@./-]+\.(?:html?|css|[cm]?js|jsx|tsx?|json))[`\s:]*$/i)?.[1];
		if (named && !supported.has(language))
			language = aliases[named.split('.').at(-1)!] ?? named.split('.').at(-1)!;
		if (!supported.has(language)) continue;
		let path: string;
		try {
			path = named
				? normalizeArtifactPath(named)
				: language === 'html'
					? 'index.html'
					: language === 'css'
						? 'styles.css'
						: ['jsx', 'tsx'].includes(language)
							? `App.${language}`
							: `main.${language}`;
		} catch {
			continue;
		}
		const existing = files.find((file) => file.path === path);
		if (existing) existing.content += '\n' + token.text;
		else files.push({ path, language, content: token.text });
		preceding = '';
	}
	return files;
}

export const isReactFile = (file: ArtifactFile) =>
	['jsx', 'tsx'].includes(file.language) ||
	(['js', 'ts'].includes(file.language) &&
		/(?:from\s*['"]react(?:\/|['"])|React\.(?:createElement|useState)|(?:return|=>)\s*\(?\s*<[A-Za-z])/.test(
			file.content
		));

export function artifactEntry(files: ArtifactFile[]): ArtifactFile | undefined {
	return (
		files.find((file) => file.path === 'index.html') ??
		files.find((file) => file.language === 'html') ??
		files.find((file) => /(?:^|\/)(?:main|index)\.[jt]sx?$/.test(file.path) && isReactFile(file)) ??
		files.find((file) => /(?:^|\/)App\.[jt]sx?$/.test(file.path)) ??
		files.find(isReactFile) ??
		files.find(
			(file) => ['js', 'ts'].includes(file.language) && /\bdocument\s*[.[]/.test(file.content)
		)
	);
}
