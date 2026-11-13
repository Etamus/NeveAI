export function isExecutableArtifactScript(value: string | null): boolean {
	const type = (value ?? '').split(';')[0].trim().toLowerCase();
	return (
		type === '' ||
		type === 'module' ||
		/^(?:text|application)\/(?:javascript|ecmascript|babel|jsx|tsx|typescript)$/.test(type)
	);
}
