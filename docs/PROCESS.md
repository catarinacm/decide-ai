# Processo de construção do iFood Match

Material de apoio para o slide de processo do case, que pede três pontos: **Prompts**, **APIs** e **Riscos**. Este arquivo é atualizado a cada fase.

---

## 1. Prompts

### 1.1 Como conversei com a IA para construir

A construção foi feita com o Claude Code (agente de programação), em português, numa sequência de fases curtas. O método:

1. **Especificação antes do código.** Escrevi a especificação completa no `ifood.docx` (problema, jornada, motor de recomendação, banco, API, estados, regras, riscos) e um prompt de briefing que aponta para ela como fonte de verdade.
2. **Regras inegociáveis no prompt.** O briefing deixa explícito o que a IA de construção não pode decidir sozinha: dados 100% fictícios, reserva sempre marcada como simulada, a IA do produto não decide orçamento, restrição nem disponibilidade.
3. **Plano antes de executar.** Pedi que o agente lesse tudo (inclusive as imagens do docx) e me mostrasse um plano curto antes de escrever código.
4. **Conflitos viram perguntas, não suposições.** O briefing manda seguir o docx quando houver conflito e me avisar. Lacunas são decididas pelo mais simples e registradas em `docs/DECISIONS.md`.
5. **Testes como critério de avanço.** Nenhuma fase segue para deploy sem os testes verdes.

#### Registro por fase

| Fase | O que pedi | O que a IA fez / propôs | O que eu decidi |
|---|---|---|---|
| Planejamento | Ler o PDF do case e o docx (texto + 16 imagens) e propor fases, estrutura, contas e chaves. | Extraiu o texto e leu as imagens (fórmula de score, stack, estados, regras, riscos, funil). Apontou 5 divergências entre o briefing e o docx, com uma proposta para cada. | Aprovei todas (D-001 a D-006). Pedi para trabalhar na pasta do projeto, testar no Postgres real assim que houver connection string e manter este registro desde o início. |
| 0. Fundação | Instalar ferramentas e criar a estrutura. | Instalou Node.js LTS e GitHub CLI, criou a estrutura de pastas do docx (seção 7 da Etapa 3) + `backend/migrations/` e `docs/`, `.gitignore` e `.env.example` sem segredos. | Material do case fora do repositório público (D-009). |
| 1. Base de restaurantes | Gerar 50 restaurantes fictícios em bairros reais de SP, com diversidade de preço e culinária, e um validador que falhe em qualquer incoerência. | Separou os valores permitidos em `data/reference.json` (fonte única para seed, backend e IA). Escreveu à mão nomes e descrições, para não lembrar lugares reais, e gerou coordenadas, horários e avaliações de forma determinística. O validador checa campos, tipos, faixa de preço por culinária, combinações inválidas, distância até o bairro, horários, unicidade e uma lista de nomes reais proibidos. Os testes provam que cada tipo de erro é detectado. | Faixas de preço por culinária viraram regra de validação, não só sugestão (D-010). |
| 2. Motor de recomendação | Implementar as Etapas A e B do docx como funções puras e testáveis, com a fórmula `S = 0,40G + 0,25P + 0,20L + 0,15A` por participante e penalização por desigualdade. | Escreveu `matching.py` sem dependência de banco ou IA: filtros com contagem por motivo, score por participante com Haversine, penalização, top 3 com detalhamento, ponto de atenção e destaques só com atributos cadastrados, e sugestões concretas ("subindo o limite de Bruno de R$ 60 para R$ 70, surgem 3 opções"). 36 testes, incluindo 300 grupos aleatórios contra o seed real para provar que nenhuma recomendação viola um filtro obrigatório. | Definição de cada componente (D-011) e regras de desempate e sugestão (D-012). Um teste de penalização falhou na primeira versão porque o cenário estava mal montado (o lugar "equilibrado" era ruim para todos); o cenário foi corrigido, não a regra. |
| 3. Backend, banco e IA | Implementar os 10 endpoints do docx e mais parse de preferências, métricas e health, com máquina de estados, tokens, rate limit, CORS, eventos do funil, IA com timeout e fallback, migrations SQL versionadas e um teste ponta a ponta dos 8 critérios de aceite. | Separou rotas (`api/`), regras (`services/`) e tabelas (`models/`). Gerou o SQL das migrations a partir dos próprios modelos, para não haver divergência entre o banco real e os testes, e ativou RLS. Escreveu o roteiro dos 8 critérios como script reutilizável: o mesmo código roda no pytest e depois contra a URL de produção. 118 testes verdes. | Um teste pegou um bug real: depois de invalidar a rodada, a tela ainda contava o voto antigo. A correção foi fazer os votos valerem só para recomendações ativas. Decisões D-013 a D-019. |

