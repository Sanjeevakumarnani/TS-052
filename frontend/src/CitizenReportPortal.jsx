import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Camera,
  CheckCircle,
  ChevronRight,
  ClipboardList,
  Eye,
  HelpCircle,
  LogIn,
  LogOut,
  MapPin,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  User,
} from 'lucide-react';
import {
  LocationVerifyPage,
  ResidentDashboard,
} from './VerificationWorkflow.jsx';

const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

const DIMENSIONS = [
  { key: 'roads', label: 'Road accessibility' },
  { key: 'electricity', label: 'Electricity reliability' },
  { key: 'digital', label: 'Digital connectivity' },
  { key: 'public_digital', label: 'Public digital infrastructure' },
  { key: 'essential_services', label: 'Essential-service access' },
];

export default function UserCitizenPortal() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);

  // Active user view: 'feedback' | 'location' | 'anonymous-report' | 'track-status'
  const [activeTab, setActiveTab] = useState('feedback');

  // Login form state
  const [username, setUsername] = useState('citizen');
  const [password, setPassword] = useState('citizen123');
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState('');

  // Anonymous report form state
  const [states, setStates] = useState([]);
  const [districts, setDistricts] = useState([]);
  const [mandals, setMandals] = useState([]);
  const [villages, setVillages] = useState([]);

  const [selectedState, setSelectedState] = useState('');
  const [selectedDistrict, setSelectedDistrict] = useState('');
  const [selectedMandal, setSelectedMandal] = useState('');
  const [selectedVillage, setSelectedVillage] = useState('');

  const [reportDimension, setReportDimension] = useState('roads');
  const [reportDescription, setReportDescription] = useState('');
  const [submittingReport, setSubmittingReport] = useState(false);
  const [reportError, setReportError] = useState('');
  const [reportReceipt, setReportReceipt] = useState(null);

  // Status lookup state
  const [refCode, setRefCode] = useState('');
  const [lookingUp, setLookingUp] = useState(false);
  const [statusError, setStatusError] = useState('');
  const [reportStatus, setReportStatus] = useState(null);

  // Check existing session
  useEffect(() => {
    const token = localStorage.getItem('infrapulse_token');
    if (!token) {
      setAuthChecking(false);
      return;
    }
    fetch(`${API}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.user) {
          setCurrentUser(data.user);
        } else {
          localStorage.removeItem('infrapulse_token');
        }
      })
      .catch(() => {})
      .finally(() => setAuthChecking(false));
  }, []);

  // Load states for reporting cascade
  useEffect(() => {
    if (activeTab === 'anonymous-report') {
      fetch(`${API}/api/v1/geography/states`)
        .then((res) => (res.ok ? res.json() : { items: [] }))
        .then((data) => setStates(data.items || []))
        .catch(() => {});
    }
  }, [activeTab]);

  useEffect(() => {
    setDistricts([]); setMandals([]); setVillages([]);
    setSelectedDistrict(''); setSelectedMandal(''); setSelectedVillage('');
    if (!selectedState) return;
    fetch(`${API}/api/v1/geography/districts?state_code=${selectedState}`)
      .then((res) => (res.ok ? res.json() : { items: [] }))
      .then((data) => setDistricts(data.items || []))
      .catch(() => {});
  }, [selectedState]);

  useEffect(() => {
    setMandals([]); setVillages([]);
    setSelectedMandal(''); setSelectedVillage('');
    if (!selectedDistrict) return;
    fetch(`${API}/api/v1/geography/mandals?district_code=${selectedDistrict}`)
      .then((res) => (res.ok ? res.json() : { items: [] }))
      .then((data) => setMandals(data.items || []))
      .catch(() => {});
  }, [selectedDistrict]);

  useEffect(() => {
    setVillages([]);
    setSelectedVillage('');
    if (!selectedMandal) return;
    fetch(`${API}/api/v1/geography/villages?mandal_code=${selectedMandal}`)
      .then((res) => (res.ok ? res.json() : { items: [] }))
      .then((data) => setVillages(data.items || []))
      .catch(() => {});
  }, [selectedMandal]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginBusy(true);
    setLoginError('');
    try {
      const res = await fetch(`${API}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Login failed.');
      }
      localStorage.setItem('infrapulse_token', data.token);
      setCurrentUser(data.user);
      setActiveTab('feedback');
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setLoginBusy(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('infrapulse_token');
    setCurrentUser(null);
    setActiveTab('feedback');
  };

  const handleAnonymousSubmit = async (e) => {
    e.preventDefault();
    if (!selectedVillage) {
      setReportError('Please select a village.');
      return;
    }
    if (reportDescription.trim().length < 5) {
      setReportError('Description must be at least 5 characters.');
      return;
    }

    setSubmittingReport(true);
    setReportError('');
    setReportReceipt(null);

    try {
      const res = await fetch(`${API}/api/v1/field-reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          village_id: selectedVillage,
          dimension: reportDimension,
          description: reportDescription.trim(),
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'Submission failed.');
      }
      setReportReceipt(data);
      setReportDescription('');
    } catch (err) {
      setReportError(err.message);
    } finally {
      setSubmittingReport(false);
    }
  };

  const handleLookup = async (e) => {
    e.preventDefault();
    if (!refCode.trim()) return;

    setLookingUp(true);
    setStatusError('');
    setReportStatus(null);

    try {
      const res = await fetch(`${API}/api/v1/field-reports/status/${encodeURIComponent(refCode.trim())}`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Report not found with that reference code.');
      }
      setReportStatus(data.report || data);
    } catch (err) {
      setStatusError(err.message);
    } finally {
      setLookingUp(false);
    }
  };

  if (authChecking) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f5f7f5' }}>
        <div style={{ textAlign: 'center', color: '#55655b' }}>
          <div className="spinner" style={{ display: 'inline-block', width: 24, height: 24, border: '2px solid #ccc', borderTopColor: '#244735', borderRadius: '50%', animation: 'spin 0.8s linear infinite', marginBottom: 12 }} />
          <div>Loading Citizen Portal…</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f4f7f4', color: '#1a241e', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      
      {/* Top Navigation Bar: Strictly Citizen Level */}
      <nav style={{ background: '#1c3829', color: '#fff', padding: '12px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: '0 2px 6px rgba(0,0,0,0.1)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 34, height: 34, background: '#2c5841', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <ShieldCheck size={20} color="#b7e7c2" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: '0.02em' }}>InfraPulse Citizen Portal</div>
            <div style={{ fontSize: 11, color: '#a2cbb1' }}>RURAL INFRASTRUCTURE CITIZEN SERVICES</div>
          </div>
        </div>

        {currentUser ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, background: 'rgba(255,255,255,0.1)', padding: '5px 12px', borderRadius: 20 }}>
              <User size={14} color="#b7e7c2" />
              <span><strong>{currentUser.display_name || currentUser.username}</strong></span>
              <span style={{ fontSize: 11, background: '#2c5841', padding: '2px 6px', borderRadius: 10, textTransform: 'capitalize' }}>
                {currentUser.role}
              </span>
            </div>
            <button
              onClick={handleLogout}
              style={{ background: 'transparent', border: '1px solid #739f84', color: '#fff', padding: '6px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
            >
              <LogOut size={13} /> Log out
            </button>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: '#a2cbb1' }}>
            Citizen & Resident Access
          </div>
        )}
      </nav>

      {/* Main Container */}
      <div style={{ maxWidth: 840, margin: '30px auto', padding: '0 16px' }}>

        {/* If user is not logged in: Show the clean citizen login screen + link to anonymous citizen reporting */}
        {!currentUser ? (
          <div style={{ maxWidth: 460, margin: '40px auto' }}>
            <div className="panel" style={{ background: '#fff', borderRadius: 12, padding: 32, boxShadow: '0 3px 12px rgba(0,0,0,0.06)', border: '1px solid #dce4de' }}>
              <div style={{ textAlign: 'center', marginBottom: 20 }}>
                <div style={{ width: 44, height: 44, background: '#e1ede4', borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
                  <LogIn size={22} color="#244735" />
                </div>
                <h2 style={{ margin: '0 0 6px', fontSize: 22, fontWeight: 700, color: '#162b20' }}>Resident & Citizen Sign In</h2>
                <p style={{ margin: 0, fontSize: 13, color: '#55655b' }}>
                  Log in to access your village development projects and submit photo feedback.
                </p>
              </div>

              <form onSubmit={handleLogin}>
                <label className="field-label" style={{ display: 'block', marginBottom: 14 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#33443a', display: 'block', marginBottom: 4 }}>Username</span>
                  <input
                    className="field-control"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #c8d3cc', fontSize: 14, boxSizing: 'border-box' }}
                  />
                </label>

                <label className="field-label" style={{ display: 'block', marginBottom: 16 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#33443a', display: 'block', marginBottom: 4 }}>Password</span>
                  <input
                    type="password"
                    className="field-control"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #c8d3cc', fontSize: 14, boxSizing: 'border-box' }}
                  />
                </label>

                {loginError && (
                  <div style={{ background: '#fdf3f2', border: '1px solid #f8b4af', color: '#b3261e', padding: '10px 12px', borderRadius: 8, fontSize: 13, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlertCircle size={15} />
                    <span>{loginError}</span>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loginBusy}
                  style={{ width: '100%', padding: '12px', background: '#244735', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: loginBusy ? 'not-allowed' : 'pointer' }}
                >
                  {loginBusy ? 'Signing In…' : 'Sign In as Citizen'}
                </button>
              </form>

              {/* Demo Credentials Quick Fill */}
              <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid #eef2ef' }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#55655b', textTransform: 'uppercase', marginBottom: 8 }}>
                  Demo Citizen Credentials
                </div>
                <button
                  type="button"
                  onClick={() => { setUsername('citizen'); setPassword('citizen123'); }}
                  style={{ width: '100%', textAlign: 'left', background: '#f5f8f5', border: '1px solid #d4dfd6', padding: '10px 14px', borderRadius: 8, cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                >
                  <div>
                    <strong style={{ color: '#162b20', fontSize: 13 }}>citizen</strong>
                    <div style={{ fontSize: 12, color: '#55655b' }}>Password: citizen123 (Resident Role)</div>
                  </div>
                  <span style={{ fontSize: 12, color: '#244735', fontWeight: 600 }}>Fill</span>
                </button>
              </div>

              {/* Direct link to isolated public reporting without login */}
              <div style={{ marginTop: 20, textAlign: 'center', fontSize: 13, color: '#55655b' }}>
                Need to submit an observation without logging in? <br />
                <a href="/report" style={{ color: '#244735', fontWeight: 700, textDecoration: 'underline' }}>
                  Use Isolated Anonymous Reporting Portal
                </a>
              </div>
            </div>
          </div>
        ) : (
          /* User is logged in: Show strictly citizen/user options */
          <div>
            {/* Citizen Tabs: Only user-level capabilities */}
            <div style={{ display: 'flex', gap: 10, background: '#e1e8e2', padding: 6, borderRadius: 10, marginBottom: 20, flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => setActiveTab('feedback')}
                style={{
                  flex: 1,
                  minWidth: 160,
                  padding: '10px 16px',
                  border: 'none',
                  borderRadius: 8,
                  background: activeTab === 'feedback' ? '#fff' : 'transparent',
                  color: activeTab === 'feedback' ? '#162b20' : '#55655b',
                  fontWeight: 700,
                  fontSize: 14,
                  cursor: 'pointer',
                  boxShadow: activeTab === 'feedback' ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <ClipboardList size={16} /> Submit Project Feedback
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('location')}
                style={{
                  flex: 1,
                  minWidth: 160,
                  padding: '10px 16px',
                  border: 'none',
                  borderRadius: 8,
                  background: activeTab === 'location' ? '#fff' : 'transparent',
                  color: activeTab === 'location' ? '#162b20' : '#55655b',
                  fontWeight: 700,
                  fontSize: 14,
                  cursor: 'pointer',
                  boxShadow: activeTab === 'location' ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <MapPin size={16} /> Verify Village Location
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('anonymous-report')}
                style={{
                  flex: 1,
                  minWidth: 160,
                  padding: '10px 16px',
                  border: 'none',
                  borderRadius: 8,
                  background: activeTab === 'anonymous-report' ? '#fff' : 'transparent',
                  color: activeTab === 'anonymous-report' ? '#162b20' : '#55655b',
                  fontWeight: 700,
                  fontSize: 14,
                  cursor: 'pointer',
                  boxShadow: activeTab === 'anonymous-report' ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <Send size={16} /> Field Observation
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('track-status')}
                style={{
                  flex: 1,
                  minWidth: 160,
                  padding: '10px 16px',
                  border: 'none',
                  borderRadius: 8,
                  background: activeTab === 'track-status' ? '#fff' : 'transparent',
                  color: activeTab === 'track-status' ? '#162b20' : '#55655b',
                  fontWeight: 700,
                  fontSize: 14,
                  cursor: 'pointer',
                  boxShadow: activeTab === 'track-status' ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <Search size={16} /> Track Report Status
              </button>
            </div>

            {/* View 1: Project Feedback with Camera & Evidence */}
            {activeTab === 'feedback' && (
              <ResidentDashboard onLogout={handleLogout} />
            )}

            {/* View 2: Location Verification */}
            {activeTab === 'location' && (
              <LocationVerifyPage
                currentUser={currentUser}
                onProceedToRecords={() => setActiveTab('feedback')}
              />
            )}

            {/* View 3: Embedded Citizen Field Observation */}
            {activeTab === 'anonymous-report' && (
              <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', border: '1px solid #e1e6e2' }}>
                <div style={{ marginBottom: 16 }}>
                  <h3 style={{ margin: '0 0 6px', fontSize: 20, fontWeight: 700, color: '#162b20' }}>
                    Submit a Village Field Observation
                  </h3>
                  <p style={{ margin: 0, color: '#55655b', fontSize: 14 }}>
                    Submit an observation or issue regarding infrastructure services in your village. All submissions receive an opaque reference code.
                  </p>
                </div>

                {reportReceipt ? (
                  <div style={{ background: '#f8faf9', border: '1.5px dashed #2e7d47', borderRadius: 10, padding: 20, marginBottom: 16 }}>
                    <div style={{ textAlign: 'center', marginBottom: 12 }}>
                      <CheckCircle size={36} color="#2e7d47" />
                      <h4 style={{ margin: '8px 0 4px', fontSize: 18 }}>Report Submitted</h4>
                      <p style={{ margin: 0, fontSize: 13, color: '#55655b' }}>Your private tracking reference code:</p>
                    </div>
                    <div style={{ fontSize: 18, fontFamily: 'monospace', fontWeight: 700, color: '#162b20', wordBreak: 'break-all', userSelect: 'all', background: '#fff', padding: '10px 14px', borderRadius: 6, border: '1px solid #e1e6e2', textAlign: 'center' }}>
                      {reportReceipt.reference_code}
                    </div>
                    <div style={{ marginTop: 16, display: 'flex', gap: 10 }}>
                      <button
                        type="button"
                        onClick={() => {
                          setRefCode(reportReceipt.reference_code);
                          setActiveTab('track-status');
                          setReportReceipt(null);
                        }}
                        style={{ flex: 1, padding: '10px', background: '#244735', color: '#fff', border: 'none', borderRadius: 6, fontWeight: 600, cursor: 'pointer' }}
                      >
                        Track Status
                      </button>
                      <button
                        type="button"
                        onClick={() => setReportReceipt(null)}
                        style={{ padding: '10px 16px', background: '#eef2ef', border: 'none', borderRadius: 6, fontWeight: 600, cursor: 'pointer' }}
                      >
                        Submit Another
                      </button>
                    </div>
                  </div>
                ) : (
                  <form onSubmit={handleAnonymousSubmit}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                      <div>
                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#55655b', marginBottom: 4 }}>State</label>
                        <select
                          value={selectedState}
                          onChange={(e) => setSelectedState(e.target.value)}
                          style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #c8d3cc', background: '#fff', fontSize: 14 }}
                        >
                          <option value="">— Select State —</option>
                          {states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                        </select>
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#55655b', marginBottom: 4 }}>District</label>
                        <select
                          value={selectedDistrict}
                          onChange={(e) => setSelectedDistrict(e.target.value)}
                          disabled={!districts.length}
                          style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #c8d3cc', background: districts.length ? '#fff' : '#f0f4f1', fontSize: 14 }}
                        >
                          <option value="">— Select District —</option>
                          {districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
                        </select>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                      <div>
                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#55655b', marginBottom: 4 }}>Mandal / Block</label>
                        <select
                          value={selectedMandal}
                          onChange={(e) => setSelectedMandal(e.target.value)}
                          disabled={!mandals.length}
                          style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #c8d3cc', background: mandals.length ? '#fff' : '#f0f4f1', fontSize: 14 }}
                        >
                          <option value="">— Select Mandal —</option>
                          {mandals.map((m) => <option key={m.code} value={m.code}>{m.name}</option>)}
                        </select>
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#55655b', marginBottom: 4 }}>Village *</label>
                        <select
                          value={selectedVillage}
                          onChange={(e) => setSelectedVillage(e.target.value)}
                          disabled={!villages.length}
                          required
                          style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #c8d3cc', background: villages.length ? '#fff' : '#f0f4f1', fontSize: 14 }}
                        >
                          <option value="">— Select Village —</option>
                          {villages.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                        </select>
                      </div>
                    </div>

                    <div style={{ marginBottom: 14 }}>
                      <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#55655b', marginBottom: 4 }}>Infrastructure Dimension</label>
                      <select
                        value={reportDimension}
                        onChange={(e) => setReportDimension(e.target.value)}
                        style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #c8d3cc', background: '#fff', fontSize: 14 }}
                      >
                        {DIMENSIONS.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
                      </select>
                    </div>

                    <div style={{ marginBottom: 16 }}>
                      <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#55655b', marginBottom: 4 }}>Observation Description *</label>
                      <textarea
                        rows={4}
                        value={reportDescription}
                        onChange={(e) => setReportDescription(e.target.value)}
                        placeholder="Describe the issue clearly (minimum 5 characters)…"
                        required
                        minLength={5}
                        maxLength={2000}
                        style={{ width: '100%', padding: '12px', borderRadius: 8, border: '1px solid #c8d3cc', fontSize: 14, boxSizing: 'border-box' }}
                      />
                    </div>

                    {reportError && (
                      <div style={{ background: '#fdf3f2', border: '1px solid #f8b4af', color: '#b3261e', padding: '10px 14px', borderRadius: 8, fontSize: 13, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <AlertCircle size={15} />
                        <span>{reportError}</span>
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={submittingReport || !selectedVillage || reportDescription.trim().length < 5}
                      style={{ width: '100%', padding: '12px', background: '#244735', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: submittingReport ? 'not-allowed' : 'pointer' }}
                    >
                      {submittingReport ? 'Submitting…' : 'Submit Field Observation'}
                    </button>
                  </form>
                )}
              </div>
            )}

            {/* View 4: Track Report Status */}
            {activeTab === 'track-status' && (
              <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', border: '1px solid #e1e6e2' }}>
                <h3 style={{ margin: '0 0 6px', fontSize: 20, fontWeight: 700, color: '#162b20' }}>
                  Track Report Verification Status
                </h3>
                <p style={{ margin: '0 0 16px', color: '#55655b', fontSize: 14 }}>
                  Enter your opaque reference code to check progress.
                </p>

                <form onSubmit={handleLookup} style={{ marginBottom: 20, display: 'flex', gap: 10 }}>
                  <input
                    type="text"
                    value={refCode}
                    onChange={(e) => setRefCode(e.target.value)}
                    placeholder="Enter reference code…"
                    required
                    style={{ flex: 1, padding: '12px 14px', borderRadius: 8, border: '1px solid #c8d3cc', fontSize: 14, fontFamily: 'monospace' }}
                  />
                  <button
                    type="submit"
                    disabled={lookingUp || !refCode.trim()}
                    style={{ padding: '12px 20px', background: '#244735', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer' }}
                  >
                    {lookingUp ? 'Searching…' : 'Search'}
                  </button>
                </form>

                {statusError && (
                  <div style={{ background: '#fdf3f2', border: '1px solid #f8b4af', color: '#b3261e', padding: '12px 14px', borderRadius: 8, fontSize: 13, marginBottom: 16 }}>
                    {statusError}
                  </div>
                )}

                {reportStatus && (
                  <div style={{ border: '1px solid #dbe2dd', borderRadius: 10, padding: 18, background: '#fbfcfb' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: '#55655b' }}>VERIFICATION STATUS</span>
                      <span style={{ padding: '3px 12px', borderRadius: 20, fontSize: 12, fontWeight: 700, textTransform: 'capitalize', background: reportStatus.verification_status === 'verified' ? '#e1f5e8' : reportStatus.verification_status === 'rejected' ? '#fde8e8' : '#fef3d6', color: reportStatus.verification_status === 'verified' ? '#1f6a38' : reportStatus.verification_status === 'rejected' ? '#b3261e' : '#8f5c00' }}>
                        {reportStatus.verification_status || 'unverified'}
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: 13, marginBottom: 14, paddingBottom: 14, borderBottom: '1px solid #eaefeb' }}>
                      <div>
                        <span style={{ color: '#687a6f', display: 'block', fontSize: 11 }}>Village ID</span>
                        <strong>{reportStatus.village_id}</strong>
                      </div>
                      <div>
                        <span style={{ color: '#687a6f', display: 'block', fontSize: 11 }}>Dimension</span>
                        <strong>{DIMENSIONS.find((d) => d.key === reportStatus.dimension)?.label || reportStatus.dimension}</strong>
                      </div>
                    </div>

                    <div>
                      <h4 style={{ margin: '0 0 10px', fontSize: 13, fontWeight: 700, color: '#244735' }}>Status History</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {(reportStatus.history || []).map((step, idx) => (
                          <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 12, background: '#fff', padding: '8px 12px', borderRadius: 6, border: '1px solid #eaefeb' }}>
                            <ChevronRight size={14} color="#2e7d47" style={{ marginTop: 2 }} />
                            <div style={{ flex: 1 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <strong style={{ textTransform: 'capitalize' }}>{step.status}</strong>
                                <span style={{ color: '#88998e' }}>{step.changed_at ? new Date(step.changed_at).toLocaleString() : '—'}</span>
                              </div>
                              {step.note && <div style={{ color: '#55655b', marginTop: 2 }}>{step.note}</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
