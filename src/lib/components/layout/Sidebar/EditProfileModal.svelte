<script lang="ts">
	import { getContext, tick } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { user } from '$lib/stores';
	import { updateUserProfile, getSessionUser } from '$lib/apis/auths';
	import { generateInitialsImage } from '$lib/utils';
	import { WEBUI_BASE_URL } from '$lib/constants';

	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const i18n = getContext('i18n');

	export let show = false;
	export let onSave: Function = () => {};

	let loading = false;

	let username = '';
	let profileImageUrl = '';

	let profileImageInputElement: HTMLInputElement;

	$: if (show) {
		init();
	}

	const init = async () => {
		username = $user?.username ?? $user?.name ?? '';
		const raw = $user?.profile_image_url ?? '';
		profileImageUrl = raw === '/user.png' || raw.endsWith('/user.png') ? '' : raw;
		await tick();
	};

	const onPickImage = () => {
		if (profileImageInputElement) {
			profileImageInputElement.value = '';
		}
		profileImageInputElement?.click();
	};

	const handleImageChange = (e: Event) => {
		const input = e.target as HTMLInputElement;
		const files = input.files ?? null;
		if (!files || files.length === 0) return;
		const file = files[0];
		if (!['image/gif', 'image/webp', 'image/jpeg', 'image/png'].includes(file.type)) {
			toast.error($i18n.t('Unsupported image type'));
			input.value = '';
			return;
		}

		const reader = new FileReader();
		reader.onload = (event) => {
			const originalImageUrl = `${event.target?.result}`;
			const img = new Image();
			img.src = originalImageUrl;
			img.onload = () => {
				const canvas = document.createElement('canvas');
				const ctx = canvas.getContext('2d');
				const aspectRatio = img.width / img.height;

				let newWidth: number;
				let newHeight: number;
				if (aspectRatio > 1) {
					newWidth = 250 * aspectRatio;
					newHeight = 250;
				} else {
					newWidth = 250;
					newHeight = 250 / aspectRatio;
				}

				canvas.width = 250;
				canvas.height = 250;

				const offsetX = (250 - newWidth) / 2;
				const offsetY = (250 - newHeight) / 2;

				ctx?.drawImage(img, offsetX, offsetY, newWidth, newHeight);
				profileImageUrl = canvas.toDataURL('image/webp', 0.8);
				input.value = '';
			};
		};
		reader.readAsDataURL(file);
	};

	const submitHandler = async () => {
		if (loading) return;
		loading = true;

		const trimmedUsername = (username ?? '').trim();

		if (!trimmedUsername) {
			toast.error($i18n.t('Username is required'));
			loading = false;
			return;
		}

		let finalImage = profileImageUrl;
		if (!finalImage) {
			finalImage = '/user.png';
		}

		const updated = await updateUserProfile(localStorage.token, {
			name: trimmedUsername,
			username: trimmedUsername,
			profile_image_url: finalImage
		}).catch((err) => {
			toast.error(`${err}`);
			return null;
		});

		if (updated) {
			const sessionUser = await getSessionUser(localStorage.token).catch(() => null);
			if (sessionUser) {
				await user.set(sessionUser);
			}
			toast.success($i18n.t('Profile updated successfully'));
			onSave();
			show = false;
		}

		loading = false;
	};
</script>

<input
	bind:this={profileImageInputElement}
	type="file"
	accept="image/*"
	hidden
	on:change={handleImageChange}
/>

<Modal size="sm" bind:show>
	<div>
		<div class=" flex justify-between dark:text-gray-300 px-5 pt-4 pb-1">
			<div class=" text-lg font-medium self-center">
				{$i18n.t('Editar perfil')}
			</div>
			<button
				class="self-center"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<form
			class="flex flex-col w-full px-5 pb-4 dark:text-gray-200"
			on:submit|preventDefault={submitHandler}
		>
			<div class="flex justify-center my-4">
				<div class="relative group">
					<button
						type="button"
						class="rounded-full block"
						on:click={onPickImage}
						aria-label={$i18n.t('Change profile picture')}
					>
						<img
							src={profileImageUrl !== '' ? profileImageUrl : `${WEBUI_BASE_URL}/user.png`}
							alt="profile"
							class="size-24 rounded-full object-cover"
						/>
					</button>

					{#if profileImageUrl}
						<button
							type="button"
							class="absolute bottom-0 right-0 p-1.5 rounded-full bg-gray-100 dark:bg-gray-800 text-black dark:text-white border border-white dark:border-gray-900 shadow group/cam"
							on:click={() => {
								profileImageUrl = '';
							}}
							aria-label={$i18n.t('Remove profile picture')}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 20 20"
								fill="currentColor"
								class="size-3.5 block group-hover/cam:hidden"
							>
								<path
									fill-rule="evenodd"
									d="M1 8a2 2 0 0 1 2-2h.93a2 2 0 0 0 1.664-.89l.812-1.22A2 2 0 0 1 8.07 3h3.86a2 2 0 0 1 1.664.89l.812 1.22A2 2 0 0 0 16.07 6H17a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8Zm13.5 3a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM10 14a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"
									clip-rule="evenodd"
								/>
							</svg>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 20 20"
								fill="currentColor"
								class="size-3.5 hidden group-hover/cam:block"
							>
								<path
									d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z"
								/>
							</svg>
						</button>
					{:else}
						<button
							type="button"
							class="absolute bottom-0 right-0 p-1.5 rounded-full bg-gray-100 dark:bg-gray-800 text-black dark:text-white border border-white dark:border-gray-900 shadow"
							on:click={onPickImage}
							aria-label={$i18n.t('Change profile picture')}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 20 20"
								fill="currentColor"
								class="size-3.5"
							>
								<path
									fill-rule="evenodd"
									d="M1 8a2 2 0 0 1 2-2h.93a2 2 0 0 0 1.664-.89l.812-1.22A2 2 0 0 1 8.07 3h3.86a2 2 0 0 1 1.664.89l.812 1.22A2 2 0 0 0 16.07 6H17a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8Zm13.5 3a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM10 14a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"
									clip-rule="evenodd"
								/>
							</svg>
						</button>
					{/if}
				</div>
			</div>

			<div
				class="flex flex-col gap-3 px-3.5 py-3 border border-gray-100 dark:border-gray-850 rounded-xl"
			>
				<div class="flex flex-col">
					<div class="text-xs text-gray-500 mb-1">{$i18n.t('Nome de usuário')}</div>
					<input
						type="text"
						bind:value={username}
						class="w-full text-sm bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-700"
						placeholder={$i18n.t('Nome de usuário')}
						autocomplete="off"
						required
					/>
				</div>
			</div>

			<div class="flex justify-end pt-4 text-sm font-medium">
				<button
					type="submit"
					class="px-4 py-1.5 text-xs font-medium bg-black hover:opacity-90 text-white dark:bg-white dark:text-black transition rounded-lg flex flex-row space-x-1 items-center {loading
						? ' cursor-not-allowed'
						: ''}"
					disabled={loading}
				>
					{$i18n.t('Salvar')}
				</button>
			</div>
		</form>
	</div>
</Modal>
