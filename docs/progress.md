# Progresso do MVP — landing pages de estúdios

Checklist rastreável por milestone. Marcar somente o que foi verificado com comando.

## M0 — Fundação e decisões registradas

Verificado em 2026-08-12 (agente de verificação).

- [x] Scaffold Next.js (App Router, TypeScript, Tailwind, ESLint) — Next.js 16.3.0
- [x] Pacote Python `studio_pipeline` com CLI de ajuda — `.\.venv\Scripts\python -m studio_pipeline --help` exit 0
- [x] Estrutura de pastas do plano (stubs; `tests/integration` e `tests/e2e` adicionados após a verificação)
- [x] `.env.example` sem segredos (13 chaves do plano §15)
- [x] ADRs: JSON, STUDIO_ID, um projeto Vercel por estúdio, limites de scraping público
- [x] JSON Schemas iniciais + fixtures sintéticas (Aurora Sound Lab; sem PII da fonte)
- [x] `npm run lint` passa (exit 0)
- [x] `npm run typecheck` passa (exit 0)
- [x] Testes básicos TS e Python passam — após review de qualidade: Vitest 5/5; pytest 20/20; `typecheck` = `next typegen && tsc --noEmit`
- [x] `python -m studio_pipeline --help` / `doctor` / `validate` exit 0; import/queue/run/retry eram stubs no M0 (exit 2)
- [x] `npm run build` sem `STUDIO_ID` passa (comportamento M0; enforcement no build público fica para M5/M7)

Review de qualidade (M0): Ajv e Python agora usam os mesmos `format` (`date-time`/`uri`); `doctor` sai 1 se faltar schema; `.env*` ignorado com `!.env.example`.

Pendências adiadas: `approved.schema.json` (M6); ports de repositório unificados e `.env` no Python (M1); redaction no `lib/logger.ts` (M1).

## M1 — Repositórios JSON, importação e fila

Python verificado em 2026-08-12: `.\.venv\Scripts\python -m pytest pipeline/tests -q` → 43 passed; `python -m studio_pipeline --help` exit 0; smoke import/queue/run/validate/doctor em `DATA_DIR` temporário (fixture sintético, não `estudios_musica.json`).

- TS: `JsonStudioRepository` / `JsonStateRepository`, escrita atômica, locks, transições §7 e redaction no logger (testes em tmpdir).
- [x] Importador Python idempotente, IDs estáveis, deduplicação e relatório (`pipeline/tests/fixtures/source_musica.json`)
- [x] `StudioRepository` / `StateRepository` Python: escrita atômica, locks `O_CREAT|O_EXCL`, máquina de estados, `STATE_CONFLICT`; `load_config()` lê `.env` da raiz (stdlib; env vence)
- [x] Alinhamento TS+Python dos ports (pipeline vazio em memória, refresh de lock do mesmo owner, `wx`/`O_EXCL`, release idempotente, `updatedAt` no save) — Vitest 25; pytest 43 (Python inalterado na alinhagem)
- [x] CLI Python `import`, `queue`, `run` vazio (M1), `retry`, `validate --studio-id`, `doctor`
- [x] Reimportar o mesmo arquivo não duplica
- [x] Interrupção simulada (`.tmp` órfão) mantém o último JSON válido
- [x] Dois processos não adquirem o mesmo lock
- [x] Enfileirar e retomar (`failed -> queued`) preserva histórico

`studioId` Python: slug ASCII do nome + sufixo curto cidade/estado (iniciais ou 3 letras + UF; São Paulo → `sp`). Colisão: sufixo do `sourceId` (hash de title+cidade+estado+address) ou numérico. `sourceHash` = SHA-256 canônico do registro original.

Verificação independente (2026-08-12): `npm run lint` / `typecheck` / `test` (Vitest 25) exit 0; pytest 43; CLI help 0. Smoke em `DATA_DIR` temporário: import 3 → reimport `unchanged: 3` → queue → run vazio (permanece `queued`, sem `discovering`) → validate → doctor → retry `failed → queued`. `data/studios` de produção não foi escrito.

