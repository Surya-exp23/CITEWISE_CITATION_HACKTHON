import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Ingest from "./pages/Ingest";
import Institution from "./pages/Institution";
import Researcher from "./pages/Researcher";
import Review from "./pages/Review";
import Policy from "./pages/Policy";
import Verify from "./pages/Verify";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public verify page: no nav chrome */}
        <Route path="/verify/:reportId" element={<Verify />} />
        <Route element={<Layout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/ingest" element={<Ingest />} />
          <Route path="/institutions/:id" element={<Institution />} />
          <Route path="/researchers/:id" element={<Researcher />} />
          <Route path="/review" element={<Review />} />
          <Route path="/policy" element={<Policy />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

function NotFound() {
  return (
    <div className="panel panel-pad text-center py-16">
      <p className="text-2xl font-bold">404</p>
      <p className="text-neutral-400 mt-2">That page doesn't exist.</p>
    </div>
  );
}
