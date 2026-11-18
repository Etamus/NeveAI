<script context="module" lang="ts">
	import type { Group } from 'three';
	export type ViewMode = 'textured' | 'solid' | 'wire' | 'normals' | 'skeleton';
	type Asset = {model: Group; bytes: number; release: () => void};
	const idle = new Map<string, { asset: Asset; timer: ReturnType<typeof setTimeout> }>();
	const limit = 64 * 1024 * 1024;
	let bytes = 0;
	function take(key: string) {
		const entry = idle.get(key);
		if (!entry) return;
		clearTimeout(entry.timer);
		idle.delete(key);
		bytes -= entry.asset.bytes;
		return entry.asset;
	}
	function retain(key: string, asset: Asset) {
		take(key)?.release();
		if (asset.bytes > limit) { asset.release(); return; }
		while (idle.size && (bytes + asset.bytes > limit || idle.size >= 2)) take(idle.keys().next().value!)?.release();
		bytes += asset.bytes;
		idle.set(key, {asset, timer: setTimeout(() => take(key)?.release(), 30000)});
	}
</script>

<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';
	import type { I18nStore } from '$lib/i18n';
	import OrbitingSpheres from './OrbitingSpheres.svelte';
	import { DropdownMenu } from 'bits-ui';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';

	export let id: string;
	export let mode: ViewMode = 'textured';
	const labels = { textured: 'Textured', solid: 'Solid surface', wire: 'Wireframe', normals: 'Surface normals', skeleton: 'Skeleton' };
	let hasSkeleton = false;
	let updateView: ((mode: ViewMode) => void) | undefined;
	$: updateView?.(mode);
	let canvas: HTMLCanvasElement;
	let error = false;
	let loading = true;
	const i18n = getContext<I18nStore>('i18n');

	onMount(() => {
		const controller = new AbortController();
		const cleanup: (() => void)[] = [];
		const token = localStorage.token ?? '';
		const keyId = JSON.stringify([token, id]);
		const disposed = () => controller.signal.aborted;
		void (async () => {
			try {
				const [THREE, { OrbitControls }, { GLTFLoader }] = await Promise.all([
					import('three'), import('three/addons/controls/OrbitControls.js'),
					import('three/addons/loaders/GLTFLoader.js')
				]);
				if (disposed()) return;
				const load = async (): Promise<Asset> => {
					const response = await fetch(`${NEVEAI_API_BASE_URL}/files/${encodeURIComponent(id)}/content`, {
						signal: controller.signal, headers: {Authorization: `Bearer ${token}`}
					});
					if (!response.ok) throw new Error('GLB unavailable');
					const {scene: model} = await new GLTFLoader().parseAsync(await response.arrayBuffer(), '');
					function release() {
						const textures = new Set<InstanceType<typeof THREE.Texture>>();
						model.traverse(object => {
							if (!(object instanceof THREE.Mesh)) return;
							object.geometry.dispose();
							for (const material of [object.material].flat()) {
								for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value);
								material.dispose();
							}
						});
						for (const texture of textures) {
							texture.dispose();
							if (typeof ImageBitmap !== 'undefined' && texture.image instanceof ImageBitmap) texture.image.close();
						}
					}
					let size = 0;
					const textures = new Set<InstanceType<typeof THREE.Texture>>();
					model.traverse(obj => {
						if (!(obj instanceof THREE.Mesh)) return;
						for (const attr of Object.values(obj.geometry.attributes) as {array: {byteLength: number}}[]) size += attr.array.byteLength;
						size += obj.geometry.index?.array.byteLength ?? 0;
						for (const material of [obj.material].flat()) for (const value of Object.values(material))
							if (value instanceof THREE.Texture) textures.add(value);
					});
					for (const tex of textures) {
						const image = tex.image as {width?: number; height?: number} | null;
						size += (image?.width || 0) * (image?.height || 0) * 4;
					}
					return {model, bytes:size, release};
				};
				const asset = take(keyId) ?? await load();
				if (disposed()) { asset.release(); return; }
				const {model} = asset;
				cleanup.push(() => { model.removeFromParent(); retain(keyId, asset); });
				const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
				cleanup.push(() => { renderer.dispose(); renderer.forceContextLoss(); });
				renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
				const scene = new THREE.Scene();
				scene.add(model, new THREE.HemisphereLight(0xffffff, 0x80859a, 2));
				const key = new THREE.DirectionalLight(0xffffff, 3);
				key.position.set(3, 5, 4);
				scene.add(key);
				const bounds = new THREE.Box3().setFromObject(model);
				const center = bounds.getCenter(new THREE.Vector3());
				const radius = bounds.getBoundingSphere(new THREE.Sphere()).radius || 1;
				const camera = new THREE.PerspectiveCamera(38, 1, radius / 100, radius * 100);
				camera.position.copy(center).addScaledVector(new THREE.Vector3(.55, .33, 1).normalize(), radius * 3.6);
				const controls = new OrbitControls(camera, canvas);
				cleanup.push(() => controls.dispose());
				// OrbitControls handles zoom; don't send the same wheel gesture to the chat.
				const containWheel = (event: WheelEvent) => {
					event.preventDefault();
					event.stopPropagation();
				};
				canvas.addEventListener('wheel', containWheel, { passive: false });
				cleanup.push(() => canvas.removeEventListener('wheel', containWheel));
				controls.target.copy(center);
				controls.minDistance = radius * .2;
				controls.maxDistance = radius * 15;
				const render = () => renderer.render(scene, camera);
				const meshes: InstanceType<typeof THREE.Mesh>[] = [];
				model.traverse(obj => {
					if (obj instanceof THREE.Mesh) meshes.push(obj);
					if (obj instanceof THREE.Bone && obj.parent instanceof THREE.Bone) hasSkeleton = true;
				});
				const originals = meshes.map(mesh => mesh.material);
				const solid = new THREE.MeshStandardMaterial({ color: 0xc3c8ce, roughness: 0.9, side: THREE.DoubleSide });
				const wire = new THREE.MeshBasicMaterial({ color: 0x618fc7, wireframe: true });
				const normals = new THREE.MeshNormalMaterial({ side: THREE.DoubleSide });
				// Pixal3D can export only positions and UVs. Use face derivatives
				// for inspection instead of shading those surfaces with zero normals.
				const flatSolid = solid.clone();
				const flatNormals = normals.clone();
				flatSolid.flatShading = flatNormals.flatShading = true;
				let bones: InstanceType<typeof THREE.SkeletonHelper> | undefined;
				const applyView = (selected: ViewMode) => {
					if (selected === 'skeleton' && hasSkeleton && !bones) {
						bones = new THREE.SkeletonHelper(model);
						bones.renderOrder = 1;
						scene.add(bones);
					}
					if (bones) bones.visible = selected === 'skeleton';
					meshes.forEach((mesh, i) => {
						const smooth = !!mesh.geometry.getAttribute('normal');
						mesh.material = selected === 'wire' ? wire : selected === 'normals' ? (smooth ? normals : flatNormals) :
							selected === 'solid' || selected === 'skeleton' ? (smooth ? solid : flatSolid) : originals[i];
					});
					render();
				};
				updateView = applyView;
				cleanup.push(() => {
					updateView = undefined;
					meshes.forEach((mesh, i) => { mesh.material = originals[i]; });
					bones?.dispose();
					solid.dispose(); wire.dispose(); normals.dispose(); flatSolid.dispose(); flatNormals.dispose();
				});
				controls.addEventListener('change', render);
				const resize = () => {
					const { clientWidth: width, clientHeight: height } = canvas;
					if (!width || !height) return;
					renderer.setSize(width, height, false);
					camera.aspect = width / height;
					camera.updateProjectionMatrix();
					render();
				};
				const observer = new ResizeObserver(resize);
				observer.observe(canvas);
				cleanup.push(() => observer.disconnect());
				controls.update();
				resize();
			} catch {
				if (!disposed()) error = true;
			} finally {
				if (!disposed()) loading = false;
			}
		})();
		return () => { controller.abort(); cleanup.reverse().forEach(dispose => dispose()); };
	});
