export const IMAGE_MODES = [
	{ id: 'normal', label: 'Padrão', image: '' },
	{ id: 'restore', label: 'Aprimorar', image: '/static/aprimorar.webp' },
	{ id: 'outpaint', label: 'Expandir', image: '/static/expandir.webp' },
	{ id: 'inpaint', label: 'Trocar objetos', image: '/static/trocarobjetos.webp' },
	{ id: 'outfit', label: 'Trocar roupas', image: '/static/trocarroupas.webp' },
	{ id: 'body', label: 'Trocar pessoas', image: '/static/trocarpessoas.webp' }
] as const;
export type ImageMode = typeof IMAGE_MODES[number]['id'];
export type ImageModeOptions = {
	mode: ImageMode;
	strength?: number;
	auto_prompt?: boolean;
	mask?: string | null;
	source_id?: string;
	grow?: number;
	feather?: number;
	rotation?: number;
	pad_left?: number;
	pad_right?: number;
	pad_top?: number;
	pad_bottom?: number;
	crop?: [number, number, number, number] | null;
	reference_crops?: ([number, number, number, number] | null)[];
	target?: string;
	reference_labels?: string[];
};
export const imageModeDefaults = (mode: ImageMode = 'normal'): ImageModeOptions => ({
	mode, strength: mode === 'restore' ? 0.5 : 1, auto_prompt: false,
	grow: 8, feather: 8, rotation: 0, pad_left: 0, pad_right: mode === 'outpaint' ? 0 : 25,
	pad_top: 0, pad_bottom: 0, target: 'the person', reference_labels: []
});

export const imageModeHasEditor = (mode: string) => mode === 'inpaint' || mode === 'outpaint';
export const imageModeHasPreview = (options: ImageModeOptions) =>
	options.mode === 'inpaint' ? Boolean(options.mask) : options.mode === 'outpaint' &&
	[options.rotation, options.pad_left, options.pad_right, options.pad_top, options.pad_bottom].some(value => Boolean(value));
export const imageModeIsSwap = (mode: string) => mode === 'outfit' || mode === 'body';
export const RESTORE_IMAGE_PROMPT = 'Restore image quality.';
const DEFAULT_PROMPTS: Record<string, string> = {
	restore: RESTORE_IMAGE_PROMPT,
	outpaint: 'Extend the image naturally into the added area. Preserve the existing image.',
	outfit: 'Dress the person in the base image in the clothes from the reference images.',
	body: 'Replace the person in the base image with the character from the reference images.'
};
export const imageModePrompt = (mode: string, prompt: string) => !prompt.trim() ? DEFAULT_PROMPTS[mode] ?? prompt : prompt;
export type ImageModeDisplay = { mode: ImageMode; prompt: string };
export function imageModeSubmission(mode: ImageMode, input: string, translate = (text: string) => text): { prompt: string; imageModeDisplay?: ImageModeDisplay } {
	const hidden = mode === 'restore' || mode === 'outpaint';
	const automatic = mode !== 'normal' && (hidden || !input.trim());
	const prompt = imageModePrompt(mode, hidden ? '' : input);
	const content = automatic ? translate(prompt) : prompt;
	return { prompt: content, ...(automatic && content ? { imageModeDisplay: { mode, prompt: content } } : {}) };
}
export function imageModeDisplayLabel(message: { content?: unknown; image_mode_display?: ImageModeDisplay }): string {
	const display = message.image_mode_display;
	if (!display || display.mode === 'normal' || display.prompt !== message.content) return '';
	return IMAGE_MODES.find(mode => mode.id === display.mode)?.label ?? '';
}
export const imageModeAttachmentLimit = (mode: string) => mode === 'restore' || imageModeHasEditor(mode) ? 1 : mode === 'body' ? 4 : mode === 'outfit' ? 5 : 10;
export const imageModeAvailable = (mode: string, files: any[]) => mode === 'normal' || (
	imageModeFiles(files).length > 0 && imageModeFiles(files).length <= imageModeAttachmentLimit(mode) &&
	!imageModeFiles(files).some(file => file.status === 'uploading' || file.status === 'error')
);
export const imageSwapSlots = (files: any[]) => {
	const images = imageModeFiles(files);
	const base = images.find(file => file.image_mode_role === 'base') ?? images.find(file => !file.image_mode_role);
	return { base, references: images.filter(file => file !== base) };
};
export const imageModeFileError = (mode: string, files: any[]) => {
	if (mode !== 'normal' && imageModeFiles(files).some(file => file.status === 'error')) return 'Não foi possível carregar a imagem.';
	if (mode === 'restore') {
		if (!imageModeFiles(files).length) return 'Adicione a imagem base.';
		if (imageModeFiles(files).length !== 1) return 'Selecione apenas uma imagem para restaurar.';
	}
	if (imageModeHasEditor(mode) && imageModeFiles(files).length !== 1) return 'Selecione apenas uma imagem para editar.';
	if (!imageModeIsSwap(mode)) return '';
	if (imageModeFiles(files).length > imageModeAttachmentLimit(mode)) return mode === 'body' ? 'Use no máximo quatro imagens, incluindo a base.' : 'Use no máximo cinco imagens, incluindo a base.';
	const slots = imageSwapSlots(files);
	if (!slots.base) return 'Adicione a imagem base.';
	if (!slots.references.length) return mode === 'outfit' ? 'Adicione a referência de roupa.' : 'Adicione a referência do personagem.';
	return '';
};
export const imageModeFiles = (files: any[]) => files.filter(file =>
	file.type === 'image' || (file.content_type ?? '').startsWith('image/')
);
export const imageModeSource = (file: any): string => {
	const url = file?.url ?? '';
	if (/^(data:|blob:|https?:|\/)/.test(url)) return url;
	const id = file?.id || url;
	return id ? `/api/v1/files/${encodeURIComponent(id)}/content` : '';
};
export const imageModeSourceKey = (file: any): string => {
	if (file?.id) return file.id;
	const url = file?.url ?? '';
	if (url.length < 500) return url;
	let hash = 2166136261;
	for (let index = 0; index < url.length; index++) hash = Math.imul(hash ^ url.charCodeAt(index), 16777619);
	return `inline:${url.length}:${hash >>> 0}`;
};
