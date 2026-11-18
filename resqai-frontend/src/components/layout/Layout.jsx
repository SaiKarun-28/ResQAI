import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { LayoutComponent } from './LayoutComponent';

export function Layout({ children, activePage }) {
  return (
    <div className="min-h-screen bg-bg text-text-main">
      <a href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus(); }} className="sr-only focus:not-sr-only focus:block focus:p-3">Skip to content</a>
      <LayoutComponent>
        <Sidebar activePage={activePage} />
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 p-3 sm:p-5">
            {children}
          </main>
        </div>
      </LayoutComponent>
    </div>
  );
}
