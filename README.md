<img width="1400" height="350" alt="Banner" src="https://github.com/user-attachments/assets/8d8de5c3-2c9d-4777-92da-efcb70ea1ac3" />

---

**Neve AI** é um ecossistema local de orquestração de IA privacy-first, desenvolvido para oferecer uma experiência de alta performance na execução de LLMs de forma acessível, privada e independente. O projeto busca reduzir a dependência de grandes plataformas, assinaturas caras e APIs externas, oferecendo ao usuário uma alternativa própria para conversar com modelos, trabalhar com documentos, automatizar tarefas e explorar o potencial da inteligência artificial diretamente no computador. O projeto consolida funcionalidades avançadas de nível empresarial em um ambiente completamente offline, integrando um backend assíncrono em FastAPI a uma interface reativa em SvelteKit 5 e utilizando o motor llama.cpp para viabilizar o suporte a modelos GGUF com aceleração de hardware via CUDA/Vulkan.

---

<img width="1919" height="1010" alt="{F622C17A-A4A8-4FA2-BB18-50FD99AB9A2D}" src="https://github.com/user-attachments/assets/c563bf45-299c-4fee-8829-db625b464805" />

---

<img width="1659" height="410" alt="{67C684F2-FDD6-499D-BB0E-42745276867F}" src="https://github.com/user-attachments/assets/eb1a0148-65f9-44c8-8e19-f1700dd3fe5b" />

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

## Atualizando a Neve AI

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

## Iniciando a Neve AI

```bat
iniciar.bat
```

O script:
1. Encerra qualquer processo existente na porta 8080
2. Inicia o backend Uvicorn em segundo plano (que já serve o frontend compilado)
3. Aguarda o health check (`http://localhost:8080/health`) por até 120 segundos
4. Abre o Neve AI em uma **janela de app isolada** via `neve_window.py` (usa Chrome/Brave/Edge em modo `--app`, sem barra de URL)

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
Neve AI\models\
```

Os modelos são carregados dinamicamente pelo painel de modelos da interface. O llama.cpp é iniciado automaticamente ao carregar um modelo, com auto-detecção do arquivo mmproj correspondente quando disponível.

### Projeções multimodais (visão)

Coloque arquivos mmproj em:

```
Neve AI\mmproj\
```

O backend auto-detecta o mmproj compatível pelo prefixo do nome do modelo (ex: `Qwen3.5 9B.gguf` → `Qwen3.5 9B Mmproj F16.gguf`).

---

## Estrutura do Projeto

```
Neve AI/
├── instalar.bat              # Instalador único — detecta GPU, baixa llama.cpp,
├── instalar.ps1              #   cria venv, instala deps, compila frontend
├── atualizar.bat             # Atualizador — checa última release no GitHub,
├── atualizar.ps1             #   baixa, aplica overlay, refaz build e deploy
├── buildar.bat               # Build e deploy do frontend com interface grafica
├── buildar.ps1               #   limpa build, compila, publica e valida hash
├── version.txt               # Versão (tag) atualmente instalada
├── iniciar.bat               # Inicia o backend e abre a janela de app
├── neve_window.py            # Abre o Neve AI em janela Chromium isolada
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
cd "c:\Neve AI"
npm run build
Copy-Item -Path "build\*" -Destination "backend\neveai\frontend" -Recurse -Force
```

Ou de forma automática via
```bat
instalar.bat → Buildar
```

<h1 align="center">
<img width="781" alt="{C01EC582-F13F-4CC0-BFC9-93D0D1A52B1C}" src="https://github.com/user-attachments/assets/fec18717-6fc5-4296-abb2-4d1360d86a78" />
</h1>

### Dev mode (hot reload)

```powershell
# Terminal 1 — Backend
cd "c:\Neve AI\backend"
..\backend\neveai\venv\Scripts\python -m uvicorn neveai.main:app --host 0.0.0.0 --port 8080 --reload

# Terminal 2 — Frontend
cd "c:\Neve AI"
npm run dev

Frontend de dev disponível em `http://localhost:5173` (proxy para o backend em 8080).
```

---

## Informações Legais

Copyright (c) 2026 Mateus Lopes. Todos os direitos reservados.

"Neve AI" e sua identidade visual são marcas/propriedade de Mateus Lopes. Este repositório é a fonte oficial do projeto. Qualquer cópia, redistribuição ou modificação deve preservar a atribuição ao autor original conforme LICENSE.txt.