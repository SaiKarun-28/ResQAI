import { LayoutDashboard, PlusCircle, History, Activity, Info } from 'lucide-react';

const items = [
  { icon: LayoutDashboard, label: 'Overview', page: 'overview', href: '#/' },
  { icon: PlusCircle, label: 'New Incident', page: 'new', href: '#/new' },
  { icon: History, label: 'Incident History', page: 'history', href: '#/history' },
  { icon: Activity, label: 'Agent Monitor', page: 'agents', href: '#/agents' },
  { icon: Info, label: 'About ResQAI', page: 'about', href: '#/about' },
];

export function Sidebar({ activePage }) {
  return (
    <aside className="w-full lg:w-64 lg:shrink-0 bg-panel border-b lg:border-r border-border-default">
      <div className="p-4 flex items-center gap-3">
        <div className="w-10 h-10 shrink-0 bg-accent-amber rounded-lg flex items-center justify-center text-black font-bold" aria-hidden="true">R</div>
        <div>
          <p className="text-xl font-bold tracking-tight">ResQAI</p>
          <p className="text-[10px] text-accent-amber uppercase tracking-widest">Crisis Intelligence</p>
        </div>
      </div>
      <nav aria-label="Main navigation" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-1 gap-1 p-2">
        {items.map(({ icon: Icon, label, page, href }) => (
          <a key={page} href={href} aria-current={activePage === page ? 'page' : undefined}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl text-sm ${activePage === page ? 'bg-accent-amber/10 text-accent-amber' : 'text-text-muted hover:bg-surface hover:text-white'}`}>
            <Icon size={18} className="shrink-0" aria-hidden="true" />
            <span>{label}</span>
          </a>
        ))}
      </nav>
      <p className="p-4 text-xs text-text-muted">Decision support only. No live dispatch.</p>
    </aside>
  );
}
