<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { fade } from 'svelte/transition';
	import { getContext, createEventDispatcher, tick } from 'svelte';

	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	const dispatch = createEventDispatcher();

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import Pencil from '$lib/components/icons/Pencil.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Tags from '$lib/components/chat/Tags.svelte';
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte';
	import { getChatById } from '$lib/apis/chats';
	import { chats, folders, settings, user } from '$lib/stores';
	import { createMessagesList } from '$lib/utils';
	import Download from '$lib/components/icons/Download.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';
	import Messages from '$lib/components/chat/Messages.svelte';

	const i18n = getContext('i18n');

	export let moveChatHandler: Function;

	export let cloneChatHandler: Function;
	export let renameHandler: Function;
	export let deleteHandler: Function;
	export let onClose: Function;

	export let chatId = '';

	export let show = false;

	let chat = null;
	let showFullMessages = false;


	const getChatAsText = async (chat) => {
		const history = chat.chat.history;
		const messages = createMessagesList(history, history.currentId);
		const chatText = messages.reduce((a, message, i, arr) => {
			return `${a}### ${message.role.toUpperCase()}\n${message.content}\n\n`;
		}, '');

		return chatText.trim();
	};

	const downloadTxt = async () => {
		const chat = await getChatById(localStorage.token, chatId);
		if (!chat) {
			return;
		}

		const chatText = await getChatAsText(chat);
		let blob = new Blob([chatText], {
			type: 'text/plain'
		});

		saveAs(blob, `chat-${chat.chat.title}.txt`);
	};

	const downloadPdf = async () => {
		chat = await getChatById(localStorage.token, chatId);
		if (!chat) {
			return;
		}

		const [{ default: jsPDF }, { default: html2canvas }] = await Promise.all([
			import('jspdf'),
			import('html2canvas-pro')
		]);

		if ($settings?.stylizedPdfExport ?? true) {
			showFullMessages = true;
			await tick();

			const containerElement = document.getElementById('full-messages-container');
			if (containerElement) {
				try {
					const isDarkMode = document.documentElement.classList.contains('dark');
					const virtualWidth = 800; // px, fixed width for cloned element

					// Clone and style
					const clonedElement = containerElement.cloneNode(true) as HTMLElement;
					clonedElement.classList.add('text-black');
					clonedElement.classList.add('dark:text-white');
					clonedElement.style.width = `${virtualWidth}px`;
					clonedElement.style.position = 'absolute';
					clonedElement.style.left = '-9999px';
					clonedElement.style.height = 'auto';
					document.body.appendChild(clonedElement);

					// Wait for DOM update/layout
					await new Promise((r) => setTimeout(r, 100));

					// Render entire content once
					const canvas = await html2canvas(clonedElement, {
						backgroundColor: isDarkMode ? '#000' : '#fff',
						useCORS: true,
						scale: 2, // increase resolution
						width: virtualWidth
					});

					document.body.removeChild(clonedElement);

					const pdf = new jsPDF('p', 'mm', 'a4');
					const pageWidthMM = 210;
					const pageHeightMM = 297;

					// Convert page height in mm to px on canvas scale for cropping
					// Get canvas DPI scale:
					const pxPerMM = canvas.width / virtualWidth; // width in px / width in px?
					// Since 1 page width is 210 mm, but canvas width is 800 px at scale 2
					// Assume 1 mm = px / (pageWidthMM scaled)
					// Actually better: Calculate scale factor from px/mm:
					// virtualWidth px corresponds directly to 210mm in PDF, so pxPerMM:
					const pxPerPDFMM = canvas.width / pageWidthMM; // canvas px per PDF mm

					// Height in px for one page slice:
					const pagePixelHeight = Math.floor(pxPerPDFMM * pageHeightMM);

					let offsetY = 0;
					let page = 0;

					while (offsetY < canvas.height) {
						// Height of slice
						const sliceHeight = Math.min(pagePixelHeight, canvas.height - offsetY);

						// Create temp canvas for slice
						const pageCanvas = document.createElement('canvas');
						pageCanvas.width = canvas.width;
						pageCanvas.height = sliceHeight;

						const ctx = pageCanvas.getContext('2d');

						// Draw the slice of original canvas onto pageCanvas
						ctx.drawImage(
							canvas,
							0,
							offsetY,
							canvas.width,
							sliceHeight,
							0,
							0,
							canvas.width,
							sliceHeight
						);

						const imgData = pageCanvas.toDataURL('image/jpeg', 0.7);

						// Calculate image height in PDF units keeping aspect ratio
						const imgHeightMM = (sliceHeight * pageWidthMM) / canvas.width;

						if (page > 0) pdf.addPage();

						if (isDarkMode) {
							pdf.setFillColor(0, 0, 0);
							pdf.rect(0, 0, pageWidthMM, pageHeightMM, 'F'); // black bg
						}

						pdf.addImage(imgData, 'JPEG', 0, 0, pageWidthMM, imgHeightMM);

						offsetY += sliceHeight;
						page++;
					}

					pdf.save(`chat-${chat.chat.title}.pdf`);

					showFullMessages = false;
				} catch (error) {
					console.error('Error generating PDF', error);
				}
			}
		} else {
			console.log('Downloading PDF');

			const chatText = await getChatAsText(chat);

			const doc = new jsPDF();

			// Margins
			const left = 15;
			const top = 20;
			const right = 15;
			const bottom = 20;

			const pageWidth = doc.internal.pageSize.getWidth();
			const pageHeight = doc.internal.pageSize.getHeight();
			const usableWidth = pageWidth - left - right;
			const usableHeight = pageHeight - top - bottom;

			// Font size and line height
			const fontSize = 8;
			doc.setFontSize(fontSize);
			const lineHeight = fontSize * 1; // adjust if needed

			// Split the markdown into lines (handles \n)
			const paragraphs = chatText.split('\n');

			let y = top;

			for (let paragraph of paragraphs) {
				// Wrap each paragraph to fit the width
				const lines = doc.splitTextToSize(paragraph, usableWidth);

				for (let line of lines) {
					// If the line would overflow the bottom, add a new page
					if (y + lineHeight > pageHeight - bottom) {
						doc.addPage();
						y = top;
					}
					doc.text(line, left, y);
					y += lineHeight * 0.5;
				}
				// Add empty line at paragraph breaks
				y += lineHeight * 0.1;
			}

			doc.save(`chat-${chat.chat.title}.pdf`);
		}
	};

	const downloadJSONExport = async () => {
		const chat = await getChatById(localStorage.token, chatId);

		if (chat) {
			let blob = new Blob([JSON.stringify([chat])], {
				type: 'application/json'
			});
			saveAs(blob, `chat-export-${Date.now()}.json`);
		}
	};

