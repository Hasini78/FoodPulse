import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppLayout } from './layouts/AppLayout'
import { ChurnPage } from './pages/ChurnPage'
import { CustomersPage } from './pages/CustomersPage'
import { ForecastPage } from './pages/ForecastPage'
import { InsightsPage } from './pages/InsightsPage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { OverviewPage } from './pages/OverviewPage'
import { RecommendationsPage } from './pages/RecommendationsPage'
import { RestaurantsPage } from './pages/RestaurantsPage'
import { SegmentsPage } from './pages/SegmentsPage'
import { SentimentPage } from './pages/SentimentPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/app" element={<AppLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="restaurants" element={<RestaurantsPage />} />
          <Route path="sentiment" element={<SentimentPage />} />
          <Route path="segments" element={<SegmentsPage />} />
          <Route path="churn" element={<ChurnPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="forecast" element={<ForecastPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="insights" element={<InsightsPage />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
