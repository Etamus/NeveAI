<script lang="ts" context="module">
	let cachedUpdateAvailable = false;
	let cachedLatestProjectVersion = '';
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';
	import { getVersionUpdates, startAppUpdater } from '$lib/apis';
	import Github from '$lib/components/icons/Github.svelte';
	import HuggingFace from '$lib/components/icons/HuggingFace.svelte';
	import Scale from '$lib/components/icons/Scale.svelte';
	import { NEVEAI_VERSION, user } from '$lib/stores';
	import { compareVersion } from '$lib/utils';
	import bundledProjectVersion from '../../../../../version.txt?raw';

	let projectVersion = get(NEVEAI_VERSION) || bundledProjectVersion.trim();
	const githubUrl = 'https://github.com/Etamus/NeveAI';
	const huggingFaceUrl = 'https://huggingface.co/NeveAI';
	const licenseUrl = 'https://github.com/Etamus/NeveAI/blob/main/LICENSE.txt';
	let versionRefreshInterval: ReturnType<typeof setInterval>;
	let updateRefreshInterval: ReturnType<typeof setInterval>;
	let updateAvailable = cachedUpdateAvailable;
	let latestProjectVersion = cachedLatestProjectVersion;
	let startingUpdater = false;

	$: if ($NEVEAI_VERSION && $NEVEAI_VERSION !== projectVersion) {
		projectVersion = $NEVEAI_VERSION;
	}

	const loadProjectVersion = async () => {
		const version = await fetch(`/api/version?t=${Date.now()}`, {
			cache: 'no-store'
		})
			.then(async (res) => {
				if (!res.ok) {
					throw new Error('Failed to load version');
				}

				const data = await res.json();
				return typeof data?.version === 'string' ? data.version.trim() : '';
			})
			.catch(() => '');

		if (version) {
			projectVersion = version;
			NEVEAI_VERSION.set(version);
		}
	};

	const checkForUpdateStatus = async () => {
		if ($user?.role !== 'admin') {
			updateAvailable = false;
			cachedUpdateAvailable = false;
			cachedLatestProjectVersion = '';
			return;
		}

		const data = await getVersionUpdates(localStorage.token).catch(() => null);
		if (!data) {
			updateAvailable = false;
			cachedUpdateAvailable = false;
			cachedLatestProjectVersion = '';
			return;
		}

		const current = typeof data?.current === 'string' ? data.current : projectVersion;
		const latest =
			typeof data?.latest_tag === 'string'
				? data.latest_tag
				: typeof data?.latest === 'string'
					? data.latest
					: '';
		const llamaCpp = data?.llama_cpp ?? null;
		const llamaLatest =
			typeof llamaCpp?.latest_tag === 'string'
				? llamaCpp.latest_tag
				: typeof llamaCpp?.latest === 'string'
					? llamaCpp.latest
					: '';
		const projectUpdateAvailable =
			typeof data?.neve_update_available === 'boolean'
				? data.neve_update_available
				: latest
					? compareVersion(latest, current)
					: false;
		const llamaUpdateAvailable =
			typeof llamaCpp?.update_available === 'boolean' ? llamaCpp.update_available : false;
		const pendingTargets: string[] = [];

		if (projectUpdateAvailable) {
			pendingTargets.push(latest ? `NeveAI ${latest}` : 'NeveAI');
		}

		if (llamaUpdateAvailable) {
			pendingTargets.push(llamaLatest ? `llama.cpp ${llamaLatest}` : 'llama.cpp');
		}

		latestProjectVersion = pendingTargets.join(' e ');
		updateAvailable = projectUpdateAvailable || llamaUpdateAvailable;
		cachedLatestProjectVersion = latestProjectVersion;
		cachedUpdateAvailable = updateAvailable;
	};

	const startUpdate = async () => {
		if (startingUpdater) {
			return;
		}

		startingUpdater = true;
		const started = await startAppUpdater(localStorage.token).catch(() => false);

		if (started) {
			startingUpdater = false;
			toast.success('Atualizador aberto.');
			return;
		}

		startingUpdater = false;
		toast.error('Falha ao abrir o atualizador.');
	};

	const openExternalUrl = async (url: string) => {
		const opened = await fetch('/api/external/open', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...(localStorage.token ? { Authorization: `Bearer ${localStorage.token}` } : {})
			},
			body: JSON.stringify({ url })
		})
			.then((res) => res.ok)
			.catch(() => false);

		if (!opened) {
			window.open(url, '_blank', 'noopener,noreferrer');
		}
	};

	onMount(() => {
		loadProjectVersion();
		checkForUpdateStatus();
		versionRefreshInterval = setInterval(loadProjectVersion, 5000);
		updateRefreshInterval = setInterval(checkForUpdateStatus, 60000);

		return () => {
			clearInterval(versionRefreshInterval);
			clearInterval(updateRefreshInterval);
		};
	});
</script>

<div id="tab-about" class="flex flex-col gap-5 text-sm text-gray-700 dark:text-gray-200">
	<section class="space-y-1.5">
		<div class="text-sm font-medium text-gray-900 dark:text-white">Versão</div>
		<div class="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-300">
			<span>{projectVersion}</span>
			{#if updateAvailable}
				<button
					type="button"
					class="bg-transparent p-0 text-sm font-medium text-gray-700 transition-opacity hover:opacity-60 disabled:cursor-default disabled:opacity-60 dark:text-gray-200"
					aria-label={latestProjectVersion
						? `Atualizar NeveAI para ${latestProjectVersion}`
						: 'Atualizar NeveAI'}
					disabled={startingUpdater}
					on:click={startUpdate}
				>
					{startingUpdater ? 'Abrindo...' : 'Atualizar'}
				</button>
			{/if}
		</div>
	</section>

	<section class="space-y-1.5">
		<div class="text-sm font-medium text-gray-900 dark:text-white">NeveAI</div>
		<p class="text-sm leading-6 text-gray-600 dark:text-gray-300">
			Copyright © 2026 Mateus Lopes<br />
			Todos os direitos reservados.
		</p>
	</section>

	<section class="space-y-2">
		<div class="text-sm font-medium text-gray-900 dark:text-white">Repositórios</div>
		<div class="flex flex-col gap-2">
			<a
				class="inline-flex items-center gap-2 text-sm text-gray-600 underline-offset-2 hover:underline dark:text-gray-300"
				href={githubUrl}
				target="_blank"
				rel="noreferrer"
				on:click|preventDefault={() => openExternalUrl(githubUrl)}
			>
				<Github className="size-4" />
				<span>GitHub</span>
			</a>

			<a
				class="inline-flex items-center gap-2 text-sm text-gray-600 underline-offset-2 hover:underline dark:text-gray-300"
				href={huggingFaceUrl}
				target="_blank"
				rel="noreferrer"
				on:click|preventDefault={() => openExternalUrl(huggingFaceUrl)}
			>
				<HuggingFace className="size-4" />
				<span>Hugging Face</span>
			</a>
		</div>
	</section>

	<section class="space-y-2">
		<div class="text-sm font-medium text-gray-900 dark:text-white">Informações Legais</div>
		<a
			class="inline-flex items-center gap-2 text-sm text-gray-600 underline-offset-2 hover:underline dark:text-gray-300"
			href={licenseUrl}
			target="_blank"
			rel="noreferrer"
			on:click|preventDefault={() => openExternalUrl(licenseUrl)}
		>
			<Scale className="size-4" strokeWidth="1.6" />
			<span>Licença</span>
		</a>
	</section>
</div>
