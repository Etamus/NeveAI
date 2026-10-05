import { describe, expect, it } from 'vitest';
import { Marked } from 'marked';
import katex from 'katex';
import katexExtension from './katex-extension';

function mathTokens(content: string) {
	const parser = new Marked(katexExtension());
	const tokens: any[] = [];
	parser.walkTokens(parser.lexer(content), (token) => {
		if (token.type === 'inlineKatex' || token.type === 'blockKatex') tokens.push(token);
	});
	return tokens;
}

describe('chat math delimiters', () => {
	it('keeps the Bhaskara explanation outside adjacent display formulas', () => {
		const content = String.raw`$$ax^2 + bx + c = 0$$

Onde:
* $a$ e o coeficiente de $x^2$.

$$x = \frac{-b \pm \sqrt{\Delta}}{2a}$$

Onde $\Delta$ (Delta) e o discriminante:

$$\Delta = b^2 - 4ac$$`;
		const tokens = mathTokens(content);
		expect(tokens.map((token) => token.text)).toEqual([
			'ax^2 + bx + c = 0', 'a', 'x^2',
			String.raw`x = \frac{-b \pm \sqrt{\Delta}}{2a}`,
			String.raw`\Delta`, String.raw`\Delta = b^2 - 4ac`
		]);
		for (const token of tokens) {
			expect(() => katex.renderToString(token.text, { displayMode: token.displayMode })).not.toThrow();
		}
	});

	it('supports multiline display formulas and inline math', () => {
		expect(mathTokens('Before $x$ and \\(y\\).\n\n$$\nx^2\n$$\n\nAfter.').map((t) => t.text.trim()))
			.toEqual(['x', 'y', 'x^2']);
	});

	it('keeps code and escaped dollar signs out of math', () => {
		expect(mathTokens('`$x$` and \\$5\n\n```tex\n$$x$$\n```')).toEqual([]);
	});

	it('does not consume following prose while a display formula is incomplete', () => {
		const tokens = mathTokens('$$x = 1$$\n\nOnde $x$ aparece.\n\n$$y =');
		expect(tokens.map((t) => t.text)).toEqual(['x = 1', 'x']);
	});

	it('recognizes same-line and bracketed display formulas as display math', () => {
		const tokens = mathTokens('$$x^2$$\n\n\\[y^2\\]\n\nText $z$ continues.');
		expect(tokens.map((t) => [t.text.trim(), t.displayMode]))
			.toEqual([['x^2', true], ['y^2', true], ['z', false]]);
	});
});
