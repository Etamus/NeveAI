<script lang="ts">
	import { getContext } from 'svelte';
	import { settings } from '$lib/stores';
	import Switch from '$lib/components/common/Switch.svelte';
	import { toastCategoryEnabled, interfaceNotificationsEnabled } from '$lib/utils/toastPreferences';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');
	export let saveSettings: Function;
	$: enabled = interfaceNotificationsEnabled($settings);
	const options = [
		{ key: 'showModelRuntimeToasts', category: 'runtime', label: 'Model loading and unloading' },
		{ key: 'showModelDownloadToasts', category: 'downloads', label: 'Model downloads' },
		{ key: 'showErrorToasts', category: 'errors', label: 'Error notifications' }
	] as const;
</script>

<div id="tab-notifications" class="pt-2 text-sm">
	<div class="flex w-full items-center justify-between gap-4">
		<span id="notification-master-label" class="text-sm font-medium"
			>{$i18n.t('Enable interface notifications')}</span
		>
		<div class="shrink-0 px-1">
			<Switch
				ariaLabelledbyId="notification-master-label"
				state={enabled}
				on:change={(event) => saveSettings({ enableInterfaceNotifications: event.detail })}
			/>
		</div>
	</div>
	{#each options as option}
		<div
			class="flex w-full items-center justify-between gap-4 py-0.5 {option.category === 'runtime'
				? 'mt-2'
				: ''}"
		>
			<span
				id={`notification-${option.category}-label`}
				class={!enabled ? 'text-gray-400 dark:text-gray-600' : ''}>{$i18n.t(option.label)}</span
			>
			<div class="shrink-0 p-1">
				<Switch
					ariaLabelledbyId={`notification-${option.category}-label`}
					state={toastCategoryEnabled($settings, option.category)}
					disabled={!enabled}
					on:change={(event) => {
						if (enabled) saveSettings({ [option.key]: event.detail });
					}}
				/>
			</div>
		</div>
	{/each}
</div>
