import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  Upload,
  List,
  FileText,
  BarChart3,
  Wallet,
  Receipt,
  ShieldCheck,
  Mail,
  FolderSearch,
  Download,
  LogOut,
  Menu,
  X,
  UserRound,
} from 'lucide-react';
import { api } from '../api/client';
import ThemeModeSelect from './ThemeModeSelect';
import AppLogo from './AppLogo';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/upload', icon: Upload, label: 'Upload' },
  { to: '/transactions', icon: List, label: 'Transactions' },
  { to: '/statements', icon: FileText, label: 'Statements' },
  { to: '/insights', icon: BarChart3, label: 'Insights' },
  { to: '/budgets', icon: Wallet, label: 'Budgets' },
  { to: '/bills', icon: Receipt, label: 'Bills' },
  { to: '/tax', icon: ShieldCheck, label: 'Tax & Audit' },
];

const secondaryItems = [
  { to: '/account', icon: UserRound, label: 'Account' },
  { to: '/gmail', icon: Mail, label: 'Gmail' },
  { to: '/imports', icon: FolderSearch, label: 'Imports' },
];

export default function Layout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const closeMobileNav = () => setMobileNavOpen(false);

  const handleExport = async () => {
    try {
      await api.exportCsv();
    } catch (err) {
      console.error('Export failed:', err);
    }
  };

  const handleLogout = () => {
    api.clearToken();
    window.location.href = '/login';
  };

  return (
    <div className="app-shell">
      <header className="app-mobile-top">
        <div className="app-brand-title" style={{ fontSize: '1rem', gap: '0.5rem' }}>
          <AppLogo size={18} />
          HisabClub
        </div>
        <button
          type="button"
          className="hc-btn hc-btn-ghost"
          onClick={() => setMobileNavOpen((v) => !v)}
          aria-label={mobileNavOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={mobileNavOpen}
        >
          {mobileNavOpen ? <X size={18} /> : <Menu size={18} />}
          Menu
        </button>
      </header>

      {mobileNavOpen && (
        <button
          type="button"
          className="app-sidebar-backdrop"
          onClick={() => setMobileNavOpen(false)}
          aria-label="Close sidebar"
        />
      )}

      <aside className="app-sidebar" data-open={mobileNavOpen ? 'true' : 'false'}>
        <div className="app-brand">
          <h1 className="app-brand-title">
            <AppLogo size={20} />
            HisabClub
          </h1>
          <p className="app-brand-subtitle">Privacy-first finance ledger</p>
        </div>

        <nav className="app-nav">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={closeMobileNav}
              className={({ isActive }) => `app-nav-link ${isActive ? 'active' : ''}`}
            >
              <Icon size={16} strokeWidth={1.5} />
              {label}
            </NavLink>
          ))}

          <div className="app-nav-section">
            {secondaryItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                onClick={closeMobileNav}
                className={({ isActive }) => `app-nav-link ${isActive ? 'active' : ''}`}
              >
                <Icon size={16} strokeWidth={1.5} />
                {label}
              </NavLink>
            ))}

            <button
              type="button"
              onClick={() => {
                closeMobileNav();
                handleExport();
              }}
              className="app-nav-action"
            >
              <Download size={16} strokeWidth={1.5} />
              Export CSV
            </button>
          </div>
        </nav>

        <div className="app-sidebar-footer">
          <ThemeModeSelect />
          <button
            type="button"
            onClick={() => {
              closeMobileNav();
              handleLogout();
            }}
            className="app-nav-action"
            style={{ marginTop: '0.75rem' }}
          >
            <LogOut size={16} strokeWidth={1.5} />
            Logout
          </button>
        </div>
      </aside>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
