<script lang="ts">
	export let compact = false;
	export let className = '';
</script>

<!-- Adapted from shadcnloaders.com, Orbiting Spheres. See shadcn-loaders-LICENSE.txt. -->
<span class="orbiting-spheres text-zinc-950 dark:text-zinc-50 {className}" class:compact class:standalone={!className} aria-hidden="true">
	<span class="orbiting-container"><span class="orbiting-dot"></span><span class="orbiting-dot"></span></span>
</span>

<style>
	.orbiting-spheres { --size: 20px; display: inline-block; flex-shrink: 0; }
	.standalone { width: var(--size); height: var(--size); margin: 0 4px; }
	.compact { --size: 16px; }
	.orbiting-container { position: relative; display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; animation: rotate-container 2.5s infinite linear; }
	.orbiting-dot { position: absolute; width: 40%; height: 40%; border-radius: 50%; background-color: currentColor; animation: orbit-motion 1.5s linear infinite; }
	.orbiting-dot:nth-child(2) { animation-delay: -0.75s; }
	@keyframes rotate-container { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
	@keyframes orbit-motion {
		0%, 100% { transform: translateX(62.5%) scale(0.73684); opacity: 0.65; }
		5% { transform: translateX(58.75%) scale(0.684208); opacity: 0.58; }
		10% { transform: translateX(45.5%) scale(0.631576); opacity: 0.51; }
		15% { transform: translateX(32.25%) scale(0.578944); opacity: 0.44; }
		20% { transform: translateX(19%) scale(0.526312); opacity: 0.37; }
		25% { transform: translateX(0%) scale(0.47368); opacity: 0.3; }
		30% { transform: translateX(-19%) scale(0.526312); opacity: 0.37; }
		35% { transform: translateX(-32.25%) scale(0.578944); opacity: 0.44; }
		40% { transform: translateX(-45.5%) scale(0.631576); opacity: 0.51; }
		45% { transform: translateX(-58.75%) scale(0.684208); opacity: 0.58; }
		50% { transform: translateX(-62.5%) scale(0.73684); opacity: 0.65; }
		55% { transform: translateX(-58.75%) scale(0.789472); opacity: 0.72; }
		60% { transform: translateX(-45.5%) scale(0.842104); opacity: 0.79; }
		65% { transform: translateX(-32.25%) scale(0.894736); opacity: 0.86; }
		70% { transform: translateX(-19%) scale(0.947368); opacity: 0.93; }
		75% { transform: translateX(0%) scale(1); opacity: 1; }
		80% { transform: translateX(19%) scale(0.947368); opacity: 0.93; }
		85% { transform: translateX(32.25%) scale(0.894736); opacity: 0.86; }
		90% { transform: translateX(45.5%) scale(0.842104); opacity: 0.79; }
		95% { transform: translateX(58.75%) scale(0.789472); opacity: 0.72; }
	}
</style>
