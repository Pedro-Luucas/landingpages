# Plano de implementação — Gerador automatizado de landing pages para estúdios musicais

## 1. Objetivo e resultado esperado

Construir um sistema capaz de importar uma base JSON de estúdios musicais, enriquecer um estúdio por vez com dados públicos da web e redes sociais, analisar seu conteúdo com IA, gerar uma landing page factual usando um de pelo menos quatro templates compartilhados, permitir revisão humana em uma pequena dashboard e, após aprovação explícita, publicar o estúdio como um projeto Vercel independente.

O sistema será um único repositório e um único app Next.js. Não haverá cópia do código por estúdio. Cada deploy usará o mesmo código e definirá `STUDIO_ID` para selecionar, durante o build, os dados e ativos do estúdio correspondente.

### Princípios obrigatórios

- Stack web: Next.js com App Router, TypeScript e Tailwind CSS, iniciada com a configuração padrão atual do `create-next-app`.
- Pipeline de coleta e processamento: Python.
- Um único repositório, um único app e quatro ou mais templates reutilizáveis.
- Dados, progresso e histórico persistidos em JSON com escrita atômica.
- Processamento inicial sequencial: um estúdio por vez, sempre com aprovação humana antes do deploy.
- Scraping apenas de páginas públicas, sem login e sem contornar bloqueios, CAPTCHA ou controles de acesso.
- Instagram é a fonte social prioritária; Facebook é fallback e complemento.
- Links intermediários podem ser seguidos. Na ausência de perfil válido, executar pesquisa web pelo estúdio.
- Analisar até 30 posts recentes, coletar seus textos e selecionar/baixar até 10 fotos úteis.
- Baixar a foto de perfil como logo independentemente de ela parecer uma marca gráfica.
- Coletar, quando publicamente disponíveis: bio, destaques, textos dos posts, avaliações Google, equipamentos, preços, horários e localização.
- IA pode inferir livremente cores, tipografia, estilo, template e direção visual, mas não pode inventar fatos.
- Cada site aprovado vira um Vercel Project independente, usando o mesmo repositório e `STUDIO_ID`.
- A arquitetura deve permitir evolução posterior para lotes de 500–2.000 sites sem reescrita do domínio.

## 2. Escopo do MVP

### Incluído

1. Importação e normalização do JSON original de estúdios.
2. Fila persistida em JSON e processamento de um estúdio por vez.
3. Descoberta de Instagram/Facebook por link direto, agregador/intermediário e pesquisa web.
4. Coleta pública de perfil e até 30 posts recentes.
5. Coleta/enriquecimento de dados comerciais e geográficos públicos.
6. Download de logo e seleção de até 10 imagens.
7. `AIProvider` abstrato para análise multimodal, branding e copy.
8. Quatro templates responsivos compartilhados.
9. Dashboard para executar, acompanhar, revisar, corrigir, aprovar, rejeitar e publicar.
10. Preview por `STUDIO_ID` e deploy independente na Vercel.
11. Logs estruturados, histórico de tentativas, idempotência e retomada após falha.

### Fora do MVP

- Login em Instagram/Facebook, automação de conta ou resolução de CAPTCHA.
- Edição visual drag-and-drop.
- Processamento paralelo em produção.
- CRM, disparo de mensagens ou venda automática.
- Compra/configuração automática de domínio próprio.
- Republicação automática após mudança de dados sem nova aprovação.
- Banco relacional ou fila externa; devem existir interfaces para futura substituição do JSON.

## 3. Regras de produto e precedência de fontes

### Descoberta social

Executar a seguinte cadeia, registrando cada tentativa e evidência:

1. Validar o campo `website` e demais URLs da fonte original.
2. Aceitar links diretos de Instagram e Facebook.
3. Abrir links intermediários públicos, como Linktree e Beacons, e extrair links sociais.
4. Se não houver perfil válido, pesquisar na web usando combinações de nome, cidade, estado, endereço e termos `Instagram`/`Facebook`.
5. Pontuar candidatos por nome, cidade, endereço, telefone, domínio e links cruzados.
6. Selecionar automaticamente somente quando a confiança atingir o limiar configurado; em caso ambíguo, exigir escolha humana.
7. Priorizar Instagram; usar Facebook como fallback ou fonte complementar.

### Precedência para fatos

1. Site oficial ou perfil social oficial do estúdio.
2. Fonte original importada.
3. Google Business/Maps e fontes comerciais públicas confiáveis.
4. Diretórios de terceiros, sempre marcados com menor confiança.
5. Inferências da IA nunca são fatos publicáveis.

Conflitos devem ser preservados no dossiê com origem, data de coleta e confiança. Preço, horário, equipamento e avaliação não podem ser publicados sem fonte registrada. Dados ausentes devem resultar na omissão elegante da seção, nunca em texto inventado.

## 4. Arquitetura proposta

