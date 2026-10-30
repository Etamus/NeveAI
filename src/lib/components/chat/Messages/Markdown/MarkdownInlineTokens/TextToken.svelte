<script lang="ts">
	import { getContext } from 'svelte';
	import type { StreamingPaintContext } from '$lib/utils/marked/streaming-structure';
	import { streamingTextFade } from '$lib/utils/streamingTextFade';
	import { stableStreamingText } from '$lib/utils/stableStreamingText';

	export let token;
	export let done = true;
	const initialText = token?.raw ?? '';
	const paintContext = getContext<StreamingPaintContext>('streaming-text-paint');

</script>

<span use:stableStreamingText={token?.raw ?? ''} use:streamingTextFade={{ text: token?.raw ?? '', done, paintContext }}>{initialText}</span>
