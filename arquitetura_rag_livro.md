# Arquitetura final para RAG de um livro biográfico com índice remissivo

## Objetivo

Construir um pipeline de ingestão, sumarização estruturada e RAG para um único livro em inglês, do tipo biografia factual com forte carga de relações pessoais, intrigas, cronologia e recorrência de nomes próprios.

A meta não é começar com a solução mais sofisticada possível. A meta é começar com uma arquitetura simples, robusta, agradável de usar e fácil de evoluir depois.

A decisão central é esta:

- **não começar com GraphRAG**;
- **usar Weaviate como base**;
- **manter duas camadas complementares**:
  - camada de **resumo estruturado por capítulo**;
  - camada de **evidência bruta** com semantic chunking do texto original.

O índice remissivo do livro entra como **sinal auxiliar de cobertura e reconciliação**, não como substituto do texto.

---

## Decisões finais

### 1. Banco vetorial

A primeira versão usa **Weaviate** com busca híbrida:

- busca vetorial para similaridade semântica;
- BM25 para nomes próprios, apelidos, eventos e termos exatos;
- filtros por capítulo, entidade, período ou tipo de capítulo.

Isso é suficiente para a primeira versão. Não há exigência estrutural de usar grafo desde o início.

### 2. Grafo

**Não é obrigatório** nesta fase.

O livro tem conteúdo altamente relacional, então uma camada de grafo pode ser útil depois, mas como evolução. A arquitetura já será preparada para isso extraindo:

- entidades;
- eventos;
- marcadores temporais;
- aliases;
- relações implícitas que poderão ser promovidas a arestas mais tarde.

### 3. Duas camadas de dados

A arquitetura final fica assim:

1. **ChapterSummary**
   - um objeto por capítulo;
   - resumo curto;
   - resumo detalhado;
   - entidades;
   - eventos;
   - temas;
   - marcadores temporais;
   - tipo do capítulo.

2. **TextChunk**
   - chunks semânticos do texto original;
   - texto bruto do chunk;
   - ordem no capítulo;
   - entidades detectadas;
   - aliases;
   - metadados de localização.

Resumo serve para **roteamento e navegação**.
Texto original serve para **evidência**.

### 4. Índice remissivo

O índice remissivo será usado para:

- reforçar nomes canônicos;
- detectar aliases e variantes;
- medir cobertura do resumo;
- auditar ausência de pessoas, temas ou eventos importantes;
- ajudar consultas futuras.

Ele não substitui a narrativa do capítulo.

---

## Fluxo geral da arquitetura

## Etapa 0 — preparação do livro

1. Extrair o EPUB.
2. Separar o texto por capítulo.
3. Remover ou tratar:
   - índice inicial;
   - copyright;
   - agradecimentos;
   - front matter irrelevante;
   - índice remissivo, que será persistido à parte.
4. Persistir uma tabela simples com:
   - `chapter_number`
   - `chapter_title`
   - `chapter_text`
   - `chapter_order`

---

## Etapa 1 — classificação preliminar do capítulo

A primeira passada existe para orientar a segunda. Ela não deve tentar resolver tudo.

### Objetivo

Descobrir **a natureza dominante do capítulo**:

- narrativa factual;
- background/contexto;
- análise;
- reflexão;
- conclusão;
- apêndice;
- misto.

### Saída

Um JSON pequeno, barato, usado como contexto de trabalho na segunda passada.

### Taxonomia adotada

Usar `chapter_kind_preliminary` com estes valores:

- `narrative`
- `background`
- `analysis`
- `reflection`
- `conclusion`
- `appendix`
- `mixed`
- `other`

A presença de `mixed` evita forçar classificação artificial.

---

## Etapa 2 — extração estruturada final do capítulo

A segunda passada recebe:

- o texto do capítulo;
- o resultado preliminar da etapa 1.

### Objetivo

Produzir o JSON final estruturado do capítulo, com:

- resumo curto;
- resumo detalhado;
- tipo final do capítulo;
- eventos principais;
- entidades;
- marcadores temporais;
- citações curtas opcionais;
- ganchos em aberto;
- palavras-chave.

Nesta fase, o modelo **pode confirmar ou corrigir** o rótulo preliminar.

---

## Etapa 3 — semantic chunking do texto original

Em paralelo à sumarização estruturada, o texto bruto do capítulo é quebrado em chunks usando o código já existente de semantic chunking.

### Regras práticas

- manter os chunks semanticamente coerentes;
- impor também um **teto máximo de tamanho**;
- preservar a ordem original;
- anexar metadados de capítulo e posição.

### Objetivo

Essa camada será a base de evidência do RAG.

---

## Etapa 4 — persistência