```text
Navegador
  ├─ landing pública/preview ───────┐
  └─ dashboard interna ─────────────┤
                                    v
                         Next.js App Router
                         ├─ templates compartilhados
                         ├─ API/ações administrativas
                         ├─ leitura do StudioRepository
                         └─ adaptador de deploy Vercel
                                    |
                                    v
                         JSON + assets locais
                                    ^
                                    |
                         Python pipeline/CLI
                         ├─ importação e normalização
                         ├─ descoberta social/web
                         ├─ scraping público
                         ├─ download/curadoria de mídia
                         └─ AIProvider
```

### Limite entre componentes

- O Python é responsável por coleta, normalização, download, análise e atualização do estado do pipeline.
- O Next.js é responsável por renderização, preview, dashboard, correções humanas, aprovação e acionamento do deploy.
- Ambos devem obedecer aos mesmos JSON Schemas versionados.
- O app não deve depender diretamente de caminhos espalhados; toda leitura/escrita passa por `StudioRepository`/`StateRepository`.
- O deploy usa apenas registros em estado `approved` e um snapshot imutável da revisão aprovada.

## 5. Estrutura de pastas

```text
studio-sites/
├─ app/
│  ├─ (public)/
│  │  ├─ page.tsx                         # resolve STUDIO_ID no deploy
│  │  └─ preview/[studioId]/page.tsx      # preview local/protegido
│  ├─ dashboard/
│  │  ├─ page.tsx
│  │  └─ studios/[studioId]/page.tsx
│  ├─ api/
│  │  ├─ studios/[studioId]/route.ts
│  │  ├─ pipeline/[studioId]/route.ts
│  │  ├─ approve/[studioId]/route.ts
│  │  └─ deploy/[studioId]/route.ts
│  ├─ layout.tsx
│  └─ globals.css
├─ components/
│  ├─ dashboard/
│  ├─ landing/
│  └─ ui/
├─ templates/
│  ├─ index.ts
│  ├─ editorial/
│  ├─ immersive/
│  ├─ minimal/
│  └─ bold/
├─ lib/
│  ├─ repositories/
│  │  ├─ studio-repository.ts
│  │  └─ state-repository.ts
│  ├─ schemas/
│  ├─ studio-loader.ts
│  ├─ template-registry.ts
│  ├─ vercel.ts
│  ├─ auth.ts
│  └─ logger.ts
├─ pipeline/
│  ├─ pyproject.toml
│  ├─ src/studio_pipeline/
│  │  ├─ cli.py
│  │  ├─ config.py
│  │  ├─ orchestrator.py
│  │  ├─ repositories/
│  │  ├─ importers/
│  │  ├─ discovery/
│  │  ├─ scrapers/
│  │  ├─ enrichment/
│  │  ├─ media/
│  │  ├─ ai/
│  │  │  ├─ base.py
│  │  │  ├─ factory.py
│  │  │  └─ providers/
│  │  ├─ validation/
│  │  └─ observability/
│  └─ tests/
├─ data/
│  ├─ source/estudios.json                # fonte original, somente leitura
│  ├─ studios/<studioId>/
│  │  ├─ studio.json                      # registro normalizado atual
│  │  ├─ dossier.json                     # evidências brutas/normalizadas
│  │  ├─ generated.json                   # branding/copy/template
│  │  ├─ approved.json                    # snapshot imutável aprovado
│  │  └─ deployment.json
│  ├─ state/pipeline.json
│  ├─ state/locks/
│  └─ logs/YYYY-MM-DD.jsonl
├─ public/studios/<studioId>/
│  ├─ logo.<ext>
│  ├─ images/01.<ext> ... 10.<ext>
│  └─ manifest.json
├─ schemas/
│  ├─ studio.schema.json
│  ├─ dossier.schema.json
│  ├─ generated.schema.json
│  ├─ pipeline.schema.json
│  └─ deployment.schema.json
├─ scripts/
│  ├─ validate-data.ts
│  └─ check-studio-build.ts
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ e2e/
├─ .env.example
├─ package.json
└─ README.md
```

`data/` e `public/studios/` serão úteis localmente no MVP. Antes da escala em múltiplos runners, os repositórios deverão poder usar armazenamento de objetos sem alterar o domínio.

## 6. Identidade, schemas e contratos de dados

Todos os documentos devem conter `schemaVersion`, datas ISO 8601 em UTC e um `studioId` estável. O ID deve ser gerado uma vez, preferencialmente como slug normalizado acrescido de um sufixo curto derivado de cidade/estado ou do ID da origem. Mudanças futuras no nome não alteram o ID.

### 6.1 `studio.json`

```ts
type Studio = {
  schemaVersion: 1;
  studioId: string;
  sourceId?: string;
  name: string;
  type?: string;
  slug: string;
  location: {
    city?: string;
    state?: string;
    address?: string;
    latitude?: number;
    longitude?: number;
  };
  contacts: {
    phone?: string;
    website?: string;
    instagram?: string;
    facebook?: string;
  };
  source: {
    importedAt: string;
    sourceFile: string;
    sourceHash: string;
    originalRecord: unknown;
  };
  commercialScore?: number;
  pipelineStatus: PipelineStatus;
  updatedAt: string;
};
```

### 6.2 `dossier.json`

