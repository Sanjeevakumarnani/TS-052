import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import CitizenReportPortal from './CitizenReportPortal.jsx';
import './styles.css';
import 'leaflet/dist/leaflet.css';

const path = window.location.pathname.toLowerCase();
const hash = window.location.hash.toLowerCase();
const search = window.location.search.toLowerCase();

// Explicitly route citizen/user endpoints to CitizenReportPortal
const isCitizenUserRoute =
  path.includes('/user') ||
  path.includes('/citizen') ||
  path.includes('/report') ||
  hash.includes('user') ||
  hash.includes('citizen') ||
  hash.includes('report') ||
  search.includes('page=user') ||
  search.includes('page=citizen') ||
  search.includes('page=report');

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {isCitizenUserRoute ? <CitizenReportPortal /> : <App />}
  </React.StrictMode>
);

