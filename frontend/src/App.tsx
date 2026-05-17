import { lazy, Suspense, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { api } from './api/client';
import { ToastProvider } from './components/ui/Toast';

const Layout = lazy(() => import('./components/Layout'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const UploadPage = lazy(() => import('./pages/UploadPage'));
const TransactionsPage = lazy(() => import('./pages/TransactionsPage'));
const TransactionDetailPage = lazy(() => import('./pages/TransactionDetailPage'));
const StatementsPage = lazy(() => import('./pages/StatementsPage'));
const StatementReviewPage = lazy(() => import('./pages/StatementReviewPage'));
const InsightsPage = lazy(() => import('./pages/InsightsPage'));
const BudgetsPage = lazy(() => import('./pages/BudgetsPage'));
const BillsPage = lazy(() => import('./pages/BillsPage'));
const GmailPage = lazy(() => import('./pages/GmailPage'));
const ImportsPage = lazy(() => import('./pages/ImportsPage'));
const TaxPage = lazy(() => import('./pages/TaxPage'));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'));
const AccountPage = lazy(() => import('./pages/AccountPage'));
const AssistantPage = lazy(() => import('./pages/AssistantPage'));
const AccountsPage = lazy(() => import('./pages/AccountsPage'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
const NetWorthPage = lazy(() => import('./pages/NetWorthPage'));
const SubscriptionsPage = lazy(() => import('./pages/SubscriptionsPage'));

function PrivateRoute({ children }: { children: ReactNode }) {
  if (!api.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function LoginRoute() {
  if (api.isAuthenticated()) {
    return <Navigate to="/" replace />;
  }
  return <LoginPage />;
}

function FallbackRoute() {
  return <Navigate to={api.isAuthenticated() ? '/' : '/login'} replace />;
}

function PageFallback() {
  return <div className="hc-panel-sub" style={{ padding: 24 }}>Loading…</div>;
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <Layout />
              </PrivateRoute>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="upload" element={<UploadPage />} />
            <Route path="transactions" element={<TransactionsPage />} />
            <Route path="transactions/:transactionId" element={<TransactionDetailPage />} />
            <Route path="statements" element={<StatementsPage />} />
            <Route path="statements/:statementId/review" element={<StatementReviewPage />} />
            <Route path="insights" element={<InsightsPage />} />
            <Route path="budgets" element={<BudgetsPage />} />
            <Route path="bills" element={<BillsPage />} />
            <Route path="tax" element={<TaxPage />} />
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="account" element={<AccountPage />} />
            <Route path="accounts" element={<AccountsPage />} />
            <Route path="net-worth" element={<NetWorthPage />} />
            <Route path="subscriptions" element={<SubscriptionsPage />} />
            <Route path="onboarding" element={<OnboardingPage />} />
            <Route path="gmail" element={<GmailPage />} />
            <Route path="imports" element={<ImportsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
          <Route path="*" element={<FallbackRoute />} />
        </Routes>
      </Suspense>
      </ToastProvider>
    </BrowserRouter>
  );
}