```ts
type Evidence<T> = {
  value: T;
  sourceUrl: string;
  sourceType: "official_site" | "instagram" | "facebook" | "google" | "directory" | "source_json";
  collectedAt: string;
  confidence: number;       // 0 a 1
  excerpt?: string;         // curto; não copiar conteúdo desnecessário
};

type Dossier = {
  schemaVersion: 1;
  studioId: string;
  discovery: {
    attempts: DiscoveryAttempt[];
    selectedProfiles: { instagram?: Evidence<string>; facebook?: Evidence<string> };
    requiresHumanReview: boolean;
  };
  social: {
    bio?: Evidence<string>;
    profileImage?: Evidence<string>;
    highlights: Array<Evidence<{ title: string; text?: string }>>;
    posts: Array<{
      externalId: string;
      url: string;
      publishedAt?: string;
      caption?: string;
      media: Array<{ url: string; type: "image" | "video" | "carousel"; localPath?: string }>;
      collectedAt: string;
    }>;
  };
  facts: {
    description: Evidence<string>[];
    equipment: Evidence<string[]>[];
    prices: Evidence<Array<{ label: string; amountText: string; conditions?: string }>>[];
    openingHours: Evidence<Array<{ day: string; intervals: string[] }>>[];
    googleReviews: Evidence<{ rating?: number; count?: number; excerpts?: string[] }>[];
    map: Evidence<{ latitude?: number; longitude?: number; address?: string; placeId?: string }>[];
  };
  media: {
    logo?: DownloadedAsset;
    candidates: MediaCandidate[];
    selected: DownloadedAsset[]; // no máximo 10
  };
  warnings: PipelineWarning[];
  completedAt?: string;
};
```

Não persistir URLs temporárias como se fossem ativos definitivos. Cada download deve registrar URL de origem, hash SHA-256, MIME real, tamanho, dimensões, caminho local, licença/status de uso quando identificável e data da coleta.

### 6.3 `generated.json`

```ts
type GeneratedSite = {
  schemaVersion: 1;
  studioId: string;
  generationId: string;
  inputHash: string;
  provider: string;
  model: string;
  promptVersion: string;
  templateId: "editorial" | "immersive" | "minimal" | "bold" | string;
  branding: {
    colors: { background: string; surface: string; primary: string; secondary: string; text: string; mutedText: string };
    fontHeading: string;
    fontBody: string;
    radius: "none" | "small" | "medium" | "large";
    mood: string[];
    imageTreatment?: string;
  };
  copy: {
    hero: { eyebrow?: string; title: string; subtitle?: string; primaryCta?: string };
    about?: { title: string; body: string };
    equipment?: { title: string; intro?: string; items: string[] };
    pricing?: { title: string; items: Array<{ label: string; value: string; note?: string }> };
    hours?: { title: string; items: Array<{ day: string; value: string }> };
    reviews?: { title: string; rating?: number; count?: number; excerpts?: string[] };
    contact: { title: string; body?: string; cta: string };
  };
  sections: Array<{ id: string; enabled: boolean; order: number }>;
  assetPaths: string[];
  factualClaims: Array<{ path: string; evidenceRefs: string[] }>;
  warnings: string[];
  createdAt: string;
};
```

Todo campo factual da copy deve apontar para ao menos uma evidência. Um validador determinístico deve rejeitar números, preços, horários, equipamentos, avaliações ou endereços sem referência.

### 6.4 `pipeline.json`

```ts
type PipelineStatus =
  | "imported"
  | "queued"
  | "discovering"
  | "needs_social_review"
  | "scraping"
  | "enriching"
  | "selecting_media"
  | "generating"
  | "validating"
  | "ready_for_review"
  | "approved"
  | "rejected"
  | "deploying"
  | "deployed"
  | "failed";

type PipelineItem = {
  studioId: string;
  status: PipelineStatus;
  currentStage?: string;
  attempt: number;
  retryAt?: string;
  lockedBy?: string;
  lockExpiresAt?: string;
  inputHash?: string;
  lastSuccessfulStage?: string;
  warnings: PipelineWarning[];
  error?: { code: string; message: string; retryable: boolean; stage: string; occurredAt: string };
  history: Array<{ from?: PipelineStatus; to: PipelineStatus; at: string; actor: string; reason?: string }>;
  createdAt: string;
  updatedAt: string;
};
```

### 6.5 Aprovação e deploy

`approved.json` é uma cópia integral e imutável do `generated.json`, acrescida de `approvedAt`, `approvedBy`, `approvalNote` e hashes dos ativos. Alterações posteriores criam nova geração e invalidam a aprovação anterior.

`deployment.json` deve conter `deploymentId`, `generationId`, `projectId`, `projectName`, `url`, `gitRef`, `status`, `studioId`, `environment`, `createdAt`, `readyAt`, `error` e histórico. Nunca persistir token da Vercel.

## 7. Máquina de estados e transições

Fluxo feliz:

```text
imported → queued → discovering → scraping → enriching
→ selecting_media → generating → validating → ready_for_review
→ approved → deploying → deployed
```

