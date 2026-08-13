# 0003 — Um projeto Vercel por estúdio

- Status: Aceita
- Data: 2026-08-12
- Milestone: M0

## Contexto

Cada landing aprovada precisa de URL e ciclo de deploy independentes, sem duplicar o repositório. Compra automática de domínio próprio está fora do MVP. Ligar milhares de projetos ao mesmo git pode disparar muitos builds a cada push.

## Decisão

Após aprovação humana explícita, cada estúdio vira um Vercel Project independente apontando para o mesmo repositório e o mesmo código. O projeto recebe `STUDIO_ID=<id>` (e variáveis comuns). O build público lê somente o `approved.json` daquele estúdio — snapshot imutável da revisão aprovada — nunca rascunhos.

O adaptador cria ou reutiliza o projeto de forma idempotente: consultar por nome/ID antes de criar; nome sanitizado e único (`studio-<slug>-<suffix>`); repetir o comando para a mesma `generationId` retorna o deploy existente ou continua o acompanhamento. Falha após criar o projeto é retomável sem criar outro. Não persistir token da Vercel.

Não comprar nem configurar domínio próprio automaticamente. Deploy é proibido sem snapshot aprovado e hashes válidos.

No MVP, usar deploy direcionado (projeto/alvo específico), não rebuild em massa a cada push. Antes do batch (500–2.000 sites), avaliar quotas da Vercel, ignorar builds não relacionados ou adotar artefato/monorepo compatível — sem mudar o contrato `STUDIO_ID`.

## Consequências

- Isolamento por site: falha ou rollback de um estúdio não derruba os outros.
- Mesmo git + `STUDIO_ID` evita N forks; o risco de fan-out de builds fica documentado e mitigado no MVP por deploy direcionado.
- Escala futura pode exigir ignore de builds ou artefato, mas o contrato de identidade permanece.
- Domínios customizados, se existirem, serão manuais ou de milestone posterior.
