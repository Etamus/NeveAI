<script lang="ts">
	import Github from '$lib/components/icons/Github.svelte';
	import { splitGitHubRepositoryLinks } from '$lib/utils/github';

	export let content = '';

	$: segments = splitGitHubRepositoryLinks(content);

	const openExternalUrl = async (event: MouseEvent, url: string) => {
		event.preventDefault();

		const opened = await fetch('/api/external/open', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...(localStorage.token ? { Authorization: `Bearer ${localStorage.token}` } : {})
			},
			body: JSON.stringify({ url })
		})
			.then((response) => response.ok)
			.catch(() => false);

		if (!opened) {
			window.open(url, '_blank', 'noopener,noreferrer');
		}
	};
</script>

{#each segments as segment}
	{#if segment.type === 'repository'}
		<a
			href={segment.url}
			target="_blank"
			rel="noopener noreferrer"
			class="github-repository-chat-link max-w-full rounded-md bg-black/5 px-1.5 text-current underline decoration-gray-400/70 underline-offset-2 transition-colors hover:bg-black/10 dark:bg-white/10 dark:decoration-gray-500 dark:hover:bg-white/15"
			aria-label={`Abrir repositório ${segment.label} no GitHub`}
			on:click={(event) => openExternalUrl(event, segment.url)}
		>
			<Github className="github-repository-chat-icon size-3.5" />
			<span class="break-all font-normal">{segment.label}</span>
		</a>
	{:else}{segment.value}{/if}
{/each}

<style>
	.github-repository-chat-link {
		display: inline-block;
		font-family: inherit;
		font-size: inherit;
		font-weight: 400;
		line-height: inherit;
		vertical-align: baseline;
	}

	:global(.github-repository-chat-icon) {
		display: inline-block;
		margin-right: 0.375rem;
		vertical-align: -0.125rem;
	}
</style>
