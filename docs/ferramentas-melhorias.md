# Melhorias de Ferramentas

## Implementado

- Com Ferramentas explicitamente ativo, qualquer pedido textual entra no fluxo
  de documento, sem filtro de palavras-chave. Perguntas geram um relatorio;
  pedidos amplos como "Melhore a historia" revisam o anexo no formato original.
  Uma recusa/falha do planejador usa um plano alternativo; anexos sem leitura ou
  planejamento impossivel geram erro explicito, nunca retorno silencioso ao chat.
  Com o toggle desligado, o chat normal nao executa esse planejamento.
- Edicao localizada de DOCX, XLSX e PPTX no pacote original, em uma nova versao.
  Partes nao selecionadas permanecem byte a byte iguais, incluindo imagens,
  estilos, relacionamentos e extensoes que conversores podem descartar.
- Substituicoes distribuidas nos runs originais, sem achatar toda a formatacao.
  Em XLSX, uma string compartilhada e clonada para a celula selecionada, sem
  alterar outras celulas que usam a mesma string; rich text e preservado.
- Formatacao localizada de paragrafos DOCX/PPTX: negrito, italico, sublinhado,
  fonte, tamanho, cor e alinhamento, sem exigir reescrever o texto.
- Formatacao de palavras/trechos DOCX/PPTX, inclusive atravessando runs, com
  selecao explicita da ocorrencia. Alinhamento continua sendo por paragrafo.
- Inspecao paginada, IDs de elementos, texto anterior exato, tipos de celulas,
  inventario de objetos, hash da fonte e rejeicao de versoes desatualizadas.
- Planejamento distingue alteracoes locais de resumo, reescrita integral,
  conversao e criacao. O pedido original em portugues guia a edicao, com
  contexto recente limitado para referencias a pedidos anteriores.
- Edicao localizada de texto UTF-8, UTF-16, UTF-32 e Windows-1252, preservando
  BOM, codificacao e terminadores de linha, inclusive em substituicoes multiline.
  Caracteres incompativeis geram conversao explicita para UTF-8 com aviso;
  declaracoes de codificacao XML/Python acompanham a conversao.
- PDF: edicao do operador simples ou de objetos Unicode, inclusive fontes
  incorporadas e texto fragmentado. Verifica texto e pixels fora da area
  autorizada. Fontes sem os glifos novos e alteracoes que exigem mais espaco
  usam reconstrucoes limitadas as paginas afetadas, com aviso de novo layout.
- Substituicao explicita entre aspas usa correspondencia deterministica,
  tolerando espacos e quebras de linha diferentes, inclusive entre elementos.
  Ocorrencias ambiguas e elementos protegidos nao sao alterados arbitrariamente.
- Pedidos literais podem selecionar primeira, segunda, ultima ou todas as
  ocorrencias. Trechos inexistentes nao provocam uma reescrita inventada.
- Substituicoes XLSX preservam os tipos de celulas quando compativeis: numeros,
  booleanos, texto e formulas. Texto iniciado por '=' nao vira formula sozinho.
- Respostas JSON invalidas do planejador recebem uma tentativa limitada de
  correcao. Pedidos para preservar formatacao nao liberam campos de estilo;
  pedidos para formatar apenas uma palavra exigem um alvo textual explicito.
- PDF usa fontes de fallback somente quando necessario; glifos indisponiveis
  geram erro explicito em vez de desaparecerem do documento silenciosamente.
- OCR local com RapidOCR, apenas quando necessario em paginas digitalizadas,
  usando CPU e dois threads. Leitura/extracao roda fora do event loop do chat.
  Cache limitado a quatro PDFs e invalidado pelo tamanho/data de modificacao.
- Extracao DOCX preserva a ordem entre paragrafos e tabelas no contexto.
- Arquivos gerados sem conteudo RAG tambem podem servir como fonte de edicao.
- Validacao independente dos bytes publicados: pacote/XML, schema OfficeCLI,
  quantidade de planilhas/slides, PDF, ZIP, JSON, XML, YAML e RTF.
