# Janela Windows com WebView2 Fixed

O launcher usa `neve_window.py` e um pequeno host WinForms compilado de
`NeveWindow.cs`. Nao utiliza `--app`, Electron nem o WebView2 Evergreen instalado
no sistema. Backend, frontend web e acesso pelo celular continuam independentes.

## Instalacao e atualizacao

`instalar.bat` delega a `launchers/instalar.ps1`, que executa
`desktop/setup_runtime.py` na instalacao e na atualizacao do aplicativo.
O instalador baixa os pacotes oficiais fixados em `runtime.json`, verifica SHA256,
valida as assinaturas Microsoft do runtime e compila o host usando o compilador
do .NET Framework do Windows. Nao instala um novo SDK .NET global.

Os arquivos gerados ficam em `.desktop/`, ignorada pelo Git. O perfil da janela
fica em `logs/webview2/profile`. O primeiro download requer internet; a reutilizacao
de uma instalacao integra nao requer baixar novamente. `iniciar.bat` verifica a
instalacao antes de abrir a janela. Nao existe fallback silencioso para navegador.

Plataforma desta implementacao: Windows x64 com .NET Framework do sistema.
O runtime 156.0.4314.42 ocupa aproximadamente 673,5 MiB extraido; o CAB em cache
ocupa mais 295,8 MiB, alem do SDK e do perfil. Nao incluir esses binarios no Git.

O Fixed Runtime nao se atualiza sozinho. Para atualizar sua seguranca, atualizar
URLs, versoes e hashes de `runtime.json` e testar a nova versao antes de distribuir.
Diretorios versionados e a publicacao atomica de `installed.json` evitam substituir
binarios em uso. O atualizador preserva `.desktop` e guarda o ponteiro anterior
para rollback. Nao apagar diretorios de runtime/host usados por processos ativos.

## Preferencias e integracao

A primeira abertura migra localStorage do perfil exclusivo antigo
`logs/browser-app`, sem apagar esse perfil. Essa transferencia unica precisa do
navegador anteriormente usado, caso exista um perfil antigo. Depois da migracao,
a janela nao depende dele. Cookies e extensoes do navegador nao sao migrados.
Chats e arquivos continuam no backend original. Geometria da janela e preferencias
locais sao preservadas; a janela so aparece apos o frontend sinalizar prontidao.

Downloads, popups locais/PDF, links externos pelo navegador padrao, clipboard,
WebSocket e temas sao tratados pelo host. O bridge so aceita mensagens de tema e
prontidao da origem local; nao expoe execucao arbitraria de comandos. O encerramento
do aplicativo reconhece apenas os processos WebView2 deste projeto.

`NEVE_WEBVIEW2_DEBUG_PORT` e `NEVE_WEBVIEW2_TEST_MODE` existem para diagnostico
explicito. Nao definir essas variaveis na instalacao de uso normal.

## Validacao reproduzivel

Executar a partir da raiz do projeto:

```powershell
backend/neveai/venv/Scripts/python.exe desktop/setup_runtime.py --check
backend/neveai/venv/Scripts/python.exe -m unittest tests.test_window_identity
backend/neveai/venv/Scripts/python.exe scripts/test_desktop_packaging.py
node scripts/test_desktop_webview.mjs
```

O teste de empacotamento usa cache verificado e uma pasta isolada com espacos.
O teste nativo usa perfil isolado, backend local em funcionamento, Playwright 1.55
em `logs/ui-image-26/node_modules` e fixtures produzidas por
`scripts/create_desktop_media_fixtures.py`. Nao executar testes de janelas em
paralelo, pois disputam o foco do Windows. Os testes nao geram imagens por IA.

Distribuicao oficial e requisitos do Fixed Runtime:
https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution
