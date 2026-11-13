export function mappedArtifactImport(
	specifier: string,
	imports: Record<string, string> = {}
): string {
	if (Object.prototype.hasOwnProperty.call(imports, specifier)) return imports[specifier];
	const prefix = Object.keys(imports)
		.filter((key) => key.endsWith('/') && specifier.startsWith(key))
		.sort((a, b) => b.length - a.length)[0];
	return prefix ? imports[prefix] + specifier.slice(prefix.length) : specifier;
}
