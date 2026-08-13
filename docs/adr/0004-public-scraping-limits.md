# 0004 — Limites de scraping público

- Status: Aceita
- Data: 2026-08-12
- Milestone: M0

## Contexto

O pipeline enriquece cada estúdio com dados da web e redes sociais. Login, automação de conta, CAPTCHA e evasão de controle de acesso estão fora do MVP e são inaceitáveis. Fatos inventados não podem ir para a landing.

## Decisão

Coletar somente páginas e recursos publicamente acessíveis. Sem login, sem resolver CAPTCHA, sem contornar bloqueios, robots pertinentes ou controles de acesso.

Cadeia de descoberta: URLs da fonte → Instagram/Facebook diretos → links intermediários públicos (Linktree, Beacons e similares) → pesquisa web se ainda não houver perfil válido. Instagram é a fonte social primária; Facebook é fallback e complemento (preenche lacunas, não duplica conteúdo cruzado).

Se a plataforma bloquear a coleta: registrar aviso ou falha (`PLATFORM_BLOCKED` / equivalente), aplicar backoff só para erros transitórios, e seguir com as fontes ainda disponíveis. Nunca tentar evasão. 401/403 persistente não é retentado automaticamente.

IA pode inferir cores, tipografia, estilo, template e direção visual. Não pode inventar fatos. Preço, horário, equipamento e avaliação só entram na página com fonte registrada; dado ausente omite a seção.

## Consequências

- Cobertura incompleta é esperada e tratável: o dossiê guarda evidências, conflitos e confiança; a dashboard revisa ambiguidades.
- Scrapers permanecem desacoplados e substituíveis; o domínio não depende de sessão autenticada.
- Bloqueios viram estado observável, não um incentivo a workarounds.
- Copy e seções factuais ficam atadas a evidência; branding visual pode ser criativo.
