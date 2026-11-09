import {
	artifactCode,
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

export function openArtifactPreview(artifact: ArtifactResult, history: any) {
	const entries = getConversationArtifacts(history);
	if (!entries.some((entry) => entry.id === artifact.id)) entries.push(artifact);
	artifactContents.set(entries);
	artifactCode.set(artifact.content);
	showEmbeds.set(false);
	showControls.set(true);
	showArtifacts.set(true);
}

export function previewArtifactCode(code: string, messageId: string, history: any) {
	const existing = getConversationArtifacts(history).find(
		(entry) =>
			entry.id.startsWith(`${messageId}:`) &&
			(entry.content.includes(code) || entry.rawHtml?.includes(code))
	);
	const type = /^\s*<svg\b/i.test(code) ? 'svg' : 'html';
	const artifact =
		existing ?? extractArtifactResults(`\`\`\`${type}\n${code}\n\`\`\``, messageId)[0];
	if (artifact) openArtifactPreview(artifact, history);
}

export function downloadArtifact(artifact: ArtifactResult) {
	const url = URL.createObjectURL(
		new Blob([artifact.content], {
			type: artifact.type === 'svg' ? 'image/svg+xml;charset=utf-8' : 'text/html;charset=utf-8'
		})
	);
	const link = document.createElement('a');
	link.href = url;
	link.download = artifact.filename;
	document.body.appendChild(link);
	link.click();
	link.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}