### 1.2 Prompts da IA dentro do produto

Os prompts ficam em `backend/app/services/ai_service.py` (`PARSE_SYSTEM`, `EXPLAIN_SYSTEM`) e têm versão (`PROMPT_VERSION`), que entra na chave do cache: mudar o prompt nunca reaproveita uma explicação antiga.

**Princípio:** o algoritmo decide e a IA explica. Nenhuma saída da IA é usada sem validação no backend, e toda falha tem resposta por regras.

#### Função A — Interpretação de preferências (`POST /ai/parse-preferences`)

- **Entrada:** só o texto livre da pessoa, entre delimitadores.
- **Prompt de sistema (v1), em resumo:**
  - use apenas os valores permitidos, listados a partir de `data/reference.json`;
  - só marque restrição alimentar se a pessoa disser que tem;
  - respeite negações ("não quero sushi");
  - **orçamento e distância só se houver número escrito**; "não muito caro" vai para `budget_hint`;
  - não invente.
- **Saída:** JSON garantido por schema (`output_config.format`), com enums dos valores permitidos.
- **Guardrails no código:**
  - Pydantic descarta qualquer valor fora da lista;
  - um número que a pessoa não escreveu é apagado, mesmo que o modelo tenha preenchido;
  - a interface mostra o resultado pré-preenchido para a pessoa corrigir antes de salvar, e **os campos estruturados são a fonte da regra**.
- **Fallback:** parser por palavras-chave, com sinônimos e negação simples. Ele interpreta corretamente a frase do docx ("quero um lugar tranquilo, não muito caro, sou vegetariana").

#### Função B — Explicação das recomendações (dentro de `POST /groups/{id}/match`)

- **Entrada:** só o top 3 elegível, já ordenado pelo algoritmo, com os atributos cadastrados, o score, o detalhamento por participante, os pontos fortes e o ponto de atenção calculados pelo motor, e um resumo das preferências com apelidos.
- **Prompt de sistema (v1), em resumo:**
  - use apenas os dados do JSON;
  - cite só os restaurantes enviados;
  - **não afirme segurança alimentar**;
  - não mude o ranking;
  - 2 a 3 frases, terminando no ponto de atenção.
- **Guardrails no código, explicação por explicação:**
  - o `restaurant_id` tem de estar entre os enviados;
  - o texto tem de citar o próprio restaurante;
  - não pode citar nenhum outro restaurante do catálogo;
  - nenhum preço "R$" fora dos preços e orçamentos enviados;
  - bloqueio de frases como "seguro para celíacos", "sem risco" e "100%";
  - tamanho entre 40 e 700 caracteres.

  A explicação reprovada cai no template; as outras continuam vindo da IA.
- **Registro:** cada recomendação grava `reason_source` (`ia` ou `fallback`), e cada chamada gera um evento `ai_call` com fonte, erro, latência e uso do cache.
- **Cache:** por hash do conteúdo enviado + versão do prompt. Consultar o ranking nunca chama a IA, porque a explicação fica gravada na rodada.

#### Como os prompts evoluíram

| Versão | Mudança | Motivo |
|---|---|---|
| v1 | Versão inicial, com as regras acima. | Escrita a partir da tabela de riscos do docx ("IA inventar informações", "ignorar alergias"). |


