<script lang="ts">
	export let className = 'size-3.5';
	export let pixelSize = 16;
	$: center = pixelSize / 2;
	$: top = Math.floor(pixelSize * 0.3) + 0.5;
	$: tip = top + center - 3.5;
	$: verticalOffset = center - (top + tip) / 2;
</script>

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pixelSize} {pixelSize}" fill="currentColor" class={className} aria-hidden="true">
	<path transform="translate(0 {verticalOffset})" d="M2.5 {top} 3.5 {top - 1} {center} {tip - 1} {pixelSize - 3.5} {top - 1} {pixelSize - 2.5} {top} {center} {tip + 1}Z" />
</svg>
