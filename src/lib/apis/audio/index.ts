import { AUDIO_API_BASE_URL } from '$lib/constants';

export async function transcribeDictation(file: File, locale: string, signal: AbortSignal) {
	const body = new FormData();
	body.append('file', file);
	const language = locale?.split(/[-_]/)[0].toLowerCase();
	if (language === 'pt' || language === 'en') body.append('language', language);
	const response = await fetch(`${AUDIO_API_BASE_URL}/dictation`, {
		method: 'POST',
		headers: { Authorization: `Bearer ${localStorage.token ?? ''}` },
		body,
		signal
	});
	if (!response.ok) throw new Error(`Dictation failed: ${response.status}`);
	const { text } = await response.json();
	return typeof text === 'string' ? text.trim().replace(/\s+/g, ' ') : '';
}

export const transcribeAudio = async (token: string, file: File, language?: string) => {
	const data = new FormData();
	data.append('file', file);
	if (language) {
		data.append('language', language);
	}

	let error = null;
	const res = await fetch(`${AUDIO_API_BASE_URL}/transcriptions`, {
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
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
