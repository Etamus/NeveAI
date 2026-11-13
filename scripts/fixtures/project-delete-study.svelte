<script>
	import RecursiveFolder from '$lib/components/layout/Sidebar/RecursiveFolder.svelte';
	const folders = { project: { id: 'project', name: 'Projeto de teste', childrenIds: [], is_expanded: false } };
</script>
<main class="p-6"><RecursiveFolder {folders} folderId="project" /></main>
