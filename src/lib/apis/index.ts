import { NEVEAI_BASE_URL } from '$lib/constants';
import { convertOpenApiToToolPayload } from '$lib/utils';

export const shutdownApp = async (token: string) => {
	const res = await fetch(`${NEVEAI_BASE_URL}/api/shutdown`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	}).catch(() => null);
	return res?.ok ?? false;
};

export const startAppUpdater = async (token: string) => {
	const res = await fetch(`${NEVEAI_BASE_URL}/api/updater/start`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	}).catch(() => null);
	return res?.ok ?? false;
};

export const getModels = async (
	token: string = '',
	connections: object | null = null,
	base: boolean = false,
	refresh: boolean = false
) => {
	const searchParams = new URLSearchParams();
	if (refresh) {
		searchParams.append('refresh', 'true');
	}

	let error = null;
	const res = await fetch(
		`${NEVEAI_BASE_URL}/api/models${base ? '/base' : ''}?${searchParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				...(token && { authorization: `Bearer ${token}` })
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	let models = res?.data ?? [];

	return models;
};

type ChatCompletedForm = {
	[key: string]: any;
	model: string;
	messages: any[];
	chat_id: string;
	session_id: string;
};

export const chatCompleted = async (token: string, body: ChatCompletedForm) => {
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/chat/completed`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify(body)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

type ChatActionForm = {
	model: string;
	messages: Array<Record<string, any>>;
	chat_id: string;
	[key: string]: any;
};

export const chatAction = async (token: string, action_id: string, body: ChatActionForm) => {
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/chat/actions/${action_id}`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify(body)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const stopTask = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/tasks/stop/${id}`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getTaskIdsByChatId = async (token: string, chat_id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/tasks/chat/${chat_id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getToolServerData = async (token: string | null, url: string) => {
	let error: unknown = null;

	const res = await fetch(url, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token ? { authorization: `Bearer ${token}` } : {})
		}
	})
		.then(async (response) => {
			if (url.toLowerCase().endsWith('.yaml') || url.toLowerCase().endsWith('.yml')) {
				if (!response.ok) throw new Error(await response.text());
				const [source, { parse }] = await Promise.all([response.text(), import('yaml')]);
				return parse(source);
			}

			if (!response.ok) throw await response.json();
			return response.json();
		})
		.catch((caughtError) => {
			error = caughtError;
			return null;
		});

	if (error) throw error;
	return res;
};

type ToolServerConnection = {
	url?: string;
	path?: string;
	key?: string;
	auth_type?: 'bearer' | 'none' | 'session' | string;
	spec_type?: 'url' | 'json' | string;
	spec?: string;
	config?: { enable?: boolean };
};

export const getToolServersData = async (servers: ToolServerConnection[]) => {
	return (
		await Promise.all(
			servers
				.filter((server) => server?.config?.enable)
				.map(async (server) => {
					let error = null;

					let toolServerToken = null;

					const auth_type = server?.auth_type ?? 'bearer';
					if (auth_type === 'bearer') {
						toolServerToken = server?.key;
					} else if (auth_type === 'none') {
						// No authentication
					} else if (auth_type === 'session') {
						toolServerToken = localStorage.token;
					}

					let res = null;
					const specType = server?.spec_type ?? 'url';

					if (specType === 'url') {
						res = await getToolServerData(
							toolServerToken,
							(server?.path ?? '').includes('://')
								? server?.path
								: `${server?.url}${(server?.path ?? '').startsWith('/') ? '' : '/'}${server?.path}`
						).catch((err) => {
							error = err;
							return null;
						});
					} else if ((specType === 'json' && server?.spec) ?? null) {
						try {
							res = JSON.parse(server?.spec);
						} catch (e) {
							error = 'Failed to parse JSON spec';
						}
					}

					if (res) {
						if (!res.paths) {
							return {
								error: 'Invalid OpenAPI spec',
								url: server?.url
							};
						}

						const { openapi, info, specs } = {
							openapi: res,
							info: res.info,
							specs: convertOpenApiToToolPayload(res)
						};

						return {
							url: server?.url,
							openapi: openapi,
							info: info,
							specs: specs
						};
					} else if (error) {
						return {
							error,
							url: server?.url
						};
					} else {
						return null;
					}
				})
		)
	).filter((server) => server);
};

export const executeToolServer = async (
	token: string,
	url: string,
	name: string,
	params: Record<string, any>,
	serverData: { openapi: any; info: any; specs: any }
) => {
	let error = null;

	try {
		// Find the matching operationId in the OpenAPI spec
		const matchingRoute = Object.entries(serverData.openapi.paths).find(([_, methods]) =>
			Object.entries(methods as any).some(([__, operation]: any) => operation.operationId === name)
		);

		if (!matchingRoute) {
			throw new Error(`No matching route found for operationId: ${name}`);
		}

		const [routePath, methods] = matchingRoute;

		const methodEntry = Object.entries(methods as any).find(
			([_, operation]: any) => operation.operationId === name
		);

		if (!methodEntry) {
			throw new Error(`No matching method found for operationId: ${name}`);
		}

		const [httpMethod, operation]: [string, any] = methodEntry;

		// Split parameters by type
		const pathParams: Record<string, any> = {};
		const queryParams: Record<string, any> = {};
		let bodyParams: any = {};

		if (operation.parameters) {
			operation.parameters.forEach((param: any) => {
				const paramName = param?.name;
				if (!paramName) return;
				const paramIn = param?.in;
				if (Object.prototype.hasOwnProperty.call(params, paramName)) {
					if (paramIn === 'path') {
						pathParams[paramName] = params[paramName];
					} else if (paramIn === 'query') {
						queryParams[paramName] = params[paramName];
					}
				}
			});
		}

		let finalUrl = `${url}${routePath}`;

		// Replace path parameters (`{param}`)
		Object.entries(pathParams).forEach(([key, value]) => {
			finalUrl = finalUrl.replace(new RegExp(`{${key}}`, 'g'), encodeURIComponent(value));
		});

		// Append query parameters to URL if any
		if (Object.keys(queryParams).length > 0) {
			const queryString = new URLSearchParams(
				Object.entries(queryParams).map(([k, v]) => [k, String(v)])
			).toString();
			finalUrl += `?${queryString}`;
		}

		// Handle requestBody composite
		if (operation.requestBody && operation.requestBody.content) {
			const contentType = Object.keys(operation.requestBody.content)[0];
			if (params !== undefined) {
				bodyParams = params;
			} else {
				// Optional: Fallback or explicit error if body is expected but not provided
				throw new Error(`Request body expected for operation '${name}' but none found.`);
			}
		}

		// Prepare headers and request options
		const headers: Record<string, string> = {
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		};

		const requestOptions: RequestInit = {
			method: httpMethod.toUpperCase(),
			headers
		};

		if (
			['post', 'put', 'patch', 'delete'].includes(httpMethod.toLowerCase()) &&
			operation.requestBody
		) {
			requestOptions.body = JSON.stringify(bodyParams);
		}

		const res = await fetch(finalUrl, requestOptions);
		if (!res.ok) {
			const resText = await res.text();
			throw new Error(`HTTP error! Status: ${res.status}. Message: ${resText}`);
		}

		// make a clone of res and extract headers
		const responseHeaders = {};
		res.headers.forEach((value, key) => {
			responseHeaders[key] = value;
		});

		const text = await res.text();
		let responseData;

		try {
			responseData = JSON.parse(text);
		} catch {
			responseData = text;
		}
		return [responseData, responseHeaders];
	} catch (err: any) {
		error = err.message;
		console.error('API Request Error:', error);
		return [{ error }, null];
	}
};

export const generateEmoji = async (
	token: string = '',
	model: string,
	prompt: string,
	chat_id?: string
) => {
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/v1/tasks/emoji/completions`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			model: model,
			prompt: prompt,
			...(chat_id && { chat_id: chat_id })
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			}
			return null;
		});

	if (error) {
		throw error;
	}

	const response = res?.choices[0]?.message?.content.replace(/["']/g, '') ?? null;

	if (response) {
		if (/\p{Extended_Pictographic}/u.test(response)) {
			return response.match(/\p{Extended_Pictographic}/gu)[0];
		}
	}

	return null;
};


export const generateAutoCompletion = async (
	token: string = '',
	model: string,
	prompt: string,
	messages?: object[],
	type: string = 'search query',
	chat_id?: string
) => {
	const controller = new AbortController();
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/v1/tasks/auto/completions`, {
		signal: controller.signal,
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			model: model,
			prompt: prompt,
			...(messages && { messages: messages }),
			type: type,
			stream: false,
			...(chat_id && { chat_id: chat_id })
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			if ('detail' in err) {
				error = err.detail;
			}
			return null;
		});

	if (error) {
		throw error;
	}

	const response = res?.choices[0]?.message?.content ?? '';

	try {
		const jsonStartIndex = response.indexOf('{');
		const jsonEndIndex = response.lastIndexOf('}');

		if (jsonStartIndex !== -1 && jsonEndIndex !== -1) {
			const jsonResponse = response.substring(jsonStartIndex, jsonEndIndex + 1);

			// Step 5: Parse the JSON block
			const parsed = JSON.parse(jsonResponse);

			// Step 6: If there's a "queries" key, return the queries array; otherwise, return an empty array
			if (parsed && parsed.text) {
				return parsed.text;
			} else {
				return '';
			}
		}

		// If no valid JSON block found, return response as is
		return response;
	} catch (e) {
		// Catch and safely return empty array on any parsing errors
		console.error('Failed to parse response: ', e);
		return response;
	}
};

export const generateMoACompletion = async (
	token: string = '',
	model: string,
	prompt: string,
	responses: string[]
) => {
	const controller = new AbortController();
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/v1/tasks/moa/completions`, {
		signal: controller.signal,
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			model: model,
			prompt: prompt,
			responses: responses,
			stream: true
		})
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

export const getBackendConfig = async () => {
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/config`, {
		method: 'GET',
		credentials: 'include',
		headers: {
			'Content-Type': 'application/json'
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getVersion = async (token: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/version`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getVersionUpdates = async (token: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_BASE_URL}/api/version/updates`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export interface ModelConfig {
	id: string;
	name: string;
	meta: ModelMeta;
	base_model_id?: string;
	params: ModelParams;
}

export interface ModelMeta {
	toolIds?: string[];
	skillIds?: string[];
	defaultFeatureIds?: string[];
	builtinTools?: Record<string, any>;
	knowledge?: any[];
	tts?: Record<string, any>;
	description?: string;
	capabilities?: Record<string, any>;
	profile_image_url?: string;
	[key: string]: unknown;
}

export type ModelParams = Record<string, unknown>;
