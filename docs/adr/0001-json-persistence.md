# 0001 — Persistência em JSON versionado

- Status: Aceita
- Data: 2026-08-12
- Milestone: M0

## Contexto

O MVP precisa persistir registros de estúdio, fila, progresso, locks e histórico de tentativas sem introduzir banco relacional, fila externa ou storage de objetos. Python (pipeline) e Next.js (dashboard/preview/deploy) devem ler e escrever os mesmos documentos. Mais tarde, lotes de 500–2.000 sites exigirão outro backend de armazenamento, mas o domínio não deve ser reescrito.

## Decisão

Persistir dados, progresso e histórico em JSON versionado (`schemaVersion` em cada documento), com datas ISO 8601 em UTC.

Toda leitura e escrita passa pelas interfaces `StudioRepository` e `StateRepository`. O app e o pipeline não acessam caminhos de arquivo espalhados.

Escrita atômica: validar o schema, gravar em arquivo temporário no mesmo volume, fazer flush e renomear. Manter backup curto do último documento válido (ou log suficiente para recuperação). Lock por estúdio com owner, timestamp e TTL; revisão otimista (`updatedAt`/etag) na dashboard.

No MVP não há banco relacional. As interfaces existem para que JSON local possa ser substituído por object storage, banco ou fila sem mudar o domínio.

## Consequências

- Contratos estáveis em `schemas/` compartilhado entre TypeScript e Python.
- Recuperação após interrupção: o último JSON válido permanece.
- Evolução para storage/DB/fila é troca de adaptador, não de regras de negócio.
- JSON em disco não escala sozinho para milhares de runners; isso fica para milestones posteriores.
