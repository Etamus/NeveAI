export type GitHubRepositoryReference = {
	type: 'repository';
	rawUrl: string;
	url: string;
	owner: string;
	repository: string;
	label: string;
};

export type GitHubMessageSegment = { type: 'text'; value: string } | GitHubRepositoryReference;

export type GitHubRepositoryMatch = {
	start: number;
	end: number;
	rawEnd: number;
	reference: GitHubRepositoryReference;
};

const GITHUB_URL_PATTERN = /https?:\/\/(?:www\.)?github\.com\/[^\s<>"']+/gi;
const REPOSITORY_PART_PATTERN = /^[A-Za-z0-9_.-]{1,100}$/;

export const parseGitHubRepositoryUrl = (rawUrl: string): GitHubRepositoryReference | null => {
	try {
		const parsed = new URL(rawUrl);
		if (!['github.com', 'www.github.com'].includes(parsed.hostname.toLowerCase())) {
			return null;
		}

		const parts = parsed.pathname.split('/').filter(Boolean);
		if (parts.length !== 2) {
			return null;
		}

		const owner = parts[0];
		const repository = parts[1].replace(/\.git$/i, '');
		if (!REPOSITORY_PART_PATTERN.test(owner) || !REPOSITORY_PART_PATTERN.test(repository)) {
			return null;
		}

		return {
			type: 'repository',
			rawUrl,
			url: `https://github.com/${owner}/${repository}`,
			owner,
			repository,
			label: `${owner}/${repository}`
		};
	} catch {
		return null;
	}
};

export const findGitHubRepositoryLinks = (content: string): GitHubRepositoryMatch[] => {
	const repositories: GitHubRepositoryMatch[] = [];

	for (const match of content.matchAll(GITHUB_URL_PATTERN)) {
		const start = match.index ?? 0;
		const matchedUrl = match[0];
		const candidate = matchedUrl.replace(/[.,;:!?\)\]\}]+$/, '');
		const reference = parseGitHubRepositoryUrl(candidate);
		if (!reference) continue;

		repositories.push({
			start,
			end: start + candidate.length,
			rawEnd: start + matchedUrl.length,
			reference
		});
	}

	return repositories;
};

export const splitGitHubRepositoryLinks = (content: string): GitHubMessageSegment[] => {
	const segments: GitHubMessageSegment[] = [];
	let cursor = 0;

	for (const match of findGitHubRepositoryLinks(content)) {
		if (match.start > cursor) {
			segments.push({ type: 'text', value: content.slice(cursor, match.start) });
		}
		segments.push(match.reference);
		const trailingText = content.slice(match.end, match.rawEnd);
		if (trailingText) {
			segments.push({ type: 'text', value: trailingText });
		}
		cursor = match.rawEnd;
	}

	if (cursor < content.length) {
		segments.push({ type: 'text', value: content.slice(cursor) });
	}

	return segments.length ? segments : [{ type: 'text', value: content }];
};
