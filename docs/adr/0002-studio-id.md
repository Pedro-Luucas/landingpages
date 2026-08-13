# 0002 — `studioId` estável e seleção via `STUDIO_ID`

- Status: Aceita
- Data: 2026-08-12
- Milestone: M0

## Contexto

Há um único repositório e um único app Next.js. Não deve haver cópia de código por estúdio. Cada landing precisa de uma identidade estável para pastas (`data/studios/<studioId>/`, `public/studios/<studioId>/`), preview, aprovação e deploy. Nomes comerciais mudam; o identificador não pode mudar junto.

## Decisão

Gerar `studioId` uma única vez na importação/normalização, de forma determinística e deduplicável:

- slug normalizado do nome;
- sufixo curto derivado de cidade/estado ou do ID da origem (`sourceId`).

Mudanças posteriores no nome (ou em outros campos) não alteram o ID. Documentos (`studio.json`, dossiê, geração, aprovação, deploy) carregam esse `studioId`.

O build público do Next.js seleciona dados e ativos exclusivamente pela variável de ambiente `STUDIO_ID`. Preview local/protegido pode usar rota `/preview/[studioId]`. O mesmo código serve todos os estúdios; não há fork nem cópia por site.

A partir do momento em que a landing pública ler o snapshot aprovado (M5/M7), build sem `STUDIO_ID` válido, ou com ID inexistente, falha de forma explícita. O scaffold M0 ainda permite `npm run build` sem a variável para validar o app em si.

## Consequências

- Um codebase, N deploys: cada projeto Vercel define `STUDIO_ID` (ver ADR 0003).
- Pastas, locks, logs e idempotência (`studioId` + `generationId`) usam a mesma chave.
- Renomear o estúdio na dashboard não quebra URLs internas, assets nem o projeto Vercel já criado.
- Colisões na importação exigem sufixo/origem estável e regra de deduplicação (`DUPLICATE_STUDIO`).
