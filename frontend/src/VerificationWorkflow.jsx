/**
 * InfraPulse Village Verification Workflow UI
 * Pages: Auth (Login/Register), Geography cascade, Location Verify,
 *        Resident Dashboard, Observation Form with Camera Capture,
 *        My Submissions, Admin Import Console, Admin Review Console.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, Camera, Check, CheckCircle, ChevronDown,
  ClipboardCheck, ClipboardList, Download, Eye, FileText,
  Layers3, LogIn, LogOut, MapPin, RefreshCw, Search,
  Shield, Upload, User, Users, X, Zap, ArrowRight,
} from 'lucide-react';

const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------
function getToken() { return localStorage.getItem('infrapulse_token') || ''; }
function setToken(t) { if (t) localStorage.setItem('infrapulse_token', t); else localStorage.removeItem('infrapulse_token'); }

async function authApi(path, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  // Don't set Content-Type for FormData — browser handles boundary
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(`${API}${path}`, { ...options, headers });
  const type = res.headers.get('content-type') || '';
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const d = type.includes('json') ? await res.json() : await res.text(); msg = d.detail || d.message || msg; } catch {}
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return type.includes('json') ? res.json() : res;
}

// ---------------------------------------------------------------------------
// Shared micro-components
// ---------------------------------------------------------------------------
function WFNotice({ children, kind = 'info' }) {
  return (
    <div className={`notice notice-${kind}`} style={{ marginBottom: 12 }}>
      <AlertTriangle size={15} />
      <span>{children}</span>
    </div>
  );
}

function InlineError({ msg }) {
  if (!msg) return null;
  return <div className="inline-error" style={{ marginTop: 8 }}><AlertTriangle size={14} /> {msg}</div>;
}

function Spinner() {
  return <span className="spinner" style={{ display: 'inline-block', width: 18, height: 18, border: '2px solid #ccc', borderTopColor: '#333', borderRadius: '50%', animation: 'spin 0.8s linear infinite', verticalAlign: 'middle', marginRight: 6 }} />;
}

function StatusBadge({ status }) {
  const colors = {
    unverified: '#c18a30', verified: '#3a7d44', rejected: '#b63e35',
    flagged: '#7b4fa0', pending_info: '#444', accepted: '#3a7d44',
    operational: '#3a7d44', reportedly_completed: '#64816b',
    exists_but_damaged_or_not_functional: '#c18a30', under_construction: '#5555cc',
    exists_and_functional: '#3a7d44', not_found: '#b63e35', could_not_observe: '#888',
  };
  const color = colors[status] || '#666';
  return (
    <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 20, background: color + '22', color, border: `1px solid ${color}66`, fontSize: 12, fontWeight: 600, textTransform: 'capitalize' }}>
      {(status || '—').replace(/_/g, ' ')}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Login / Register
// ---------------------------------------------------------------------------
export function AuthPage({ onLogin }) {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('resident');
  const [displayName, setDisplayName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const body = mode === 'login'
        ? { username, password }
        : { username, password, role, display_name: displayName || undefined };
      const res = await authApi(`/api/v1/auth/${mode}`, { method: 'POST', body: JSON.stringify(body) });
      setToken(res.token);
      onLogin(res.user, res.token);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 440, margin: '40px auto' }}>
      <div className="panel" style={{ padding: 32 }}>
        <div className="panel-head">
          <div>
            <div className="eyebrow">{mode === 'login' ? 'SIGN IN' : 'CREATE ACCOUNT'}</div>
            <h2 style={{ marginTop: 4 }}>{mode === 'login' ? 'Log in to InfraPulse' : 'Register as a resident or admin'}</h2>
          </div>
          <LogIn size={20} />
        </div>
        <WFNotice>
          Credentials are stored as secure hashes server-side. Tokens are stored in localStorage — use only on trusted devices.
        </WFNotice>
        <form onSubmit={submit}>
          <label className="field-label">Username
            <input className="field-control" value={username} onChange={e => setUsername(e.target.value)} required autoComplete="username" />
          </label>
          <label className="field-label">Password
            <input className="field-control" type="password" value={password} onChange={e => setPassword(e.target.value)} required autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
          </label>
          {mode === 'register' && (
            <>
              <label className="field-label">Role
                <select className="field-control" value={role} onChange={e => setRole(e.target.value)}>
                  <option value="resident">Resident</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
              <label className="field-label">Display name (optional)
                <input className="field-control" value={displayName} onChange={e => setDisplayName(e.target.value)} />
              </label>
            </>
          )}
          <InlineError msg={error} />
          <button className="btn btn-primary btn-wide" type="submit" disabled={busy} style={{ marginTop: 16 }}>
            {busy ? <><Spinner /> Processing…</> : mode === 'login' ? 'Log in' : 'Create account'}
          </button>
        </form>
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          {mode === 'login'
            ? <span className="muted">No account? <button className="text-button" onClick={() => { setMode('register'); setError(''); }}>Register</button></span>
            : <span className="muted">Already have an account? <button className="text-button" onClick={() => { setMode('login'); setError(''); }}>Log in</button></span>
          }
        </div>

        {/* Pre-seeded demo credentials quick-fill */}
        <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid #eef2ef', fontSize: 13 }}>
          <div style={{ fontWeight: 700, color: '#33443a', marginBottom: 8 }}>Seeded Demo Credentials:</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: '8px 10px', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 2 }}
              onClick={() => { setUsername('admin'); setPassword('admin123'); setMode('login'); setError(''); }}
            >
              <strong>Admin Role</strong>
              <span className="muted" style={{ fontSize: 11 }}>admin / admin123</span>
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: '8px 10px', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 2 }}
              onClick={() => { setUsername('citizen'); setPassword('citizen123'); setMode('login'); setError(''); }}
            >
              <strong>Citizen / User Role</strong>
              <span className="muted" style={{ fontSize: 11 }}>citizen / citizen123</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Location Verification Page (Resident)
