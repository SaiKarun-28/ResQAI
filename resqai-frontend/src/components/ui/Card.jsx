export function Card({ children, className = '', variant = 'default' }) {
  const variantClasses = {
    default: 'bg-[#101D2C] border-[#1A2533]',
    alert: 'bg-[#26364A] border-[#2D3748]',
    card: 'bg-[#0A0F16] border-[#1A2533]',
  };

  return (
    <div
      className={`overflow-hidden border rounded-2xl shadow-sm transition-all duration-200 ${
        variantClasses[variant] || variantClasses.default
      } ${className}`}
    >
      <div className="p-6">{children}</div>
    </div>
  );
}