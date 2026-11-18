import {
	artifactCode,
	artifactSelection,
	artifactContents,
	showArtifacts,
	showControls,
	showEmbeds
} from '$lib/stores';
import {
	getConversationArtifacts,
	extractArtifactResults,
	type ArtifactResult
} from './artifactResults';
import { downloadChatFile } from '$lib/utils/chatFileSave';

export function openArtifactPreview(artifact: ArtifactResult, history: any) {
	const entries = getConversationArtifacts(history);
	if (!entries.some((entry) => entry.id === artifact.id)) entries.push(artifact);
	artifactSelection.set(artifact.id);
	artifactContents.set(entries);
	artifactCode.set(artifact.content);
	showEmbeds.set(false);
	showControls.set(true);
	showArtifacts.set(true);
}

export function previewArtifactCode(code: string, messageId: string, history: any, language = 'html') {
	const existing = getConversationArtifacts(history, [], `${messageId}:html`).find(
		(entry) =>
			entry.id.startsWith(`${messageId}:`) &&
			(entry.content.includes(code) || entry.rawHtml?.includes(code) || entry.files?.some(file => file.content.includes(code)))
	);
	const type = /^\s*<svg\b/i.test(code) ? 'svg' : language;
	const artifact =
		existing ?? extractArtifactResults(`\`\`\`${type}\n${code}\n\`\`\``, messageId)[0];
	if (artifact) {
		openArtifactPreview(artifact, history);
		artifactCode.set(code);
	}
}

export function downloadArtifact(artifact: ArtifactResult) {
	return downloadChatFile(artifact.filename, async () => {
		const content = artifact.type === 'svg' ? artifact.content : await (await import('./artifacts/export')).exportArtifact(artifact);
		return new Blob([content], {type: artifact.type === 'svg' ? 'image/svg+xml;charset=utf-8' : 'text/html;charset=utf-8'});
	});
}
