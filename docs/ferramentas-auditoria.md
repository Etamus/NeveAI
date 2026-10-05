# Auditoria de Ferramentas

Data: 2026-10-03. Analise do codigo atual; nenhuma alteracao no funcionamento
de Ferramentas foi feita nesta rodada. Nao constitui uma avaliacao comparativa
de resultados com o ChatGPT, nem uma garantia de qualidade de qualquer LLM.

## O que ja existe

- Criacao de arquivos reais anexados a resposta, com registro na biblioteca.
- PDF, DOCX, XLSX, PPTX, texto, codigo, legendas e ZIP entre os formatos de saida.
- Planejamento de transformacoes, deteccao de intencao e contexto dos anexos.
- Leitura nativa de textos, tabelas, celulas e slides; processamento em blocos
  para fontes grandes, respeitando o contexto do modelo.
- Caminho estrutural sem reescrita pela LLM para algumas transformacoes simples.
- Verificacoes de cobertura, reparo de omissoes e uma segunda tentativa limitada.
- OfficeCLI para criar/validar DOCX, XLSX e PPTX, com geradores alternativos.
- Limites de 4 milhoes de caracteres, 32 MB de saida e 100 arquivos por ZIP.

## Pontos Cegos

### 1. Editar ainda significa frequentemente reconstruir

`backend/neveai/tools/builtin.py:create_downloadable_file` recebe nome, formato
e conteudo final. Nao recebe um arquivo original e uma lista de alteracoes
enderecadas a seus elementos. `officecli_files.py:build_officecli_file` cria um
arquivo vazio e aplica comandos nele; nao abre o original para edicao.

Isso permite reescrever e resumir, mas nao assegura manter o documento intacto
fora da mudanca pedida. A quantizacao ou um prompt melhor nao resolve essa
limitacao arquitetural sozinho.

### 2. A representacao intermediaria perde elementos

`middleware.py:_read_native_file_generation_content` extrai:

- DOCX: paragrafos e tabelas em listas separadas. Nao conserva sua intercalacao,
  estilos completos, imagens, cabecalhos, rodapes e comentarios.
- XLSX: valores e formulas das celulas (`data_only=False`), mas nao o conjunto
  completo de formatos, mesclagens, graficos, validacoes e objetos da planilha.
  Preservar o texto da formula nao significa preservar seu funcionamento e
  todas as referencias apos uma reestruturacao.
- PPTX: textos e tabelas, nao os objetos graficos, imagens, temas e animacoes.
- PDF: texto por pagina, nao a geometria editavel da pagina; essa leitura nativa
  nao executa OCR. PDFs digitalizados precisam de um caminho apropriado de OCR
  e de tratamento das paginas sem texto.

Mesmo o caminho chamado estrutural preserva dados selecionados, nao todo o
pacote original do Office ou a aparencia original de um PDF.

### 3. A validacao nao comprova fidelidade visual

OfficeCLI valida o arquivo criado. A verificacao de cobertura procura omissoes
de dados e a auditoria semantica consulta uma LLM. Nenhuma dessas verificacoes
comprova automaticamente que uma tabela cabe na pagina ou que slides e imagens
continuaram nas mesmas posicoes.

`_review_generated_file_content` nao roda quando a soma da fonte e da saida
ultrapassa 120.000 caracteres, e retorna sem revisar quando o plano nao pede
preservacao integral. Falhas dessa revisao sao registradas e podem permitir que
o fluxo prossiga, se as outras verificacoes nao tiverem detectado problemas.

### 4. Existem limites e possiveis perdas silenciosas

O adaptador OfficeCLI limita a construcao a 50 planilhas e 100 slides por meio
de fatias das listas. Esses cortes precisam de erro explicito ou paginacao,
em vez de se presumir que todo documento aceito sera integralmente gerado.
O fallback pode produzir um arquivo valido com fidelidade visual inferior.

### 5. Muitas etapas dependem da mesma LLM

Planejar, reescrever e conferir usam o modelo selecionado ou o modelo de tarefa
configurado. Uma segunda chamada ao mesmo modelo nao e uma verificacao
independente. Pedidos ambiguos, contexto limitado, formulas complexas e revisoes
longas continuam dependendo da capacidade real desse modelo.

## Melhorias Prioritarias

1. Edicao estrutural no original: copiar o arquivo, localizar elementos por
   identificadores estaveis e aplicar apenas alteracoes autorizadas. Preservar
   estilos, objetos e relacionamentos nao alterados. Reaproveitar OfficeCLI onde
   houver suporte, com adaptadores especificos para cada formato.
2. Inspecao antes de editar: inventario de paginas, paragrafos, tabelas,
   imagens, formulas e slides; OCR quando necessario; pedir esclarecimento
   quando o alvo da alteracao for ambiguo.
3. Validacoes deterministicas: comparar elementos antes/depois, recalcular
   formulas com um motor compativel quando necessario, verificar referencias,
   arquivos truncados e paginas vazias. Falhar explicitamente em limites.
4. Validacao visual: renderizar documentos/slides em previews e verificar
   sobreposicoes, cortes e mudancas de layout nao autorizadas.
5. Versoes e rastreabilidade: original imutavel, arquivo derivado, resumo das
   mudancas, possibilidade de desfazer e erro claro se fidelidade nao puder ser
   garantida. A existencia de arquivos anexados nao substitui esse mecanismo.
6. Uma bateria de documentos de referencia com criterios objetivos: mudancas
   localizadas, preservacao de imagens e estilos, formulas, multiplos anexos,
   PDFs digitalizados e documentos longos, com testes de resultados reais.

## Conclusao

A base atual e util para criar documentos novos, extrair informacoes, resumir e
reescrever arquivos relativamente simples. Ainda nao e um editor geral com
preservacao garantida do original. Para aproximar a experiencia desejada,
edicao estrutural e validacao deterministica/visual trazem mais beneficio do
que apenas adicionar outra biblioteca ou trocar o prompt. A qualidade final
tambem continuara dependendo da LLM e do hardware; paridade com ChatGPT nao
pode ser prometida so pela integracao.