Desvios permitidos:

- `discovering → needs_social_review → discovering`: candidato ambíguo ou nenhum perfil confiável.
- Qualquer etapa operacional → `failed`: erro terminal ou tentativas esgotadas.
- `failed → queued`: retry manual, retomando de `lastSuccessfulStage`.
- `ready_for_review → rejected → queued`: revisão pede nova coleta/geração.
- `ready_for_review → approved`: somente ação humana autenticada.
- `approved → ready_for_review`: somente se os dados/ativos mudarem e o snapshot aprovado ficar obsoleto.
- `deploying → approved`: falha de deploy recuperável, mantendo a aprovação.

Transições devem ser validadas por uma tabela explícita, nunca por atribuição livre. Cada transição gera evento no histórico e log.

## 8. Pipeline Python detalhado

### Etapa A — importação

1. Validar o JSON de entrada e manter o registro original.
2. Normalizar strings, telefones, URLs, cidade/estado e coordenadas.
3. Gerar/deduplicar `studioId` usando dados estáveis.
4. Calcular `sourceHash`; se igual ao já importado, não reprocessar.
5. Criar `studio.json` e item `imported` sem sobrescrever enriquecimento existente.
6. Emitir relatório de importados, atualizados, duplicados e inválidos.

### Etapa B — descoberta social

1. Classificar URLs existentes.
2. Seguir redirecionamentos e extrair redes de páginas intermediárias públicas.
3. Executar pesquisa web apenas se necessário.
4. Normalizar handles/URLs, remover parâmetros de rastreamento e deduplicar.
5. Verificar correspondência do perfil com o estúdio.
6. Guardar todos os candidatos e a justificativa do score.
7. Pausar em `needs_social_review` se o resultado for ambíguo.

### Etapa C — scraping social público

1. Respeitar limites, termos aplicáveis, robots quando pertinente e backoff.
2. Coletar perfil, bio, foto, destaques que estejam publicamente acessíveis e até 30 posts mais recentes.
3. Coletar caption/texto, URL canônica, data e metadados de mídia.
4. Não tratar Reels sem imagem estática útil como foto selecionável; thumbnail pública pode ser candidata se tiver qualidade adequada.
5. Facebook complementa lacunas; não duplicar conteúdo cruzado.
6. Se a plataforma bloquear a coleta, registrar falha/aviso e seguir com fontes disponíveis; nunca tentar login ou evasão.

### Etapa D — enriquecimento factual

1. Visitar site oficial e páginas públicas relevantes.
2. Obter avaliações agregadas do Google, equipamentos, preços, horários e localização/mapa quando disponíveis por meio permitido.
3. Normalizar fatos sem apagar a forma original.
4. Registrar origem e confiança por valor.
5. Identificar conflitos e dados possivelmente desatualizados para revisão.

### Etapa E — mídia

1. Baixar a foto de perfil como `logo`, validando tipo e limite de tamanho.
2. Montar candidatos a partir dos até 30 posts.
3. Remover duplicatas por hash perceptual e SHA-256.
4. Rejeitar arquivos corrompidos, muito pequenos ou de tipo inesperado.
5. Analisar qualidade, relevância, variedade, presença de ambiente/equipamento e adequação a hero/galeria.
6. Selecionar até 10 fotos, preservando diversidade e ordem editorial, e baixar versões locais.
7. Se houver menos de 10 fotos válidas, prosseguir com menos e adaptar o template.
8. Não baixar nem executar SVG/HTML como imagem; reencodar raster quando necessário.

### Etapa F — IA

Implementar a interface:

```python
class AIProvider(Protocol):
    def analyze_brand(self, dossier, asset_paths) -> BrandAnalysis: ...
    def select_media(self, dossier, candidates) -> MediaSelection: ...
    def generate_site(self, dossier, brand, selected_media) -> GeneratedSite: ...
```

Requisitos:

- Provider selecionado por configuração, sem imports do fornecedor fora do adaptador.
- Saída estruturada validada por JSON Schema/Pydantic.
- Prompt versionado e armazenado com provider/model.
- Retry apenas para erros transitórios; resposta inválida pode ser corrigida uma vez e depois falha claramente.
- Entrada inclui bio primeiro, seguida de destaques, captions dos 30 posts e demais evidências.
- Liberdade visual total dentro dos tokens aceitos pelos templates.
- Copy deve sintetizar tom e proposta do estúdio, mas usar apenas fatos sustentados.
- Não enviar dados ou mídia desnecessários ao provider.

### Etapa G — validação

1. Validar todos os schemas.
2. Verificar referências de evidência e existência/hashes dos ativos.
3. Impedir publicação de placeholders, URLs temporárias, fatos órfãos e links inválidos.
4. Verificar contraste mínimo, texto alternativo, headings, responsividade e seções vazias.
5. Executar build com o `STUDIO_ID` alvo.
6. Somente então definir `ready_for_review`.

## 9. Templates e renderização

Criar um contrato `LandingTemplateProps` único. Templates não leem JSON diretamente; recebem um `StudioViewModel` já validado.

