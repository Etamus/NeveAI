export function normalizeArtifactPath(path: string): string {
	const parts: string[] = [];
	for (const part of path.replace(/\\/g, '/').replace(/^@\//, 'src/').split('/')) {
		if (!part || part === '.') continue;
		if (part === '..') {
			if (!parts.length) throw new Error('Invalid artifact path');
			parts.pop();
		} else parts.push(part);
	}
	return parts.join('/');
}
