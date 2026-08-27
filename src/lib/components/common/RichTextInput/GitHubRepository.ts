import { mergeAttributes, Node } from '@tiptap/core';
import { NodeSelection, Plugin, PluginKey, TextSelection } from 'prosemirror-state';

import { findGitHubRepositoryLinks } from '$lib/utils/github';

const GitHubRepository = Node.create({
	name: 'githubRepository',

	group: 'inline',
	inline: true,
	atom: true,
	selectable: true,
	draggable: false,

	addAttributes() {
		return {
			url: {
				default: null,
				parseHTML: (element) => element.getAttribute('data-github-repository-url'),
				renderHTML: (attributes) => ({
					'data-github-repository-url': attributes.url
				})
			},
			label: {
				default: null,
				parseHTML: (element) => element.getAttribute('data-github-repository-label'),
				renderHTML: (attributes) => ({
					'data-github-repository-label': attributes.label
				})
			}
		};
	},

	parseHTML() {
		return [{ tag: 'span[data-type="githubRepository"]' }];
	},

	renderHTML({ node, HTMLAttributes }) {
		return [
			'span',
			mergeAttributes(HTMLAttributes, {
				'data-type': this.name,
				class: 'github-repository-input-link',
				contenteditable: 'false'
			}),
			node.attrs.label
		];
	},

	renderText({ node }) {
		return node.attrs.url;
	},

	addNodeView() {
		return ({ node, editor, getPos }) => {
			const dom = document.createElement('span');
			const updateElement = () => {
				dom.textContent = node.attrs.label;
				dom.setAttribute('data-type', this.name);
				dom.setAttribute('data-github-repository-url', node.attrs.url);
				dom.setAttribute('data-github-repository-label', node.attrs.label);
				dom.setAttribute('contenteditable', 'false');
				dom.className = 'github-repository-input-link';
			};
			const selectRepository = (event: MouseEvent) => {
				if (event.button !== 0) return;

				const position = getPos();
				if (typeof position !== 'number') return;

				event.preventDefault();
				editor.view.focus();
				editor.view.dispatch(
					editor.state.tr.setSelection(NodeSelection.create(editor.state.doc, position))
				);
			};

			updateElement();
			dom.addEventListener('mousedown', selectRepository);

			return {
				dom,
				selectNode: () => dom.classList.add('ProseMirror-selectednode'),
				deselectNode: () => dom.classList.remove('ProseMirror-selectednode'),
				destroy: () => dom.removeEventListener('mousedown', selectRepository)
			};
		};
	},

	addProseMirrorPlugins() {
		const repositoryNodeType = this.type;

		return [
			new Plugin({
				key: new PluginKey('githubRepository'),
				props: {
					handleTextInput: (view, from, _to, text) => {
						if (!/^\s+$/.test(text)) return false;

						const resolvedPosition = view.state.doc.resolve(from);
						if (!resolvedPosition.parent.isTextblock) return false;

						const textBeforeCursor = resolvedPosition.parent.textBetween(
							0,
							resolvedPosition.parentOffset,
							'',
							'\uFFFC'
						);
						const repository = findGitHubRepositoryLinks(textBeforeCursor).find(
							(match) => match.rawEnd === textBeforeCursor.length
						);
						if (!repository) return false;

						const repositoryStart = resolvedPosition.start() + repository.start;
						const repositoryEnd = resolvedPosition.start() + repository.end;
						const transaction = view.state.tr.replaceWith(
							repositoryStart,
							repositoryEnd,
							repositoryNodeType.create({
								url: repository.reference.url,
								label: repository.reference.label
							})
						);
						const insertionPosition = transaction.mapping.map(from, 1);
						transaction.insertText(text, insertionPosition);
						transaction.setSelection(
							TextSelection.create(transaction.doc, insertionPosition + text.length)
						);
						view.dispatch(transaction.scrollIntoView());

						return true;
					}
				}
			})
		];
	}
});

export default GitHubRepository;
