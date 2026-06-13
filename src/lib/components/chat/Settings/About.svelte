<script lang="ts">
	import { onMount } from 'svelte';
	import Github from '$lib/components/icons/Github.svelte';
	import Document from '$lib/components/icons/Document.svelte';

	let projectVersion = '...';
	const githubUrl = 'https://github.com/Etamus/NeveAI';
	const huggingFaceUrl = 'https://huggingface.co/NeveAI';
	const licenseUrl = 'https://github.com/Etamus/NeveAI/blob/main/LICENSE.txt';
	let versionRefreshInterval: ReturnType<typeof setInterval>;

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
		}
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
		versionRefreshInterval = setInterval(loadProjectVersion, 5000);

		return () => {
			clearInterval(versionRefreshInterval);
		};
	});
</script>

<div id="tab-about" class="flex flex-col gap-5 text-sm text-gray-700 dark:text-gray-200">
	<section class="space-y-1.5">
		<div class="text-sm font-medium text-gray-900 dark:text-white">Versão</div>
		<div class="text-sm text-gray-600 dark:text-gray-300">{projectVersion}</div>
	</section>

	<section class="space-y-1.5">
		<div class="text-sm font-medium text-gray-900 dark:text-white">Neve AI</div>
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
				<Document className="size-4" />
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
			<Document className="size-4" />
			<span>Licença</span>
		</a>
	</section>
</div>
