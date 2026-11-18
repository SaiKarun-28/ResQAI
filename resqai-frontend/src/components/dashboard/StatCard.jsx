import { TrendingUp, TrendingDown } from 'lucide-react';

export function StatCard({ title, value, change, icon: Icon }) {
  const isNegative = change?.startsWith('-');
  return (
    <div className="border border-border-default rounded-2xl bg-panel p-4">
      <div className="flex justify-between items-start gap-2 mb-3">
        <span className="text-sm text-text-muted font-medium">{title}</span>
        {Icon && <Icon size={18} className="text-accent-amber shrink-0" aria-hidden="true" />}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold tracking-tight">{value}</span>
        {change && <span className={`inline-flex items-center gap-1 text-xs ${isNegative ? 'text-accent-green' : 'text-accent-red'}`}>
          {isNegative ? <TrendingDown size={12} /> : <TrendingUp size={12} />}{change}
        </span>}
      </div>
    </div>
  );
}
