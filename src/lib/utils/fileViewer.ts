export function truncateFileName(name: string, limit = 44): string {
	if (name.length <= limit) return name;

	const extensionStart = name.lastIndexOf('.');
	const extension =
		extensionStart > 0 && name.length - extensionStart <= 10 ? name.slice(extensionStart) : '';
	const suffix = `...${extension}`;

	return `${name.slice(0, Math.max(1, limit - suffix.length))}${suffix}`;
}
