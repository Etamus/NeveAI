# Contribuindo para a NeveAI

Obrigado pelo seu interesse em contribuir para a NeveAI!

A NeveAI é uma plataforma de IA local-first, focada em privacidade, construída em torno de FastAPI, SvelteKit, llama.cpp, modelos GGUF, RAG híbrido, execução de código baseada em Pyodide e fluxos de trabalho offline-first. Contribuições de todos os tipos são bem-vindas, seja corrigindo bugs, melhorando a documentação, testando configurações de hardware, refinando a interface ou propondo novos recursos.

## Formas de Contribuir

Você pode ajudar a NeveAI de várias formas:

* **Reportar Bugs**: Abra uma issue quando algo não estiver funcionando como esperado.
* **Sugerir Recursos**: Compartilhe ideias que melhorem fluxos de trabalho de IA local, privacidade, usabilidade, desempenho ou suporte a modelos.
* **Melhorar a Documentação**: Ajude a tornar as instruções de instalação, uso, solução de problemas e desenvolvimento mais claras.
* **Corrigir Problemas**: Envie pull requests que resolvam bugs, melhorem a estabilidade ou simplifiquem a base de código.
* **Melhorar o Frontend**: Trabalhe na interface SvelteKit, componentes, layout, acessibilidade ou experiência do usuário.
* **Melhorar o Backend**: Trabalhe em rotas FastAPI, comportamento de WebSocket, RAG, carregamento de modelos, lógica de banco de dados ou ferramentas locais.
* **Testar Suporte de Hardware**: Ajude a testar configurações NVIDIA, AMD, Vulkan, ROCm ou somente CPU.
* **Compartilhar Feedback**: Conte-nos como a NeveAI se comporta na sua máquina e o que poderia ser melhorado.

Mesmo pequenas contribuições são valiosas. Um relatório de bug claro, uma correção de erro de digitação, uma captura de tela ou uma reprodução testada podem economizar muito tempo.

## Antes de Começar

Antes de abrir uma issue ou pull request:

1. Pesquise issues e pull requests existentes para evitar duplicatas.
2. Certifique-se de que sua cópia local está atualizada com a branch `main`.
3. Mantenha suas alterações focadas em um único assunto sempre que possível.
4. Evite fazer commit de arquivos gerados, dados locais, modelos, logs, ambientes virtuais ou arquivos de configuração privados.

## Requisitos de Desenvolvimento

A NeveAI é desenvolvida principalmente para Windows.

Requisitos recomendados:

* Python 3.11 ou 3.12
* Node.js 18 ou mais recente
* Git
* PowerShell
* Uma GPU compatível é recomendada, mas testes somente com CPU também são úteis
* Acesso à internet apenas durante a instalação

Linux e macOS podem exigir adaptações. Contribuições que melhorem o suporte multiplataforma são bem-vindas, mas descreva claramente o sistema operacional e o ambiente usados para os testes.

## Configuração do Projeto

Clone o repositório:

```bash
git clone https://github.com/Etamus/NeveAI.git
cd NeveAI
```

No Windows, execute o instalador:

```bat
instalar.bat
```

O instalador prepara o ambiente Python, instala as dependências do Node.js, baixa os binários necessários do llama.cpp, compila o frontend, cria as pastas de execução e prepara a configuração padrão.

Após a instalação, inicie a NeveAI com:

```bat
iniciar.bat
```

Por padrão, a NeveAI roda em:

```text
http://localhost:8080
```

## Modo de Desenvolvimento

Para desenvolvimento com hot reload, execute o backend e o frontend separadamente.

### Backend

```powershell
cd "c:\NeveAI\backend"
..\backend\neveai\venv\Scripts\python -m uvicorn neveai.main:app --host 0.0.0.0 --port 8080 --reload
```

### Frontend

```powershell
cd "c:\NeveAI"
npm run dev
```

O frontend de desenvolvimento estará disponível em:

```text
http://localhost:5173
```

O servidor de desenvolvimento do frontend encaminha as requisições para o backend em execução na porta `8080`.

## Compilando o Projeto

Para compilar o frontend manualmente:

```powershell
npm run build
```

Em seguida, copie a build gerada do frontend para o diretório frontend do backend:

```powershell
Copy-Item -Path "build\*" -Destination "backend\neveai\frontend" -Recurse -Force
```

Você também pode usar os scripts de build fornecidos, quando disponíveis:

```bat
buildar.bat
```

## Estilo de Código

Mantenha a base de código limpa, legível e consistente com o estilo existente.

Para alterações no frontend:

```bash
npm run check
npm run lint:frontend
npm run format
```

