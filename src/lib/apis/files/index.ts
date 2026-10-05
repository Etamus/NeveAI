import { NEVEAI_API_BASE_URL } from '$lib/constants';
import { splitStream } from '$lib/utils';

export const getGeneratedFiles = async (token: string, kind = 'all', query = '', skip = 0) => {
	const params = new URLSearchParams({ kind, query, skip: String(skip), limit: '50' });
	const response = await fetch(`${NEVEAI_API_BASE_URL}/files/generated?${params}`, {
		cache: 'no-store', headers: { authorization: `Bearer ${token}` }
	});
	if (!response.ok) throw (await response.json().catch(() => null))?.detail ?? String(response.status);
	return response.json();
};

export const getFileProcessStatus = async (token: string, id: string) => {
	const queryParams = new URLSearchParams({ stream: 'true' });
	const res = await fetch(
		`${NEVEAI_API_BASE_URL}/files/${id}/process/status?${queryParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'text/event-stream',
				authorization: `Bearer ${token}`
			}
		}
	);

	if (!res.ok) {
		const detail = await res.json().catch(() => null);
		throw detail?.detail ?? `Falha ao processar o arquivo (${res.status})`;
	}

	return res;
};

export const uploadFile = async (
	token: string,
	file: File,
	metadata?: object | null,
	process?: boolean | null
) => {
	const data = new FormData();
	data.append('file', file);
	if (metadata) {
		data.append('metadata', JSON.stringify(metadata));
	}

	const searchParams = new URLSearchParams();
	if (process !== undefined && process !== null) {
		searchParams.append('process', String(process));
	}

	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/files/?${searchParams.toString()}`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		},
		body: data
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	if (res) {
		const status = await getFileProcessStatus(token, res.id);

		if (status && status.ok) {
			const reader = status.body
				.pipeThrough(new TextDecoderStream())
				.pipeThrough(splitStream('\n'))
				.getReader();

			while (true) {
				const { value, done } = await reader.read();
				if (done) {
					break;
				}

				try {
					let lines = value.split('\n');

					for (const line of lines) {
						if (line !== '') {
							console.log(line);
							if (line === 'data: [DONE]') {
								console.log(line);
							} else {
								let data = JSON.parse(line.replace(/^data: /, ''));
								console.log(data);

								if (data?.error) {
									console.error(data.error);
									res.error = data.error;
								}

								if (res?.data) {
									res.data = data;
								}
							}
						}
					}
				} catch (error) {
					console.log(error);
				}
			}
		}
	}

	if (error) {
		throw error;
	}

	return res;
};

export const searchFiles = async (
	token: string,
	filename: string = '*',
	skip: number = 0,
	limit: number = 50
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	searchParams.append('filename', filename);
	searchParams.append('skip', String(skip));
	searchParams.append('limit', String(limit));

	const res = await fetch(`${NEVEAI_API_BASE_URL}/files/search?${searchParams.toString()}`, {
		method: 'GET',
		cache: 'no-store',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return [];
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getFileById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/files/${id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
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

export const getFileContentById = async (id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/files/${id}/content`, {
		method: 'GET',
		headers: {
			Accept: 'application/json'
		},
		credentials: 'include'
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return await res.arrayBuffer();
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

export const deleteFileById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/files/${id}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	if (res !== null && typeof window !== 'undefined') window.dispatchEvent(new Event('neve:files-changed'));
	return res;
};

export const deleteAllFiles = async (token: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/files/all`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	if (res !== null && typeof window !== 'undefined') window.dispatchEvent(new Event('neve:files-changed'));
	return res;
};
