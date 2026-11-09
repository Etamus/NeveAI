<script lang="ts">
	import { onMount, setContext, tick } from 'svelte';
	import { writable } from 'svelte/store';
	import i18next from 'i18next';
	import pt from '$lib/i18n/locales/pt-BR/translation.json';
	import { mobile, user, pinnedChats } from '$lib/stores';
	import ChatItem from '$lib/components/layout/Sidebar/ChatItem.svelte';
	import NeveUpdateToast from '$lib/components/chat/NeveUpdateToast.svelte';
	const i18n = i18next.createInstance();
	i18n.init({ lng: 'pt-BR', initImmediate: false, resources: { 'pt-BR': { translation: pt } } });
	setContext('i18n', writable(i18n));
	let version = 'NeveAI v3.1.83 • llama.cpp b12167';
	let opened = 0;
	onMount(() => {
		mobile.set(innerWidth < 768);
		user.set({ id: 'fixture', name: 'Fixture', role: 'admin' } as any);
		pinnedChats.set([{ id: 'pinned', title: 'Conversa fixada' }] as any);
		(window as any).__sidebarActions = {
			async version(value: string) { version = value; await tick(); },
			opened: () => opened
		};
		return () => { delete (window as any).__sidebarActions; };
	});
</script>

<div class="min-h-screen bg-white p-4 dark:bg-black">
	<div id="sidebar" class="w-[276px] text-sm">
		<ChatItem id="regular" title="Conversa normal" />
		<ChatItem id="pinned" title="Conversa fixada" />
		<div class="pl-4"><ChatItem id="project-chat" title="Conversa de projeto" /></div>
	</div>
	<div id="update-fixture" class="mt-12 flex justify-end">
		<NeveUpdateToast {version} onOpen={() => opened++} />
	</div>
</div>