Persistir separadamente:

- o **ChapterSummary** final;
- os **TextChunks**;
- opcionalmente uma estrutura auxiliar de **IndexEntry** derivada do índice remissivo.

### Regra importante

Pode haver um **objeto temporário de trabalho** do LLM contendo resumo e chunks juntos, mas isso **não deve ser o formato final de persistência**.

Resumo e evidência devem ser separados no armazenamento.

---

## Etapa 5 — consulta RAG

### Consulta em duas fases

1. Buscar primeiro em **ChapterSummary** para localizar os capítulos ou seções mais promissores.
2. Usar esses resultados como filtro no conjunto **TextChunk**.
3. Recuperar poucos chunks relevantes.
4. Gerar a resposta final com base nesses chunks.

### Tipos de consulta

#### Consultas panorâmicas
Exemplos:

- "Qual é o arco da relação entre A e B?"
- "Como o livro retrata a ascensão de X?"

Podem começar só com resumos e poucos chunks.

#### Consultas factuais ou fofoqueiras
Exemplos:

- "Quem rompeu com quem primeiro?"
- "Quando começou a rivalidade?"
- "Em que capítulo aparece a acusação contra fulano?"

Devem trazer chunks brutos.

---

## Modelo de dados lógico

## 1. ChapterSummary

Objeto analítico por capítulo.

Campos principais:

- `chapter_number`
- `chapter_title`
- `chapter_kind`
- `summary_short`
- `summary_detailed`
- `summary_confidence`
- `themes`
- `key_events`
- `entities`
- `time_markers`
- `important_quotes`
- `open_loops`
- `chapter_keywords`
- `ambiguities_or_gaps`

## 2. TextChunk

Objeto de evidência por chunk.

Campos principais:

- `chunk_id`
- `chapter_number`
- `chapter_title`
- `chunk_order`
- `chunk_text`
- `chunk_kind`
- `entities_mentioned`
- `aliases`
- `time_markers`

## 3. IndexEntry

Opcional, derivado do índice remissivo.

Campos possíveis:

- `entry_name`
- `canonical_name`
- `entry_type`
- `aliases`
- `chapter_numbers`
- `notes`

---

## Estratégia de prompts

## Primeira passada

Função: classificação preliminar leve.

### Instrução sugerida

```text
Você receberá o texto completo de um capítulo de uma biografia.
Classifique a natureza dominante do capítulo.
Não tente resumir tudo em detalhe.
Use uma das categorias permitidas.
Se houver mistura real de modos, use "mixed".
Se houver ambiguidade, reflita isso na confiança.
```

## Segunda passada

Função: extração final estruturada.

### Instrução sugerida

```text
Você receberá o texto completo de um capítulo e uma classificação preliminar.
Produza um resumo estruturado em JSON.
Você pode confirmar ou corrigir a classificação preliminar.
Não invente fatos além do texto.
Use arrays vazios quando não houver dados claros.
Prefira nomes canônicos para entidades.
Se houver pontos obscuros, registre em ambiguities_or_gaps.
```

---

## Schema da primeira passada

```json
{
  "type": "object",
  "properties": {
    "chapter_number": {
      "type": ["integer", "null"]
    },
    "chapter_title": {
      "type": "string"
    },
    "chapter_kind_preliminary": {
      "type": "string",
      "enum": [
        "narrative",
        "background",
        "analysis",
        "reflection",
        "conclusion",
        "appendix",
        "mixed",
        "other"
      ]
    },
    "classification_confidence": {
      "type": "string",
      "enum": ["low", "medium", "high"]
    },
    "classification_rationale": {
      "type": "string"
    },
    "dominant_entities": {
      "type": "array",
      "items": { "type": "string" }
    },
    "dominant_timeframe": {
      "type": ["string", "null"]
    },
    "possible_themes": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "required": [
    "chapter_number",
    "chapter_title",
    "chapter_kind_preliminary",
    "classification_confidence",
    "classification_rationale",
    "dominant_entities",
    "dominant_timeframe",
    "possible_themes"
  ],
  "additionalProperties": false
}
```

---

## Schema final do capítulo

Este é o schema final recomendado para persistência analítica por capítulo.

