/**
 * API client for local GGUF models via llama-cpp-python.
 */
import { WEBUI_BASE_URL } from '$lib/constants';

export interface LocalModel {
	id: string;
	filename: string;
	file_size: number;
	file_size_human: string;
	is_loaded: boolean;
	loaded_at: number | null;
	n_gpu_layers: number | null;
	n_ctx: number | null;
	mmproj_filename: string | null;
}

export const getLocalModels = async (token: string = ''): Promise<LocalModel[]> => {
	const res = await fetch(`${WEBUI_BASE_URL}/llamacpp/models`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	});

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: 'Falha ao buscar modelos locais' }));
		throw new Error(err.detail || 'Falha ao buscar modelos locais');
	}

	const data = await res.json();
	return data.models ?? [];
};

export const getLoadedLocalModels = async (token: string = ''): Promise<LocalModel[]> => {
	const res = await fetch(`${WEBUI_BASE_URL}/llamacpp/models/loaded`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	});

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: 'Falha ao buscar modelos carregados' }));
		throw new Error(err.detail || 'Falha ao buscar modelos carregados');
	}

	const data = await res.json();
	return data.models ?? [];
};

export const getMmProjFiles = async (token: string = ''): Promise<string[]> => {
	const res = await fetch(`${WEBUI_BASE_URL}/llamacpp/models/mmproj`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	});

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: 'Falha ao buscar arquivos mmproj' }));
		throw new Error(err.detail || 'Falha ao buscar arquivos mmproj');
	}

	const data = await res.json();
	return data.mmproj_files ?? [];
};

export const loadLocalModel = async (
	token: string = '',
	filename: string,
	n_gpu_layers: number = -1,
	n_ctx: number = 4096,
	mmproj_filename?: string | null,
	cache_type: string = 'q8_0'
): Promise<any> => {
	const res = await fetch(`${WEBUI_BASE_URL}/llamacpp/models/load`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({ filename, n_gpu_layers, n_ctx, mmproj_filename: mmproj_filename ?? null, cache_type })
	});

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: 'Failed to load model' }));
		throw new Error(err.detail || 'Failed to load model');
	}

	return res.json();
};

export const unloadLocalModel = async (token: string = '', model_id: string): Promise<any> => {
	const res = await fetch(`${WEBUI_BASE_URL}/llamacpp/models/unload`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({ model_id })
	});

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: 'Failed to unload model' }));
		throw new Error(err.detail || 'Failed to unload model');
	}

	return res.json();
};

// ---------------------------------------------------------------------------
// Neve Hugging Face catalog / downloads
// ---------------------------------------------------------------------------

export interface NeveCatalogModel {
	id: string;
	name: string;
	repo: string;
	installed: boolean;
	size_label?: string;
}

export const getNeveCatalog = async (token: string = ''): Promise<NeveCatalogModel[]> => {
	const res = await fetch(`${WEBUI_BASE_URL}/llamacpp/catalog`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: 'Falha ao buscar catálogo' }));
		throw new Error(err.detail || 'Falha ao buscar catálogo');
	}
	const data = await res.json();
	return data.models ?? [];
};

export const startNeveDownload = async (token: string = '', model_id: string): Promise<string> => {
	const res = await fetch(`${WEBUI_BASE_URL}/llamacpp/download`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({ model_id })
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: 'Falha ao iniciar download' }));
		throw new Error(err.detail || 'Falha ao iniciar download');
	}
	const data = await res.json();
	return data.task_id as string;
};

export const streamNeveDownload = (
	task_id: string,
	onUpdate: (state: any) => void,
	onDone: (state: any) => void,
	onError: (err: any) => void
): EventSource => {
	const url = `${WEBUI_BASE_URL}/llamacpp/download/status/${task_id}`;
	const es = new EventSource(url);
	es.onmessage = (e) => {
		try {
			const state = JSON.parse(e.data);
			onUpdate(state);
			if (state.status === 'completed' || state.status === 'error') {
				es.close();
				if (state.status === 'completed') onDone(state);
				else onError(new Error(state.error || 'Falha no download'));
			}
		} catch (err) {
			onError(err);
			es.close();
		}
	};
	es.onerror = (err) => {
		es.close();
		onError(err);
	};
	return es;
};
