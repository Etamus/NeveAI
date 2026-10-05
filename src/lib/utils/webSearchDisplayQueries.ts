const supplementalSearchSuffix = /\s+(?:fontes oficiais documenta[c\u00e7][a\u00e3]o|an[a\u00e1]lise independente limita[c\u00e7][o\u00f5]es|official sources documentation|independent analysis limitations)\s*$/i;

function conciseSearchLabel(query: string): string {
	// Existing chats may contain the original long question rather than a planned query.
	if (query.length < 90 || /https?:\/\/|["\u201c\u201d]/.test(query)) return query;
	return query
		.replace(/^(?:dado|considerando) (?:o cen[a\u00e1]rio|a situa[c\u00e7][a\u00e3]o)(?: atual)? (?:do|da|de)\s+|^given (?:the )?(?:current )?(?:situation|scenario) (?:of|with)\s+/i, '')
		.replace(/(?:^|,\s*)(?:qual|quais) (?:[e\u00e9]|seria|seriam|s[a\u00e3]o) (?:a|as|o|os) (?:melhor|melhores) (?:forma|formas|maneira|maneiras) (?:de|para)\s+|(?:^|,\s*)what (?:is|would be) the best way to\s+/gi, ' ')
		.replace(/\s+(?:em geral|in general)[?.!]*$/i, '')
		.replace(/\s+/g, ' ').replace(/^[ ,?.!]+|[ ,?.!]+$/g, '') || query;
}

export function getWebSearchDisplayQueries(queries: unknown, deep: boolean): string[] {
	if (!Array.isArray(queries)) return [];
	const seen = new Set<string>();
	return queries.flatMap((query) => {
		if (typeof query !== 'string' || !query.trim()) return [];
		const original = query.trim();
		const display = conciseSearchLabel(deep ? original.replace(supplementalSearchSuffix, '').trim() || original : original);
		const key = display.toLocaleLowerCase();
		if (seen.has(key)) return [];
		seen.add(key);
		return [display];
	});
}
