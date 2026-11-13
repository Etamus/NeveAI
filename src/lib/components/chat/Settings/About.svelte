<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import Github from '$lib/components/icons/Github.svelte';
	import HuggingFace from '$lib/components/icons/HuggingFace.svelte';
	import Scale from '$lib/components/icons/Scale.svelte';
	import { NEVEAI_VERSION } from '$lib/stores';
	import bundledProjectVersion from '../../../../../version.txt?raw';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');
	let projectVersion = get(NEVEAI_VERSION) || bundledProjectVersion.trim();
	const githubUrl = 'https://github.com/Etamus/NeveAI';
	const huggingFaceUrl = 'https://huggingface.co/NeveAI';
	const licenseUrl = 'https://github.com/Etamus/NeveAI/blob/main/LICENSE.txt';
	$: if ($NEVEAI_VERSION) projectVersion = $NEVEAI_VERSION;
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
		void fetch('/api/version', {cache: 'no-store'}).then(r => r.ok ? r.json() : null).then(data => {
			if(data?.version) NEVEAI_VERSION.set(data.version);
		}).catch(() => {});
	});
</script>

<div id="tab-about" class="flex flex-col gap-3 pt-2 text-sm text-gray-700 dark:text-gray-100">
	<section class="space-y-1.5">
		<div class="text-sm font-medium">{$i18n.t('Version')}</div>
		<div class="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-300">
			<span>{projectVersion}</span>
		</div>
	</section>

	<section class="space-y-1.5">
		<div class="text-sm font-medium">NeveAI</div>
		<p class="text-sm leading-6 text-gray-600 dark:text-gray-300">
			Copyright © 2026 Mateus Lopes<br />
			{$i18n.t('All rights reserved.')}
		</p>
	</section>

	<section class="space-y-2">
		<div class="text-sm font-medium">{$i18n.t('Repositories')}</div>
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
		<div class="text-sm font-medium">{$i18n.t('Legal Information')}</div>
		<a
			class="inline-flex items-center gap-2 text-sm text-gray-600 underline-offset-2 hover:underline dark:text-gray-300"
			href={licenseUrl}
			target="_blank"
			rel="noreferrer"
			on:click|preventDefault={() => openExternalUrl(licenseUrl)}
		>
			<Scale className="size-4" strokeWidth="1.6" />
			<span>{$i18n.t('License')}</span>
		</a>
	</section>
</div>
