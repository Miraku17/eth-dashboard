import { useQuery } from "@tanstack/react-query";

type Health = { status: string; version: string };

export default function App() {
  const { data, isLoading, error } = useQuery<Health>({
    queryKey: ["health"],
    queryFn: async () => {
      const r = await fetch("/api/health");
      if (!r.ok) throw new Error("health check failed");
      return r.json();
    },
  });

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-bold mb-4">Eth Analytics</h1>
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="text-lg font-semibold mb-2">Backend status</h2>
        {isLoading && <p>checking…</p>}
        {error && <p className="text-red-400">unreachable</p>}
        {data && (
          <p className="text-emerald-400">
            {data.status} (v{data.version})
          </p>
        )}
      </section>
    </main>
  );
}
