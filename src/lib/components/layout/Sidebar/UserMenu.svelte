<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { createEventDispatcher, getContext, tick } from 'svelte';
	import { fade } from 'svelte/transition';

	import { getSessionUser } from '$lib/apis/auths';

	import { showSettings, mobile, showSidebar, sidebarWidth, user } from '$lib/stores';

	import Settings from '$lib/components/icons/Settings.svelte';
	import SignOut from '$lib/components/icons/SignOut.svelte';
	import { shutdownApp } from '$lib/apis';
	import EditProfileModal from './EditProfileModal.svelte';
	import UserCircle from '$lib/components/icons/UserCircle.svelte';

	const i18n = getContext('i18n');

	export let show = false;
	export let role = '';

	export let help = false;

	export let className = '';
	export let align = 'end';


	let showEditProfileModal = false;

	const dispatch = createEventDispatcher();

	const handleDropdownChange = (state: boolean) => {
		dispatch('change', state);
	};
</script>

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
			style="width: {Math.max(224, $sidebarWidth - 16)}px; max-width: calc(100vw - 16px);"
			sideOffset={4}
			side="top"
			align="start"
			avoidCollisions={true}
			fitViewport={true}
			transition={(e) => fade(e, { duration: 100 })}
		>



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