Templates iniciais:

1. `editorial`: foco em narrativa, tipografia e avaliações.
2. `immersive`: hero fotográfico e galeria de ambiente/equipamentos.
3. `minimal`: layout limpo para estúdios com pouca mídia.
4. `bold`: cores fortes, blocos assimétricos e chamadas comerciais.

Cada template deve suportar hero, sobre, galeria, equipamentos, preços, horários, avaliações, contato e mapa, ocultando seções sem dados. Branding deve ser aplicado por CSS variables validadas, não por classes Tailwind montadas dinamicamente. Fontes devem vir de uma allowlist compatível com `next/font` ou fallback seguro.

O mapa incorporado deve usar endereço/coordenadas validados e URL construída internamente. Não aceitar HTML de embed vindo das fontes. Carregar o mapa de modo preguiçoso e oferecer link externo como fallback.

## 10. Dashboard web

### Lista

- Contagem por estado.
- Busca por nome/cidade/ID.
- Filtros de status e presença de rede social.
- Próximo estúdio da fila, última atualização e erro resumido.
- Ações: enfileirar, retomar, abrir revisão.

### Revisão do estúdio

- Dados originais e enriquecidos lado a lado com fontes.
- Candidatos sociais e score de confiança.
- Visualização dos 30 posts/metadados coletados e das 10 fotos escolhidas.
- Preview responsivo do template.
- Campos editáveis para correções factuais, template, paleta, copy e ordem/visibilidade de seções.
- Avisos sobre conflitos, ausências e baixa confiança.
- Ações separadas: salvar rascunho, regenerar, rejeitar, aprovar e publicar.
- Confirmação antes de deploy, exibindo `STUDIO_ID`, geração aprovada e nome do projeto.

No MVP, proteger `/dashboard` e APIs administrativas com segredo/sessão simples adequada ao ambiente. Nenhuma API de alteração pode ficar pública. Ações devem registrar ator e horário.

## 11. Deploy na Vercel

### Estratégia

- Um Vercel Project por estúdio.
- Todos apontam para o mesmo repositório e código.
- Cada projeto recebe `STUDIO_ID=<id>` e demais variáveis comuns.
- O build público lê exclusivamente `approved.json` correspondente.
- Nome do projeto sanitizado e único, por exemplo `studio-<slug>-<suffix>`.
- O adaptador da Vercel cria ou reutiliza projeto, configura variáveis e dispara/acompanha deploy.

### Segurança e consistência

- `VERCEL_TOKEN`, team/org ID e credenciais de IA ficam somente em variáveis de ambiente.
- Deploy é proibido sem snapshot aprovado e hashes válidos.
- Antes de criar um projeto, consultar por nome/ID para evitar duplicata.
- Repetir o comando para a mesma `generationId` retorna o deploy existente ou continua seu acompanhamento.
- Registrar URL e IDs, mas nunca segredos.
- Falha depois de criar o projeto deve ser retomável sem criar outro projeto.

### Observação para escala

Milhares de projetos ligados ao mesmo repositório podem gerar muitos builds em cada push, dependendo da configuração. No MVP, documentar e testar uma estratégia de deploy direcionado; antes do batch, avaliar limites/quotas atuais da Vercel, ignorar builds não relacionados ou adotar artefato/monorepo compatível, sem mudar o contrato `STUDIO_ID`.

## 12. Idempotência, concorrência e persistência JSON

### Idempotência

- Cada estágio calcula `inputHash` com dados de entrada, versão do scraper/prompt e configuração relevante.
- Se o estágio já terminou com o mesmo hash e seus arquivos existem, reutilizar o resultado.
- Downloads usam hash e caminho determinístico.
- Geração usa `generationId` determinístico ou chave de idempotência baseada no `inputHash`.
- Deploy usa `studioId + generationId` como chave de idempotência.
- `--force-stage <stage>` permite reexecução explícita sem apagar histórico.

### Escrita segura

- Escrever em arquivo temporário no mesmo volume, executar flush e renomear atomicamente.
- Validar schema antes da substituição.
- Manter backup curto do último documento válido ou log de eventos suficiente para recuperação.
- Usar lock por estúdio com owner, timestamp e TTL; lock expirado pode ser recuperado com evento de auditoria.
- Nunca permitir dois workers no mesmo estúdio. A interface do repositório deve preparar futura concorrência entre estúdios.
- Dashboard deve usar revisão otimista (`updatedAt`/etag) para não sobrescrever mudanças concorrentes.

## 13. Tratamento de erros

Definir erros estáveis por categoria:

- `INPUT_INVALID`, `SCHEMA_INVALID`, `DUPLICATE_STUDIO`.
- `SOCIAL_NOT_FOUND`, `SOCIAL_AMBIGUOUS`, `PLATFORM_BLOCKED`, `RATE_LIMITED`.
- `HTTP_TIMEOUT`, `HTTP_NOT_FOUND`, `DOWNLOAD_INVALID`, `ASSET_TOO_LARGE`.
- `AI_RATE_LIMITED`, `AI_OUTPUT_INVALID`, `AI_PROVIDER_ERROR`.
- `FACT_WITHOUT_EVIDENCE`, `BUILD_FAILED`, `APPROVAL_REQUIRED`.
- `VERCEL_AUTH_ERROR`, `VERCEL_QUOTA`, `DEPLOY_FAILED`.
- `LOCKED`, `LOCK_EXPIRED`, `STATE_CONFLICT`.