- Validacao de sintaxe Python respeitando a codificacao real; JSON rejeita
  chaves duplicadas e numeros nao finitos. XML rejeita DTD, inclusive em UTF-16.
- RTF real com escapes Unicode, incluindo caracteres fora do BMP. Leitura usa
  striprtf e normaliza pares substitutos UTF-16.
- Fim dos cortes silenciosos em 50 planilhas/100 slides: limites geram erros
  explicitos. Falhas de leitura e edicao nao provocam reescrita silenciosa.
- Originais imutaveis, nova versao com referencia ao original, hashes, contagem
  de alteracoes e preview limitado das diferencas. Isso evita devolver enormes
  diffs a LLM na resposta final e inflar o historico do chat.
- Auditorias semanticas indisponiveis/acima do contexto ficam registradas como
  avisos na validacao, em vez de serem confundidas com verificacao completa.

## Limites Que Continuam Reais

- Paridade com ChatGPT nao e uma garantia. Entender e executar pedidos continua
  dependendo da LLM, do contexto disponivel e da qualidade dos arquivos.
- Edicao localizada nao adiciona/remove/reorganiza elementos arbitrarios. Esses
  pedidos usam a reconstrucao existente, sem prometer layout original intacto.
  Nao e um editor universal de estilos de celulas ou de objetos graficos;
  runs com controles/objetos complexos nao sao divididos arbitrariamente.
- Nao foi instalado Word/LibreOffice nem um motor de recalculo Excel. Formulas
  sao preservadas ou alteradas explicitamente, e o arquivo solicita recalculo
  ao abrir. Validacao de schema nao verifica matematica ou fidelidade visual
  completa de Office; a comparacao visual implementada e para PDF simples.
- PDF com formularios graficos, rotacoes, glifos ausentes ou substituicao longa
  pode exigir novo layout. A reconstrucao preserva o texto, mas imagens e
  anotacoes das paginas editadas podem mudar; a resposta informa isso. Nao ha
  corte automatico do novo texto para fingir sucesso. Se o texto nao couber de
  forma legivel, o fluxo pede para dividir o pedido ou criar novo documento.
- OCR nao garante transcricao perfeita. Baixa confianca interrompe o fluxo.
  Texto dentro de imagens em paginas que tambem contem texto nativo nao ganha
  interpretacao visual geral automaticamente.
- Arquivos corrompidos, criptografados ou binarios disfarcados de texto podem
  ser rejeitados. Fontes instaladas limitam os alfabetos disponiveis em PDF;
  validacao sintatica nao comprova a semantica de todo codigo gerado.
- O preview das alteracoes nao e um diff completo, e nao foi criado um botao
  novo de desfazer. O original permanece disponivel e nunca e sobrescrito.
- Limites: 32 MB por arquivo, 128 MB descompactados em Office, 20.000 elementos,
  2.000 alteracoes, 32 blocos de edicao; PDF ate 200 paginas, OCR ate 30 paginas.
  Fontes acima de 4 milhoes de caracteres ou planilhas com area declarada acima
  de 1 milhao de celulas precisam ser divididas. Nao ha truncamento silencioso.

## Referencias Tecnicas