// ---------------------------------------------------------------------------
export function LocationVerifyPage({ currentUser, onProceedToRecords }) {
  const [states, setStates] = useState([]);
  const [districts, setDistricts] = useState([]);
  const [mandals, setMandals] = useState([]);
  const [villages, setVillages] = useState([]);
  const [selectedState, setSelectedState] = useState('');
  const [selectedDistrict, setSelectedDistrict] = useState('');
  const [selectedMandal, setSelectedMandal] = useState('');
  const [selectedVillage, setSelectedVillage] = useState('');
  const [gpsResult, setGpsResult] = useState(null);
  const [gpsError, setGpsError] = useState('');
  const [busy, setBusy] = useState(false);
  const [membership, setMembership] = useState(null);

  useEffect(() => {
    authApi('/api/v1/geography/states').then(r => setStates(r.items || [])).catch(() => {});
    authApi('/api/v1/me/village').then(r => setMembership(r.village)).catch(() => {});
  }, []);

  useEffect(() => {
    setDistricts([]); setMandals([]); setVillages([]);
    setSelectedDistrict(''); setSelectedMandal(''); setSelectedVillage('');
    if (!selectedState) return;
    authApi(`/api/v1/geography/districts?state_code=${selectedState}`).then(r => setDistricts(r.items || [])).catch(() => {});
  }, [selectedState]);

  useEffect(() => {
    setMandals([]); setVillages([]);
    setSelectedMandal(''); setSelectedVillage('');
    if (!selectedDistrict) return;
    authApi(`/api/v1/geography/mandals?district_code=${selectedDistrict}`).then(r => setMandals(r.items || [])).catch(() => {});
  }, [selectedDistrict]);

  useEffect(() => {
    setVillages([]);
    setSelectedVillage('');
    if (!selectedMandal) return;
    authApi(`/api/v1/geography/villages?mandal_code=${selectedMandal}`).then(r => setVillages(r.items || [])).catch(() => {});
  }, [selectedMandal]);

  const verifyLocation = () => {
    if (!selectedVillage) { setGpsError('Please select a village first.'); return; }
    setGpsError(''); setGpsResult(null); setBusy(true);
    if (!navigator.geolocation) { setGpsError('Geolocation is not supported by your browser.'); setBusy(false); return; }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const res = await authApi('/api/v1/village-memberships/verify-location', {
            method: 'POST',
            body: JSON.stringify({
              village_id: selectedVillage,
              latitude: pos.coords.latitude,
              longitude: pos.coords.longitude,
              accuracy_meters: pos.coords.accuracy,
            }),
          });
          setGpsResult(res);
          if (res.matched) {
            authApi('/api/v1/me/village').then(r => setMembership(r.village)).catch(() => {});
          }
        } catch (e) {
          setGpsError(e.message);
        } finally {
          setBusy(false);
        }
      },
      (err) => { setGpsError(`GPS error: ${err.message}`); setBusy(false); },
      { enableHighAccuracy: true, timeout: 15000 }
    );
  };

  return (
    <div>
      {membership && (
        <div className="panel" style={{ marginBottom: 20, padding: '14px 20px', background: '#f0faf3', border: '1px solid #b0dbb9' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <CheckCircle size={18} color="#3a7d44" />
            <span>Active membership: <strong>{membership.village_name || membership.village_id}</strong></span>
          </div>
        </div>
      )}
      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="eyebrow">RESIDENT VERIFICATION</div>
            <h2>Verify your village membership</h2>
            <p>Select your village using the geography cascade below, then press the GPS button to capture your current location. Location is accepted from anywhere for demo purposes.</p>
          </div>
          <MapPin size={20} />
        </div>
        <WFNotice>
          GPS is used to record your location against the selected village. For this demo, any location is accepted regardless of distance. Your coordinates are not shared publicly.
        </WFNotice>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12, marginTop: 16 }}>
          <label className="field-label">State
            <select className="field-control" value={selectedState} onChange={e => setSelectedState(e.target.value)}>
              <option value="">— select state —</option>
              {states.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
          </label>
          <label className="field-label">District
            <select className="field-control" value={selectedDistrict} onChange={e => setSelectedDistrict(e.target.value)} disabled={!districts.length}>
              <option value="">— select district —</option>
              {districts.map(d => <option key={d.code} value={d.code}>{d.name}</option>)}
            </select>
          </label>
          <label className="field-label">Mandal / Block
            <select className="field-control" value={selectedMandal} onChange={e => setSelectedMandal(e.target.value)} disabled={!mandals.length}>
              <option value="">— select mandal —</option>
              {mandals.map(m => <option key={m.code} value={m.code}>{m.name}</option>)}
            </select>
          </label>
          <label className="field-label">Village
            <select className="field-control" value={selectedVillage} onChange={e => setSelectedVillage(e.target.value)} disabled={!villages.length}>
              <option value="">— select village —</option>
              {villages.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
        </div>
        <button className="btn btn-primary" onClick={verifyLocation} disabled={busy || !selectedVillage} style={{ marginTop: 16 }}>
          {busy ? <><Spinner /> Getting GPS…</> : <><MapPin size={15} /> Verify my location</>}
        </button>
        <InlineError msg={gpsError} />
        {gpsResult && (
          <div style={{ marginTop: 16, padding: '16px 20px', background: '#f0faf3', border: '1.5px solid #6bb57d', borderRadius: 10, boxShadow: '0 2px 8px rgba(36,71,53,0.08)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <CheckCircle size={20} color="#244735" style={{ marginTop: 2, flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#162b20' }}>
                  Location Confirmed! Village Membership Verified
                </div>
                <div style={{ fontSize: 13, color: '#33443a', marginTop: 4 }}>
                  Your device location is accepted and recorded. You now have full verified access to view and report on local development projects.
                </div>
                {gpsResult.result?.distance_meters != null && (
                  <div style={{ fontSize: 12, color: '#55655b', marginTop: 4 }}>
                    Reference distance: {(gpsResult.result.distance_meters / 1000).toFixed(1)} km &bull; Location match verified
                  </div>
                )}
                
                {/* Direct action to access Development Records */}
                <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #cce5d3', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    style={{ background: '#244735', color: '#fff', padding: '10px 18px', borderRadius: 8, fontWeight: 700, fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 8, cursor: 'pointer', border: 'none' }}
                    onClick={() => {
                      if (onProceedToRecords) {
                        onProceedToRecords();
                      } else {
                        window.location.hash = '#feedback';
                      }
                    }}
                  >
                    <ClipboardList size={16} /> Proceed to Development Records <ArrowRight size={15} />
                  </button>
                  <span style={{ fontSize: 12, color: '#4a6052' }}>
                    View public works, take photos, and submit verification observations
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Camera Capture component
// ---------------------------------------------------------------------------
function CameraCapture({ onCapture, onCancel }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [streaming, setStreaming] = useState(false);
  const [gps, setGps] = useState(null);
  const [error, setError] = useState('');
  const streamRef = useRef(null);

  useEffect(() => {
    // Get GPS alongside camera
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        p => setGps({ lat: p.coords.latitude.toFixed(5), lon: p.coords.longitude.toFixed(5), acc: Math.round(p.coords.accuracy) }),
        () => {}
      );
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      .then(stream => {
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; }
        setStreaming(true);
      })
      .catch(e => setError(`Camera unavailable: ${e.message}. You can upload a photo instead.`));
    return () => { if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop()); };
  }, []);

  const capture = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);
    // GPS overlay at bottom
    if (gps) {
      ctx.fillStyle = 'rgba(0,0,0,0.55)';
      ctx.fillRect(0, canvas.height - 28, canvas.width, 28);
      ctx.fillStyle = '#fff';
      ctx.font = '13px monospace';
      ctx.fillText(`GPS: ${gps.lat}, ${gps.lon} ±${gps.acc}m  ${new Date().toISOString().slice(0, 19)}Z`, 8, canvas.height - 8);
    }
    canvas.toBlob(blob => {
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      onCapture(blob, gps);
    }, 'image/jpeg', 0.88);
  };

  return (
    <div style={{ background: '#000', borderRadius: 10, overflow: 'hidden', position: 'relative', maxWidth: 560 }}>
      {error
        ? <div style={{ color: '#fff', padding: 24 }}><AlertTriangle size={18} style={{ marginRight: 6 }} />{error}</div>
        : <>
          <video ref={videoRef} autoPlay playsInline muted style={{ width: '100%', display: 'block' }} />
          <canvas ref={canvasRef} style={{ display: 'none' }} />
          {gps && (
            <div style={{ position: 'absolute', bottom: 44, left: 0, right: 0, background: 'rgba(0,0,0,0.5)', color: '#fff', fontSize: 11, padding: '4px 10px', fontFamily: 'monospace' }}>
              GPS: {gps.lat}, {gps.lon} ±{gps.acc}m
            </div>
          )}
          <div style={{ display: 'flex', gap: 10, padding: 10, background: '#111' }}>
            <button className="btn btn-secondary" onClick={onCancel} style={{ flex: 1 }}>Cancel</button>
            {streaming && <button className="btn btn-primary" onClick={capture} style={{ flex: 2 }}><Camera size={15} /> Capture photo</button>}
          </div>
        </>
      }
    </div>
  );
}

