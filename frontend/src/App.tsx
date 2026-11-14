import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Dashboards from "./pages/Dashboards";
import Regions from "./pages/Regions";
import Satellite from "./pages/Satellite";
import Vegetation from "./pages/Vegetation";
import Climate from "./pages/Climate";
import Water from "./pages/Water";
import Spatial from "./pages/Spatial";
import Statistics from "./pages/Statistics";
import Reports from "./pages/Reports";
import Methodology from "./pages/Methodology";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="dashboards" element={<Dashboards />} />
        <Route path="regions" element={<Regions />} />
        <Route path="satellite" element={<Satellite />} />
        <Route path="vegetation" element={<Vegetation />} />
        <Route path="climate" element={<Climate />} />
        <Route path="water" element={<Water />} />
        <Route path="spatial" element={<Spatial />} />
        <Route path="statistics" element={<Statistics />} />
        <Route path="reports" element={<Reports />} />
        <Route path="methodology" element={<Methodology />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
