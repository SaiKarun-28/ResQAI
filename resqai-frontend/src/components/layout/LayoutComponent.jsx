export function LayoutComponent({ children }) {
  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {children}
    </div>
  );
}
