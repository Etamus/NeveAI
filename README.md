<img width="1400" height="350" alt="1776513530968" src="https://github.com/user-attachments/assets/abfd31c4-4ba6-4790-8f64-61c83ac0fdfc" />

---

**Neve AI** é um ecossistema de orquestração de IA privacy-first, desenvolvido para oferecer uma experiência de inferência local de alta performance com soberania total de dados. A plataforma integra um backend assíncrono em FastAPI a uma interface reativa em SvelteKit 5, utilizando o motor llama.cpp para viabilizar o suporte a modelos GGUF com aceleração de hardware (CUDA/Vulkan). O projeto consolida funcionalidades avançadas de nível empresarial em um ambiente 100% offline, incluindo um pipeline de RAG híbrido (ChromaDB/BM25), execução de código em sandbox via Pyodide, automação de busca web e ferramentas de produtividade, eliminando qualquer dependência de APIs externas ou serviços de terceiros.

---

<img width="1918" height="1008" alt="{CB39D918-42A2-4334-BDDE-09DC11A0057C}" src="https://github.com/user-attachments/assets/5fb399ec-e2eb-470a-a844-311e326ae55e" />

---

<img width="1656" height="379" alt="{F197E691-096C-4BC1-9EC3-27D56D5A7B06}" src="https://github.com/user-attachments/assets/611c6dec-7f2c-4a97-bc32-12b9c0556fbf" />

---

## Visão Geral

| Atributo | Detalhe |
|---|---|
| Versão | 0.8.10 |
| Frontend | SvelteKit 2 + Svelte 5 + Tailwind CSS 4.2.1 |
| Backend | FastAPI + Uvicorn + Python 3.11/3.12 |
| Banco de dados | SQLite via SQLAlchemy + Alembic |
| Inferência local | llama.cpp (binários baixados pelo instalador) |
| Porta padrão | 8080 |
| OS | Windows (principal); Linux/macOS somente com adaptações |

---

<img width="1128" height="191" alt="neveai_cover" src="https://github.com/user-attachments/assets/09383a14-20c2-48fb-9eff-753ec710cff9" />

---

## Instalação

### Pré-requisitos

- **Python 3.11 ou 3.12** instalado e no PATH
- **Node.js 18+** e **npm 9+** instalados e no PATH
- Conexão com a internet (apenas durante a instalação)

### Executar o instalador

```bat
instalar.bat
```

O instalador (`instalar.bat` → `instalar.ps1`) realiza automaticamente:

1. **Detecta a GPU** — NVIDIA (identifica a série e configura CUDA), AMD (HIP/ROCm ou Vulkan) ou CPU
2. **Baixa o llama.cpp** mais recente do GitHub (binários compilados para o hardware detectado)
3. **Cria o ambiente virtual Python** (`backend/neveai/venv/`) e instala todas as dependências (PyTorch, FastAPI, ChromaDB, Whisper, etc.)
4. **Instala as dependências Node.js** (`npm install`)
5. **Compila e faz deploy do frontend** (`npm run build` + cópia para `backend/neveai/frontend/`)
6. **Cria as pastas necessárias** (`models/`, `mmproj/`, `backend/data/`, `logs/`)
7. **Cria o arquivo `.env`** com configurações padrão (se ainda não existir)

> O log completo da instalação fica em `logs/install.log`.

---

## Iniciando o Neve AI

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

### Modelos de linguagem (LLM)

Coloque arquivos `.gguf` em:

```
d:\Neve AI\models\
```

Os modelos são carregados dinamicamente pelo painel de modelos da interface. O llama.cpp é iniciado automaticamente ao carregar um modelo, com auto-detecção do arquivo mmproj correspondente quando disponível.

### Projeções multimodais (visão)

Coloque arquivos mmproj em:

```
d:\Neve AI\mmproj\
```

O backend auto-detecta o mmproj compatível pelo prefixo do nome do modelo (ex: `Qwen3.5 9B.gguf` → `Qwen3.5 9B Mmproj F16.gguf`).

---

## Estrutura do Projeto

```
Neve AI/
├── instalar.bat              # Instalador único — detecta GPU, baixa llama.cpp,
├── instalar.ps1              #   cria venv, instala deps, compila frontend
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
│       └── data/             # uploads/, vector_db/, cache/, webui.db [runtime]
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
- Múltiplos modelos simultâneos (comparação lado a lado)
- **Modo Rápido / Raciocínio** — alternável com descrição no dropdown
- **Contador de tokens** circular com alerta visual por faixa de uso
- Auto-carga de modelo ao enviar mensagem (modal de seleção de contexto)
- Auto-detecção de mmproj compatível (sem configuração manual)
- Histórico de conversas com pastas, favoritos, tags e arquivamento
- Edição e regeneração de mensagens individuais

### Interface
- Sidebar retrátil com busca, pastas e histórico
- Campo de digitação compacto (pill) ou expandido
- **Painel de artefatos** (código, gráficos, HTML renderizado)
- Tela de boas-vindas com posicionamento alto e limpo
- Tema claro/escuro

### Entrada
- Upload de arquivos: PDF, DOCX, PPTX, imagens, vídeo, código, planilhas
- Integração Google Drive e OneDrive

### RAG (Retrieval-Augmented Generation)
- Base de conhecimento vetorial com ChromaDB
- Busca híbrida BM25 + semântica
- OCR para PDFs e imagens escaneadas (RapidOCR)
- Embeddings locais (sentence-transformers) ou via API

### Outras Funcionalidades
- **Busca na web** via DuckDuckGo (sem chave de API)
- **Execução de código Python** via Pyodide (WebAssembly, no browser)
- **Geração de imagens** via Stable Diffusion local
- **MCP (Model Context Protocol)** v1.26 para ferramentas externas
- Painel administrativo completo (usuários, modelos, permissões, analytics)

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
| Pyodide | embutido |

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
cd "d:\Neve AI"
npm run build
Copy-Item -Path "build\*" -Destination "backend\neveai\frontend" -Recurse -Force
```

### Dev mode (hot reload)

```powershell
# Terminal 1 — Backend
cd "d:\Neve AI\backend"
..\backend\neveai\venv\Scripts\python -m uvicorn neveai.main:app --host 0.0.0.0 --port 8080 --reload

# Terminal 2 — Frontend
cd "d:\Neve AI"
npm run dev
```

Frontend de dev disponível em `http://localhost:5173` (proxy para o backend em 8080).