Política:

- Retry com backoff exponencial e jitter somente para timeout, 429 e 5xx transitórios.
- Não repetir automaticamente 401/403 persistente, schema inválido, perfil inexistente ou erro factual.
- Limitar tentativas por etapa, registrar a próxima tentativa e preservar checkpoint.
- Bloqueio de plataforma vira aviso/falha tratável, nunca tentativa de evasão.
- Erros exibidos na dashboard devem trazer etapa, mensagem compreensível, código, tentativa e ação recomendada, sem expor tokens ou stack traces.

## 14. Observabilidade e auditoria

- Logs JSONL com `timestamp`, `level`, `runId`, `studioId`, `stage`, `event`, `durationMs`, `attempt`, `status`, `errorCode` e metadados seguros.
- Um `runId` por execução e correlação em Python, Next.js e deploy.
- Métricas deriváveis: duração por estágio, sucesso/falha, retries, perfis encontrados, posts coletados, ativos válidos, custo/tokens da IA e deploys.
- Registrar chamadas externas com host, status, duração e volume; nunca captions inteiras, tokens ou dados sensíveis nos logs.
- Histórico de transições e ações humanas imutável/apensado.
- Dashboard mostra linha do tempo e permite baixar um relatório sanitizado do run.
- Comando de diagnóstico valida locks, schemas, arquivos ausentes e divergência de hashes.

## 15. Configuração e comandos

### Variáveis de ambiente

```dotenv
STUDIO_ID=
DATA_DIR=./data
ASSETS_DIR=./public/studios
APP_BASE_URL=http://localhost:3000
DASHBOARD_SECRET=
AI_PROVIDER=
AI_MODEL=
AI_API_KEY=
SEARCH_PROVIDER=
SEARCH_API_KEY=
VERCEL_TOKEN=
VERCEL_TEAM_ID=
LOG_LEVEL=info
```

Criar `.env.example`; nunca versionar `.env*` reais, tokens ou dados de sessão.

### Comandos esperados

```bash
# Web
npm install
npm run dev
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run validate:data
STUDIO_ID=<id> npm run build

# Pipeline Python
python -m venv .venv
python -m pip install -e "./pipeline[dev]"
python -m studio_pipeline import --input data/source/estudios.json
python -m studio_pipeline queue --studio-id <id>
python -m studio_pipeline run --studio-id <id>
python -m studio_pipeline retry --studio-id <id>
python -m studio_pipeline validate --studio-id <id>
python -m studio_pipeline doctor

# Deploy (via serviço/API protegida ou CLI administrativa)
npm run deploy:studio -- --studio-id <id> --generation-id <generationId>
```

No Windows, documentar equivalentes PowerShell para definir `STUDIO_ID`; os scripts npm devem ser multiplataforma e não depender de sintaxe exclusiva de shell Unix.

## 16. Testes

### Unitários

- Normalização, slug/ID estável e deduplicação.
- Classificação de URLs e extração de links intermediários usando fixtures.
- Score de correspondência social.
- Máquina de estados e transições proibidas.
- Escrita atômica, locks, TTL e conflitos de versão.
- Validação de evidências e bloqueio de alucinações factuais.
- Seleção de template, tokens visuais e ViewModel.
- Idempotência de estágio e deploy.

### Integração

- Importação → dossiê usando respostas HTTP gravadas/sanitizadas, sem depender das plataformas nos testes.
- Provider de IA fake produzindo saída válida e inválida.
- Pipeline retomando após falha em cada checkpoint.
- Dashboard alterando rascunho sem corromper JSON.
- Adaptador Vercel simulado para create/reuse/deploy/failure.

### E2E

- Processar um fixture completo até `ready_for_review`.
- Revisar, aprovar e gerar snapshot.
- Renderizar preview nos quatro templates em mobile e desktop.
- Validar links, mapa fallback, seções ausentes e acessibilidade básica.
- Executar build com `STUDIO_ID` válido e confirmar falha clara com ID ausente/inválido.
- Fluxo de deploy em ambiente de teste/simulado; deploy real somente em smoke test autorizado.

## 17. Milestones e critérios de aceite

### M0 — Fundação e decisões registradas

Entregas:

- Scaffold Next.js/TypeScript/Tailwind e pacote Python.
- Estrutura de pastas, `.env.example`, lint, typecheck e testes.
- ADRs curtos para JSON, `STUDIO_ID`, um projeto por estúdio e limites de scraping público.
- JSON Schemas iniciais e fixtures sem dados sensíveis.

Critérios de aceite:

- `npm run lint`, `npm run typecheck` e testes básicos passam.
- Pipeline Python instala e sua CLI exibe ajuda.
- Schemas são validados em TypeScript e Python com fixtures equivalentes.

