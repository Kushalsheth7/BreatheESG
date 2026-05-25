import React, { useState, useEffect } from 'react';
import { 
  Upload, CheckCircle, AlertTriangle, AlertOctagon, Edit3, 
  RefreshCw, FileText, Database, Shield, X, HelpCircle, 
  MapPin, Plane, Hotel, Navigation, Search, Layers, CheckSquare
} from 'lucide-react';
import { 
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, 
  Tooltip, Legend, PieChart, Pie, Cell 
} from 'recharts';

const BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000/api'
  : 'https://breatheesg-tz6e.onrender.com/api';

export default function App() {
  // Tenant states
  const [tenantId, setTenantId] = useState(1);
  const [tenantName, setTenantName] = useState('Global Enterprises Ltd');
  const [analystName, setAnalystName] = useState('Lead ESG Auditor');
  
  // App data states
  const [activities, setActivities] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Selection and UI states
  const [selectedActivity, setSelectedActivity] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [activeSource, setActiveSource] = useState('SAP');
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null);
  
  // Filtering states
  const [scopeFilter, setScopeFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Drawer edit states
  const [editQty, setEditQty] = useState('');
  const [editReason, setEditReason] = useState('');
  const [editError, setEditError] = useState('');
  const [editSuccess, setEditSuccess] = useState('');

  // Fetch initial system states
  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch Metrics
      const metricsRes = await fetch(`${BASE_URL}/metrics/?tenant=${tenantId}`);
      if (metricsRes.ok) {
        const metricsData = await metricsRes.json();
        setMetrics(metricsData);
      }
      
      // Fetch Activities
      let activitiesUrl = `${BASE_URL}/activities/?tenant=${tenantId}`;
      if (scopeFilter !== 'All') activitiesUrl += `&scope=${scopeFilter}`;
      if (statusFilter !== 'All') activitiesUrl += `&status=${statusFilter}`;
      if (searchQuery.trim() !== '') activitiesUrl += `&search=${encodeURIComponent(searchQuery)}`;
      
      const activitiesRes = await fetch(activitiesUrl);
      if (activitiesRes.ok) {
        const activitiesData = await activitiesRes.json();
        setActivities(activitiesData);
      }
      
      // Fetch Jobs
      const jobsRes = await fetch(`${BASE_URL}/jobs/?tenant=${tenantId}`);
      if (jobsRes.ok) {
        const jobsData = await jobsRes.json();
        setJobs(jobsData.results || jobsData);
      }
    } catch (err) {
      console.error("Error communicating with backend API:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [tenantId, scopeFilter, statusFilter, searchQuery]);

  // Seed DB handler
  const handleSeedDatabase = async () => {
    try {
      const res = await fetch(`${BASE_URL}/seed-db/`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setTenantId(data.tenant_id);
        setTenantName(data.tenant_name);
        fetchData();
      }
    } catch (err) {
      console.error("Error seeding master directory:", err);
    }
  };

  // Upload handler
  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    setUploading(true);
    setUploadStatus({ type: 'info', message: 'Ingesting and normalizing raw source records...' });

    const formData = new FormData();
    formData.append('tenant', tenantId);
    formData.append('source_type', activeSource);
    formData.append('file', selectedFile);

    try {
      const res = await fetch(`${BASE_URL}/upload-source/`, {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const result = await res.json();
        setUploadStatus({
          type: result.status === 'SUCCESS' ? 'success' : 'warning',
          message: `Ingestion Completed! Job Status: ${result.status}. Processed ${result.activities_count} rows from "${selectedFile.name}".`
        });
        setSelectedFile(null);
        fetchData();
      } else {
        const errorData = await res.json();
        setUploadStatus({ type: 'error', message: errorData.error || 'Ingestion failure.' });
      }
    } catch (err) {
      setUploadStatus({ type: 'error', message: 'Failed to connect to the backend Django API.' });
    } finally {
      setUploading(false);
    }
  };

  // Drawer select handler
  const selectActivityRow = (activity) => {
    setSelectedActivity(activity);
    setEditQty(activity.quantity);
    setEditReason('');
    setEditError('');
    setEditSuccess('');
  };

  // Row approval action
  const handleApproveRow = async (id) => {
    try {
      const res = await fetch(`${BASE_URL}/activities/${id}/approve/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analyst_name: analystName })
      });
      if (res.ok) {
        const updated = await res.json();
        setSelectedActivity(updated);
        setEditSuccess('Row successfully locked and signed-off for audit.');
        fetchData();
      } else {
        const err = await res.json();
        setEditError(err.error || 'Sign-off failed.');
      }
    } catch (e) {
      setEditError('Connection to server lost.');
    }
  };

  // Bulk approval action
  const handleBulkApprove = async () => {
    if (!window.confirm("Are you sure you want to bulk approve all pending/flagged records? This will lock all of them for compliance.")) return;
    try {
      const res = await fetch(`${BASE_URL}/activities/bulk-approve/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant: tenantId, analyst_name: analystName })
      });
      if (res.ok) {
        alert("Bulk sign-off completed!");
        fetchData();
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Row adjustment action
  const handleAdjustRow = async (e) => {
    e.preventDefault();
    if (!editReason || editReason.trim().length < 5) {
      setEditError("A valid justification explanation (at least 5 characters) is required.");
      return;
    }
    
    setEditError('');
    setEditSuccess('');

    try {
      const res = await fetch(`${BASE_URL}/activities/${selectedActivity.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quantity: editQty,
          analyst_name: analystName,
          change_reason: editReason
        })
      });

      if (res.ok) {
        const updated = await res.json();
        setSelectedActivity(updated);
        setEditSuccess("Quantity updated and audit logged successfully.");
        setEditReason('');
        fetchData();
      } else {
        const err = await res.json();
        setEditError(err.error || 'Adjustment failed.');
      }
    } catch (e) {
      setEditError("Failed to update record on backend.");
    }
  };

  // Pie chart colors
  const COLORS = ['#10b981', '#3b82f6', '#8b5cf6'];
  const pieData = metrics ? [
    { name: 'Scope 1', value: metrics.metrics.scope_1_kg },
    { name: 'Scope 2', value: metrics.metrics.scope_2_kg },
    { name: 'Scope 3', value: metrics.metrics.scope_3_kg },
  ].filter(d => d.value > 0) : [];

  return (
    <div className="dashboard-layout">
      {/* App Header */}
      <header className="app-header">
        <div className="app-title-group">
          <div className="app-logo">
            <Shield size={32} />
          </div>
          <div>
            <h1 className="app-title">Breathe ESG</h1>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Analyst Normalization & Audit Workspace</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <span className="tenant-badge">{tenantName}</span>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-dark)' }}>Multi-Tenant Client ID: #{tenantId}</span>
          </div>
          <div className="edit-form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Auditor Name:</span>
            <input 
              type="text" 
              className="edit-form-input" 
              style={{ padding: '4px 8px', width: '130px', fontSize: '0.8rem' }}
              value={analystName} 
              onChange={e => setAnalystName(e.target.value)} 
            />
          </div>
          <button className="btn" style={{ padding: '8px' }} onClick={fetchData}>
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      {/* Main metrics overview */}
      {metrics && (
        <section className="metrics-grid">
          <div className="glass-card metric-card">
            <span className="metric-label">Audited Emissions</span>
            <div className="metric-value">
              {(metrics.metrics.total_co2e_kg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}
              <span className="metric-unit"> t CO2e</span>
            </div>
            <span className="metric-subtext">Total Scope 1/2/3 carbon footprint</span>
          </div>
          <div className="glass-card metric-card scope1">
            <span className="metric-label">Scope 1 (Direct)</span>
            <div className="metric-value">
              {(metrics.metrics.scope_1_kg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}
              <span className="metric-unit"> t</span>
            </div>
            <span className="metric-subtext">Stationary & Mobile Fuel Combustion</span>
          </div>
          <div className="glass-card metric-card scope2">
            <span className="metric-label">Scope 2 (Indirect)</span>
            <div className="metric-value">
              {(metrics.metrics.scope_2_kg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}
              <span className="metric-unit"> t</span>
            </div>
            <span className="metric-subtext">Purchased Facility Electricity</span>
          </div>
          <div className="glass-card metric-card scope3">
            <span className="metric-label">Scope 3 (Value Chain)</span>
            <div className="metric-value">
              {(metrics.metrics.scope_3_kg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}
              <span className="metric-unit"> t</span>
            </div>
            <span className="metric-subtext">Travel, Procurement & Logistics</span>
          </div>
          <div className="glass-card metric-card flagged">
            <span className="metric-label">Flagged Issues</span>
            <div className="metric-value" style={{ color: '#fb7185' }}>
              {metrics.metrics.flagged_rows + metrics.metrics.error_rows}
              <span className="metric-unit"> rows</span>
            </div>
            <span className="metric-subtext">Suspicious values or parser errors</span>
          </div>
          <div className="glass-card metric-card">
            <span className="metric-label">Auditor Sign-off</span>
            <div className="metric-value">
              {metrics.metrics.approval_rate}%
            </div>
            <span className="metric-subtext">{metrics.metrics.approved_rows} approved / {metrics.metrics.total_rows} total rows locked</span>
          </div>
        </section>
      )}

      {/* Database Loading State */}
      {loading && (
        <section className="glass-card" style={{ textAlign: 'center', padding: '60px 40px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
          <RefreshCw size={36} style={{ color: 'var(--primary)', filter: 'drop-shadow(0 0 10px rgba(16,185,129,0.3))' }} />
          <h2>Analyzing Carbon Database...</h2>
          <p style={{ color: 'var(--text-muted)' }}>Retrieving normalized scopes, grid coefficients, and compliance logs.</p>
        </section>
      )}

      {/* Database Bootstrap State */}
      {!loading && activities.length === 0 && (
        <section className="glass-card" style={{ textAlign: 'center', padding: '40px' }}>
          <Database size={48} color="var(--primary)" style={{ marginBottom: '16px', filter: 'drop-shadow(0 0 10px rgba(16,185,129,0.3))' }} />
          <h2 style={{ marginBottom: '10px' }}>ESG Database Uninitialized</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: '24px', maxWidth: '600px', margin: '0 auto 24px' }}>
            Breathe ESG relies on tenant Plants lookups, IATA Airport coordinates, and activity factors directories to accurately parse and compute carbon emissions. Bootstrap the prototype database using our pre-seeded directories right now.
          </p>
          <button className="btn btn-primary" onClick={handleSeedDatabase}>
            <Layers size={18} /> Seed Master Directory & Load Demo Data
          </button>
        </section>
      )}

      {/* Analytics Visualization and Uploader Section */}
      {!loading && activities.length > 0 && (
        <section className="analytics-section">
          {/* Uploader Box */}
          <div className="glass-card uploader-box">
            <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Raw Data Ingest Gateway</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Upload raw exports from client ERPs, Utility billing portals, or Travel logs.
            </p>
            
            <div className="source-selector">
              <button 
                type="button" 
                className={`source-btn ${activeSource === 'SAP' ? 'active' : ''}`}
                onClick={() => setActiveSource('SAP')}
              >
                SAP ERP
              </button>
              <button 
                type="button" 
                className={`source-btn ${activeSource === 'UTILITY' ? 'active' : ''}`}
                onClick={() => setActiveSource('UTILITY')}
              >
                Utility Portal
              </button>
              <button 
                type="button" 
                className={`source-btn ${activeSource === 'TRAVEL' ? 'active' : ''}`}
                onClick={() => setActiveSource('TRAVEL')}
              >
                Concur Travel
              </button>
            </div>

            <form onSubmit={handleUpload}>
              <div 
                className="upload-dropzone"
                onClick={() => document.getElementById('file-upload').click()}
              >
                <Upload size={24} className="upload-icon" />
                <div>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {selectedFile ? selectedFile.name : 'Select file to ingest'}
                  </span>
                  <p style={{ fontSize: '0.7rem', color: 'var(--text-dark)', marginTop: '4px' }}>
                    Supports raw tabular CSV exports
                  </p>
                </div>
              </div>
              <input 
                id="file-upload" 
                type="file" 
                className="file-input-hidden" 
                accept=".csv"
                onChange={handleFileChange}
              />
              
              <button 
                type="submit" 
                className="btn btn-primary" 
                style={{ width: '100%', marginTop: '16px', justifyContent: 'center' }}
                disabled={!selectedFile || uploading}
              >
                {uploading ? 'Processing Data...' : `Ingest raw ${activeSource} Export`}
              </button>
            </form>

            {uploadStatus && (
              <div 
                style={{ 
                  padding: '10px', 
                  borderRadius: '8px', 
                  fontSize: '0.75rem',
                  marginTop: '10px',
                  background: uploadStatus.type === 'error' ? 'var(--status-error-bg)' : 
                              uploadStatus.type === 'success' ? 'var(--status-approved-bg)' : 'var(--status-pending-bg)',
                  border: `1px solid ${uploadStatus.type === 'error' ? 'var(--status-error-border)' : 
                                       uploadStatus.type === 'success' ? 'var(--status-approved-border)' : 'var(--status-pending-border)'}`,
                  color: uploadStatus.type === 'error' ? 'var(--status-error-text)' : 
                         uploadStatus.type === 'success' ? 'var(--status-approved-text)' : 'var(--status-pending-text)'
                }}
              >
                {uploadStatus.message}
              </div>
            )}

            <div style={{ marginTop: '16px' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>Ingestion Jobs History</span>
              <div className="history-list">
                {jobs.map(j => (
                  <div className="history-item" key={j.id}>
                    <div>
                      <div style={{ fontWeight: 600 }}>{j.file_name}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-dark)', marginTop: '2px' }}>
                        Type: {j.source_type} | Rows: {j.row_count} | Err: {j.error_count}
                      </div>
                    </div>
                    <span className={`history-status ${j.status}`}>{j.status}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Charts Panel */}
          <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Compliance Carbon Analytics</h3>
            <div className="chart-panel-container">
              {/* Monthly line/area chart */}
              <div style={{ height: '240px' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px', display: 'block' }}>Monthly Carbon Profile (Approved tCO2e)</span>
                {metrics && metrics.monthly_emissions.length > 0 ? (
                  <ResponsiveContainer width="100%" height="90%">
                    <AreaChart data={metrics.monthly_emissions.map(m => ({
                      ...m,
                      'Scope 1': m['Scope 1'] / 1000,
                      'Scope 2': m['Scope 2'] / 1000,
                      'Scope 3': m['Scope 3'] / 1000,
                    }))}>
                      <defs>
                        <linearGradient id="colorScope1" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#34d399" stopOpacity={0.2}/>
                          <stop offset="95%" stopColor="#34d399" stopOpacity={0}/>
                        </linearGradient>
                        <linearGradient id="colorScope2" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.2}/>
                          <stop offset="95%" stopColor="#60a5fa" stopOpacity={0}/>
                        </linearGradient>
                        <linearGradient id="colorScope3" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.2}/>
                          <stop offset="95%" stopColor="#a78bfa" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="month" stroke="var(--text-dark)" fontSize={10} />
                      <YAxis stroke="var(--text-dark)" fontSize={10} />
                      <Tooltip contentStyle={{ background: '#0e1726', border: '1px solid var(--border-light)' }} />
                      <Area type="monotone" dataKey="Scope 1" stackId="1" stroke="#34d399" fillOpacity={1} fill="url(#colorScope1)" />
                      <Area type="monotone" dataKey="Scope 2" stackId="1" stroke="#60a5fa" fillOpacity={1} fill="url(#colorScope2)" />
                      <Area type="monotone" dataKey="Scope 3" stackId="1" stroke="#a78bfa" fillOpacity={1} fill="url(#colorScope3)" />
                      <Legend verticalAlign="top" height={36} iconSize={8} wrapperStyle={{ fontSize: '10px' }} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ display: 'flex', height: '90%', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dark)', fontSize: '0.85rem' }}>
                    Approved data required to render monthly timeline.
                  </div>
                )}
              </div>

              {/* Pie breakdown chart */}
              <div style={{ height: '240px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px', display: 'block', alignSelf: 'flex-start' }}>Scope Allocation</span>
                {pieData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="80%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={70}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {pieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value) => `${(value / 1000).toFixed(1)} t CO2e`} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ display: 'flex', height: '80%', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dark)', fontSize: '0.85rem' }}>
                    No carbon data.
                  </div>
                )}
                {pieData.length > 0 && (
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center', fontSize: '9px' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ width: '6px', height: '6px', background: '#10b981', borderRadius: '50%' }}></span> Scope 1
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ width: '6px', height: '6px', background: '#3b82f6', borderRadius: '50%' }}></span> Scope 2
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ width: '6px', height: '6px', background: '#8b5cf6', borderRadius: '50%' }}></span> Scope 3
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Grid Activity Workspace Table */}
      {!loading && activities.length > 0 && (
        <section className="glass-card grid-section">
          <div className="grid-header-actions">
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Normalized Activity Records</h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                Review validation issues, execute adjustments, and sign-off records before auditing.
              </p>
            </div>
            
            <div className="action-buttons-group">
              <button className="btn btn-primary" onClick={handleBulkApprove}>
                <CheckSquare size={16} /> Bulk Sign-off & Lock
              </button>
            </div>
          </div>

          {/* Filtering and Search controls */}
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'center', justifyBetween: 'space-between', width: '100%' }}>
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Scope:</span>
              <div className="filter-tabs">
                {['All', 'Scope 1', 'Scope 2', 'Scope 3'].map(scope => (
                  <button 
                    key={scope} 
                    className={`filter-tab ${scopeFilter === scope ? 'active' : ''}`}
                    onClick={() => setScopeFilter(scope)}
                  >
                    {scope}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Status:</span>
              <div className="filter-tabs">
                {['All', 'PENDING', 'APPROVED', 'FLAGGED', 'ERROR'].map(status => (
                  <button 
                    key={status} 
                    className={`filter-tab ${statusFilter === status ? 'active' : ''}`}
                    onClick={() => setStatusFilter(status)}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', background: 'var(--bg-tertiary)', border: '1px solid var(--border-light)', borderRadius: '8px', padding: '6px 12px', gap: '8px', flex: 1, minWidth: '200px' }}>
              <Search size={16} color="var(--text-muted)" />
              <input 
                type="text" 
                placeholder="Search category, plant code..."
                style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', outline: 'none', width: '100%', fontSize: '0.85rem' }}
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          {/* Data Table */}
          <div className="table-container">
            <table className="activity-table">
              <thead>
                <tr>
                  <th>Scope</th>
                  <th>Category</th>
                  <th>Quantity (Base)</th>
                  <th>Emissions (kg CO2e)</th>
                  <th>Start Date</th>
                  <th>End Date</th>
                  <th>Plant/Meter</th>
                  <th>Audit Status</th>
                  <th>Audit Trace Warnings</th>
                </tr>
              </thead>
              <tbody>
                {activities.map(act => (
                  <tr 
                    key={act.id} 
                    className={selectedActivity && selectedActivity.id === act.id ? 'selected' : ''}
                    onClick={() => selectActivityRow(act)}
                  >
                    <td>
                      <span className={`scope-badge ${act.scope.replace(' ', '-')}`}>
                        {act.scope}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{act.category}</td>
                    <td>{parseFloat(act.quantity).toLocaleString(undefined, { maximumFractionDigits: 2 })} <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{act.unit}</span></td>
                    <td style={{ fontWeight: 700 }}>{parseFloat(act.co2e_kg).toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                    <td>{act.start_date}</td>
                    <td>{act.end_date}</td>
                    <td><span style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{act.plant_code || '-'}</span></td>
                    <td>
                      <span className={`status-badge ${act.status}`}>
                        {act.status === 'PENDING' && <HelpCircle size={10} />}
                        {act.status === 'APPROVED' && <CheckCircle size={10} />}
                        {act.status === 'FLAGGED' && <AlertTriangle size={10} />}
                        {act.status === 'ERROR' && <AlertOctagon size={10} />}
                        {act.status.replace('PENDING', 'PENDING REVIEW').replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      {act.validation_issues.length > 0 ? (
                        <span className="validation-bubble" style={{ color: act.status === 'ERROR' ? '#ef4444' : '#f59e0b' }}>
                          <AlertTriangle size={12} /> {act.validation_issues[0]}
                          {act.validation_issues.length > 1 && ` (+${act.validation_issues.length-1})`}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-dark)', fontSize: '0.75rem' }}>Passes checks</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Analyst Activity Review slide drawer */}
      {selectedActivity && (
        <>
          <div className="drawer-overlay" onClick={() => setSelectedActivity(null)}></div>
          <div className="drawer-content">
            <div className="drawer-header">
              <div className="drawer-title-group">
                <span className="drawer-subtitle">AUDIT DOCUMENT ROW DIRECTORY</span>
                <span className="drawer-title">Activity ID #{selectedActivity.id}</span>
              </div>
              <button className="drawer-close" onClick={() => setSelectedActivity(null)}>
                <X size={24} />
              </button>
            </div>

            {/* Scope info */}
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <span className={`scope-badge ${selectedActivity.scope.replace(' ', '-')}`}>
                {selectedActivity.scope}
              </span>
              <span className={`status-badge ${selectedActivity.status}`}>
                {selectedActivity.status}
              </span>
              {selectedActivity.is_locked && (
                <span className="status-badge APPROVED" style={{ background: 'rgba(59, 130, 246, 0.1)', color: '#60a5fa', borderColor: 'rgba(59, 130, 246, 0.3)' }}>
                  <Shield size={10} /> compliance locked
                </span>
              )}
            </div>

            {/* Validation issues */}
            {selectedActivity.validation_issues.length > 0 && (
              <div className="issues-container">
                <div className="issues-header">
                  <AlertTriangle size={16} /> Audit Warnings Triggered:
                </div>
                {selectedActivity.validation_issues.map((iss, i) => (
                  <span className="issue-bullet" key={i}>• {iss}</span>
                ))}
              </div>
            )}

            {/* Ingestion Source-of-Truth tracking */}
            <div>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>Ingestion Trace Metadata</span>
              <div 
                style={{ 
                  marginTop: '6px', 
                  padding: '12px', 
                  background: 'rgba(255,255,255,0.01)', 
                  border: '1px solid var(--border-light)', 
                  borderRadius: '8px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  fontSize: '0.8rem'
                }}
              >
                <div style={{ display: 'flex', justifyBetween: 'space-between', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Source Ingestion Job:</span>
                  <span style={{ fontWeight: 600 }}>#{selectedActivity.ingestion_job || 'Manual'}</span>
                </div>
                <div style={{ display: 'flex', justifyBetween: 'space-between', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Raw Process Status:</span>
                  <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>SUCCESS</span>
                </div>
                {selectedActivity.plant_code && (
                  <div style={{ display: 'flex', justifyBetween: 'space-between', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}><MapPin size={12} style={{ verticalAlign: 'middle', marginRight: '4px' }} /> Plant/Meter Ref:</span>
                    <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{selectedActivity.plant_code}</span>
                  </div>
                )}
                {selectedActivity.origin_airport && (
                  <div style={{ display: 'flex', justifyBetween: 'space-between', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}><Plane size={12} style={{ verticalAlign: 'middle', marginRight: '4px' }} /> Airport Route:</span>
                    <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{selectedActivity.origin_airport} → {selectedActivity.destination_airport} ({selectedActivity.cabin_class})</span>
                  </div>
                )}
                {selectedActivity.hotel_nights && (
                  <div style={{ display: 'flex', justifyBetween: 'space-between', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}><Hotel size={12} style={{ verticalAlign: 'middle', marginRight: '4px' }} /> Room Stay:</span>
                    <span style={{ fontWeight: 600 }}>{selectedActivity.hotel_nights} room-nights</span>
                  </div>
                )}
                <div style={{ display: 'flex', justifyBetween: 'space-between', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Auditor Sign-off:</span>
                  <span style={{ fontWeight: 600, color: 'var(--primary)' }}>{selectedActivity.approved_by || 'Unsigned'}</span>
                </div>
              </div>
            </div>

            {/* Original Row Inspection */}
            <div>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Original Export Columns Inspector</span>
              <div className="raw-json-inspector">
                {JSON.stringify(selectedActivity.original_data, null, 2)}
              </div>
            </div>

            {/* Manual Adjustment Form */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>Audited Adjustment Gateway</span>
                <span style={{ fontSize: '0.7rem', color: '#6b7280' }}><Shield size={10} style={{ verticalAlign: 'middle' }} /> Full Audit Trail Active</span>
              </div>
              
              <form onSubmit={handleAdjustRow} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div className="edit-form-group">
                  <label className="edit-form-label">Quantity Value</label>
                  <input 
                    type="number" 
                    step="0.0001"
                    className="edit-form-input" 
                    value={editQty}
                    onChange={e => setEditQty(e.target.value)}
                    disabled={selectedActivity.is_locked}
                  />
                </div>
                <div className="edit-form-group">
                  <label className="edit-form-label">Adjustment Compliance Explanation</label>
                  <textarea 
                    className="edit-form-input" 
                    style={{ minHeight: '60px', resize: 'vertical' }}
                    placeholder="Enter reason for modifying parsed activity..."
                    value={editReason}
                    onChange={e => setEditReason(e.target.value)}
                    disabled={selectedActivity.is_locked}
                  />
                </div>
                
                {editError && (
                  <div style={{ color: 'var(--status-error-text)', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertOctagon size={12} /> {editError}
                  </div>
                )}
                {editSuccess && (
                  <div style={{ color: 'var(--status-approved-text)', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <CheckCircle size={12} /> {editSuccess}
                  </div>
                )}

                <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
                  <button 
                    type="submit" 
                    className="btn" 
                    style={{ flex: 1, justifyContent: 'center' }}
                    disabled={selectedActivity.is_locked}
                  >
                    <Edit3 size={14} /> Commit Adjustment
                  </button>
                  <button 
                    type="button" 
                    className="btn btn-primary" 
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => handleApproveRow(selectedActivity.id)}
                    disabled={selectedActivity.is_locked}
                  >
                    <CheckCircle size={14} /> Lock & Sign-off
                  </button>
                </div>
              </form>
            </div>

            {/* Audit Trail Logs */}
            {selectedActivity.audit_logs && selectedActivity.audit_logs.length > 0 && (
              <div>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>Historical Audit Log</span>
                <div className="audit-list">
                  {selectedActivity.audit_logs.map(log => (
                    <div className="audit-log-item" key={log.id}>
                      <div className="audit-log-header">
                        <span>{log.changed_by}</span>
                        <span>{new Date(log.changed_at).toLocaleString()}</span>
                      </div>
                      <div className="audit-change-line">
                        Field <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{log.field_name}</span> adjusted from "{log.old_value}" to "{log.new_value}".
                      </div>
                      <div className="audit-reason">
                        Reason: {log.reason}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
