# Landing pages de estúdios

Um único engine Next.js 16 renderiza uma coleção pública e páginas individuais para estúdios musicais. O pipeline Python mantém importação, descoberta, scraping público, enriquecimento e geração separados; o dashboard local cobre revisão, regeneração, aprovação e deploy.

## Lote atual

- Fonte: `estudios_musica.json` (local, não versionada).
- Critério inclusivo: `80 <= score_comercial <= 99.01`.
- Seleção: score decrescente, desempate estável por nome/cidade, limite de 100.
- Resultado materializado: exatamente 100 estúdios, faixa efetiva 94.40–99.01.
- Cada página pública lê somente `approved.json`; rascunhos ficam na rota administrativa protegida.
- Campos não comprovados (mídia, preços, horários e equipamentos) são omitidos, nunca inventados.

Regere o lote de forma idempotente:

```powershell
npm run generate:batch -- --input estudios_musica.json --limit 100 --min-score 80 --max-score 99.01
```

## Desenvolvimento e verificação

```powershell
npm install
npm run dev
npm run lint
npm run typecheck
npm test
npm run validate:data
npm run build
npm run test:e2e
py -m pytest pipeline/tests -q
```

`npm run test:e2e` inicia o build local, verifica a coleção, a primeira e a última landing e o sitemap, e encerra o servidor.

## Rotas

- `/` — catálogo das 100 páginas.
- `/studios/<studioId>` — snapshot público aprovado.
- `/dashboard` — operação protegida por `DASHBOARD_SECRET`.
- `/preview/<studioId>` — rascunho protegido.
- `/api/ai/<studioId>` — nova direção visual estruturada via Vercel AI Gateway.
- `/api/approve/<studioId>` — aprovação humana e hash dos assets.
- `/api/deploy/<studioId>` — deploy aprovado via Vercel Deploy Hook.

## IA

O adapter usa AI SDK 7, Vercel AI Gateway e saída Zod estruturada. O default é `openai/gpt-5.6-luna`, configurável por `AI_MODEL`. A IA só altera template, branding e microcopy não factual; nome, endereço, descrição, avaliações e demais fatos permanecem vindos do dossiê. Há timeout, limite de tokens e validação que bloqueia números sem evidência.

Em Vercel, OIDC pode autenticar o Gateway. Localmente, configure `AI_GATEWAY_API_KEY` em `.env.local`. Nunca versione `.env*` real.

## Dashboard e segurança

Defina `DASHBOARD_SECRET` em `.env.local`. A sessão é `httpOnly`, `SameSite=Strict`, expira em oito horas e as mutações validam origem. Login tem limite local de tentativas; APIs administrativas validam autenticação e a máquina de estados. CSP, HSTS, `nosniff`, `SAMEORIGIN` e Permissions Policy são enviados em todas as rotas.

O backend JSON é deliberadamente local/operacional. As páginas públicas são pré-renderizadas; para tornar edição concorrente no dashboard distribuída entre instâncias Vercel, substitua os repositórios JSON por storage compartilhado.

## Deploy

O deploy do dashboard exige um Deploy Hook HTTPS de `api.vercel.com`:

```powershell
$env:VERCEL_DEPLOY_HOOK_URL="https://api.vercel.com/v1/integrations/deploy/..."
npm run deploy:studio -- <studioId>
```

O lote atual também pode ser publicado como uma coleção única, com 100 URLs estáticas. A integração nunca publica sem snapshot aprovado.
