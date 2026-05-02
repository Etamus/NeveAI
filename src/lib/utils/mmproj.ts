const normalizeMmprojName = (filename: string): string => {
	const baseName = (filename.split(/[\\/]/).pop() ?? filename)
		.replace(/\.[^.]+$/, '')
		.normalize('NFD')
		.replace(/[\u0300-\u036f]/g, '')
		.toLowerCase();

	return baseName
		.replace(/(^|[\s._-]+)mmproj([\s._-].*)?$/i, '')
		.replace(/^mmproj[\s._-]*/i, '')
		.replace(/[\s._-]+model$/i, '')
		.replace(/[\s._-]+(?:u?d?q\d[\w.-]*|q\d[\w.-]*|f\d+|bf\d+|fp\d+)$/i, '')
		.replace(/[^a-z0-9]+/g, '');
};

export const findMatchingMmproj = (modelFilename: string, mmProjFiles: string[]): string | null => {
	const modelName = normalizeMmprojName(modelFilename);
	if (!modelName) return null;

	let bestMatch: string | null = null;
	let bestScore = 0;

	for (const mmprojFile of mmProjFiles) {
		const mmprojName = normalizeMmprojName(mmprojFile);
		if (!mmprojName) continue;

		if (modelName.startsWith(mmprojName) || mmprojName.startsWith(modelName)) {
			const score = Math.min(modelName.length, mmprojName.length);
			if (score > bestScore) {
				bestMatch = mmprojFile;
				bestScore = score;
			}
		}
	}

	return bestMatch;
};