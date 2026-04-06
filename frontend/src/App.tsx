import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { api } from './api/client';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import UploadPage from './pages/UploadPage';
import TransactionsPage from './pages/TransactionsPage';
import TransactionDetailPage from './pages/TransactionDetailPage';
import StatementsPage from './pages/StatementsPage';
import StatementReviewPage from './pages/StatementReviewPage';
import InsightsPage from './pages/InsightsPage';
import BudgetsPage from './pages/BudgetsPage';
import BillsPage from './pages/BillsPage';
import GmailPage from './pages/GmailPage';
import ImportsPage from './pages/ImportsPage';
import TaxPage from './pages/TaxPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import AccountPage from './pages/AccountPage';
import AssistantPage from './pages/AssistantPage';
import AccountsPage from './pages/AccountsPage';
import OnboardingPage from './pages/OnboardingPage';
import NetWorthPage from './pages/NetWorthPage';
import SubscriptionsPage from './pages/SubscriptionsPage';

function PrivateRoute({ children }: { children: React.ReactNode }) {
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

export default function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  );
}
