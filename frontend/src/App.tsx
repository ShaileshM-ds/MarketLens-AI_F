import { Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { ProductExplorer } from './pages/ProductExplorer';
import { AnalystDashboard } from './pages/AnalystDashboard';
import { MethodologyPage } from './pages/MethodologyPage';
import { ImageCreditsPage } from './pages/ImageCreditsPage';
import { ProductPage } from './pages/ProductPage';
import { ComparePage } from './pages/ComparePage';
import { WatchlistPage } from './pages/WatchlistPage';
import { SignInPage } from './pages/SignInPage';
import { NotFound } from './pages/NotFound';
import { AdminPage } from './pages/admin/AdminPage';
import { ImportWizard } from './pages/admin/ImportWizard';

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="products" element={<ProductExplorer />} />
        <Route path="products/:productId" element={<ProductPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="watchlist" element={<WatchlistPage />} />
        <Route path="signin" element={<SignInPage />} />
        <Route path="analyst" element={<AnalystDashboard />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="admin/import" element={<ImportWizard />} />
        <Route path="admin/import/:runId" element={<ImportWizard />} />
        <Route path="methodology" element={<MethodologyPage />} />
        <Route path="credits" element={<ImageCreditsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
