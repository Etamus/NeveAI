<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { createEventDispatcher, getContext, onMount, tick } from 'svelte';

	import { flyAndScale } from '$lib/utils/transitions';
	import { goto } from '$app/navigation';
	import { fade, slide } from 'svelte/transition';

	import { getUsage } from '$lib/apis';
	import { getSessionUser, userSignOut } from '$lib/apis/auths';

	import { showSettings, showLocalModelsModal, mobile, showSidebar, user, config } from '$lib/stores';

	import { WEBUI_API_BASE_URL } from '$lib/constants';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import QuestionMarkCircle from '$lib/components/icons/QuestionMarkCircle.svelte';
	import Map from '$lib/components/icons/Map.svelte';
	import Settings from '$lib/components/icons/Settings.svelte';
	import UserGroup from '$lib/components/icons/UserGroup.svelte';
	import SignOut from '$lib/components/icons/SignOut.svelte';
	import FaceSmile from '$lib/components/icons/FaceSmile.svelte';
	import { shutdownApp } from '$lib/apis';
	import UserStatusModal from './UserStatusModal.svelte';
	import EditProfileModal from './EditProfileModal.svelte';
	import UserCircle from '$lib/components/icons/UserCircle.svelte';
	import Emoji from '$lib/components/common/Emoji.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import { updateUserStatus } from '$lib/apis/users';
	import { toast } from 'svelte-sonner';

	const i18n = getContext('i18n');

	export let show = false;
	export let role = '';

	export let profile = false;
	export let help = false;

	export let className = 'max-w-[11rem]';
	export let align = 'end';

	export let showActiveUsers = true;

	let showUserStatusModal = false;
	let showEditProfileModal = false;

	const dispatch = createEventDispatcher();

	let usage = null;
	const getUsageInfo = async () => {
		const res = await getUsage(localStorage.token).catch((error) => {
			console.error('Error fetching usage info:', error);
		});

		if (res) {
			usage = res;
		} else {
			usage = null;
		}
	};

	const handleDropdownChange = (state: boolean) => {
		dispatch('change', state);

		// Fetch usage info when dropdown opens, if user has permission
		if (state && ($config?.features?.enable_public_active_users_count || role === 'admin')) {
			getUsageInfo();
		}
	};
</script>

<UserStatusModal
	bind:show={showUserStatusModal}
	onSave={async () => {
		user.set(await getSessionUser(localStorage.token));
	}}
/>

<EditProfileModal
	bind:show={showEditProfileModal}
	onSave={async () => {
		user.set(await getSessionUser(localStorage.token));
	}}
/>



