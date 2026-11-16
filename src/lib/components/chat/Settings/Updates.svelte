<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { getVersionUpdates, updateRequest } from '$lib/apis';
	import { settings, NEVEAI_VERSION } from '$lib/stores';
	import { versionUpdateStatus, getAvailableUpdateTargets } from '$lib/utils/updateAvailability';
	import { updateNotificationsEnabled } from '$lib/utils/updateToast';
	import Switch from '$lib/components/common/Switch.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import Download from '$lib/components/icons/ModelDownload.svelte';
	import Restart from '$lib/components/icons/UpdateRestart.svelte';
	import { interfaceNotificationsEnabled } from '$lib/utils/toastPreferences';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');
	export let saveSettings: Function;
	let job: any = { status: 'idle' };
	let busy = false,
		refreshBusy = false,
		mounted = true,
		stateReady = false,
		operation = 0;
	$: status = $versionUpdateStatus;
	$: available = getAvailableUpdateTargets(status, $NEVEAI_VERSION);
	$: neveAvailable = available.some((value) => value.startsWith('NeveAI '));
	$: llamaAvailable = available.some((value) => value.startsWith('llama.cpp '));
	$: locked = ['downloading', 'ready', 'restarting', 'applying'].includes(job.status);
	$: receiveLlama = $settings?.receiveLlamaUpdates !== false;
	$: eligible = [
		...(neveAvailable ? ['neve'] : []),
		...(llamaAvailable && receiveLlama ? ['llama'] : [])
	];
	// Prepared packages stay authoritative until their transaction finishes.
	$: targets = locked ? job.targets || eligible : eligible;
	$: llamaSwitch = locked ? targets.includes('llama') : receiveLlama;
	$: components = [
		{
			id: 'neve',
			name: 'NeveAI',
			version: (locked ? job.versions?.neve : null) || status?.latest_tag
		},
		{
			id: 'llama',
			name: 'Llama.cpp',
			version: (locked ? job.versions?.llama : null) || status?.llama_cpp?.latest_tag
		}
	].filter((component) => targets.includes(component.id));
	$: progressing = job.status === 'downloading' || job.status === 'applying';
	$: visibleComponents = progressing || locked
		? []
		: components.filter((component) => component.id === 'llama');
	$: neveVersion = components.find((component) => component.id === 'neve')?.version;
	$: downloadVersion =
		neveVersion || components.find((component) => component.id === 'llama')?.version;
	$: heading = progressing
		? 'Software update'
		: job.status === 'ready'
			? 'Restart to apply changes'
			: job.status === 'restarting'
				? 'Restarting...'
				: components.length
					? 'New update available'
					: !status
						? 'Checking for updates...'
						: 'Up to date';
	$: headingVersion = progressing
		? downloadVersion
		: heading === 'New update available'
			? neveVersion
			: null;
	async function refresh() {
		if (refreshBusy) return;
		refreshBusy = true;
		const revision = operation;
		try {
			const value = await updateRequest(localStorage.token, 'state');
			if (mounted && revision === operation) {
				if (value.status === 'completed' && job.status !== 'completed')
					void getVersionUpdates(localStorage.token).catch(() => {});
				job = value;
				stateReady = true;
			}
		} catch (error) {
			if (mounted && job.status !== 'restarting')
				job = { ...job, error: String(error.message || error) };
		} finally {
			refreshBusy = false;
		}
	}
	async function act() {
		if (busy || !stateReady || (job.status !== 'ready' && !eligible.length)) return;
		busy = true;
		operation++;
		try {
			const value = await updateRequest(
				localStorage.token,
				job.status === 'ready' ? 'restart' : 'download',
				eligible
			);
			job = { ...job, ...value };
		} catch (error) {
			toast.error(String(error.message || error));
		} finally {
			busy = false;
		}
	}
	onMount(() => {
		mounted = true;
		void refresh();
		void getVersionUpdates(localStorage.token).catch(() => {});
		const timer = setInterval(() => {
			if (!stateReady || ['downloading', 'restarting', 'applying'].includes(job.status))
				void refresh();
		}, 1000);
		return () => {
			mounted = false;
			clearInterval(timer);
		};
	});
</script>