Para alterações no backend:

```bash
npm run lint:backend
npm run format:backend
```

Antes de enviar uma pull request, execute as verificações relevantes para os arquivos que você alterou.

## O Que Não Fazer Commit

Não faça commit de arquivos locais de execução, pastas geradas, configurações privadas, modelos baixados ou dados específicos da máquina.

Evite fazer commit de:

```text
.env
backend/neveai/venv/
backend/neveai/frontend/
backend/neveai/data/
backend/data/
models/
mmproj/
llamacpp-server/
node_modules/
build/
logs/
.svelte-kit/
```

Se sua alteração exigir modificar saída gerada, explique o motivo na pull request.

## Reportando Bugs

Ao reportar um bug, inclua o máximo possível de informações úteis.

Um bom relatório de bug deve incluir:

* Um título claro
* Uma breve explicação do que aconteceu
* O que você esperava que acontecesse
* Etapas para reproduzir o problema
* Seu sistema operacional
* Versão do Python
* Versão do Node.js
* Modelo da GPU, se relevante
* Se você está usando CUDA, Vulkan, ROCm ou CPU
* O formato e tipo do modelo, se estiver relacionado a modelos
* Capturas de tela, logs ou saída de traceback quando disponíveis

Remova informações privadas dos logs antes de publicá-los publicamente.

## Sugerindo Recursos

Solicitações de recursos são bem-vindas.

Ao sugerir um recurso, descreva:

* O problema que você está tentando resolver
* Por que o recurso seria útil para os usuários da NeveAI
* Como você imagina que o recurso funcionaria
* Quais alternativas você considerou
* Se o recurso deve funcionar totalmente offline

Como a NeveAI é focada em IA local-first e privacy-first, recursos que exigem serviços externos, APIs em nuvem, telemetria ou contas de terceiros devem ser claramente explicados e opcionais.

## Diretrizes para Pull Requests

Ao enviar uma pull request:

1. Faça um fork do repositório.
2. Crie uma nova branch com um nome descritivo.
3. Mantenha suas alterações focadas e fáceis de revisar.
4. Atualize a documentação quando o comportamento mudar.
5. Teste suas alterações localmente.
6. Não inclua alterações de formatação não relacionadas.
7. Não faça commit de arquivos gerados ou dados da máquina local.
8. Explique o que mudou e por quê.

Exemplos de nomes de branches:

```text
fix/model-loading-error
feature/rag-source-preview
docs/improve-windows-setup
ui/chat-message-actions
```

## Checklist de Pull Request

Antes de abrir uma pull request, verifique se:

* O projeto compila com sucesso.
* As verificações relevantes do frontend ou backend foram executadas.
* A alteração foi testada localmente.
* A documentação foi atualizada, se necessário.
* Nenhum arquivo privado, modelo, log ou pasta gerada foi incluído no commit.
* A descrição da pull request explica claramente a alteração.
* Capturas de tela ou gravações foram incluídas para alterações de UI quando úteis.

## Contribuições para a Documentação

Melhorias na documentação são muito apreciadas.

Você pode ajudar melhorando:

* Instruções de instalação
* Notas de configuração no Windows
* Notas de configuração de GPU
* Uso de modelos e `mmproj`
* Documentação de RAG
* Guias de solução de problemas
* Capturas de tela e exemplos
* Instruções de fluxo de trabalho para desenvolvedores

Mantenha a documentação prática, direta e fácil de seguir.

## Segurança e Privacidade

A NeveAI foi projetada em torno da execução local e da soberania dos dados. As contribuições devem respeitar esse objetivo.

Evite adicionar recursos que:

* Enviem dados do usuário para serviços externos sem consentimento claro
* Exijam APIs em nuvem para funcionalidades principais
* Adicionem telemetria por padrão
* Exponham arquivos locais, prompts, conversas ou dados de modelos
* Armazenem segredos no código-fonte
* Registrem dados sensíveis do usuário desnecessariamente

Se você descobrir um problema de segurança, não abra uma issue pública com detalhes de exploração. Em vez disso, entre em contato com o mantenedor do projeto em particular.

## Padrões da Comunidade

Seja respeitoso e construtivo em todas as interações.

Ao participar deste projeto, você concorda em seguir o Código de Conduta do projeto:

```text
https://github.com/Etamus/NeveAI/blob/main/CODE_OF_CONDUCT.md
```

## Obrigado

Obrigado por ajudar a melhorar a NeveAI.

Seja sua contribuição código, testes, documentação, feedback ou simplesmente compartilhar o projeto, isso ajuda a tornar a IA local-first mais acessível, privada e poderosa para todos.