// ---------------------------------------------------------------------------
// Observation / Submission Form
// ---------------------------------------------------------------------------
const OBSERVED_STATUSES = [
  { key: 'exists_and_functional', label: 'Exists and functional' },
  { key: 'exists_but_damaged_or_not_functional', label: 'Exists but damaged / not functional' },
  { key: 'under_construction', label: 'Under construction' },
  { key: 'reportedly_completed', label: 'Reportedly completed (not personally verified)' },
  { key: 'not_found', label: 'Not found at reported location' },
  { key: 'could_not_observe', label: 'Could not observe (access/visibility issue)' },
];

function ObservationForm({ record, onDone, onCancel }) {
  const [observedStatus, setObservedStatus] = useState('');
  const [notes, setNotes] = useState('');
  const [photoBlob, setPhotoBlob] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [gpsCapture, setGpsCapture] = useState(null);
  const [showCamera, setShowCamera] = useState(false);
  const [fileInput, setFileInput] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const handleCameraCapture = (blob, gps) => {
    setPhotoBlob(blob);
    setPhotoPreview(URL.createObjectURL(blob));
    setGpsCapture(gps);
    setShowCamera(false);
  };

  const handleFileChange = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setPhotoBlob(f);
    setPhotoPreview(URL.createObjectURL(f));
    setGpsCapture(null);
  };

  const submit = async () => {
    if (!observedStatus) { setError('Please select an observed status.'); return; }
    if (!photoBlob) { setError('Please capture or upload a photo.'); return; }
    setBusy(true); setError('');
    try {
      const form = new FormData();
      form.append('file', photoBlob, 'observation.jpg');
      form.append('observed_status', observedStatus);
      form.append('notes', notes);
      if (gpsCapture) {
        form.append('capture_latitude', gpsCapture.lat);
        form.append('capture_longitude', gpsCapture.lon);
        form.append('capture_accuracy', String(gpsCapture.acc));
      }
      form.append('client_capture_time', new Date().toISOString());
      const res = await authApi(`/api/v1/development-records/${record.id}/submissions`, { method: 'POST', body: form });
      setResult(res.submission);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <div className="panel" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <CheckCircle size={22} color="#3a7d44" />
          <h3 style={{ margin: 0 }}>Observation submitted</h3>
        </div>
        <p className="muted">Your submission ID: <strong>#{result.id}</strong></p>
        {result.ai_analysis && result.ai_analysis.status === 'complete' && (
          <div style={{ background: '#f5f7fb', borderRadius: 8, padding: 14, marginTop: 12 }}>
            <strong>AI analysis (preliminary):</strong>
            <p style={{ margin: '6px 0 0' }}>{result.ai_analysis.summary}</p>
          </div>
        )}
        <WFNotice>Your observation is queued for admin review. It will not affect village scores until an admin explicitly promotes it as a trusted indicator.</WFNotice>
        <button className="btn btn-primary" onClick={onDone} style={{ marginTop: 12 }}>Done</button>
      </div>
    );
  }

  if (showCamera) {
    return <CameraCapture onCapture={handleCameraCapture} onCancel={() => setShowCamera(false)} />;
  }

  return (
    <div className="panel" style={{ padding: 24 }}>
      <div className="panel-head">
        <div>
          <div className="eyebrow">FIELD OBSERVATION</div>
          <h3>{record.asset_or_project_name}</h3>
          <p className="muted">{record.dimension} · {record.description}</p>
        </div>
        <button className="icon-btn" onClick={onCancel} aria-label="Close"><X size={18} /></button>
      </div>
      <fieldset style={{ border: 'none', padding: 0, margin: '16px 0' }}>
        <legend style={{ fontWeight: 600, marginBottom: 8 }}>What did you observe? <span style={{ color: '#b63e35' }}>*</span></legend>
        {OBSERVED_STATUSES.map(s => (
          <label key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, cursor: 'pointer' }}>
            <input type="radio" name="obs_status" value={s.key} checked={observedStatus === s.key} onChange={() => setObservedStatus(s.key)} />
            {s.label}
          </label>
        ))}
      </fieldset>
      <label className="field-label">Additional notes (optional)
        <textarea className="field-control text-control" value={notes} onChange={e => setNotes(e.target.value)} rows={3} maxLength={2000} placeholder="Describe what you saw in detail…" />
      </label>
      <div style={{ margin: '16px 0' }}>
        <div style={{ fontWeight: 600, marginBottom: 10 }}>Photo evidence <span style={{ color: '#b63e35' }}>*</span></div>
        {photoPreview
          ? <div style={{ position: 'relative', display: 'inline-block' }}>
              <img src={photoPreview} alt="Captured evidence" style={{ maxWidth: 320, maxHeight: 240, borderRadius: 8, border: '1px solid #ddd' }} />
              <button className="icon-btn" onClick={() => { setPhotoBlob(null); setPhotoPreview(null); setGpsCapture(null); }}
                style={{ position: 'absolute', top: 4, right: 4, background: 'rgba(0,0,0,0.5)', borderRadius: '50%', color: '#fff' }} aria-label="Remove photo"><X size={14} /></button>
            </div>
          : <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" onClick={() => setShowCamera(true)}><Camera size={15} /> Open Camera</button>
              <label className="btn btn-secondary" style={{ cursor: 'pointer' }}>
                <Upload size={15} /> Upload photo
                <input type="file" accept="image/jpeg,image/png,image/webp" style={{ display: 'none' }} onChange={handleFileChange} />
              </label>
            </div>
        }
      </div>
      <InlineError msg={error} />
      <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="btn btn-primary" onClick={submit} disabled={busy}>
          {busy ? <><Spinner /> Submitting…</> : <><ClipboardCheck size={15} /> Submit observation</>}
        </button>
      </div>
      <WFNotice kind="info">Your GPS coordinates are embedded in the photo overlay only. The observation does not change village reliability scores until an admin reviews and promotes it.</WFNotice>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Resident Dashboard
