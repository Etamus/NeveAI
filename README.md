<img width="1400" height="350" alt="Banner" src="https://github.com/user-attachments/assets/8d8de5c3-2c9d-4777-92da-efcb70ea1ac3" />

---

**NeveAI** é um ecossistema local de orquestração de IA privacy-first, desenvolvido para oferecer uma experiência de alta performance na execução de LLMs de forma acessível, privada e independente. O projeto busca reduzir a dependência de grandes plataformas, assinaturas caras e APIs externas, oferecendo ao usuário uma alternativa própria para conversar com modelos, trabalhar com documentos, automatizar tarefas e explorar o potencial da inteligência artificial diretamente no computador. O projeto consolida funcionalidades avançadas de nível empresarial em um ambiente completamente offline, integrando um backend assíncrono em FastAPI a uma interface reativa em SvelteKit 5 e utilizando o motor llama.cpp para viabilizar o suporte a modelos GGUF com aceleração de hardware via CUDA/Vulkan.

---

<img width="1917" height="1000" alt="{372DD1EB-1236-49B9-8224-C8BC487A9BE3}" src="https://github.com/user-attachments/assets/133935ca-c9fb-4727-bf41-9a30da473600" />

---

<img width="1654" height="374" alt="{1EDCDA18-B461-4F17-9F4F-63A65322D971}" src="https://github.com/user-attachments/assets/6855986e-d1ed-4e90-8947-996d40d67697" />

---

## Visão Geral

| Atributo | Detalhe |
|---|---|
| Frontend | SvelteKit 2 + Svelte 5 + Tailwind CSS 4.2.1 |
| Backend | FastAPI + Uvicorn + Python 3.11/3.12 |
| Banco de dados | SQLite via SQLAlchemy + Alembic |
| Inferência local | llama.cpp (binários baixados pelo instalador) |
| Porta padrão | 8080 |
| OS | Windows (principal); Linux/macOS somente com adaptações |

---

## Instalação

### Pré-requisitos

- **Python 3.11 ou 3.12** instalado e no PATH
- **Node.js 18+** instalado e no PATH (Opcional)
- Conexão com a internet (apenas durante a instalação)

### Executar o instalador

```bat
instalar.bat → Instalar
```

<h1 align="center">
<img width="781" alt="{8463A164-33B1-463F-BD22-27ADD721B656}" src="https://github.com/user-attachments/assets/3ea357fd-032c-4eaa-a895-fc435e9b5a01" />
</h1>

O instalador realiza automaticamente as seguintes ações:

1. **Detecta a GPU** — NVIDIA (identifica a série e configura CUDA), AMD (HIP/ROCm ou Vulkan) ou CPU
2. **Baixa o llama.cpp** mais recente do GitHub (binários compilados para o hardware detectado)
3. **Cria o ambiente virtual Python** (`backend/neveai/venv/`) e instala todas as dependências (PyTorch, FastAPI, ChromaDB, Whisper, etc.)
4. **Instala as dependências Node.js** (`npm install`)
5. **Compila e faz deploy do frontend** (`npm run build` + cópia para `backend/neveai/frontend/`)
6. **Cria as pastas necessárias** (`models/`, `mmproj/`, `backend/data/`, `logs/`)
7. **Cria o arquivo `.env`** com configurações padrão (se ainda não existir)

---

## Atualizando a NeveAI

```bat
instalar.bat → Atualizar
```

<h1 align="center">
<img width="781" alt="{B1C7232C-0F8D-4E74-8FE6-963D284FED4B}" src="https://github.com/user-attachments/assets/469a93d7-4c0c-4660-83e4-bb543327046c" />
</h1>

O atualizador realiza automaticamente as seguintes ações:

