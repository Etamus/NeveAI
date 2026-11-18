/**
 * Lightweight PPTX → Image renderer.
 *
 * Extracts text and images from each slide and renders them
 * directly to canvas, returning PNG data URLs.
 *
 * Uses jszip (dynamically imported) and the browser Canvas 2D API.
 * No theme resolution, charts, SmartArt, or animations — preview only.
 */

const EMU_PER_PX = 9525;
const emuToPx = (emu: number) => Math.round(emu / EMU_PER_PX);

const parseEmu = (val: string | null | undefined): number => (val ? parseInt(val, 10) || 0 : 0);

/** Load a data URI into an Image element and wait for it. */
const loadImage = (src: string): Promise<HTMLImageElement> =>
	new Promise((resolve, reject) => {
		const img = new Image();
		img.onload = () => resolve(img);
		img.onerror = () => reject(new Error('Failed to load image'));
		img.src = src;
	});

/**
 * Convert PPTX ArrayBuffer → array of PNG data URL strings, one per slide.
 */
export async function pptxToImages(
	buffer: ArrayBuffer
) {
	const JSZip = (await import('jszip')).default;
	const zip = await JSZip.loadAsync(buffer);

	// ── Read slide dimensions from presentation.xml ──────────────────
	let slideW = 960;
	let slideH = 540;
	const presXml = zip.file('ppt/presentation.xml');
	if (presXml) {
		const presText = await presXml.async('text');
		const presDoc = new DOMParser().parseFromString(presText, 'application/xml');
		const sldSz = presDoc.getElementsByTagName('p:sldSz')[0];
		if (sldSz) {
			slideW = emuToPx(parseEmu(sldSz.getAttribute('cx')));
			slideH = emuToPx(parseEmu(sldSz.getAttribute('cy')));
		}
	}

	// ── Discover slide files ─────────────────────────────────────────
	const slideFiles = Object.keys(zip.files)
		.filter((f) => /^ppt\/slides\/slide\d+\.xml$/.test(f))
		.sort((a, b) => {
			const na = parseInt(a.match(/slide(\d+)/)?.[1] ?? '0');
			const nb = parseInt(b.match(/slide(\d+)/)?.[1] ?? '0');
			return na - nb;
		});

	const decodedImages = new Map<string, Promise<HTMLImageElement>>();
	const decodeImage = (source: string) => {
		let result = decodedImages.get(source);
		if (!result) {
			result = (async () => {
				const file = zip.file(source);
				if (!file) throw new Error('Missing image');
				const ext = source.split('.').pop()?.toLowerCase() ?? '';
				const mime = ({ png: 'image/png', gif: 'image/gif', svg: 'image/svg+xml' } as Record<string,string>)[ext] ?? 'image/jpeg';
				const url = URL.createObjectURL(new Blob([await file.async('arraybuffer')], {type: mime}));
				try { return await loadImage(url); } finally { URL.revokeObjectURL(url); }
			})().then(image => {
				if (image.naturalWidth * image.naturalHeight > 4_000_000) decodedImages.delete(source);
				return image;
			}).catch(error => { decodedImages.delete(source); throw error; });
			decodedImages.set(source, result);
			if (decodedImages.size > 4) decodedImages.delete(decodedImages.keys().next().value!);
		} else {
			decodedImages.delete(source);
			decodedImages.set(source, result);
		}
		return result;
	};

	const renderSlide = async (index: number, requestedScale = 1) => {
		const slidePath = slideFiles[index];
		const slideText = await zip.file(slidePath)!.async('text');
		const slideDoc = new DOMParser().parseFromString(slideText, 'application/xml');

		// Load relationship file for this slide to resolve image references
		const slideNum = slidePath.match(/slide(\d+)/)?.[1];
		const relsPath = `ppt/slides/_rels/slide${slideNum}.xml.rels`;
		const rels: Record<string, string> = {};
		const relsFile = zip.file(relsPath);
		if (relsFile) {
			const relsText = await relsFile.async('text');
			const relsDoc = new DOMParser().parseFromString(relsText, 'application/xml');
			const relEls = relsDoc.getElementsByTagName('Relationship');
			for (let i = 0; i < relEls.length; i++) {
				const rel = relEls[i];
				const id = rel.getAttribute('Id') ?? '';
				const target = rel.getAttribute('Target') ?? '';
				if (target.startsWith('../')) {
					rels[id] = 'ppt/' + target.replace('../', '');
				} else {
					rels[id] = target;
				}
			}
		}

		// ── Create canvas and render slide ───────────────────────────
		const canvas = document.createElement('canvas');
		const scale = Math.min(requestedScale, Math.sqrt(8_000_000 / (slideW * slideH)));
		canvas.width = Math.ceil(slideW * scale);
		canvas.height = Math.ceil(slideH * scale);
		const ctx = canvas.getContext('2d')!;
		ctx.scale(scale, scale);

		// White background
		ctx.fillStyle = '#ffffff';
		ctx.fillRect(0, 0, slideW, slideH);

		const spTree = slideDoc.getElementsByTagName('p:spTree')[0];
		if (!spTree) {
			return canvas.toDataURL('image/png');
		}

		const shapes = [
			...Array.from(spTree.getElementsByTagName('p:sp')),
			...Array.from(spTree.getElementsByTagName('p:pic'))
		];

		for (const shape of shapes) {
			const xfrm =
				shape.getElementsByTagName('a:xfrm')[0] ?? shape.getElementsByTagName('p:xfrm')[0];
			if (!xfrm) continue;

			const off = xfrm.getElementsByTagName('a:off')[0];
			const ext = xfrm.getElementsByTagName('a:ext')[0];
			if (!off || !ext) continue;

			const x = emuToPx(parseEmu(off.getAttribute('x')));
			const y = emuToPx(parseEmu(off.getAttribute('y')));
			const w = emuToPx(parseEmu(ext.getAttribute('cx')));
			const h = emuToPx(parseEmu(ext.getAttribute('cy')));

			if (w === 0 && h === 0) continue;

			// ── Picture ──────────────────────────────────────────────
			const blipFill = shape.getElementsByTagName('p:blipFill')[0];
			if (blipFill) {
				const blip = blipFill.getElementsByTagName('a:blip')[0];
				if (blip) {
					const rEmbed = blip.getAttribute('r:embed') ?? '';
					const mediaPath = rels[rEmbed];
					if (mediaPath && !/\.(emf|wmf)$/i.test(mediaPath)) {
						try {
							const img = await decodeImage(mediaPath);
							ctx.drawImage(img, x, y, w, h);
						} catch {
							// Skip images that fail to load
						}
					}
				}
				continue;
			}

			// ── Text shape ───────────────────────────────────────────
			const txBody = shape.getElementsByTagName('p:txBody')[0];
			if (!txBody) continue;

			ctx.save();
			ctx.beginPath();
			ctx.rect(x, y, w, h);
			ctx.clip();

			const paragraphs = txBody.getElementsByTagName('a:p');
			let cursorY = y;
			const defaultFontSize = 12;

			for (let pi = 0; pi < paragraphs.length; pi++) {
				const para = paragraphs[pi];
				const runs = para.getElementsByTagName('a:r');

				if (runs.length === 0) {
					cursorY += defaultFontSize * 1.5;
					continue;
				}

				// Calculate max font size in this paragraph for line height
				let maxFontPt = defaultFontSize;
				for (let ri = 0; ri < runs.length; ri++) {
					const rPr = runs[ri].getElementsByTagName('a:rPr')[0];
					if (rPr) {
						const sz = rPr.getAttribute('sz');
						if (sz) {
							const pt = parseInt(sz, 10) / 100;
							if (pt > maxFontPt) maxFontPt = pt;
						}
					}
				}

				const maxFontPx = maxFontPt * 96 / 72;
				const lineHeight = maxFontPx * 1.2;
				cursorY += maxFontPx; // baseline offset

				let cursorX = x + 4; // small left padding

				for (let ri = 0; ri < runs.length; ri++) {
					const run = runs[ri];
					const rPr = run.getElementsByTagName('a:rPr')[0];
					const text = run.getElementsByTagName('a:t')[0]?.textContent ?? '';
					if (!text) continue;

					let fontPt = defaultFontSize;
					let bold = false;
					let italic = false;
					let color = '#000000';

					if (rPr) {
						if (rPr.getAttribute('b') === '1') bold = true;
						if (rPr.getAttribute('i') === '1') italic = true;
						const sz = rPr.getAttribute('sz');
						if (sz) fontPt = parseInt(sz, 10) / 100;
						const solidFill = rPr.getElementsByTagName('a:solidFill')[0];
						if (solidFill) {
							const srgb = solidFill.getElementsByTagName('a:srgbClr')[0];
							if (srgb) {
								const val = srgb.getAttribute('val');
								if (val) color = `#${val}`;
							}
						}
					}

					const family = rPr?.getElementsByTagName('a:latin')[0]?.getAttribute('typeface');
					const face = family && !family.startsWith('+') ? JSON.stringify(family) + ', ' : '';
					ctx.font = `${italic ? 'italic ' : ''}${bold ? 'bold ' : ''}${fontPt}pt ${face}Calibri, Arial, sans-serif`;
					ctx.fillStyle = color;
					ctx.textBaseline = 'alphabetic';

					// Simple word-wrap within the shape bounds
					const words = text.split(/(\s+)/);
					for (const word of words) {
						const metrics = ctx.measureText(word);
						if (cursorX + metrics.width > x + w && cursorX > x + 4) {
							cursorX = x + 4;
							cursorY += lineHeight;
						}
						if (cursorY > y + h) break;
						ctx.fillText(word, cursorX, cursorY);
						cursorX += metrics.width;
					}
				}

				cursorY += lineHeight * 0.4; // paragraph spacing
			}

			ctx.restore();
		}

		return canvas.toDataURL('image/png');
	};
	const base = new Map<number, Promise<string>>();
	const baseSlide = (index: number) => {
		if (index < 0 || index >= slideFiles.length) throw new RangeError('Invalid slide');
		const old = base.get(index);
		base.delete(index);
		const result = old ?? renderSlide(index).catch(error => { base.delete(index); throw error; });
		base.set(index, result);
		if (base.size > 3) base.delete(base.keys().next().value!);
		return result;
	};
	return { count: slideFiles.length, width: slideW, height: slideH, renderSlide, baseSlide };
}