// ---------------------------------------------------------------------------
export function ResidentDashboard({ onLogout }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [village, setVillage] = useState(null);
  const [tab, setTab] = useState('records'); // 'records' | 'submissions'
  const [submissions, setSubmissions] = useState([]);
  const [subLoading, setSubLoading] = useState(false);

  const DIMS = { digital: 'Digital', electricity: 'Electricity', roads: 'Roads', public_digital: 'Public digital', essential_services: 'Essential services' };

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [r, v] = await Promise.all([
        authApi('/api/v1/me/development-records'),
        authApi('/api/v1/me/village').catch(() => ({ village: null })),
      ]);
      setRecords(r.items || []);
      setVillage(v.village);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSubs = useCallback(async () => {
    setSubLoading(true);
    try {
      const r = await authApi('/api/v1/me/submissions');
      setSubmissions(r.items || []);
    } catch (e) {} finally { setSubLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === 'submissions') loadSubs(); }, [tab, loadSubs]);

  if (selectedRecord) {
    return <ObservationForm record={selectedRecord} onDone={() => { setSelectedRecord(null); load(); }} onCancel={() => setSelectedRecord(null)} />;
  }

  const grouped = records.reduce((acc, r) => { (acc[r.dimension] = acc[r.dimension] || []).push(r); return acc; }, {});

  return (
    <div>
      {village && (
        <div style={{ background: '#f0faf3', border: '1px solid #b0dbb9', borderRadius: 8, padding: '10px 16px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
          <CheckCircle size={16} color="#3a7d44" />
          <span>Verified resident of <strong>{village.village_name || village.village_id}</strong></span>
        </div>
      )}
      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="eyebrow">RESIDENT PORTAL</div>
            <h2>My dashboard</h2>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="icon-btn" onClick={load} aria-label="Refresh"><RefreshCw size={16} /></button>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid #eee', paddingBottom: 8 }}>
          {[['records', <><ClipboardList size={14} /> Development records</>], ['submissions', <><Eye size={14} /> My submissions</>]].map(([key, label]) => (
            <button key={key} className={`btn ${tab === key ? 'btn-primary' : 'btn-secondary'}`} style={{ fontSize: 13, padding: '6px 14px' }} onClick={() => setTab(key)}>{label}</button>
          ))}
        </div>

        {tab === 'records' && (
          <>
            {loading ? <div className="loading-state"><div className="spinner" /><span>Loading records…</span></div>
              : error ? <div className="inline-error">{error}</div>
              : records.length === 0 ? <div className="empty-state">No development records found for your village.</div>
              : Object.entries(grouped).map(([dim, recs]) => (
                <div key={dim} style={{ marginBottom: 20 }}>
                  <h3 style={{ fontSize: 14, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#555', marginBottom: 10 }}>{DIMS[dim] || dim}</h3>
                  <div style={{ display: 'grid', gap: 10 }}>
                    {recs.map(rec => (
                      <div key={rec.id} style={{ border: '1px solid #e8e8e8', borderRadius: 8, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 600 }}>{rec.asset_or_project_name}</div>
                          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{rec.description}</div>
                          <div style={{ marginTop: 6 }}><StatusBadge status={rec.reported_status} /></div>
                        </div>
                        <button className="btn btn-secondary" style={{ whiteSpace: 'nowrap', fontSize: 13 }} onClick={() => setSelectedRecord(rec)}>
                          <Camera size={14} /> Observe
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            }
          </>
        )}

        {tab === 'submissions' && (
          <>
            {subLoading ? <div className="loading-state"><div className="spinner" /><span>Loading…</span></div>
              : submissions.length === 0 ? <div className="empty-state">No submissions yet.</div>
              : <div style={{ display: 'grid', gap: 10 }}>
                {submissions.map(s => (
                  <div key={s.id} style={{ border: '1px solid #e8e8e8', borderRadius: 8, padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <strong>#{s.id}</strong>
                      <StatusBadge status={s.observed_status} />
                      <StatusBadge status={s.review_status || 'pending_review'} />
                      <span className="muted" style={{ fontSize: 12, marginLeft: 'auto' }}>{new Date(s.submitted_at).toLocaleString()}</span>
                    </div>
                    {s.notes && <p className="muted" style={{ margin: '6px 0 0', fontSize: 13 }}>{s.notes}</p>}
                    {s.ai_analysis?.summary && s.ai_analysis?.status === 'complete' && (
                      <p style={{ fontSize: 12, color: '#555', margin: '6px 0 0', fontStyle: 'italic' }}>AI: {s.ai_analysis.summary}</p>
                    )}
                  </div>
                ))}
              </div>
            }
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin Import Console
// ---------------------------------------------------------------------------
export function AdminImportConsole() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [histLoading, setHistLoading] = useState(false);

  const loadHistory = useCallback(async () => {
    setHistLoading(true);
    try {
      const r = await authApi('/api/v1/admin/imports');
      setHistory(r.items || []);
    } catch (e) {} finally { setHistLoading(false); }
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  const downloadTemplate = async () => {
    const res = await fetch(`${API}/api/v1/admin/imports/template.csv`, { headers: { Authorization: `Bearer ${getToken()}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'development_records_template.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  const handlePreview = async () => {
    if (!file) return;
    setBusy(true); setError(''); setPreview(null);
    try {
      const form = new FormData(); form.append('file', file);
      const r = await authApi('/api/v1/admin/imports/validate', { method: 'POST', body: form });
      setPreview(r);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setBusy(true); setError('');
    try {
      await authApi('/api/v1/admin/imports/confirm', {
        method: 'POST',
        body: JSON.stringify({
          batch_id: preview.batch_id,
          filename: preview.filename || file?.name || '',
          file_hash: preview.file_hash || '',
          records: preview.preview_records || [],
          errors: preview.rejected || [],
          notes: 'Confirmed via admin import console',
        }),
      });
      setPreview(null); setFile(null); loadHistory();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div>
      <div className="panel" style={{ marginBottom: 20 }}>
        <div className="panel-head">
          <div>
            <div className="eyebrow">ADMIN</div>
            <h2>Development Records Import</h2>
            <p>Upload a CSV of development records. Preview and confirm before committing.</p>
          </div>
          <Shield size={20} />
        </div>
        <WFNotice>Only admin accounts can import records. Imported data is marked as unverified until reviewed.</WFNotice>
        <button className="btn btn-secondary" onClick={downloadTemplate} style={{ marginBottom: 16 }}>
          <Download size={15} /> Download CSV template
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <input type="file" accept=".csv,text/csv" aria-label="Upload CSV" onChange={e => { setFile(e.target.files?.[0] || null); setPreview(null); setError(''); }} />
          <button className="btn btn-secondary" disabled={!file || busy} onClick={handlePreview}>{busy ? <><Spinner /> Validating…</> : 'Preview CSV'}</button>
        </div>
        <InlineError msg={error} />
        {preview && (
          <div style={{ marginTop: 16, border: '1px solid #d0e8d8', borderRadius: 8, padding: 16, background: '#f7fbf8' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <Check size={16} color="#3a7d44" />
              <strong>{preview.accepted_count} record(s) accepted, {preview.rejected_count || preview.rejected?.length || 0} rejected</strong>
            </div>
            {(preview.preview_records || []).slice(0, 20).length > 0 && (
              <div style={{ overflowX: 'auto', marginBottom: 12 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead><tr style={{ borderBottom: '1px solid #ddd' }}>
                    {['ID', 'Village', 'Dimension', 'Asset/Project', 'Status'].map(h => <th key={h} scope="col" style={{ textAlign: 'left', padding: '4px 8px', fontWeight: 600 }}>{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {(preview.preview_records || []).slice(0, 20).map((r, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: '4px 8px', fontFamily: 'monospace', fontSize: 11 }}>{r.id}</td>
                        <td style={{ padding: '4px 8px' }}>{r.village_name || r.village_id}</td>
                        <td style={{ padding: '4px 8px' }}>{r.dimension}</td>
                        <td style={{ padding: '4px 8px' }}>{r.asset_or_project_name}</td>
                        <td style={{ padding: '4px 8px' }}><StatusBadge status={r.reported_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {(preview.rejected || []).length > 0 && (
              <details style={{ marginBottom: 10 }}>
                <summary style={{ cursor: 'pointer', color: '#b63e35', fontWeight: 600 }}>{(preview.rejected || []).length} rejected row(s)</summary>
                {(preview.rejected || []).map((r, i) => <div key={i} style={{ fontSize: 12, color: '#b63e35', paddingLeft: 12 }}>Row {r.row}: {r.reason}</div>)}
              </details>
            )}
            <button className="btn btn-primary" onClick={handleConfirm} disabled={busy}>
              {busy ? <><Spinner /> Importing…</> : <><Check size={15} /> Confirm import</>}
            </button>
          </div>
        )}
      </div>
      <div className="panel">
        <div className="panel-head">
          <div><h3>Import history</h3></div>
          <button className="icon-btn" onClick={loadHistory} aria-label="Refresh history"><RefreshCw size={15} /></button>
        </div>
        {histLoading ? <div className="loading-state"><div className="spinner" /><span>Loading…</span></div>
          : history.length === 0 ? <div className="empty-state">No confirmed imports yet.</div>
          : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead><tr style={{ borderBottom: '1px solid #ddd' }}>
                  {['ID', 'Filename', 'Accepted', 'Rejected', 'Confirmed at'].map(h => <th key={h} scope="col" style={{ textAlign: 'left', padding: '6px 10px', fontWeight: 600 }}>{h}</th>)}
                </tr></thead>
                <tbody>
                  {history.map(h => (
                    <tr key={h.id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '6px 10px' }}>#{h.id}</td>
                      <td style={{ padding: '6px 10px' }}>{h.filename}</td>
                      <td style={{ padding: '6px 10px', color: '#3a7d44', fontWeight: 600 }}>{h.accepted_count}</td>
                      <td style={{ padding: '6px 10px', color: h.rejected_count > 0 ? '#b63e35' : '#888' }}>{h.rejected_count}</td>
                      <td style={{ padding: '6px 10px', color: '#666', fontSize: 12 }}>{new Date(h.confirmed_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin Review Console
// ---------------------------------------------------------------------------
export function AdminReviewConsole() {
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [reviewStatus, setReviewStatus] = useState('verified');
  const [reviewNote, setReviewNote] = useState('');
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [promoteDim, setPromoteDim] = useState('roads');
  const [promoteIndicator, setPromoteIndicator] = useState('');
  const [promoteValue, setPromoteValue] = useState(50);
  const [promoteReason, setPromoteReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [opError, setOpError] = useState('');
  const [opSuccess, setOpSuccess] = useState('');

  const DIMS = ['digital', 'electricity', 'roads', 'public_digital', 'essential_services'];

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await authApi('/api/v1/admin/submissions');
      setSubmissions(r.items || []);
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const submitReview = async () => {
    if (!selected) return;
    setBusy(true); setOpError(''); setOpSuccess('');
    try {
      await authApi(`/api/v1/admin/submissions/${selected.id}/review`, {
        method: 'POST',
        body: JSON.stringify({ review_status: reviewStatus, review_note: reviewNote }),
      });
      setOpSuccess('Review recorded.');
      setSelected(s => ({ ...s, review_status: reviewStatus }));
      load();
    } catch (e) { setOpError(e.message); } finally { setBusy(false); }
  };

  const submitPromotion = async () => {
    if (!selected) return;
    setBusy(true); setOpError(''); setOpSuccess('');
    try {
      await authApi(`/api/v1/admin/submissions/${selected.id}/promote-indicator`, {
        method: 'POST',
        body: JSON.stringify({ dimension: promoteDim, indicator_name: promoteIndicator, promoted_value: promoteValue, reason: promoteReason }),
      });
      setOpSuccess('Indicator promoted successfully. It is now flagged as a trusted value.');
      setPromoteOpen(false);
      load();
    } catch (e) { setOpError(e.message); } finally { setBusy(false); }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 1fr' : '1fr', gap: 20 }}>
      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="eyebrow">ADMIN REVIEW</div>
            <h2>Submission queue</h2>
            <p>{submissions.length} submission(s) in queue</p>
          </div>
          <button className="icon-btn" onClick={load} aria-label="Refresh"><RefreshCw size={16} /></button>
        </div>
        <WFNotice>Only verified and admin-promoted submissions can affect village scores.</WFNotice>
        {loading ? <div className="loading-state"><div className="spinner" /><span>Loading…</span></div>
          : error ? <div className="inline-error">{error}</div>
          : submissions.length === 0 ? <div className="empty-state">No submissions in queue.</div>
          : (
            <div style={{ display: 'grid', gap: 8 }}>
              {submissions.map(s => (
                <button key={s.id} onClick={() => { setSelected(s); setOpError(''); setOpSuccess(''); setReviewNote(''); setPromoteOpen(false); }}
                  style={{ textAlign: 'left', padding: '12px 14px', border: `2px solid ${selected?.id === s.id ? '#244735' : '#e8e8e8'}`, borderRadius: 8, background: selected?.id === s.id ? '#f0faf3' : '#fff', cursor: 'pointer', width: '100%' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <strong>#{s.id}</strong>
                    <StatusBadge status={s.observed_status} />
                    <StatusBadge status={s.review_status || 'pending_review'} />
                    <span className="muted" style={{ fontSize: 11, marginLeft: 'auto' }}>{new Date(s.submitted_at).toLocaleString()}</span>
                  </div>
                  <div style={{ fontSize: 13, color: '#555' }}>Village: {s.village_id} · User: {s.user_id}</div>
                  {s.notes && <div style={{ fontSize: 12, color: '#777', marginTop: 4, fontStyle: 'italic' }}>{s.notes.slice(0, 100)}{s.notes.length > 100 ? '…' : ''}</div>}
                </button>
              ))}
            </div>
          )
        }
      </div>

      {selected && (
        <div className="panel">
          <div className="panel-head">
            <div>
              <div className="eyebrow">REVIEW SUBMISSION #{selected.id}</div>
              <h3>{selected.observed_status?.replace(/_/g, ' ')}</h3>
              <p className="muted">Village: {selected.village_id} · Submitted by user {selected.user_id}</p>
            </div>
            <button className="icon-btn" onClick={() => setSelected(null)} aria-label="Close"><X size={18} /></button>
          </div>
          {selected.notes && <blockquote style={{ borderLeft: '3px solid #ccc', paddingLeft: 12, margin: '12px 0', color: '#555', fontSize: 14 }}>{selected.notes}</blockquote>}
          {selected.ai_analysis?.summary && (
            <div style={{ background: '#f5f7fb', borderRadius: 8, padding: 12, marginBottom: 16 }}>
              <strong style={{ fontSize: 12 }}>AI ANALYSIS</strong>
              <p style={{ margin: '6px 0 0', fontSize: 13 }}>{selected.ai_analysis.summary}</p>
              {selected.ai_analysis.relation_to_claim && <p style={{ margin: '4px 0 0', fontSize: 12, color: '#555' }}>Relation to claim: {selected.ai_analysis.relation_to_claim}</p>}
            </div>
          )}
          <label className="field-label">Review decision
            <select className="field-control" value={reviewStatus} onChange={e => setReviewStatus(e.target.value)}>
              <option value="verified">Verified — accept evidence</option>
              <option value="rejected">Rejected — evidence insufficient/inaccurate</option>
              <option value="flagged">Flagged — needs further investigation</option>
              <option value="needs_more_info">Needs more info from resident</option>
            </select>
          </label>
          <label className="field-label">Review note
            <textarea className="field-control text-control" value={reviewNote} onChange={e => setReviewNote(e.target.value)} rows={2} placeholder="Explain your decision…" maxLength={1000} />
          </label>
          <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
            <button className="btn btn-primary" onClick={submitReview} disabled={busy}>
              {busy ? <><Spinner /> Saving…</> : <><Check size={14} /> Record review</>}
            </button>
            <button className="btn btn-secondary" onClick={() => setPromoteOpen(p => !p)}>
              <Zap size={14} /> {promoteOpen ? 'Cancel promote' : 'Promote to indicator'}
            </button>
          </div>
          {opError && <InlineError msg={opError} />}
          {opSuccess && <div style={{ color: '#3a7d44', marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}><CheckCircle size={15} />{opSuccess}</div>}

          {promoteOpen && (
            <div style={{ marginTop: 16, border: '1px solid #f0d080', borderRadius: 8, padding: 16, background: '#fffdf0' }}>
              <h4 style={{ margin: '0 0 12px' }}>Promote to trusted indicator</h4>
              <WFNotice kind="warn">Promoting an indicator can update village reliability scores. Only promote evidence you have personally verified.</WFNotice>
              <label className="field-label">Dimension
                <select className="field-control" value={promoteDim} onChange={e => setPromoteDim(e.target.value)}>
                  {DIMS.map(d => <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>)}
                </select>
              </label>
              <label className="field-label">Indicator name
                <input className="field-control" value={promoteIndicator} onChange={e => setPromoteIndicator(e.target.value)} placeholder="e.g. Field-Verified Road Accessibility" />
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '8px 0' }}>
                <label className="field-label" style={{ flex: 1, marginBottom: 0 }}>Promoted value (0–100)
                  <input type="range" min={0} max={100} value={promoteValue} onChange={e => setPromoteValue(Number(e.target.value))} className="range" />
                </label>
                <strong style={{ minWidth: 40 }}>{promoteValue}/100</strong>
              </div>
              <label className="field-label">Reason / evidence basis
                <textarea className="field-control text-control" value={promoteReason} onChange={e => setPromoteReason(e.target.value)} rows={2} maxLength={1000} />
              </label>
              <button className="btn btn-primary" onClick={submitPromotion} disabled={busy || !promoteIndicator.trim()}>
                {busy ? <><Spinner /> Promoting…</> : <><Zap size={14} /> Confirm promotion</>}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Verification Summary (Admin)
// ---------------------------------------------------------------------------
export function VerificationSummaryPage() {
  const [villages, setVillages] = useState([]);
  const [selectedVillage, setSelectedVillage] = useState('');
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    authApi('/api/v1/villages?limit=200').then(r => setVillages(r.items || [])).catch(() => {});
  }, []);

  const load = async () => {
    if (!selectedVillage) return;
    setLoading(true); setSummary(null); setError('');
    try {
      const r = await authApi(`/api/v1/admin/villages/${selectedVillage}/verification-summary`);
      setSummary(r.summary);
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <div className="eyebrow">ADMIN</div>
          <h2>Verification Summary</h2>
          <p>View coverage, agreement rate and discrepancy count for a village.</p>
        </div>
        <ClipboardList size={20} />
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 16 }}>
        <label className="field-label" style={{ flex: 1, minWidth: 200, marginBottom: 0 }}>Select village
          <select className="field-control" value={selectedVillage} onChange={e => setSelectedVillage(e.target.value)}>
            <option value="">— select village —</option>
            {villages.map(v => <option key={v.id} value={v.id}>{v.name} ({v.district})</option>)}
          </select>
        </label>
        <button className="btn btn-primary" onClick={load} disabled={!selectedVillage || loading}>
          {loading ? <><Spinner /> Loading…</> : <><Search size={14} /> Load summary</>}
        </button>
      </div>
      <InlineError msg={error} />
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
          {[
            ['Total submissions', summary.total_submissions],
            ['Verified', summary.verified_submissions_count],
            ['Response coverage', `${(summary.response_coverage_percent || 0).toFixed(1)}%`],
            ['Discrepancy rate', `${(summary.discrepancy_rate_percent || 0).toFixed(1)}%`],
            ['Agreement rate', `${(summary.agreement_rate_percent || 0).toFixed(1)}%`],
            ['Promoted indicators', summary.promoted_indicators_count],
          ].map(([label, value]) => (
            <div key={label} style={{ border: '1px solid #e8e8e8', borderRadius: 8, padding: '12px 16px' }}>
              <div className="muted" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>{value ?? '—'}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

