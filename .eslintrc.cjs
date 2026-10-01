module.exports = {
	root: true,
	extends: [
		'eslint:recommended',
		'plugin:@typescript-eslint/recommended',
		'plugin:svelte/recommended',
		'prettier'
	],
	parser: '@typescript-eslint/parser',
	plugins: ['@typescript-eslint'],
	parserOptions: {
		sourceType: 'module',
		ecmaVersion: 2020,
		extraFileExtensions: ['.svelte']
	},
	env: {
		browser: true,
		es2017: true,
		node: true
	},
	rules: {
		'@typescript-eslint/no-explicit-any': 'off',
		'@typescript-eslint/no-unsafe-function-type': 'off',
		'@typescript-eslint/no-unused-vars': 'warn',
		'@typescript-eslint/no-empty-object-type': 'warn',
		'@typescript-eslint/prefer-as-const': 'warn',
		'no-constant-condition': 'warn',
		'no-control-regex': 'warn',
		'no-empty': 'warn',
		'no-undef': 'off',
		'no-useless-escape': 'warn',
		'prefer-const': 'warn'
	},
	overrides: [
		{
			files: ['*.svelte'],
			parser: 'svelte-eslint-parser',
			parserOptions: {
				parser: '@typescript-eslint/parser'
			},
			rules: {
				'@typescript-eslint/no-unused-vars': 'off',
				'@typescript-eslint/no-unused-expressions': 'off',
				'svelte/no-at-html-tags': 'warn',
				'svelte/no-inner-declarations': 'warn',
				'svelte/no-unused-svelte-ignore': 'warn',
				'svelte/valid-compile': 'warn'
			}
		}
	]
};