### M1 — Repositórios JSON, importação e fila

Entregas:

- Importador idempotente, IDs estáveis, deduplicação e relatório.
- `StudioRepository`, `StateRepository`, escrita atômica, locks e máquina de estados.
- CLI de importação, queue, run vazio, retry e doctor.

Critérios de aceite:

- Reimportar o mesmo arquivo não duplica nem altera registros sem necessidade.
- Interrupção simulada durante escrita mantém o último JSON válido.
- Dois processos não adquirem o mesmo lock.
- Um estúdio pode ser enfileirado e retomado preservando histórico.

### M2 — Descoberta social e scraping público

Entregas:

- Classificação de links diretos/intermediários.
- Adaptador de pesquisa web configurável.
- Scrapers públicos desacoplados para Instagram/Facebook e site oficial.
- Coleta de bio, logo, destaques acessíveis e até 30 posts/captions.

Critérios de aceite:

- Fixtures cobrem link direto, intermediário, pesquisa, perfil ambíguo, ausente e bloqueado.
- Instagram vence Facebook quando ambos são válidos.
- Candidato ambíguo pausa para revisão; não é escolhido silenciosamente.
- Nenhum fluxo exige login ou tenta contornar bloqueio.

### M3 — Enriquecimento e mídia

Entregas:

- Evidências para avaliações, equipamentos, preços, horários e mapa.
- Downloader seguro, deduplicação, scoring e seleção de até 10 fotos.
- Manifesto de ativos e limpeza apenas de temporários órfãos conhecidos.

Critérios de aceite:

- Todo fato contém URL, tipo de fonte, horário e confiança.
- Logo é baixada quando acessível.
- Até 10 imagens válidas, variadas e locais são selecionadas; menos imagens não quebram o fluxo.
- Arquivos malformados, enormes ou de MIME divergente são rejeitados.

### M4 — AIProvider, branding e copy factual

Entregas:

- Interface abstrata, provider fake e ao menos um adaptador real configurável.
- Prompts versionados e saída estruturada.
- Análise de bio → destaques → captions → demais fatos.
- Validador de factualidade/evidências.

Critérios de aceite:

- Trocar provider exige apenas configuração e novo adaptador.
- Saída inválida nunca chega à renderização.
- Preço, horário, avaliação, equipamento e endereço sem evidência bloqueiam a geração.
- Dados ausentes são omitidos ou descritos sem alegações inventadas.

### M5 — Quatro templates e preview

Entregas:

- Registry e contrato compartilhado.
- Templates editorial, immersive, minimal e bold.
- Landing acessível por `STUDIO_ID` e preview por rota administrativa.
- Mapa seguro, galeria otimizada, SEO e metadados básicos.

Critérios de aceite:

- Um mesmo `generated.json` pode ser renderizado em qualquer template.
- Os quatro layouts funcionam em 360 px e desktop sem overflow.
- Lighthouse local acordado: acessibilidade e boas práticas sem erros críticos; imagens com dimensões/alt e carregamento apropriado.
- Ausência de preços, horários, reviews ou imagens oculta/adapta a seção.

### M6 — Dashboard e aprovação humana

Entregas:

- Lista, filtros, detalhe, evidências, timeline, edição e preview.
- Escolha manual de perfil social e mídia.
- Aprovação/rejeição e snapshot imutável.
- Proteção das rotas administrativas e trilha de auditoria.

Critérios de aceite:

- Nenhum deploy pode ser acionado antes da aprovação.
- Edição concorrente é detectada e não sobrescreve dados.
- Alterar dados após aprovação invalida o snapshot ou cria nova geração.
- Usuário consegue entender e recuperar um erro pela dashboard.

### M7 — Vercel por estúdio

Entregas:

- Adaptador Vercel idempotente.
- Criação/reuso de projeto, variável `STUDIO_ID`, deploy e acompanhamento.
- Registro de `projectId`, URL, geração e status.

Critérios de aceite:

- Repetir deploy da mesma geração não cria projeto duplicado.
- Dois estúdios aprovados geram projetos/URLs independentes com o mesmo código.
- O build falha antes de publicar se `STUDIO_ID` ou snapshot for inválido.
- Falha transitória é retomada sem perder aprovação.

### M8 — Hardening e piloto

Entregas:

- Logs, métricas deriváveis, diagnóstico, limites, retries e runbook.
- Testes E2E e piloto com 5–10 estúdios representativos.
- Documentação de operação, recuperação e custos.

Critérios de aceite:

- Pipeline retoma depois de interrupções simuladas em todas as etapas.
- Nenhum segredo aparece em JSON, log, bundle ou erro da dashboard.
- Piloto registra tempo, taxa de sucesso, custo de IA, bloqueios e trabalho manual.
- Problemas do piloto são priorizados antes de habilitar batch.

### M9 — Preparação para batch de 500–2.000 (não ativar ainda)

Entregas:

