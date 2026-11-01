<script lang="ts">
	import { onMount, setContext, tick } from 'svelte';
	import { writable } from 'svelte/store';
	import UnifiedModels from '../../src/lib/components/chat/UnifiedModels.svelte';
	import Modal from '../../src/lib/components/common/Modal.svelte';
	import { applyModelAvailability } from '../../src/lib/stores/modelAvailability';
	import { models, mobile } from '../../src/lib/stores';
	setContext('i18n', writable({ language: 'en-US', t: (text: string) => text }));
	let show = false;
	const local = ['Alpha', 'Beta', 'Gamma'].map((name, i) => ({
		id: `local/${name}`, filename: `${name}.gguf`, file_size: 1000000000, file_size_human: '1 GB',
		is_loaded: i === 0, loaded_at: 100, n_ctx: 8192, n_gpu_layers: -1, cache_type: 'q8_0',
		mmproj_filename: '', speculative_decoding: 'off', token_prediction: 'off', context_shift: 'off'
	}));
	const admin = local.map(model => ({ id: model.id, name: model.filename.replace('.gguf', ''), is_active: true, meta: {} }));
	const preload = { loaded: true, runtimeUpdatedAt: 1, localModels: local, mmProjFiles: [],
		adminModels: admin, workspaceModels: admin, baseModels: admin,
		vramInfo: { available: true, source: 'nvidia-smi', total: 17179869184,
			used: 4294967296, free: 12884901888, total_human: '16 GB',
			used_human: '4 GB', free_human: '12 GB', gpus: [] } };
	onMount(() => {
		models.set(admin as any);
		mobile.set(innerWidth < 768);
		(window as any).__availabilityFixture = {
			async event(value: any) { applyModelAvailability(value); await tick(); },
			async open() { show = true; await tick(); },
			async close() { show = false; await tick(); },
			local
		};
		return () => { delete (window as any).__availabilityFixture; };
	});
</script>
<button id="open-models" on:click={() => show = true}>Models</button>
<Modal bind:show keepMounted animated={false} size="md">
	<UnifiedModels {show} {preload} />
</Modal>
