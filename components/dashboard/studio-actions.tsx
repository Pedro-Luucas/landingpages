"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const templateIds = ["editorial", "immersive", "minimal", "bold"] as const;

export function StudioActions({ studioId, templateId, status, hasAi, hasDeployHook }: {
  studioId: string;
  templateId: string;
  status: string;
  hasAi: boolean;
  hasDeployHook: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string>();
  const [message, setMessage] = useState<string>();

  async function call(label: string, url: string, body?: object, method = "POST") {
    setBusy(label);
    setMessage(undefined);
    try {
      const response = await fetch(url, {
        method,
        headers: { "content-type": "application/json" },
        body: body ? JSON.stringify(body) : "{}",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
      setMessage(`${label}: concluído.`);
      router.refresh();
    } catch (error) {
      setMessage(`${label}: ${error instanceof Error ? error.message : "falhou"}`);
    } finally {
      setBusy(undefined);
    }
  }

  return (
    <section className="border border-[#f0eadf]/20 p-5">
      <h2 className="font-mono text-xs uppercase tracking-[.2em] text-[#d7ff3f]">Ações</h2>
      <label className="mt-6 block font-mono text-[.65rem] uppercase tracking-[.14em] text-[#f0eadf]/55" htmlFor="template">Template</label>
      <select id="template" defaultValue={templateId} disabled={Boolean(busy)} onChange={(event) => call("Alterar template", `/api/studios/${studioId}`, { templateId: event.target.value }, "PATCH")} className="mt-2 w-full border border-[#f0eadf]/30 bg-[#11110f] px-3 py-3 text-sm">
        {templateIds.map((id) => <option key={id} value={id}>{id}</option>)}
      </select>
      <div className="mt-4 grid gap-3">
        <button disabled={Boolean(busy) || !hasAi} onClick={() => call("Gerar com IA", `/api/ai/${studioId}`)} className="border border-[#f0eadf]/30 px-4 py-3 text-left text-sm disabled:cursor-not-allowed disabled:opacity-35">Gerar nova direção com IA</button>
        <button disabled={Boolean(busy) || status !== "ready_for_review"} onClick={() => call("Aprovar", `/api/approve/${studioId}`, { approvedBy: "dashboard:human", approvalNote: "Revisado visualmente no dashboard." })} className="bg-[#d7ff3f] px-4 py-3 text-left text-sm font-semibold text-[#11110f] disabled:cursor-not-allowed disabled:opacity-35">Aprovar geração</button>
        <button disabled={Boolean(busy) || status !== "approved" || !hasDeployHook} onClick={() => call("Deploy", `/api/deploy/${studioId}`)} className="border border-[#d7ff3f] px-4 py-3 text-left text-sm text-[#d7ff3f] disabled:cursor-not-allowed disabled:opacity-35">Publicar na Vercel</button>
      </div>
      {!hasAi ? <p className="mt-4 text-xs leading-5 text-[#f0eadf]/45">IA disponível após configurar AI_GATEWAY_API_KEY ou OIDC da Vercel.</p> : null}
      {!hasDeployHook ? <p className="mt-2 text-xs leading-5 text-[#f0eadf]/45">Deploy do painel disponível após configurar VERCEL_DEPLOY_HOOK_URL.</p> : null}
      {message ? <p role="status" className="mt-4 border-l-2 border-[#d7ff3f] pl-3 text-xs leading-5">{message}</p> : null}
    </section>
  );
}
