export function Badge({ children, variant = 'status', className = '', size = 'sm' }) {
  const variantClasses = {
    status: 'bg-[#16A085]/10 text-[#16A085] border border-[#16A085]/20',
    warning: 'bg-[#D64545]/10 text-[#D64545] border border-[#D64545]/20',
    success: 'bg-[#16A085]/10 text-[#16A085] border border-[#16A085]/20',
  };

  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-1.5 text-base',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium transition-all duration-200 ${
        variantClasses[variant] || variantClasses.status
      } ${sizeClasses[size]} ${className}`}
    >
      {children}
    </span>
  );
}