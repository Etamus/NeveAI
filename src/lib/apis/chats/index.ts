import { NEVEAI_API_BASE_URL } from '$lib/constants';
import { getTimeRange } from '$lib/utils';

export const createNewChat = async (token: string, chat: object, folderId: string | null) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/new`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			chat: chat,
			folder_id: folderId ?? null
		})
	})
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

	return res;
};

export const importChats = async (token: string, chats: object[]) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/import`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			chats
		})
	})
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

	return res;
};

export const getChatList = async (
	token: string = '',
	page: number | null = null,
	include_pinned: boolean = false,
	include_folders: boolean = false
) => {
	let error = null;
	const searchParams = new URLSearchParams();

	if (page !== null) {
		searchParams.append('page', `${page}`);
	}

	if (include_folders) {
		searchParams.append('include_folders', 'true');
	}

	if (include_pinned) {
		searchParams.append('include_pinned', 'true');
	}

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/?${searchParams.toString()}`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	if (!res) {
		return [];
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};


export const getAllChats = async (token: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/all`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatListBySearchText = async (token: string, text: string, page: number = 1) => {
	let error = null;

	const searchParams = new URLSearchParams();
	searchParams.append('text', text);
	searchParams.append('page', `${page}`);

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/search?${searchParams.toString()}`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};

export const getChatsByFolderId = async (token: string, folderId: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/folder/${folderId}`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatListByFolderId = async (token: string, folderId: string, page: number = 1) => {
	let error = null;

	const searchParams = new URLSearchParams();
	if (page !== null) {
		searchParams.append('page', `${page}`);
	}

	const res = await fetch(
		`${NEVEAI_API_BASE_URL}/chats/folder/${folderId}/list?${searchParams.toString()}`,
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getAllTags = async (token: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/all/tags`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getPinnedChatList = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/pinned`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};


export const getChatById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}`, {
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


export const getChatPinnedStatusById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}/pinned`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const toggleChatPinnedStatusById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}/pin`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const cloneChatById = async (token: string, id: string, title?: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}/clone`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			...(title && { title: title })
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};



export const updateChatFolderIdById = async (token: string, id: string, folderId?: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}/folder`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			folder_id: folderId
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};


export const updateChatById = async (token: string, id: string, chat: object) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			chat: chat
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteChatById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}`, {
		method: 'DELETE',
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

export const getTagsById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}/tags`, {
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const addTagById = async (token: string, id: string, tagName: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}/tags`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			name: tagName
		})
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

export const deleteTagById = async (token: string, id: string, tagName: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/${id}/tags`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			name: tagName
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteAllChats = async (token: string) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/chats/`, {
		method: 'DELETE',
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