---

## 2. APIs e ferramentas

| Camada | Escolha | Por quê |
|---|---|---|
| Frontend | React + Vite + Tailwind, na Vercel | Stack do docx. Vite builda rápido; Tailwind dá a cara de app (cards, cantos arredondados) sem biblioteca de componentes. A Vercel publica SPA de graça com rewrite de rotas. |
| Backend | Python + FastAPI + Pydantic, no Render | Python permite testar o motor de recomendação isolado da interface (docx). FastAPI valida entrada e saída com Pydantic e gera a documentação da API. Render tem plano gratuito e Blueprint (`render.yaml`). |
| Banco | Supabase (PostgreSQL) | Postgres gerenciado e gratuito, com restrições de integridade de verdade. Acesso só pelo backend (D-004). |
| IA | API da Anthropic, `claude-haiku-5-5` | Barato e rápido para tarefas curtas; chamada só do backend, com timeout e fallback por regras (D-005). |
| Repositório | GitHub | Versionamento e origem do deploy no Render. |

---

## 3. Riscos

Tabela de riscos do docx e como cada um é tratado. A coluna "Onde no código" é preenchida conforme as fases avançam.

| Risco | Como tratamos | Onde no código |
|---|---|---|
| IA inventar informações | A IA só recebe os elegíveis e os campos cadastrados. Guardrails conferem ids, nomes citados, preços e frases proibidas, explicação por explicação; a reprovada cai no template. A Função A só aceita valores da lista e números escritos pela pessoa. | `backend/app/services/ai_service.py` (`validate_explanations`, `parse_preferences`); `tests/test_ai.py` |
| Recomendar acima do orçamento | Filtro obrigatório antes do ranking, com o menor teto entre grupo e participantes (D-001). Teste com 300 grupos aleatórios garante que nenhum recomendado passa do teto. | `backend/app/services/matching.py` (`effective_budget`, `failed_filters`); `tests/test_matching.py` |
| Ignorar alergias ou restrições críticas | A restrição de qualquer participante é filtro obrigatório e nunca é relaxada nas sugestões. A IA é proibida de afirmar segurança alimentar, e um regex bloqueia essas frases. A interface sempre lembra de confirmar com o restaurante. | `matching.py` (`failed_filters`, `suggestions`); `ai_service.py` (`FORBIDDEN`); `api/serializers.py` (`DIETARY_DISCLAIMER`) |
| Grupo não chegar a consenso | Encerramento pelo organizador e prazo opcional. Empate decidido pelo maior score coletivo e, sem votos, vence o maior score; a decisão vem com a explicação do critério usado. | `backend/app/services/decision_service.py` (`pick_winner`, `maybe_auto_close`) |
| Usuários acessarem grupos indevidos | Convite de 8 caracteres de `secrets` (31^8 combinações); token por participante e token separado do organizador, guardados só como hash; autorização em todas as rotas; rate limit; CORS restrito; RLS no Supabase. | `backend/app/services/auth.py`, `limiter.py`, `main.py`, `migrations/001_schema.sql`; `tests/test_api.py` |
| Exposição de informações pessoais | Só apelido; o validador recusa apelido com "@" ou com 6 ou mais dígitos (e-mail ou telefone). A localização é só o bairro, e nenhum outro dado pessoal é coletado. | `backend/app/schemas.py` (`clean_nickname`); interface na fase 4 |
| Falha da API de IA | Timeout de 8 s, sem retries; recusa, truncamento, erro HTTP, rede ou JSON inválido caem no fallback por regras, e o banco registra se foi IA ou fallback. | `ai_service.py` (`call_model`, `template_explanation`, `parse_preferences_rules`); `tests/test_ai.py` |
| Reserva não ser real | `is_simulated` com `CHECK (is_simulated = true)` no banco, código `SIM-...`, rótulo "Reserva simulada" na API e selo na interface (fase 4); no máximo uma reserva confirmada por grupo (índice único parcial). | `models/tables.py`, `services/decision_service.py`; `tests/test_api.py` |
