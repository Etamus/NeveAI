<script lang="ts">
	import { onMount, setContext, tick } from 'svelte';
	import { writable } from 'svelte/store';
	import i18next from 'i18next';
	import pt from '$lib/i18n/locales/pt-BR/translation.json';
	import { user, models, settings, mobile } from '$lib/stores';
	import UserMessage from '$lib/components/chat/Messages/UserMessage.svelte';
	import ResponseMessage from '$lib/components/chat/Messages/ResponseMessage.svelte';
	import MessageInput from '$lib/components/chat/MessageInput.svelte';
	const i18n=i18next.createInstance();
	i18n.init({lng:'pt-BR',initImmediate:false,resources:{'pt-BR':{translation:pt}}});
	setContext('i18n',writable(i18n));
	const person={id:'fixture',name:'Pessoa',role:'admin'};
	const text='Texto de exemplo para comparar a fonte e o tamanho das mensagens.';
	let history:any={currentId:'answer',messages:{
		question:{id:'question',role:'user',content:text,timestamp:1,childrenIds:['answer']},
		answer:{id:'answer',role:'assistant',model:'fixture-model',content:text+'\n\n- Primeiro item\n- Segundo item\n\n## Titulo\n\n```js\nconst value = 1;\n```',done:true,timestamp:2,parentId:'question',childrenIds:[]}
	}};
	let submitted:any[]=[];
	const noop=()=>{};
	onMount(()=>{
		user.set(person as any);
		models.set([{id:'fixture-model',name:'Modelo',owned_by:'openai'}] as any);
		settings.update(value=>({...value,chatBubble:true,showMessageCopyButton:true}));
		mobile.set(innerWidth<768);
		(window as any).__typography={
			submitted:()=>submitted,
			async done(value:boolean){history={...history,messages:{...history.messages,answer:{...history.messages.answer,done:value}}};await tick();}
		};
		return ()=>{delete (window as any).__typography;};
	});
</script>

<div class="min-h-screen bg-white p-4 dark:bg-black">
	<div class="mx-auto w-full max-w-[750px]" id="messages-container">
		<UserMessage user={person} chatId="fixture" {history} messageId="question" siblings={[history.messages.question]}
			isFirstMessage={true} readOnly={false} gotoMessage={noop} showPreviousMessage={noop} showNextMessage={noop}
			editMessage={(...args)=>submitted.push(args)} deleteMessage={noop} />
		<ResponseMessage chatId="fixture" {history} messageId="answer" selectedModels={['fixture-model']} readOnly={true}
			showPreviousMessage={noop} showNextMessage={noop} updateChat={noop} editMessage={noop} saveMessage={noop}
			rateMessage={noop} actionMessage={noop} deleteMessage={noop} submitMessage={noop} continueResponse={noop}
			regenerateResponse={noop} addMessages={noop} />
		<MessageInput {history} selectedModels={['fixture-model']} />
	</div>
</div>
