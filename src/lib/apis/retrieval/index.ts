import { RETRIEVAL_API_BASE_URL } from '$lib/constants';

type ChunkConfigForm = {
	chunk_size: number;
	chunk_overlap: number;
};

type DocumentIntelligenceConfigForm = {
	key: string;
	endpoint: string;
	model: string;
};

type ContentExtractConfigForm = {
	engine: string;
	tika_server_url: string | null;
	document_intelligence_config: DocumentIntelligenceConfigForm | null;
};

type YoutubeConfigForm = {
	language: string[];
	translation?: string | null;
	proxy_url: string;
};

type RAGConfigForm = {
	PDF_EXTRACT_IMAGES?: boolean;
	ENABLE_GOOGLE_DRIVE_INTEGRATION?: boolean;
	ENABLE_ONEDRIVE_INTEGRATION?: boolean;
	chunk?: ChunkConfigForm;
	content_extraction?: ContentExtractConfigForm;
	web_loader_ssl_verification?: boolean;
	youtube?: YoutubeConfigForm;
};

type QuerySettings = {
	k: number | null;
	r: number | null;
	template: string | null;
};

type EmbeddingModelUpdateForm = {
	[key: string]: unknown;
	embedding_batch_size?: number;
};

type RerankingModelUpdateForm = {
	reranking_model: string;
};

export interface SearchDocument {
	status: boolean;
	collection_name: string;
	filenames: string[];
}

export const processYoutubeVideo = async (token: string, url: string) => {
	let error = null;

	const res = await fetch(`${RETRIEVAL_API_BASE_URL}/process/youtube`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			url: url
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const processWeb = async (
	token: string,
	collection_name: string,
	url: string,
	process: boolean = true
) => {
	let error = null;

	const searchParams = new URLSearchParams();

	if (!process) {
		searchParams.append('process', 'false');
	}

	const res = await fetch(`${RETRIEVAL_API_BASE_URL}/process/web?${searchParams.toString()}`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			url: url,
			collection_name: collection_name
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
