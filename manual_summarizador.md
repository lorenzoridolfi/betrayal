# Manual de uso do sumarizador

O script `summarize_betrayal_json.py` transforma o conteúdo de `data/betrayal.json` em um resumo estruturado capítulo a capítulo, salvando o resultado em `data/betrayal_short.json`. Ele foi pensado para executar com validações antecipadas, de modo que problemas de entrada sejam detectados antes de consumir chamadas de LLM. Na prática, isso reduz risco de custo desnecessário e deixa a execução mais previsível.

Quando você usa opções que alteram o perfil da execução, o nome do arquivo de saída também muda para registrar esse contexto no próprio filename. Isso evita sobrescrever um resultado completo com uma execução parcial ou de rascunho, e facilita a identificação rápida do artefato correto para cada cenário.

Para executar o fluxo completo com as configurações padrão, use o comando abaixo a partir da raiz do projeto. Esse modo processa todos os capítulos disponíveis e respeita o modelo definido por `SUMMARY_MODEL` no ambiente, com fallback para o padrão do script quando a variável não estiver presente.

```bash
uv run python summarize_betrayal_json.py
```

Se a sua prioridade for custo menor durante iterações rápidas, utilize o modo de rascunho com `--draft`. Essa opção força o uso do modelo econômico configurado para draft, que atualmente é `gpt-5-mini`, independentemente do valor de `SUMMARY_MODEL` no ambiente.

```bash
uv run python summarize_betrayal_json.py --draft
```

Quando você quiser testar só uma parte do livro, use `--chapter-limit N`. Esse parâmetro limita a execução aos primeiros `N` capítulos, o que acelera validações de prompt, estrutura de saída e comportamento geral do pipeline.

```bash
uv run python summarize_betrayal_json.py --chapter-limit 3
```

Também é possível combinar as opções para rodar um recorte pequeno com custo reduzido. Essa combinação é útil para ciclos de ajuste, porque entrega feedback rápido sem comprometer o orçamento da execução completa.

```bash
uv run python summarize_betrayal_json.py --draft --chapter-limit 3
```

## Opções de command-line

As opções de linha de comando do programa são objetivas e cobrem os cenários principais de uso. A lista abaixo corresponde ao `--help` atual do script.

- `-h, --help`: mostra a ajuda e encerra a execução.
- `--draft`: força o modo econômico de sumarização com `gpt-5-mini`.
- `--chapter-limit CHAPTER_LIMIT`: processa apenas os primeiros `N` capítulos.

## Nome do arquivo de saída

O nome padrão continua sendo `data/betrayal_short.json` quando nenhuma opção especial é usada. Ao ativar `--draft` e/ou `--chapter-limit`, o script adiciona sufixos no arquivo de saída para deixar explícito como aquele resultado foi gerado.

- Sem flags: `data/betrayal_short.json`
- Só `--draft`: `data/betrayal_short_draft.json`
- Só `--chapter-limit 3`: `data/betrayal_short_limit_3.json`
- `--draft --chapter-limit 3`: `data/betrayal_short_draft_limit_3.json`

## Regras práticas para evitar gasto desnecessário

Antes de rodar o livro inteiro, faça primeiro uma execução curta com `--draft --chapter-limit 1` ou `--draft --chapter-limit 2`. Esse passo confirma se arquivos de entrada, prompt e formato de saída estão corretos, reduzindo a chance de falha tardia após várias chamadas de API. Depois que o teste curto estiver estável, rode sem limite para gerar o resumo completo.
