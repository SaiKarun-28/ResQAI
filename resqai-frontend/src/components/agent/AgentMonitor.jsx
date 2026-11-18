const agentNames = ['intake', 'triage', 'resource', 'planning', 'verification'];

export function AgentMonitor({ agents = {}, trace = [] }) {
  return (
    <section className="bg-panel border border-border-default rounded-lg p-4">
      <h2 className="text-lg font-semibold text-accent-amber mb-3">Agent Execution Monitor</h2>
      <p className="text-xs text-text-muted mb-3">Recorded results, not a live execution stream.</p>
      <ul className="space-y-3">
        {agentNames.map((name) => {
          const item = trace.find((entry) => entry.agent.toLowerCase().replace(/[_\s-]*agent$/, '') === name);
          const status = item?.status || agents[name] || 'pending';
          return (
            <li key={name} className="text-sm">
              <div className="flex justify-between gap-2">
                <span className="capitalize">{name} Agent</span>
                <span className={`text-xs capitalize ${status === 'completed' ? 'text-emerald-300' : status === 'failed' ? 'text-red-300' : 'text-text-muted'}`}>{status}</span>
              </div>
              {item && <p className="text-xs text-text-muted mt-1 break-words">{item.model} · {item.duration_ms.toFixed(1)} ms</p>}
              {item?.error && <p className="text-xs text-red-300 mt-1 break-words">{item.error}</p>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