</script>

{#if chat && showFullMessages}
	<div class="hidden w-full h-full flex-col">
		<div id="full-messages-container">
			<Messages
				className="h-full flex pt-4 pb-8 w-full"
				chatId={`chat-preview-${chat?.id ?? ''}`}
				user={$user}
				readOnly={true}
				history={chat.chat.history}
				autoScroll={true}
				sendMessage={() => {}}
				continueResponse={() => {}}
				regenerateResponse={() => {}}
				messagesCount={null}
				editCodeBlock={false}
			/>
		</div>
	</div>
{/if}

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('More')}>
		<slot />
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="select-none w-full max-w-[200px] rounded-md px-1 py-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-md"
			sideOffset={-2}
			side="bottom"
			align="start"
			transition={(e) => fade(e, { duration: 100 })}
		>

			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-1.5 text-sm  cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-sm"
				on:click={() => {
					renameHandler();
				}}
			>
				<Pencil strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Rename')}</div>
			</DropdownMenu.Item>

			<hr class="border-gray-50/30 dark:border-gray-800/30 my-1" />

			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-1.5 text-sm  cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-sm"
				on:click={() => {
					cloneChatHandler();
				}}
			>
				<DocumentDuplicate strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Clone')}</div>
			</DropdownMenu.Item>

			{#if chatId && $folders.length > 0}
				<DropdownMenu.Sub>
					<DropdownMenu.SubTrigger
						draggable="false"
						class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-sm select-none w-full"
					>
						<Folder />

						<div class="flex items-center">{$i18n.t('Move')}</div>
					</DropdownMenu.SubTrigger>
					<DropdownMenu.SubContent
						class="select-none w-full max-w-[200px] rounded-md p-1 z-50 bg-white dark:bg-gray-850 dark:text-white border border-gray-100 dark:border-gray-800 shadow-md max-h-52 overflow-y-auto scrollbar-hidden"
					transition={(e) => fade(e, { duration: 100 })}
						sideOffset={8}
					>
						{#each $folders.sort((a, b) => b.updated_at - a.updated_at) as folder}
							<DropdownMenu.Item
								draggable="false"
								class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-sm overflow-hidden"
								on:click={() => {
									moveChatHandler(chatId, folder.id);
								}}
							>
								<div class="shrink-0">
									<Folder />
								</div>

								<div class="truncate">{folder?.name ?? 'Folder'}</div>
							</DropdownMenu.Item>
						{/each}
					</DropdownMenu.SubContent>
				</DropdownMenu.Sub>
			{/if}

			<DropdownMenu.Item
				draggable="false"
				class="flex  gap-2  items-center px-3 py-1.5 text-sm  cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-sm"
				on:click={() => {
					deleteHandler();
				}}
			>
				<GarbageBin strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Delete')}</div>
			</DropdownMenu.Item>
		</DropdownMenu.Content>
	</div>
</Dropdown>