```json
{
  "type": "object",
  "properties": {
    "chapter_number": {
      "type": ["integer", "null"],
      "description": "Número do capítulo, ou null se não houver numeração explícita."
    },
    "chapter_title": {
      "type": "string",
      "description": "Título canônico do capítulo."
    },
    "chapter_kind": {
      "type": "string",
      "enum": [
        "narrative",
        "background",
        "analysis",
        "reflection",
        "conclusion",
        "appendix",
        "mixed",
        "other"
      ],
      "description": "Tipo predominante do capítulo."
    },
    "summary_short": {
      "type": "string",
      "description": "Resumo curto em 2 a 4 frases."
    },
    "summary_detailed": {
      "type": "string",
      "description": "Resumo detalhado em prosa corrida."
    },
    "summary_confidence": {
      "type": "string",
      "enum": ["low", "medium", "high"],
      "description": "Confiança do modelo na qualidade do resumo."
    },
    "themes": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Temas centrais do capítulo."
    },
    "key_events": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/key_event"
      },
      "description": "Eventos principais do capítulo."
    },
    "entities": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/entity"
      },
      "description": "Entidades relevantes no capítulo."
    },
    "time_markers": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/time_marker"
      },
      "description": "Datas, períodos ou referências temporais mencionadas ou inferidas."
    },
    "important_quotes": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/quote_stub"
      },
      "description": "Citações curtas ou paráfrases marcantes."
    },
    "open_loops": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Questões deixadas em aberto ou ganchos narrativos."
    },
    "chapter_keywords": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Palavras-chave úteis para busca."
    },
    "ambiguities_or_gaps": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Pontos ambíguos, contraditórios ou insuficientemente claros."
    }
  },
  "$defs": {
    "key_event": {
      "type": "object",
      "properties": {
        "sequence": {
          "type": "integer",
          "description": "Ordem lógica do evento no capítulo."
        },
        "event_summary": {
          "type": "string",
          "description": "Descrição curta do evento."
        },
        "importance": {
          "type": "string",
          "enum": ["low", "medium", "high"],
          "description": "Peso narrativo do evento no capítulo."
        },
        "involved_entities": {
          "type": "array",
          "items": {
            "type": "string"
          },
          "description": "Entidades envolvidas no evento."
        },
        "consequences": {
          "type": "string",
          "description": "Consequência factual ou narrativa do evento."
        }
      },
      "required": [
        "sequence",
        "event_summary",
        "importance",
        "involved_entities",
        "consequences"
      ],
      "additionalProperties": false
    },
    "entity": {
      "type": "object",
      "properties": {
        "canonical_name": {
          "type": "string",
          "description": "Nome canônico da entidade."
        },
        "entity_type": {
          "type": "string",
          "enum": [
            "person",
            "organization",
            "place",
            "work",
            "event",
            "concept",
            "other"
          ],
          "description": "Tipo principal da entidade."
        },
        "role_in_chapter": {
          "type": "string",
          "description": "Papel da entidade neste capítulo."
        },
        "salience": {
          "type": "string",
          "enum": ["minor", "secondary", "major"],
          "description": "Importância relativa da entidade no capítulo."
        },
        "aliases": {
          "type": "array",
          "items": {
            "type": "string"
          },
          "description": "Nomes alternativos, apelidos ou formas abreviadas."
        }
      },
      "required": [
        "canonical_name",
        "entity_type",
        "role_in_chapter",
        "salience",
        "aliases"
      ],
      "additionalProperties": false
    },
    "time_marker": {
      "type": "object",
      "properties": {
        "label": {
          "type": "string",
          "description": "Expressão temporal como aparece no texto."
        },
        "normalized": {
          "type": ["string", "null"],
          "description": "Versão normalizada, ou null se não for possível normalizar."
        },
        "certainty": {
          "type": "string",
          "enum": ["explicit", "inferred"],
          "description": "Se a referência temporal é explícita ou inferida."
        },
        "related_event": {
          "type": "string",
          "description": "Evento associado ao marcador temporal."
        }
      },
      "required": [
        "label",
        "normalized",
        "certainty",
        "related_event"
      ],
      "additionalProperties": false
    },
    "quote_stub": {
      "type": "object",
      "properties": {
        "speaker_or_source": {
          "type": ["string", "null"],
          "description": "Quem falou ou originou o trecho, se isso estiver claro."
        },
        "text": {
          "type": "string",
          "description": "Trecho curto ou paráfrase muito próxima."
        },
        "why_it_matters": {
          "type": "string",
          "description": "Por que esse trecho é importante."
        }
      },
      "required": [
        "speaker_or_source",
        "text",
        "why_it_matters"
      ],
      "additionalProperties": false
    }
  },
  "required": [
    "chapter_number",
    "chapter_title",
    "chapter_kind",
    "summary_short",
    "summary_detailed",
    "summary_confidence",
    "themes",
    "key_events",
    "entities",
    "time_markers",
    "important_quotes",
    "open_loops",
    "chapter_keywords",
    "ambiguities_or_gaps"
  ],
  "additionalProperties": false
}
```

---

## Schema do objeto temporário de trabalho com chunks

