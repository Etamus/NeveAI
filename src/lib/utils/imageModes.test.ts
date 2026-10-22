import { describe, expect, it } from 'vitest';
import { IMAGE_MODES, imageModeDefaults, imageModeFiles, imageModeSource, imageModeSourceKey, imageModeHasEditor, imageModeHasPreview, imageSwapSlots, imageModeFileError, imageModePrompt, imageModeAvailable, imageModeAttachmentLimit, imageModeSubmission, imageModeDisplayLabel } from './imageModes';

describe('Neve Image 2 modes', () => {
	it('only renders a composite thumbnail after a mask or expansion has been applied', () => {
		for(const {id} of IMAGE_MODES) expect(imageModeHasPreview(imageModeDefaults(id))).toBe(false);
		expect(imageModeHasPreview({mode:'inpaint',mask:'mask.png'})).toBe(true);
		for(const property of ['rotation','pad_left','pad_right','pad_top','pad_bottom']) {
			expect(imageModeHasPreview({...imageModeDefaults('outpaint'),[property]:20})).toBe(true);
		}
		expect(imageModeHasPreview({mode:'restore',mask:'unused',pad_left:20})).toBe(false);
	});
	it('uses the supplied animated examples for each special mode', () => {
		expect(IMAGE_MODES.filter(mode=>mode.image).map(mode=>mode.image)).toEqual([
			'/static/aprimorar.gif','/static/expandir.gif','/static/trocarobjetos.gif',
			'/static/trocarroupas.gif','/static/trocarpessoas.gif'
		]);
	});
	it('separates automatic mode labels from the full generation prompt', () => {
		for (const mode of ['restore','outpaint','outfit','body'] as const) {
			const submission = imageModeSubmission(mode, '');
			expect(submission.prompt).toBe(imageModePrompt(mode, ''));
			const message = JSON.parse(JSON.stringify({content:submission.prompt,image_mode_display:submission.imageModeDisplay}));
			expect(imageModeDisplayLabel(message)).toBe(IMAGE_MODES.find(item=>item.id===mode)?.label);
			message.content='A different user instruction';
			expect(imageModeDisplayLabel(message)).toBe('');
		}
	});
	it('preserves typed prompts even if they match an automatic instruction', () => {
		for (const mode of ['normal','inpaint','outfit','body'] as const) {
			for (const input of ['My own instruction',imageModePrompt('outfit','')]) {
				expect(imageModeSubmission(mode,input)).toEqual({prompt:input});
			}
		}
		expect(imageModeDisplayLabel({content:'Hello'})).toBe('');
	});
	it('uses automatic instructions in modes without text input, ignoring hidden drafts', () => {
		for (const mode of ['restore','outpaint'] as const) {
			const submission=imageModeSubmission(mode,'A hidden old draft',text=>'Localized: '+text);
			expect(submission.prompt).toBe('Localized: '+imageModePrompt(mode,''));
			expect(submission.imageModeDisplay?.prompt).toBe(submission.prompt);
		}
	});
	it('keeps the requested display order without changing workflow IDs', () => {
		expect(IMAGE_MODES.map(({id,label})=>[id,label])).toEqual([
			['normal','Padrão'],['restore','Aprimorar'],['outpaint','Expandir'],
			['inpaint','Trocar objetos'],['outfit','Trocar roupas'],['body','Trocar pessoas']
		]);
	});
	it('only mask and outpaint modes open editors', () => {
		for (const mode of IMAGE_MODES) expect(imageModeHasEditor(mode.id)).toBe(['inpaint','outpaint'].includes(mode.id));
		expect(IMAGE_MODES.map(mode=>mode.id)).not.toContain('head');
		expect(IMAGE_MODES.map(mode=>mode.id)).not.toContain('auto');
		expect(IMAGE_MODES.map(mode=>mode.id)).not.toContain('consistent');
	});
	it('keeps explicit reference-first uploads out of the base slot', () => {
		const reference={id:'ref',type:'image',image_mode_role:'reference'},base={id:'base',type:'image',image_mode_role:'base'};
		expect(imageSwapSlots([reference]).base).toBeUndefined();
		expect(imageModeFileError('body',[reference])).toContain('base');
		expect(imageSwapSlots([reference,base])).toEqual({base,references:[reference]});
		expect(imageModeFileError('body',[reference,base])).toBe('');
		expect(imageModeFileError('body',[reference,base,{id:'third',type:'image'}])).toBe('');
		expect(imageModeFileError('normal',[])).toBe('');
	});
	it('restores without a typed prompt while keeping custom user instructions intact', () => {
		expect(imageModePrompt('restore','')).toContain('Restore');
		expect(imageModePrompt('restore','Keep the lettering')).toBe('Keep the lettering');
		expect(imageModePrompt('normal','')).toBe('');
		expect(imageModeFileError('restore',[])).not.toBe('');
		expect(imageModeFileError('restore',[{type:'image'}])).toBe('');
	});
	it('starts in isolated normal mode with automatic rewriting disabled', () => {
		expect(imageModeDefaults().mode).toBe('normal');
		expect(IMAGE_MODES).toHaveLength(6);
		for (const mode of IMAGE_MODES) expect(imageModeDefaults(mode.id).auto_prompt).toBe(false);
		expect(imageModeDefaults('restore').strength).toBe(0.5);
	});
	 it('requires images to enable editing and enforces mode-specific limits', () => {
		const images=Array.from({length:6},(_,id)=>({id:String(id),type:'image'}));
		for(const mode of IMAGE_MODES) expect(imageModeAvailable(mode.id,[])).toBe(mode.id==='normal');
		expect(imageModeAvailable('inpaint',[{type:'image',status:'uploading'}])).toBe(false);
		expect(imageModeAvailable('restore',images.slice(0,2))).toBe(false);
		for(const mode of ['inpaint','outpaint']) {
			expect(imageModeAttachmentLimit(mode)).toBe(1);
			expect(imageModeAvailable(mode,images.slice(0,2))).toBe(false);
			expect(imageModeFileError(mode,images.slice(0,2))).not.toBe('');
			expect(imageModeFileError(mode,images.slice(0,1))).toBe('');
		}
		for(const mode of ['outfit','body']) {
			const limit=mode==='body'?4:5;
			expect(imageModeAttachmentLimit(mode)).toBe(limit);
			expect(imageModeFileError(mode,images.slice(0,limit))).toBe('');
			expect(imageModeFileError(mode,images.slice(0,limit+1))).not.toBe('');
			expect(imageModeFileError(mode,images)).not.toBe('');
			expect(imageModePrompt(mode,'')).not.toBe('');
		}
		expect(imageModePrompt('outpaint','')).not.toBe('');
	});
	it('does not share mutable reference settings', () => {
		const first = imageModeDefaults('outfit'), second = imageModeDefaults('outfit');
		first.reference_labels!.push('coat');
		expect(second.reference_labels).toEqual([]);
	});
	it('selects image files only and retains authenticated file routes', () => {
		const files = [{id:'1',type:'image'}, {id:'2',content_type:'image/png'}, {id:'3',type:'file',content_type:'text/plain'}];
		expect(imageModeFiles(files)).toHaveLength(2);
		expect(imageModeSource(files[0])).toBe('/api/v1/files/1/content');
		expect(imageModeSource({url:'uploaded-id',content_type:'image/png'})).toBe('/api/v1/files/uploaded-id/content');
		expect(imageModeSource({url:'data:image/png;base64,abc'})).toBe('data:image/png;base64,abc');
		expect(imageModeSource(undefined)).toBe('');
		expect(imageModeSourceKey(files[0])).toBe('1');
		expect(imageModeSourceKey({url:'data:image/png;base64,'+'a'.repeat(1000)}).length).toBeLessThan(500);
	});
});