<!-- svelte-ignore a11y-no-static-element-interactions -->
<DropdownMenu.Root bind:open={show} onOpenChange={handleDropdownChange}>
	<DropdownMenu.Trigger>
		<slot />
	</DropdownMenu.Trigger>

	<slot name="content">
		<DropdownMenu.Content
				class="w-full {className} rounded-md px-1 py-0.5 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-md text-sm"
			sideOffset={4}
			side="top"
			align="start"
			avoidCollisions={false}
			transition={(e) => fade(e, { duration: 100 })}
		>
			{#if profile}
				<div class=" flex gap-3.5 w-full p-1.5 items-center">
					<div class=" items-center flex shrink-0">
						<img
							src={`${WEBUI_API_BASE_URL}/users/${$user?.id}/profile/image`}
						class=" size-8 object-cover rounded-full"
							alt="profile"
						/>
					</div>

					<div class=" flex flex-col w-full flex-1">
						<div class="font-medium line-clamp-1 pr-2">
							{$user.name}
						</div>

						<div class=" flex items-center gap-2">
							{#if $user?.is_active ?? true}
								<div>
									<span class="relative flex size-2">
										<span class="relative inline-flex rounded-full size-2 bg-green-500" />
									</span>
								</div>

								<span class="text-xs"> {$i18n.t('Active')} </span>
							{:else}
								<div>
									<span class="relative flex size-2">
										<span class="relative inline-flex rounded-full size-2 bg-gray-500" />
									</span>
								</div>

								<span class="text-xs"> {$i18n.t('Away')} </span>
							{/if}
						</div>
					</div>
				</div>

				{#if $user?.status_emoji || $user?.status_message}
					<div class="mx-1">
						<button
							class="mb-1 w-full gap-2 px-2.5 py-1.5 rounded-xl bg-gray-50 dark:text-white dark:bg-gray-900/50 text-black transition text-xs flex items-center"
							type="button"
							on:click={() => {
								show = false;
								showUserStatusModal = true;
							}}
						>
							{#if $user?.status_emoji}
								<div class=" self-center shrink-0">
									<Emoji className="size-4" shortCode={$user?.status_emoji} />
								</div>
							{/if}

							<Tooltip
								content={$user?.status_message}
								className=" self-center line-clamp-2 flex-1 text-left"
							>
								{$user?.status_message}
							</Tooltip>

							<div class="self-start">
								<Tooltip content={$i18n.t('Clear status')}>
									<button
										type="button"
										on:click={async (e) => {
											e.preventDefault();
											e.stopPropagation();
											e.stopImmediatePropagation();

											const res = await updateUserStatus(localStorage.token, {
												status_emoji: '',
												status_message: ''
											});

											if (res) {
												toast.success($i18n.t('Status cleared successfully'));
												user.set(await getSessionUser(localStorage.token));
											} else {
												toast.error($i18n.t('Failed to clear status'));
											}
										}}
									>
										<XMark className="size-4 opacity-50" strokeWidth="2" />
									</button>
								</Tooltip>
							</div>
						</button>
					</div>
				{:else}
					<div class="mx-1">
						<button
							class="mb-1 w-full px-3 py-1.5 gap-1 rounded-xl bg-gray-50 dark:text-white dark:bg-gray-900/50 text-black transition text-xs flex items-center justify-center"
							type="button"
							on:click={() => {
								show = false;
								showUserStatusModal = true;
							}}
						>
							<div class=" self-center">
								<FaceSmile className="size-4" strokeWidth="1.5" />
							</div>
							<div class=" self-center truncate">{$i18n.t('Update your status')}</div>
						</button>
					</div>
				{/if}

					<hr class=" border-gray-50/30 dark:border-gray-800/30 my-1 p-0" />
			{/if}



			<div class="flex flex-col items-stretch px-1 py-0.5 gap-0.5">
				<DropdownMenu.Item
					class="flex items-center rounded-sm py-1.5 px-3 w-full hover:bg-gray-50 dark:hover:bg-gray-800 transition cursor-pointer select-none"
					on:click={async () => {
						show = false;
						showEditProfileModal = true;

						if ($mobile) {
							await tick();
							showSidebar.set(false);
						}
					}}
				>
					<div class="flex items-center gap-3">
						<UserCircle className="w-5 h-5" strokeWidth="1.5" />
						<span class="text-sm">{$i18n.t('Profile')}</span>
					</div>
				</DropdownMenu.Item>

				<DropdownMenu.Item
					class="flex items-center rounded-sm py-1.5 px-3 w-full hover:bg-gray-50 dark:hover:bg-gray-800 transition cursor-pointer select-none"
					on:click={async () => {
						show = false;

						await showSettings.set(true);

						if ($mobile) {
							await tick();
							showSidebar.set(false);
						}
					}}
				>
					<div class="flex items-center gap-3">
						<Settings className="w-5 h-5" strokeWidth="1.5" />
						<span class="text-sm">{$i18n.t('Settings')}</span>
					</div>
				</DropdownMenu.Item>

				<DropdownMenu.Item
					class="flex items-center rounded-sm py-1.5 px-3 w-full hover:bg-gray-50 dark:hover:bg-gray-800 transition cursor-pointer select-none"
					on:click={async () => {
						show = false;
						try { await shutdownApp(localStorage.token); } catch {}
						window.close();
					}}
				>
					<div class="flex items-center gap-3">
					<SignOut className="w-5 h-5 translate-x-0.5" />
						<span class="text-sm">{$i18n.t('Sair')}</span>
					</div>
				</DropdownMenu.Item>
			</div>
		</DropdownMenu.Content>
	</slot>
</DropdownMenu.Root>
