export function Button({ children, variant = 'primary', size = 'md', className = '', disabled = false, onClick, ...props }) {
  const sizeClasses = {
    sm: 'px-3 py-1 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base',
  };

  const variantClasses = {
    primary: 'bg-[#E9A23B] text-black hover:bg-[#E9A23B]/90 active:bg-[#E9A23B]/80 font-bold',
    secondary: 'bg-[#2D3748] text-white hover:bg-[#2D3748]/90 active:bg-[#2D3748]/80',
    ghost: 'bg-transparent border border-white text-white hover:bg-white/10 active:bg-white/20',
  };

  return (
    <button
      className={`rounded-xl transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#E9A23B] ${
        variantClasses[variant] || variantClasses.primary
      } ${sizeClasses[size]} ${className} ${disabled ? 'cursor-not-allowed opacity-70' : ''}`}
      type="button"
      disabled={disabled}
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  );
}