import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppLayout } from './layouts/AppLayout'
import { CustomersPage } from './pages/CustomersPage'
import { InsightsPage } from './pages/InsightsPage'
import { OverviewPage } from './pages/OverviewPage'
import { RestaurantsPage } from './pages/RestaurantsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="restaurants" element={<RestaurantsPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="insights" element={<InsightsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
