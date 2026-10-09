# Neve no macOS

Distribuicao isolada. Os scripts do Windows, `.env`, banco, modelos e dependencias
da raiz nao sao alterados. Todos os arquivos gerados ficam em `macos/.runtime/`.

## Instalar e iniciar

Recomendado: Apple Silicon nativo, macOS 14+, internet e espaco livre para as
dependencias e modelos escolhidos. Nao use Terminal/Python sob Rosetta.

1. Copie o projeto completo para o Mac, incluindo esta pasta.
2. Abra `instalar.command`. Ele prepara o Python local e abre o instalador nativo.
3. Selecione imagem/musica e clique em **Instalar / Reparar**.
4. Abra `iniciar.command`. Fechar a janela encerra somente o backend e os
   subprocessos iniciados por essa instancia.

Sem Command Line Tools, imagens ficam desmarcadas inicialmente: a instalacao
principal funciona sem essas ferramentas. Para preparar imagens depois, instale
as ferramentas da Apple e execute novamente o instalador com imagens marcadas.

Para abrir sem Terminal, use **Instalar Neve.app** e **Iniciar Neve.app**. O ZIP
`Inicializadores-macOS.zip` preserva permissoes dos executaveis; extraia-o na raiz
do projeto (ele contem apenas esta pasta, nao o projeto completo). Se o Gatekeeper
bloquear um app nao assinado, use o fluxo de **Abrir** / **Privacidade e Seguranca**
do macOS. Nao e necessario desativar o Gatekeeper globalmente.

Os apps podem ser reconstruidos localmente, sem Xcode, com
`macos/.runtime/venv/bin/python macos/build_launchers.py`. Esse comando usa
`osacompile` e assinatura local do macOS, preservando os apps anteriores em
`.runtime/original-launchers/`. A assinatura local nao substitui notarizacao
Apple: a primeira abertura pode exigir autorizacao do macOS. Se ela nao concluir,
use `bash macos/iniciar.command`.

Se o transporte dos arquivos perder permissao de execucao:

```bash
chmod +x macos/*.command macos/*.sh macos/*.app/Contents/MacOS/*
```

Alternativa sem depender da permissao Finder:

```bash
bash macos/instalar.command
bash macos/iniciar.command
```

Nao e necessario instalar Homebrew nem usar sudo. Para compilar imagem,
instale os Command Line Tools oficiais da Apple (`xcode-select --install`).
Uma falha de compilacao e exibida no log; nao e tratada como sucesso.
O instalador so marca sucesso depois de iniciar o backend real e verificar
frontend/configuracao HTTP. Uma falha impede o estado de instalacao concluida.

## Isolamento

- Python gerenciado por uv, venv, Node, npm, cache e ferramentas ficam nesta pasta.
- FFmpeg/FFprobe nativos sao verificados por SHA-256; Pandoc vem no wheel nativo.
- O instalador usa uma lista permitida para copiar codigo e assets para `.runtime/app`.
  Ele nao copia `.env`, dados, `.git`, venv, `node_modules` ou executaveis Windows.
- Conversas do Mac ficam em `.runtime/data/neve.db`. Nao compartilhe o banco ativo
  entre Windows/macOS. O primeiro acesso cria uma conta local com autenticacao.
- Coloque GGUFs em `.runtime/app/models/` e projetores em `.runtime/app/mmproj/`,
  ou use o download integrado. Eles nao sao apagados ao reparar.
- Ha trava de execucao: instalar/reparar e iniciar nao podem manipular o mesmo
  ambiente simultaneamente. Porta ocupada gera erro, sem matar outro aplicativo.
- O servidor escuta somente `127.0.0.1:8080`. Nao e exposto a rede por padrao.
- Adaptacoes de plataforma sao aplicadas somente a copia de execucao.
- O indicador de memoria mostra RAM unificada no Apple Silicon, nao VRAM NVIDIA.
- Reparar atualiza a copia a partir deste projeto. Nao faz `git pull` na raiz.

## Recursos

| Recurso | Caminho macOS |
| --- | --- |
| Chat, GGUF, visao e raciocinio | llama.cpp nativo; Metal em Apple Silicon |
| Contexto, KV, DE e MTP | Mantidos; disponibilidade depende do modelo/backend llama.cpp |
| Pesquisa web/profunda, ferramentas e documentos | Mesma aplicacao; dependencias nativas e OfficeCLI |
| Embeddings | PyTorch MPS quando disponivel; CPU de fallback |
| Transcricao local | faster-whisper em CPU (CTranslate2 nao usa MPS) |
| Neve Image 1 / 1.5 | stable-diffusion.cpp compilado para Metal |
| Neve Image 2 / 2.1 | ComfyUI e GGUF em MPS, sem wheel CUDA; requer memoria suficiente |
| Musica | ACE-Step, cujo projeto oferece suporte macOS; runtime proprio |
| Video MiniMax H3 atual | Desabilitado: o workflow deste projeto exige CUDA/Blackwell |

Os modelos de imagem sao grandes; suporte de plataforma nao significa caber em
qualquer Mac. Falhas por memoria nao devem ser confundidas com incompatibilidade.
O fallback de operacoes PyTorch MPS esta habilitado, mas operacoes nao implementadas
ou problemas upstream podem exigir atualizacao dos respectivos runtimes.

Intel usa llama.cpp CPU/Accelerate e PyTorch 2.2.2 (ultima linha com wheels macOS
x86_64), com Transformers/embeddings compativeis com essa linha. Apple Silicon e o alvo principal. O caminho ComfyUI MPS exige Apple
Silicon; em Intel use imagem via stable-diffusion.cpp/CPU. Dependencias sem wheels
Intel podem impedir instalacao e precisam ser diagnosticadas, nao ignoradas.

## Diagnostico e testes

```bash
bash macos/diagnosticar.command
bash macos/diagnosticar.command --smoke
bash macos/instalar.command --cli --no-images
bash macos/iniciar.command --browser
```

`--smoke` inicia a instancia real, valida sua identidade, frontend e configuracao
HTTP e a encerra. Nao testa inferencia de modelos ou todas as geracoes.

Teste nativo completo de inicializacao: `bash macos/test-native.sh`.

Logs: `.runtime/logs/install.log` e `.runtime/logs/backend.log`.
Preparacao inicial: `.runtime/logs/bootstrap-install.log`; inicializador:
`.runtime/logs/bootstrap-start.log`. Em falhas, aparece um alerta com as ultimas
linhas e a opcao de abrir o log. No Terminal, o erro permanece ate pressionar Enter.

Se apos autorizar no Gatekeeper nenhuma janela aparecer, abra o Terminal, digite
`/bin/bash ` (com espaco), arraste `instalar.command` para ele e pressione Enter.
Na primeira execucao e necessario baixar Python e a ponte Cocoa antes da janela.
Envie as ultimas linhas de `bootstrap-install.log` para diagnosticar; nao remova
protecoes do sistema nem use comandos de exclusao global de quarentena.
Versoes instaladas: `.runtime/installation.json` e `.runtime/requirements-installed.lock`.

Os testes automatizados incluem isolamento, deteccao das ferramentas de imagem
e precedencia da rota de identificacao do backend sobre a interface. `test-native.sh`
valida a instalacao no Mac real. Inferencia depende de um modelo baixado e deve
ser testada separadamente; o teste HTTP nao comprova geracao de imagens ou musica.

Referencias oficiais:
- https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
- https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/build.md
- https://github.com/Comfy-Org/ComfyUI#installing
- https://github.com/ace-step/ACE-Step-1.5
- https://pywebview.flowrl.com/guide/installation
