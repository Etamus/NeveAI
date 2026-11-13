import { getCodeBlockContents, createMessagesList } from '$lib/utils';
import { artifactFiles, artifactEntry, visibleArtifactSource, type ArtifactFile } from './artifacts/project';

export type ArtifactResult = {
	id: string;
	type: 'iframe' | 'svg';
	content: string;
	filename: string;
	rawHtml?: string;
	rawCss?: string;
	rawJs?: string;
	files?: ArtifactFile[];
	entry?: string;
	live?: boolean;
};

const extractionCache = new Map<string, { source: string; live: boolean; results: ArtifactResult[] }>();
let cachedCharacters = 0;
function cachedArtifacts(message: any): ArtifactResult[] {
	const source = message.content ?? '';
	const live = message.done === false;
	const old = extractionCache.get(message.id);
	if (old?.source === source && old.live === live) return old.results;
	const results = extractArtifactResults(source, message.id, live);
	if (old) { cachedCharacters -= old.source.length; extractionCache.delete(message.id); }
	if (source.length <= 500_000) {
		extractionCache.set(message.id, { source, live, results }); cachedCharacters += source.length;
		while (extractionCache.size > 64 || cachedCharacters > 2_000_000) {
			const key = extractionCache.keys().next().value!;
			cachedCharacters -= extractionCache.get(key)!.source.length; extractionCache.delete(key);
		}
	}
	return results;
}

export function extractArtifactResults(content: string, messageId = '', unfinished = false): ArtifactResult[] {
	if (!content || (!content.includes('```') && !/<(?:html|svg)\b/i.test(content))) return [];
	let { html, css, js, codeBlocks } = getCodeBlockContents(content);
	const files = artifactFiles(content, unfinished);
	const entry = artifactEntry(files);
	if (entry?.language === 'html') {
		html = files.filter(file => file.language === 'html' && (file.path === entry.path || file.path === 'index.html')).map(file => file.content).join('\n');
		css = files.filter(file => file.language === 'css').map(file => file.content).join('\n');
		js = files.filter(file => file.language === 'js').map(file => file.content).join('\n');
	}
	if (codeBlocks.length === 0) {
		const visibleContent = visibleArtifactSource(content);
		const document = visibleContent.match(
			/(?:<!doctype\s+html[^>]*>\s*)?<html\b[^>]*>[\s\S]*?<\/html>/i
		);
		if (document) {
			html = document[0];
			// A raw document already contains its own dependencies.
			css = '';
			js = '';
		} else {
			for (const match of visibleContent.matchAll(/<svg\b[^>]*>[\s\S]*?<\/svg>/gi)) {
				codeBlocks.push({ lang: 'svg', code: match[0] });
			}
		}
	}
	const results: ArtifactResult[] = [];
	if (html) {
		let document = html;
		const styles = css ? `<style>\n${css}\n</style>` : '';
		const scripts = js ? `<script>\n${js}\n</script>` : '';
		if (/<html\b/i.test(html)) {
			if (styles)
				document = /<\/head>/i.test(document)
					? document.replace(/<\/head>/i, `${styles}\n</head>`)
					: `${styles}\n${document}`;
			if (scripts)
				document = /<\/body>/i.test(document)
					? document.replace(/<\/body>/i, `${scripts}\n</body>`)
					: `${document}\n${scripts}`;
		} else {
			document = `<!DOCTYPE html>\n<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">${styles}</head><body>${html}${scripts}</body></html>`;
		}
		results.push({
			id: `${messageId}:html`,
			type: 'iframe',
			content: document,
			filename: 'artifact.html',
			...(entry ? { files, entry: entry.path } : {}),
			...(unfinished ? { live: true } : {}),
			rawHtml: html,
			rawCss: css,
			rawJs: js
		});
	}
	if (!html && entry) {
		results.push({ id: `${messageId}:html`, type: 'iframe', filename: 'artifact.html',
			content: '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div></body></html>',
			files, entry: entry.path, ...(unfinished ? { live: true } : {}) });
	}
	for (const [index, block] of codeBlocks.entries()) {
		if (block.lang === 'svg' || (block.lang === 'xml' && /<svg\b/i.test(block.code))) {
			results.push({
				id: `${messageId}:svg:${index}`,
				type: 'svg',
				content: block.code,
				filename: `artifact-${index + 1}.svg`
			});
		}
	}
	return results;
}

export function getConversationArtifacts(
	history: any,
	manualPreviews: ArtifactResult[] = [],
	liveArtifactId: string | null = null,
	includeLive = false
): ArtifactResult[] {
	const messages = history ? createMessagesList(history, history.currentId) : [];
	const results = messages
		.filter((message) => message.role === 'assistant' && (message.done !== false || includeLive || liveArtifactId?.startsWith(`${message.id}:`)))
		.flatMap(cachedArtifacts);
	// An explicitly opened unfinished codeblock remains usable until it is replaced or removed.
	for (const preview of manualPreviews) {
		if (
			!results.some((entry) => entry.id === preview.id) &&
			messages.some(
				(message) =>
					message.role === 'assistant' &&
					preview.id?.startsWith(`${message.id}:`) &&
					message.content?.includes(preview.rawHtml || preview.content)
			)
		)
			results.push(messages.find(message => preview.id?.startsWith(`${message.id}:`))?.done === false ? preview : { ...preview, live: false });
	}
	const generating = messages.at(-1);
	if (includeLive && generating?.role === 'assistant' && generating.done === false && !results.some(entry => entry.id.startsWith(`${generating.id}:`))) {
		const previous = manualPreviews.find(entry => entry.id === liveArtifactId);
		if (previous && !results.some(entry => entry.id === previous.id) && Object.values(history.messages).some((message: any) => previous.id.startsWith(`${message.id}:`))) {
			// Regeneration can clear the source before any replacement code arrives.
			results.push({ ...previous, live: false });
		}
	}
	return results;
}
