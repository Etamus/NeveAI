import { getCodeBlockContents, createMessagesList, removeAllDetails } from '$lib/utils';

export type ArtifactResult = {
	id: string;
	type: 'iframe' | 'svg';
	content: string;
	filename: string;
	rawHtml?: string;
	rawCss?: string;
	rawJs?: string;
};

export function extractArtifactResults(content: string, messageId = ''): ArtifactResult[] {
	if (!content || (!content.includes('```') && !/<(?:html|svg)\b/i.test(content))) return [];
	let { html, css, js, codeBlocks } = getCodeBlockContents(content);
	if (codeBlocks.length === 0) {
		const visibleContent = removeAllDetails(content);
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
			rawHtml: html,
			rawCss: css,
			rawJs: js
		});
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
	manualPreviews: ArtifactResult[] = []
): ArtifactResult[] {
	const messages = history ? createMessagesList(history, history.currentId) : [];
	const results = messages
		.filter((message) => message.role === 'assistant' && message.done !== false)
		.flatMap((message) => extractArtifactResults(message.content ?? '', message.id));
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
			results.push(preview);
	}
	return results;
}