</script>

<div class="relative size-full">
	<canvas bind:this={canvas} class="block size-full touch-none" aria-label={$i18n.t('3D preview')}></canvas>
	{#if !loading && !error}
		<div class="absolute top-2 left-2">
			<DropdownMenu.Root portal={null} preventScroll={false}>
				<DropdownMenu.Trigger data-mesh-view aria-label={`${$i18n.t('Display mode')}: ${$i18n.t(labels[mode])}`}
					class="flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[0.79rem] font-normal text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800">
					{$i18n.t(labels[mode])}<ChevronDown className="size-3" />
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="start" sideOffset={4} strategy="fixed" class="z-[10002] min-w-32 rounded-md border border-gray-100 bg-white p-1 text-sm shadow-md dark:border-gray-800 dark:bg-gray-850">
					<DropdownMenu.RadioGroup bind:value={mode}>
						{#each Object.entries(labels) as [value, name]}
							{#if value !== 'skeleton' || hasSkeleton}
								<DropdownMenu.RadioItem {value} class="flex cursor-pointer items-center justify-between gap-3 rounded-sm px-2.5 py-1.5 outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800">
									{$i18n.t(name)}{#if value === mode}<CheckCircle className="size-4" />{/if}
								</DropdownMenu.RadioItem>
							{/if}
						{/each}
					</DropdownMenu.RadioGroup>
				</DropdownMenu.Content>
			</DropdownMenu.Root>
		</div>
	{/if}
	{#if loading || error}<div class="pointer-events-none absolute inset-0 grid place-items-center px-4 text-center text-sm text-gray-500" role="status">
		{#if error}{$i18n.t('Unable to open 3D preview')}{:else}
			<span class="sr-only">{$i18n.t('Loading...')}</span><OrbitingSpheres className="size-5" />
		{/if}
	</div>{/if}
</div>
