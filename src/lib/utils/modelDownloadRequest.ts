export type ModelDownloadRequest =
	| { source: 'neve'; modelId: string; name: string; filename?: string }
	| { source: 'hf'; repo: string; filename: string; encoder?: string; name: string };

export const hfDownloadKey = (repo: string, filename: string) => `hf:${JSON.stringify([repo, filename])}`;
export const modelDownloadKey = (request: ModelDownloadRequest) =>
	request.source === 'neve' ? request.modelId : hfDownloadKey(request.repo, request.filename);

export const downloadFilename = (filename?: string) => filename?.split('/').pop() ?? '';
