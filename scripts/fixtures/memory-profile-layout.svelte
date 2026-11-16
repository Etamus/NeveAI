<script lang="ts">
	import { onMount, setContext, tick } from 'svelte';
	import { writable } from 'svelte/store';
	import { user } from '$lib/stores';
	import ManageMemory from '$lib/components/chat/Settings/Personalization/ManageModal.svelte';
	import EditProfile from '$lib/components/layout/Sidebar/EditProfileModal.svelte';
	import ProjectModal from '$lib/components/layout/Sidebar/Folders/FolderModal.svelte';
	setContext('i18n', writable({ language: 'en-US', t: (text: string) => text }));
	user.set({ id: 'memory-layout-fixture', name: 'Test person', role: 'admin', email: 'test@example.test', profile_image_url: '' } as any);
	let manager, memory = false, profile = false, project = false;
	onMount(() => {
		(window as any).__smallUI = {
			async memories() { await manager.open(); await tick(); },
			async profile() { profile = true; await tick(); },
			async project() { project = true; await tick(); },
			async close() { memory = false; profile = false; project = false; await tick(); }
		};
		return () => delete (window as any).__smallUI;
	});
</script>
<ManageMemory bind:this={manager} bind:show={memory} />
<EditProfile bind:show={profile} />
<ProjectModal bind:show={project} onSubmit={(value) => { (window as any).__projectSubmit = value; }} />