Este schema **não é o formato final de persistência**. Ele serve apenas se for conveniente enviar ao LLM, na mesma estrutura de trabalho, o resumo e os chunks de apoio.

```json
{
  "type": "object",
  "properties": {
    "chapter_number": {
      "type": ["integer", "null"]
    },
    "chapter_title": {
      "type": "string"
    },
    "summary_short": {
      "type": "string"
    },
    "summary_detailed": {
      "type": "string"
    },
    "themes": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "entities": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/entity"
      }
    },
    "supporting_chunks": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/supporting_chunk_compact"
      }
    }
  },
  "$defs": {
    "entity": {
      "type": "object",
      "properties": {
        "canonical_name": {
          "type": "string"
        },
        "entity_type": {
          "type": "string",
          "enum": [
            "person",
            "organization",
            "place",
            "work",
            "event",
            "concept",
            "other"
          ]
        },
        "role_in_chapter": {
          "type": "string"
        },
        "salience": {
          "type": "string",
          "enum": ["minor", "secondary", "major"]
        },
        "aliases": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      },
      "required": [
        "canonical_name",
        "entity_type",
        "role_in_chapter",
        "salience",
        "aliases"
      ],
      "additionalProperties": false
    },
    "supporting_chunk_compact": {
      "type": "object",
      "properties": {
        "chunk_id": {
          "type": "string"
        },
        "chunk_text": {
          "type": "string"
        }
      },
      "required": [
        "chunk_id",
        "chunk_text"
      ],
      "additionalProperties": false
    }
  },
  "required": [
    "chapter_number",
    "chapter_title",
    "summary_short",
    "summary_detailed",
    "themes",
    "entities",
    "supporting_chunks"
  ],
  "additionalProperties": false
}
```

---

## Estrutura sugerida no Weaviate

## Collection `ChapterSummary`

Campos sugeridos:

- `book_id`
- `chapter_number`
- `chapter_order`
- `chapter_title`
- `chapter_kind`
- `summary_short`
- `summary_detailed`
- `summary_confidence`
- `themes`
- `chapter_keywords`
- `entities_canonical`
- `time_labels`

## Collection `TextChunk`

Campos sugeridos:

- `book_id`
- `chapter_number`
- `chapter_title`
- `chunk_id`
- `chunk_order`
- `chunk_kind`
- `chunk_text`
- `entities_mentioned`
- `aliases`
- `time_labels`

## Collection opcional `IndexEntry`

Campos sugeridos:

- `book_id`
- `entry_name`
- `canonical_name`
- `entry_type`
- `aliases`
- `chapter_numbers`

---

## Estratégia de consulta

## Consulta ampla

1. Buscar em `ChapterSummary`.
2. Pegar os capítulos mais relevantes.
3. Buscar poucos `TextChunk` desses capítulos.
4. Responder.

## Consulta factual

1. Buscar diretamente por hybrid search em `TextChunk`.
2. Reranquear.
3. Usar `ChapterSummary` apenas como contexto auxiliar.

## Consulta exploratória por pessoa

1. Buscar pelo nome canônico e aliases.
2. Usar também `IndexEntry`, se existir.
3. Consolidar capítulos e chunks relacionados.

---

## Evolução futura para grafo

Se a segunda fase do projeto justificar, pode ser criado um grafo com:

### Nós

- `Person`
- `Organization`
- `Place`
- `Event`
- `Chapter`

### Arestas

- `MENTIONED_IN`
- `ASSOCIATED_WITH`
- `ALLY_OF`
- `RIVAL_OF`
- `ATTENDED`
- `CONNECTED_TO_EVENT`

Essa fase só vale a pena quando as consultas começarem a exigir raciocínio relacional mais explícito.

---

## Recomendações finais

1. **Começar simples.**
   Weaviate + summaries + semantic chunks já é suficiente para uma primeira versão muito boa.

2. **Não usar o resumo como substituto da evidência.**
   Resumo navega. Chunk prova.

3. **Usar duas passagens.**
   A primeira classifica. A segunda extrai de forma final.

4. **Usar o índice remissivo como auditor.**
   Não como fonte principal.

5. **Separar objeto temporário de objeto persistido.**
   No prompt pode haver mistura. No armazenamento, não.

6. **Adiar o grafo.**
   Só subir esse custo quando aparecer necessidade real.

---

## Ponto ótimo desta arquitetura

A arquitetura final fica no meio exato entre simplicidade e riqueza analítica:

- simples o bastante para ficar de pé rápido;
- rica o bastante para responder perguntas divertidas, detalhadas e relacionais sobre o livro;
- organizada o bastante para evoluir depois para grafo, auditoria pelo índice e consultas mais sofisticadas.
