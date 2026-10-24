// Histories are mutated in place, so reference equality alone cannot detect updates.
// Compare values without serializing unchanged message text or attachment payloads.
export function messageSnapshotEqual(snapshot: unknown, source: unknown): boolean {
	if (Object.is(snapshot, source)) return true;
	if (
		snapshot === null || source === null ||
		typeof snapshot !== 'object' || typeof source !== 'object'
	) return false;
	if (Array.isArray(snapshot) !== Array.isArray(source)) return false;
	if (Array.isArray(snapshot) && Array.isArray(source) && snapshot.length !== source.length) return false;
	if (snapshot instanceof Date || source instanceof Date) {
		return snapshot instanceof Date && source instanceof Date &&
			Object.is(snapshot.getTime(), source.getTime());
	}
	const left = snapshot as Record<string, unknown>;
	const right = source as Record<string, unknown>;
	const keys = Object.keys(right);
	if (Object.keys(left).length !== keys.length) return false;
	for (const key of keys) {
		if (!Object.prototype.hasOwnProperty.call(left, key) ||
			!messageSnapshotEqual(left[key], right[key])) return false;
	}
	return true;
}
