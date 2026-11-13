import type { ArtifactFile } from './project';

export type CompileRequest = {
	id: number;
	files: ArtifactFile[];
	entry: string;
	scripts: string[];
	react: boolean;
	imports?: Record<string, string>;
};
export type PreviewPacket = {
	html: string;
	js: string;
	css: string;
	react: boolean;
	tailwind: boolean;
	live: boolean;
	preserveJS?: boolean;
	files: string[];
	accent: string;
	imports?: Record<string, string>;
};
