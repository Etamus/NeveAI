import { NEVEAI_BASE_URL } from '$lib/constants';
import { prepareChatRequestBody } from '$lib/utils/chatRequestBody';

export const chatCompletion = async (
	token: string = '',
	body: object,
	url: string = `${NEVEAI_BASE_URL}/api`,
	controller: AbortController = new AbortController()
): Promise<[Response | null, AbortController]> => {
	let error = null;

	const res = await fetch(`${url}/chat/completions`, {
		signal: controller.signal,
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(body)
	}).catch((err) => {
		console.error(err);
		error = err;
		return null;
	});

	if (error) {
		throw error;
	}

	return [res, controller];
};

export const generateOpenAIChatCompletion = async (
	token: string = '',
	body: object,
	url: string = `${NEVEAI_BASE_URL}/api`,
	shouldSend?: () => boolean
) => {
	let error = null;
	const requestBody = await prepareChatRequestBody(body);
	if (shouldSend && !shouldSend()) return null;

	const res = await fetch(`${url}/chat/completions`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		credentials: 'include',
		body: requestBody
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