Qualidade (2026-08-12): pytest 52; Vitest 25. Corrigido: `studioId` estável na troca de nome; parser `.env` com aspas/comentários; update de sourceHash preserva Instagram/Facebook; audit `LOCK_EXPIRED` só após `O_EXCL`; CLI com códigos estáveis e redaction; OCC no `save_studio`; teste de replace falho.

Aberto para M6: schema no read Python vs TS; `save_approved`; `listLocks` só no Python.

Correção pós-qualidade (2026-08-12): takeover de lock expirado agora **renomeia** o `*.lock` para `.stale-*` e só então cria com `O_EXCL`/`wx` (pytest 65; Vitest 26). CLI `queue` aceita `imported → queued` e `rejected → queued`; `retry` continua só `failed → queued`.

Pendências adiadas: `approved.schema.json` (M6); `log_event` JSONL estruturado.

## M2 — Descoberta social e scraping público

Em implementação.

- [x] Descoberta: `discover_profiles(...)` (classificar, intermediários, busca injetável, score, limiar 0.85, Instagram > Facebook, ambiguidade → `requiresHumanReview`) — 9 testes; `run` ainda não ligado
- [x] Scrapers públicos Instagram/Facebook (fixtures; bloqueio = `PLATFORM_BLOCKED`, sem evasão) — 14 testes
- [x] Orchestrator: `queued → discovering` → scrape (`scraping`) ou `needs_social_review`; não entra em `enriching`
- [x] Fixtures: link direto, intermediário, pesquisa, ambíguo, ausente, bloqueado (descoberta 9 + scrape 14 + run 4)

Glue (2026-08-12): pytest pipeline **83 passed**. CLI `run` em `*.example` pausa em `needs_social_review` (HTTP mockado nos testes). Live IG/FB costuma ser `PLATFORM_BLOCKED`.

Anti-pattern (2026-08-12): sem login, Graph privado, rotação de UA ou auto-select ambíguo. `ROBOTS_USER_AGENT` alinhado a `DEFAULT_USER_AGENT`.

Verificação independente (2026-08-12): pytest **83**; Vitest **26**; `typecheck` OK. Aceite §17 M2: direto/intermediário/busca/ambíguo/ausente/bloqueado; Instagram > Facebook; ambíguo → `needs_social_review`; `PLATFORM_BLOCKED` sem evasão; `run` não entra em enriching/AI. Site oficial fica para M3.

Qualidade (2026-08-12): pytest **88**. Corrigido: re-run 403 idempotente; HTTP status 0 → timeout; busca só quando não há perfil válido; `as_response` duck-type. `scraping → needs_social_review` continua ilegal.

M2 fechado para aceite. Busca HTTP licenciada continua fora (NullSearchProvider).

## M3 — Enriquecimento e mídia

Fechado.

- [x] Mídia: `select_assets(...)` — logo + até 10 fotos, SHA-256 + hash perceptual, rejeita SVG/HTML/MIME divergente; `logo.<ext>`, `images/01–10`, `manifest.json` — 9 testes, sem rede
- [x] Enriquecimento factual (site oficial + source_json + Places fake) — `enrich_facts(...)` devolve facts+warnings; 7 testes
- [x] Orchestrator: `scraping → enriching → selecting_media` (parar antes de `generating`) — pytest pipeline **111**; re-run com `lastSuccessfulStage=selecting_media` sem HTTP

Verificação independente (2026-08-12): pytest **111+**; Vitest **26**; `typecheck` OK. Fatos com evidência; logo/fotos locais; SVG/HTML/MIME rejeitados; `run` para em `selecting_media` (não `generating`); conflitos preservados; Places não baixa Maps HTML.

Qualidade (2026-08-12): pytest **117**. Corrigido: candidatos não selecionados agora têm arquivo; Places não reusa SEARCH_*; warnings de estágio não empilham no re-run; FACT_CONFLICT inclui description; redirect binário não segue URL privada.

M3 fechado para aceite.

