import { describe, expect, it } from 'vitest';
import { getWebSearchDisplayQueries } from './webSearchDisplayQueries';

describe('Deep research query presentation', () => {
	it('shows the topic and action instead of a long conversational question', () => {
		const question = 'Dado o cenario atual do aquecimento global, qual seria a melhor forma de ajudar o meio ambiente em geral?';
		expect(getWebSearchDisplayQueries([question], false)).toEqual(['aquecimento global ajudar o meio ambiente']);
	});
	it('preserves quoted entities and explicit source URLs in long requests', () => {
		const query = 'Considerando o cenario atual da tecnologia, qual seria a melhor forma de comparar "Qwen3.5" com https://huggingface.co/test';
		expect(getWebSearchDisplayQueries([query], false)).toEqual([query]);
	});
	it('cleans redundant supplemental queries in existing Portuguese chats', () => {
		const topic = 'Qual a melhor temporada de GOT';
		expect(getWebSearchDisplayQueries([topic, `${topic} fontes oficiais documentacao`, `${topic} analise independente limitacoes`], true)).toEqual([topic]);
	});
	it('supports English and accented Portuguese without hiding distinct topics', () => {
		expect(getWebSearchDisplayQueries(['GOT reviews official sources documentation', 'GOT reviews independent analysis limitations', 'GOT ratings', 'GOT ratings an\u00e1lise independente limita\u00e7\u00f5es'], true)).toEqual(['GOT reviews', 'GOT ratings']);
	});
	it('does not change normal search queries or the stored queries', () => {
		const original = ['GOT fontes oficiais documentacao'];
		expect(getWebSearchDisplayQueries(original, false)).toEqual(original);
		getWebSearchDisplayQueries(original, true);
		expect(original).toEqual(['GOT fontes oficiais documentacao']);
		expect(getWebSearchDisplayQueries(null, true)).toEqual([]);
	});
});