<div id="tab-updates" class="space-y-5 pt-2 text-sm text-gray-700 dark:text-gray-100">
	<section
		class="overflow-hidden rounded-lg bg-gray-50/70 dark:bg-gray-800/25"
		aria-label={$i18n.t('Updates')}
	>
		<header
			class="flex min-h-[40px] items-center justify-between gap-3 px-4 py-3"
		>
			<div class="min-w-0">
			<h3 class="relative min-w-0 text-sm font-medium leading-5">
				{#if job.status === 'restarting'}
					<span class="invisible block" aria-hidden="true">{$i18n.t('Restart to apply changes')}</span>
					<span class="absolute inset-0">{$i18n.t(heading)}</span>
				{:else}
				{#if heading === 'Up to date'}<span class="mr-2 inline-flex align-middle"
						><Check className="size-4" /></span
					>{/if}{$i18n.t(heading)}{#if headingVersion}
					{' '}({headingVersion})
				{/if}
				{/if}
			</h3>
			{#each visibleComponents as component (component.id)}
				<div data-update-component={component.id} class="mt-0.5 flex min-w-0 flex-wrap items-baseline gap-x-2 text-gray-500 dark:text-gray-400">
					<span class="text-[13px] font-normal">{component.name}</span>
					<span class="break-all text-xs tabular-nums">{component.version}</span>
				</div>
			{/each}
			</div>
			{#if job.status === 'ready' || job.status === 'restarting' || (!locked && eligible.length > 0)}
				<button
					type="button"
					class="update-action grid size-8 shrink-0 place-items-center rounded-lg p-0 text-gray-500 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-gray-400 dark:hover:bg-gray-800 {job.status === 'restarting' ? 'invisible' : ''}"
					aria-label={$i18n.t(['ready', 'restarting'].includes(job.status) ? 'Restart' : 'Update now')}
					title={$i18n.t(['ready', 'restarting'].includes(job.status) ? 'Restart' : 'Update now')}
					aria-hidden={job.status === 'restarting' ? true : undefined}
					disabled={!stateReady || busy || job.status === 'restarting'}
					on:click={act}>{#if ['ready', 'restarting'].includes(job.status)}<Restart className="block size-5" />{:else}<Download className="block size-5" />{/if}</button
				>
			{/if}
		</header>
		{#if progressing}
			<div
				class="px-4 pb-3 pt-1"
				role="progressbar"
				aria-valuenow={job.progress || 0}
				aria-valuemin="0"
				aria-valuemax="100"
				aria-label={$i18n.t('Updates')}
			>
				<div class="h-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
					<div
						class="h-full rounded-full bg-blue-600 dark:bg-blue-500"
						style={`width:${job.progress || 0}%`}
					></div>
				</div>
				<div
					class="mt-2 flex items-start justify-between gap-3 text-xs text-gray-500 dark:text-gray-400"
				>
					<p data-update-phase class="min-w-0 break-words">{job.phase}</p>
					<span class="shrink-0 tabular-nums">{job.progress || 0}%</span>
				</div>
			</div>
		{/if}
		{#if job.error}<p role="alert" class="break-words text-xs text-red-600 dark:text-red-400">
				{job.error}
			</p>{/if}
	</section>
	<div>
		<div class="flex w-full items-center justify-between gap-4 py-0.5">
			<span
				id="update-notifications-label"
				class={!interfaceNotificationsEnabled($settings) ? 'text-gray-400 dark:text-gray-600' : ''}
				>{$i18n.t('Notify about new updates')}</span
			>
			<div class="shrink-0 p-1">
				<Switch
					ariaLabelledbyId="update-notifications-label"
					state={updateNotificationsEnabled($settings)}
					disabled={!interfaceNotificationsEnabled($settings)}
					on:change={(event) => {
						if (interfaceNotificationsEnabled($settings))
							saveSettings({ showUpdateToast: event.detail });
					}}
				/>
			</div>
		</div>
		<div class="flex w-full items-center justify-between gap-4 py-0.5">
			<span id="llama-updates-label">{$i18n.t('Receive llama.cpp updates')}</span>
			<div class="shrink-0 p-1">
				<Switch
					ariaLabelledbyId="llama-updates-label"
					state={llamaSwitch}
					disabled={!stateReady || locked || busy}
					on:change={(event) => saveSettings({ receiveLlamaUpdates: event.detail })}
				/>
			</div>
		</div>
	</div>
</div>