- Abstrações de storage, fila, worker e rate limiter documentadas/testadas.
- Comando batch com dry-run, limite, filtros, pausa e orçamento, inicialmente desabilitado por feature flag.
- Estratégia de quotas de busca, IA, plataformas e Vercel.

Critérios de aceite:

- Domínio e templates não precisam mudar ao substituir JSON por storage/banco/fila externos.
- Batch respeita concorrência por host/provider e orçamento global.
- É possível pausar, retomar e repetir sem duplicar ativos, geração ou projetos.
- Há aprovação explícita do operador antes de habilitar execução em massa.

## 18. Passos operacionais para o Cursor

O Cursor deve executar na ordem abaixo, entregando uma milestone por vez. Não avançar deixando testes vermelhos ou contratos parcialmente implementados.

1. Ler este plano inteiro e inspecionar o repositório, arquivos existentes e instruções locais (`AGENTS.md`, regras e README). Preservar alterações do usuário.
2. Criar uma checklist rastreável por milestone e marcar apenas itens realmente verificados.
3. Implementar M0. Usar o scaffold padrão do `create-next-app` com TypeScript, Tailwind, ESLint e App Router; não criar um app por estúdio.
4. Definir primeiro os schemas e fixtures; gerar/compartilhar tipos de modo que Python e TypeScript validem o mesmo contrato.
5. Implementar M1 e provar importação idempotente, locks e escrita atômica com testes de falha.
6. Implementar M2 por adaptadores. Usar fixtures/mocks nos testes e documentar limites e conformidade de cada fonte.
7. Implementar M3, mantendo evidências e ativos rastreáveis. Nunca usar texto extraído sem URL de origem.
8. Implementar M4 começando pelo provider fake; só depois integrar um provider real. Guardar versão de prompt/modelo e custo quando disponível.
9. Implementar M5 com conteúdo fixture antes de ligar ao pipeline. Garantir que templates consumam somente `StudioViewModel`.
10. Implementar M6 com proteção administrativa, controle otimista e snapshots aprovados.
11. Implementar M7 primeiro contra adaptador fake. Solicitar/configurar credenciais apenas quando o código e os testes estiverem prontos. Não criar projetos reais sem autorização explícita.
12. Executar M8 com piloto pequeno e produzir relatório de problemas, custos e ajustes.
13. Implementar apenas a preparação de M9; manter batch desligado até nova decisão.
14. Ao final de cada milestone, executar lint, typecheck, testes relevantes e build de ao menos um fixture; registrar comandos, resultados e pendências no README ou relatório de progresso.

### Regras de execução para o Cursor

- Não inventar endpoints privados ou métodos de evasão para redes sociais.
- Não escolher bibliotecas de scraping, pesquisa ou IA sem confirmar manutenção, licença e adequação no momento da implementação.
- Não misturar acesso a arquivos com regras de negócio; usar repositórios/interfaces.
- Não permitir que a IA escreva HTML/React arbitrário. Ela produz dados estruturados consumidos pelos templates.
- Não inserir texto externo como HTML; sanitizar/escapar todo conteúdo.
- Não publicar rascunho nem usar dados não aprovados no build público.
- Não apagar dados anteriores em retry; criar histórico e substituir somente arquivos derivados de forma atômica.
- Se uma fonte mudar ou bloquear acesso, falhar de forma observável e oferecer revisão manual.
- Toda alteração de schema exige incremento/migração e fixtures de compatibilidade.

## 19. Definition of Done do MVP

O MVP está concluído somente quando:

1. Um JSON de origem pode ser importado duas vezes sem duplicação.
2. Um estúdio pode percorrer o pipeline completo com checkpoint e retomada.
3. Links direto, intermediário e encontrado por pesquisa são tratados com confiança/auditoria.
4. O dossiê contém o conteúdo público disponível, até 30 posts e suas captions, logo e até 10 fotos válidas.
5. Branding/copy são gerados por `AIProvider` abstrato, com validação de fatos.
6. A landing funciona com qualquer um dos quatro templates e omite dados ausentes com elegância.
7. A dashboard permite revisar fontes, corrigir, aprovar e acompanhar o deploy.
8. O deploy aprovado cria/reutiliza um projeto Vercel independente configurado com `STUDIO_ID`.
9. Repetições não duplicam estúdio, arquivos, geração, aprovação ou projeto.
10. Logs e timeline permitem explicar o que ocorreu sem vazar segredos.
11. Testes, lint, typecheck e build passam.
12. Um piloto pequeno foi concluído antes de qualquer processamento em massa.

## 20. Decisões a parametrizar, não bloquear

As escolhas abaixo devem ficar configuráveis e podem ser fechadas durante a implementação sem alterar a arquitetura:

- Provider/modelo de IA e limites de custo.
- Provedor de pesquisa web e fonte permitida para dados Google/Maps.
- Limiar de confiança para descoberta social.
- Máximo de retries, timeout, rate limit e tamanho de mídia.
- Regra exata de nome de projeto Vercel e time/organização alvo.
- Método final de autenticação da dashboard.

Usar defaults conservadores, documentá-los e evitar valores mágicos no código.