O patch direto evita a perda de objetos nao suportados em uma regravacao geral,
que a propria documentacao de [openpyxl](https://openpyxl.readthedocs.io/en/stable/tutorial.html#loading-from-a-file)
alerta ser possivel. PDF usa [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
para inspecao de operadores e [pypdfium2](https://pypdfium2.readthedocs.io/en/stable/python_api.html)
para renderizacao. OCR usa [RapidOCR](https://github.com/RapidAI/RapidOCR);
RTF usa [striprtf](https://pypi.org/project/striprtf/).
Fontes adicionais em PDF seguem o mecanismo de
[fallback de fpdf2](https://github.com/py-pdf/fpdf2/blob/master/docs/Unicode.md).

## Testes

Testes de preservacao de runs, tabelas, imagens, cabecalhos, rodapes, formulas,
graficos, validacoes e strings compartilhadas; casos negativos de IDs, hashes,
formato, limites e schema; publicacao de versoes sem alterar o original; OCR
real em PDF digitalizado; planejamento e edicao com Qwen3.5 9B local e pedidos
em portugues em DOCX, XLSX, PPTX, PDF simples e TXT. Nenhuma conversa do usuario
foi alterada para estes testes. Veja backend/tests/test_document_edits.py.

Verificacao inicial: 172 testes de backend (dois testes opcionais com LLM foram
executados separadamente com sucesso), 45 testes de frontend, nove testes da
janela, pip check sem conflitos, Svelte sem erros e build de producao concluida.
Neve Image 1.5 foi verificado em 60 combinacoes de largura (320-1280 px), tema e
chat novo/em andamento, tanto no servidor de desenvolvimento quanto na build.
Os 141 avisos de Svelte existentes nao foram eliminados nesta alteracao.

Correcao de PDF: 184 testes de backend, incluindo 12 novos casos de regressao
para fontes incorporadas, fragmentos, operadores TJ, OCR, rotacao, glifos ausentes,
reconstrucao, ambiguidade e substituicao literal sem reescrita por LLM. Dois testes
opcionais com LLM nao foram repetidos nesta rodada. O pedido exato do usuario em
Aquela que Permanece.pdf foi executado em copia: cinco paginas, substituicao por
Abobora, sem reconstruir layout, com verificacao de texto/pixels e fonte intacta.

## Cobertura Ampliada

A nova bateria backend/tests/test_document_scenarios.py inclui 25 testes com
subcasos para os 26 formatos de saida anunciados e 150 substituicoes literais
aleatorias reprodutiveis. Cobre BOM/codificacoes, quebras de linha, substituicoes
multiline, ocorrencias, tipos XLSX, estilos parciais DOCX/PPTX, reparacao limitada
de propostas, cancelamento, JSON invalido, Python, XML e fontes PDF. DOCX/XLSX/PPTX
tambem foram gerados pelo caminho preferencial OfficeCLI e pelo fallback.
Todos os 19 formatos de texto com edicao nativa foram editados e validados,
comparando os bytes para confirmar que o texto ao redor permaneceu intacto.

Criacao/validacao nos 26 formatos nao significa edicao nativa de todos eles:
edicao localizada e para DOCX, XLSX, PPTX, PDF e os formatos de texto suportados.
RTF e ZIP, por exemplo, usam seus caminhos de criacao/reconstrucao existentes.
O teste opcional com Qwen3.5 9B exercita pedidos em portugues e formatacao de
palavra isolada; os testes nao modificam as conversas nem os anexos originais.

Resultado desta rodada: 209 testes de backend, com dois opcionais pulados na
bateria geral e executados separadamente dentro dos 35 testes que passaram com
Qwen3.5 9B real. Frontend: 45 testes passaram; Svelte: zero erros, 141 avisos
preexistentes. pip check sem conflitos e compilacao Python sem erros. Nenhuma
mudanca de interface, dependencia nova ou alteracao nos scripts de inicializacao
foi necessaria nesta rodada. Reiniciar o backend ativa os novos modulos.

## Correcao Do Encaminhamento

O filtro de intencao ignorava "Melhore a historia" antes de chamar o planejador.
Esse filtro foi removido do modo ativo. O planejador agora recebe a obrigacao de
produzir um arquivo, com orcamento de resposta JSON maior para nao cortar planos.
Falhas de planejamento/leitura nao voltam ao fluxo comum. Titulos nao devem ser
inventados/traduzidos a partir do nome do arquivo.

Regressao: 216 testes backend, com tres opcionais nao executados na bateria geral;
o teste opcional de historia foi executado separadamente com Qwen3.5 9B e o PDF
do ultimo pedido do usuario. "Melhore a historia" gerou um PDF revisado, passou
pela auditoria de conteudo e validacao estrutural, manteve Kael/Lysa e nao alterou
o original nem o chat. Resultado em logs/ferramentas-validacao/Historia-melhorada.pdf.
Os testes verificam fallback diante de recusa/indisponibilidade do planejador,
pedidos curtos, perguntas, anexos sem leitura, cancelamento e toggle desligado.

## Resumos E Verificacao Do Objetivo

A classificacao secundaria de conversao nao pode mais apagar operacoes semanticas
declaradas. A copia estrutural e bloqueada quando existe resumo, traducao, revisao
ou selecao. Pedidos explicitos de resumo corrigem planos contraditorios; palavras
entre aspas e pedidos para nao resumir nao sao tratados como esse comando.
Resumos e selecoes permitem omissoes, mas tambem recebem auditoria do objetivo,
dos fatos essenciais e de conteudo inventado. Falhas da auditoria impedem entrega
como sucesso. Resumos globais quase do tamanho do original recebem uma tentativa
limitada de reparacao; resumos de trechos nao exigem reduzir as partes intactas.

O pedido real "Resuma o conteudo do pdf" foi repetido com o Qwen3.5 9B e o PDF
original: 16.810 caracteres de entrada e 8.461 de saida, auditados e validados.
Outro teste com limite de cinco topicos produziu 3.109 caracteres. PDFs de teste
em logs/ferramentas-validacao/Historia-resumida.pdf e Historia-resumida-5-topicos.pdf.
Conversas e fontes originais permaneceram intactas. A bateria passou com 223 testes
backend (tres opcionais executados separadamente nas baterias com modelo real),
45 frontend, Svelte sem erros e build concluida; os 141 avisos existentes permanecem.

A interface recebeu uma mascara visual acima da barra em chats em andamento e
centralizacao do icone de erro. O ajuste anterior de altura fixa e isolamento dos
cards foi revertido por nao resolver o relato. A tentativa seguinte de alterar
clip-path e visibilidade da barra de rolagem tambem foi revertida. O ajuste atual
compoe a resposta com documento gerado inteira em uma camada, incluindo texto,
card e controles; nao altera calculos de altura, ancoragem ou eventos de rolagem.
Respostas normais e arquivos de imagem/audio/video nao recebem essa classe.

Testes em 390/1280 px e temas claro/escuro mediram zero alteracao de altura/rolagem
no hover, apos rolar novamente, reabrir e receber eventos de geracao simulados.
Na conversa real, capturas da janela nativa maximizada e comparacao de pixels
normalizados nao detectaram deslocamento vertical no texto, PDF ou controle de
copia. A composicao foi confirmada pelo LayerTree do Chromium. Abrir e baixar o
PDF real na build passou em ambas as larguras. O defeito original tambem nao foi
reproduzido antes da mudanca; portanto esses resultados nao comprovam sua causa
nem permitem afirmar que o relato do usuario foi definitivamente resolvido.
Uma bateria adicional na conversa real percorreu textos e botoes das tres
respostas com PDF, nos dois temas/larguras e em duas aberturas: 176 hovers sem
alteracao de posicao ou altura. Regressao de chat normal, ferramentas, imagem e
video passou apos a build, incluindo a seta de ir ao final e a posicao ao concluir.

No toast de atualizacao, o X foi elevado em 0.125 rem; Detalhes agora usa as mesmas
cores normal e de hover do Cancelar do download. Ambos os temas/larguras passaram
em comparacoes de estilo e testes de fechamento/cancelamento. Build concluida,
45 testes frontend passaram e Svelte manteve zero erros e 141 avisos existentes.