1. **Lê a versão local** do arquivo `version.txt` na raiz do projeto.
2. **Consulta a última release** em [github.com/Etamus/NeveAI/releases/latest](https://github.com/Etamus/NeveAI/releases/latest) e mostra:
   - versão instalada × versão disponível
   - status: **Atualizado**, **Pendente** (`vX → vY`) ou **Erro de rede**
3. Se já estiver na última versão, exibe **"Você já está na última versão"** e oferece apenas o botão **Fechar** (nada é baixado).
4. Se houver atualização pendente, ao clicar em **Atualizar**:
   - Baixa o `zipball` da release no `%TEMP%`
   - Aplica os arquivos novos sobre o projeto via `robocopy`, **preservando** dados locais: `backend/neveai/venv/`, `backend/neveai/frontend/`, `backend/neveai/data/`, `backend/data/`, `models/`, `mmproj/`, `llamacpp-server/`, `node_modules/`, `build/`, `logs/`, `.git/`, `.svelte-kit/`, `.env` e `version.txt` (com backup automático do `.env`)
   - Roda `npm install` e `npm run build`
   - Recria `backend/neveai/frontend/` com o novo build
   - Grava o novo tag em `version.txt`
5. Painel final mostra **"Atualização concluída!"** com o resumo `versão anterior → versão instalada`.

---

## Iniciando a NeveAI

```bat
iniciar.bat
```

O script:
1. Encerra qualquer processo existente na porta 8080
2. Inicia o backend Uvicorn em segundo plano (que já serve o frontend compilado)
3. Aguarda o health check (`http://localhost:8080/health`) por até 120 segundos
4. Abre o NeveAI em uma **janela de app isolada** via `neve_window.py` (usa Chrome/Brave/Edge em modo `--app`, sem barra de URL)

Acesse manualmente se preferir: **http://localhost:8080**

---

## Modelos

<h1 align="center">
<img width="700" alt="Guia de Hardware Atualizado" src="https://github.com/user-attachments/assets/13c6a0eb-8e72-4560-ab12-0fcdd7cb8342" />
</h1>

---

### Modelos de linguagem (LLM)

Coloque arquivos `.gguf` em:

```
NeveAI\models\
```

Os modelos são carregados dinamicamente pelo painel de modelos da interface. O llama.cpp é iniciado automaticamente ao carregar um modelo, com auto-detecção do arquivo mmproj correspondente quando disponível.

### Projeções multimodais (visão)

Coloque arquivos mmproj em:

```
NeveAI\mmproj\
```

O backend auto-detecta o mmproj compatível pelo prefixo do nome do modelo (ex: `Qwen3.5 9B.gguf` → `Qwen3.5 9B Mmproj F16.gguf`).

---

## Estrutura do Projeto

```
NeveAI/
├── instalar.bat              # Abre o Neve Hub para instalar, atualizar ou buildar
├── depurar.bat               # Inicia o NeveAI mantendo o console de diagnóstico
├── launchers/                # Scripts PowerShell e VBS usados pelos launchers
├── version.txt               # Versão (tag) atualmente instalada
├── iniciar.bat               # Inicia o backend e abre a janela de app
├── neve_window.py            # Abre o NeveAI em janela Chromium isolada
├── .env                      # Variáveis de ambiente (gerado pelo instalar)
├── .gitignore                # Exclui pastas pesadas (venv, build, models, etc.)
│
├── src/                      # Código-fonte do frontend SvelteKit
│   ├── routes/               # Páginas e layouts
│   └── lib/
│       └── components/
│           ├── chat/         # Interface de chat, modelos, mensagens
│           ├── layout/       # Sidebar, navbar, modais globais
│           ├── workspace/    # Editor de modelos, prompts, knowledge
│           ├── admin/        # Painel administrativo
│           └── common/       # Componentes reutilizáveis
│
├── backend/
│   ├── data/                 # Caches de runtime
│   └── neveai/
│       ├── main.py           # Entry point FastAPI
│       ├── config.py         # Configuração global
│       ├── routers/          # Endpoints REST (chat, models, audio, images...)
│       ├── socket/           # WebSocket (python-socketio)
│       ├── retrieval/        # Motor RAG (ChromaDB, embeddings, BM25)
│       ├── migrations/       # Alembic migrations
│       ├── venv/             # Ambiente virtual Python [gerado pelo instalar]
│       ├── frontend/         # Frontend compilado [gerado pelo instalar]
│       └── data/             # uploads/, vector_db/, cache/, neve.db [runtime]
│
├── build/                    # Saída do npm run build [gerado, não commitado]
├── models/                   # Arquivos .gguf (usuário baixa os seus)
├── mmproj/                   # Projeções multimodais .gguf
├── llamacpp-server/
│   └── bin/                  # Binários llama.cpp [baixados pelo instalar]
├── logs/                     # Logs de runtime [não commitado]
└── static/                   # Assets estáticos do frontend (pyodide, wasm...)
```
---

## Funcionalidades

### Chat & Modelos
- Streaming de respostas em tempo real via WebSocket
- **Modo Rápido / Raciocínio** — alternável com descrição no dropdown
- **Contador de tokens** com alerta visual por faixa de uso
- Auto-carga de modelo ao enviar mensagem (modal de seleção de contexto)
- Auto-detecção de mmproj compatível (sem configuração manual)
- Histórico de conversas com pastas e arquivamento
- Edição e regeneração de mensagens individuais

### Interface
- Sidebar retrátil com busca, projetos e histórico
- Campo de digitação compacto (pill) ou expandido
- **Painel de artefatos** (código, gráficos, HTML renderizado)
- Tema claro/escuro

### Entrada
- Upload de arquivos: PDF, DOCX, PPTX, imagens, áudios, vídeos, códigos, planilhas

### RAG (Retrieval-Augmented Generation)
- Base de conhecimento vetorial com ChromaDB
- Busca híbrida BM25 + semântica
- OCR para PDFs e imagens escaneadas (RapidOCR)
- Embeddings locais (sentence-transformers) ou via API

### Outras Funcionalidades
- **Busca na web** via SearXNG (sem chave de API)
- **Execução de código Python** via Pyodide (WebAssembly, no browser)
- **Geração de imagens** via Neve-Image-Turbo local em Q4_0 com Encoder, stable-diffusion.cpp e 8 steps
- **Geração de músicas** via Neve-Step 1.5 Turbo local, com orientação de estilo e letras em português
- **MCP (Model Context Protocol)** v1.26 para ferramentas externas

---

## Stack Tecnológica

### Frontend

| Tecnologia | Versão |
|---|---|
| Svelte | 5.0.0 |
| SvelteKit | 2.5.27 |
| TypeScript | 5.5.4 |
| Vite | 5.4.21 |
| Tailwind CSS | 4.2.1 |
| TipTap (editor) | 3.0.7+ |
| CodeMirror | 6.x |
| Pyodide | Embutido |

### Backend

| Tecnologia | Versão |
|---|---|
| Python | 3.11 / 3.12 |
| FastAPI | 0.135.1 |
| Uvicorn | 0.41.0 |
| Pydantic | 2.12.5 |
| SQLAlchemy | 2.0.48 |
| ChromaDB | — |
| MCP SDK | 1.26.0 |

---

## Desenvolvimento

### Compilar e fazer deploy manualmente

```powershell
cd "c:\NeveAI"
npm run build
Copy-Item -Path "build\*" -Destination "backend\neveai\frontend" -Recurse -Force
```

Ou de forma automática via
```bat
instalar.bat → Buildar
```

<h1 align="center">
<img width="778" alt="{767081D2-462D-4E97-A1FF-8B1F3A027F0F}" src="https://github.com/user-attachments/assets/eea2377c-27da-435d-8ace-264306a70a5e" />
</h1>

### Dev mode (hot reload)

```powershell
# Terminal 1 — Backend
cd "c:\NeveAI\backend"
..\backend\neveai\venv\Scripts\python -m uvicorn neveai.main:app --host 0.0.0.0 --port 8080 --reload

# Terminal 2 — Frontend
cd "c:\NeveAI"
npm run dev

Frontend de dev disponível em `http://localhost:5173` (proxy para o backend em 8080).
```

---

## Informações Legais

Copyright (c) 2026 Mateus Lopes. Todos os direitos reservados.

"NeveAI" e sua identidade visual são marcas/propriedade de Mateus Lopes. Este repositório é a fonte oficial do projeto. Qualquer cópia, redistribuição ou modificação deve preservar a atribuição ao autor original conforme LICENSE.txt.