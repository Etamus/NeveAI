// Replacements share the document clock instead of restarting their rotation.
export function continuousSpinner(node: Element, enabled = true) {
	function sync(active: boolean) {
		if (!active) return;
		for (const animation of node.getAnimations({ subtree: true })) animation.startTime = 0;
	}
	sync(enabled);
	return { update: sync };
}