## M4 — AIProvider, branding e copy factual

Fechado.

- [x] FakeProvider emite `generated.json` válido contra o schema; prompt `m4.v1`; `inputHash`/`generationId`
- [x] Adapter OpenAI-compatible (`urllib`, sem pacote novo): `AI_PROVIDER=openai|openai_compatible`; testes mockados 11; factory lazy-import
- [x] Validador factual `validate_generated` — preço/horário/review/equipamento/endereço sem evidência → `FACT_WITHOUT_EVIDENCE`
- [x] Orchestrator: 1º `run` para em `selecting_media`; 2º `run` faz `generating → validating → ready_for_review` (sem build Next.js, sem auto-approve). JSON inválido → `AI_OUTPUT_INVALID` + sidecar, nunca o arquivo live. pytest pipeline **147**

Verificação independente (2026-08-12): pytest **147**; Vitest **26**; `typecheck` OK. Aceite §17 M4: Fake + adapter OpenAI-compatible; troca por config; `m4.v1`; fatos ausentes omitidos; copy sem evidência bloqueada; JSON inválido não vira `generated.json` live; `run` não auto-aprova. 1º `run` para em `selecting_media` (checkpoint); 2º continua M4.

Anti-pattern (2026-08-12): bloqueio — `Fechado`/`closed` no validador exige evidência de intervalos vazios (não mais um early-return). FakeProvider não inventa “hora marcada”. Pytest pinna `AI_PROVIDER=fake` (autouse).

Qualidade (2026-08-12): pytest **157**. Corrigido: endereço só com cidade, horários em texto PT, count de review inventado, rating truncado, preços “250 reais”, `Fechado` em dia aberto; `inputHash` ignora warnings/`completedAt`.

M4 fechado para aceite. P2 residual: adapter OpenAI sem `inputHash`/`createdAt` (orchestrator carimba no `run`); telefones não varridos; CLI em dois passos (M3 depois M4).

## Execução do lote solicitado — 2026-08-13

- [x] Histórico de tarefas e conversa de planejamento revisados; nenhum subagente permaneceu em execução.
- [x] Filtro inclusivo `80 <= score_comercial <= 99.01`: 654 registros elegíveis.
- [x] Seleção determinística dos 100 maiores scores; faixa efetiva 94.40–99.01.
- [x] 100 conjuntos `studio.json` / `dossier.json` / `generated.json` / `approved.json` e 100 itens de pipeline.
- [x] Lote source-only: fatos ausentes e mídias não verificadas foram omitidos; aprovação registrada como `batch:user-authorized` a partir do pedido explícito do usuário.
- [x] Catálogo, sitemap e 100 rotas SSG `/studios/<id>`; o build público usa somente snapshots aprovados.
- [x] AI SDK 7 + Vercel AI Gateway, modelo configurável, Zod, timeout, limite de tokens e preservação de copy factual.
- [x] Dashboard autenticado: lista, detalhe, preview privado, troca de template, geração por IA, aprovação com hashes e deploy hook.
- [x] Hardening: CSRF/origin check, sessão `httpOnly`/`SameSite=Strict`, rate limit de login, URL allowlisted para deploy e security headers.
- [x] Verificação final: ESLint; TypeScript; Vitest 52/52; pytest 157/157; npm audit de produção sem vulnerabilidades; build Next 109/109; smoke E2E das 100 páginas.
- [ ] Verificação visual automatizada: indisponível nesta sessão porque a conexão local do navegador falhou antes de abrir a página; smoke HTTP e renderização SSG passaram.
- [ ] Deploy remoto: a integração recusou publicar na equipe `asteroide` sem confirmação explícita desse destino e do payload. Nenhum contorno foi tentado.

Decisão para este lote: uma coleção Vercel com 100 URLs é o artefato publicável. O desenho “um projeto Vercel por estúdio” permanece disponível como evolução operacional, mas criar 100 projetos não foi inferido automaticamente nem executado.

## M5 — Quatro templates e preview

Em implementação.





