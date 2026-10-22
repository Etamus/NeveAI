export const getLastChatUsage = (history: any) => {
	let id = history?.currentId;
	const visited = new Set<string>();
	while (id && !visited.has(id)) {
		visited.add(id);
		const message = history?.messages?.[id];
		if (message?.role === 'assistant' && message.done && message.usage) {
			return message.usage;
		}
		id = message?.parentId;
	}
	return null;
};

export const getUsageContextWindow = (usage: any): number | null => {
	const value = Number(usage?.context_window);
	return Number.isFinite(value) && value > 0 ? value : null;
};

export const getChatContextWindow = (history: any): number | null => {
	let id = history?.currentId;
	const visited = new Set<string>();
	while (id && !visited.has(id)) {
		visited.add(id);
		const message = history?.messages?.[id];
		if (message?.role === 'assistant') {
			const context = getUsageContextWindow(message.usage) ?? getUsageContextWindow(message);
			if (context !== null) return context;
		}
		id = message?.parentId;
	}
	return null;
};

const tokenCount = (...values: unknown[]): number | null => {
	for (const value of values) {
		if (value === null || value === undefined || value === '') continue;
		const count = Number(value);
		if (Number.isFinite(count) && count >= 0) return count;
	}
	return null;
};

export const getUsageTotalTokens = (usage: any): number => {
	const input = tokenCount(usage?.prompt_tokens, usage?.input_tokens, usage?.prompt_n) ?? 0;
	const output = tokenCount(usage?.completion_tokens, usage?.output_tokens, usage?.predicted_n) ?? 0;
	const total = tokenCount(usage?.total_tokens);
	// Some providers send zero as an empty aggregate while retaining actual component counts.
	return total !== null && total > 0 ? total : input + output;
};

const speedNumber = (value: unknown): number | null => {
	if (typeof value !== 'number' && typeof value !== 'string') return null;
	if (typeof value === 'string' && !value.trim()) return null;
	const number = typeof value === 'string' ? Number(value.replace(',', '.')) : value;
	return Number.isFinite(number) && number >= 0 ? number : null;
};

export const getUsageTokensPerSecond = (usage: any): number | null => {
	if (!usage) return null;
	for (const key of [
		'tokens_per_second', 'output_tokens_per_second', 'completion_tokens_per_second',
		'response_tokens_per_second', 'response_token/s', 'tokens/s',
		'predicted_per_second', 'eval_per_second'
	]) {
		const value = speedNumber(usage[key]);
		if (value !== null) return value;
	}
	const output = speedNumber(
		usage.output_tokens ?? usage.completion_tokens ?? usage.eval_count ?? usage.predicted_n
	);
	if (output === null) return null;
	const nanoseconds = speedNumber(usage.eval_duration);
	if (nanoseconds && nanoseconds > 0) return output / (nanoseconds / 1_000_000_000);
	const milliseconds = speedNumber(usage.predicted_ms);
	return milliseconds && milliseconds > 0 ? output / (milliseconds / 1000) : null;
};

export const formatUsageTokensPerSecond = (value: number | null): string =>
	value !== null && Number.isFinite(value) && value >= 0 ? value.toFixed(0) : '0';
