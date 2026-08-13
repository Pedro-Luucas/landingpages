export default async function DashboardLoginPage({ searchParams }: PageProps<"/dashboard-login">) {
  const query = await searchParams;
  return (
    <main className="min-h-screen bg-[#11110f] px-5 py-20 text-[#f0eadf]">
      <div className="mx-auto max-w-md border border-[#f0eadf]/25 p-7 sm:p-10">
        <p className="mb-12 font-mono text-xs uppercase tracking-[.28em] text-[#d7ff3f]">Área operacional</p>
        <h1 className="text-4xl font-semibold tracking-[-.05em]">Acessar dashboard</h1>
        <p className="mt-4 text-sm leading-6 text-[#f0eadf]/65">Use o segredo configurado em <code>DASHBOARD_SECRET</code>. A sessão expira em oito horas.</p>
        {query.error ? <p role="alert" className="mt-5 border-l-2 border-red-500 pl-3 text-sm text-red-300">Segredo inválido.</p> : null}
        <form action="/api/auth/login" method="post" className="mt-8 grid gap-4">
          <label htmlFor="secret" className="text-xs uppercase tracking-[.18em]">Segredo</label>
          <input id="secret" name="secret" type="password" required autoComplete="current-password" className="border border-[#f0eadf]/35 bg-transparent px-4 py-3 outline-none focus:border-[#d7ff3f]" />
          <button className="mt-2 bg-[#d7ff3f] px-4 py-3 font-semibold text-[#11110f]">Entrar</button>
        </form>
      </div>
    </main>
  );
}
