const normalizedVersion = (value: unknown) =>
	typeof value === 'string' ? value.trim().replace(/^\uFEFF/, '').replace(/^v/i, '').toLowerCase() : '';

const newerVersion = (latest: unknown, current: unknown) => {
	const next = normalizedVersion(latest);
	const installed = normalizedVersion(current);
	if (!next || !installed || installed === '0.0.0') return false;
	if (!/^(?:b\d+|\d+(?:\.\d+)*(?:[-+][\da-z.-]+)?)$/.test(next) ||
		!/^(?:b\d+|\d+(?:\.\d+)*(?:[-+][\da-z.-]+)?)$/.test(installed)) return false;
	return installed.localeCompare(next, undefined, { numeric: true, sensitivity: 'case', caseFirst: 'upper' }) < 0;
};

export const getAvailableUpdateTargets = (data: any, currentVersion: string): string[] => {
	if (!data) return [];
	const targets: string[] = [];
	const latest = data.latest_tag ?? data.latest;
	if (data.neve_update_available !== false && newerVersion(latest, data.current_tag ?? data.current ?? currentVersion)) {
		targets.push(`NeveAI ${latest}`);
	}
	const llama = data.llama_cpp;
	const llamaLatest = llama?.latest_tag ?? llama?.latest;
	if (llama?.update_available === true && newerVersion(llamaLatest, llama.current_tag ?? llama.current)) {
		targets.push(`llama.cpp ${llamaLatest}`);
	}
	return targets;
};
