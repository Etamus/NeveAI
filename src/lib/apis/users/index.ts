import { NEVEAI_API_BASE_URL } from '$lib/constants';
import { getUserPosition } from '$lib/utils';


export const getUserSettings = async (token: string) => {
	let error = null;
	const res = await fetch(`${NEVEAI_API_BASE_URL}/users/user/settings`, {
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
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateUserSettings = async (token: string, settings: object) => {
	let error = null;

	const res = await fetch(`${NEVEAI_API_BASE_URL}/users/user/settings/update`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			...settings
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};


export const updateUserInfo = async (token: string, info: Record<string, unknown>) => {
	let error: unknown = null;
	const res = await fetch(`${NEVEAI_API_BASE_URL}/users/user/info/update`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify(info)
	})
		.then(async (response) => {
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

export const getAndUpdateUserLocation = async (token: string) => {
	const location = await getUserPosition().catch((err) => {
		console.error(err);
		return null;
	});

	if (location) {
		await updateUserInfo(token, { location: location });
		return location;
	} else {
		console.info('Failed to get user location');
		return null;
	}
};

type UserUpdateForm = {
	role: string;
	profile_image_url: string;
	email: string;
	name: string;
	password: string;
};
