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

### 1.2 Prompts da IA dentro do produto

Serão documentados na fase 3, com as versões e o motivo de cada mudança:

- **Função A — Interpretação de preferências:** texto livre → JSON validado com Pydantic contra os valores permitidos.
- **Função B — Explicação das recomendações:** explica o top 3 citando só atributos cadastrados, com o principal ponto de atenção.

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
| IA inventar informações | Prompt restrito aos restaurantes e campos enviados; validação de que todo restaurante citado está entre os enviados; fallback se a resposta não passar. | _fase 3_ |
| Recomendar acima do orçamento | Filtro obrigatório antes do ranking, com o menor teto entre grupo e participantes (D-001). | _fase 2_ |
| Ignorar alergias ou restrições críticas | Restrições são filtro obrigatório; a IA é proibida de afirmar segurança alimentar e a interface avisa para confirmar com o restaurante. | _fases 2 e 3_ |
| Grupo não chegar a consenso | Votação com encerramento pelo organizador e prazo opcional (D-003); empate decidido pelo maior score coletivo. | _fase 3_ |
| Usuários acessarem grupos indevidos | Código de convite aleatório (`secrets`), token por participante e token do organizador, autorização em todas as rotas. | _fase 3_ |
| Exposição de informações pessoais | Apelidos fictícios, nenhum dado pessoal coletado, localização só por bairro. | _fases 3 e 4_ |
| Falha da API de IA | Timeout e explicação por template a partir dos mesmos dados; o banco registra se foi IA ou fallback. | _fase 3_ |
| Reserva não ser real | `is_simulated = true` no banco e selo "Reserva simulada" na interface. | _fases 3 e 4_ |
