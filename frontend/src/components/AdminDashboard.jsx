import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './AdminDashboard.css';

const API = import.meta.env.VITE_API_URL || (window.location.hostname === 'localhost' ? 'http://localhost:8000' : '');

export default function AdminDashboard() {
  const [activeTab, setActiveTab] = useState('schemes');
  const [stagingSchemes, setStagingSchemes] = useState([]);
  const [pendingSchemes, setPendingSchemes] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const [stagingRes, pendingRes, statsRes] = await Promise.all([
        axios.get(`${API}/admin/staging`),
        axios.get(`${API}/admin/pending`),
        axios.get(`${API}/admin/stats`)
      ]);
      setStagingSchemes(stagingRes.data.schemes || []);
      setPendingSchemes(pendingRes.data.schemes || []);
      setStats(statsRes.data);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleApproveStaging = async (schemeId) => {
    try {
      await axios.post(`${API}/admin/approve/${schemeId}`);
      loadDashboardData();
    } catch (err) {
      console.error('Failed to approve scheme:', err);
    }
  };

  const handleRejectStaging = async (schemeId) => {
    try {
      await axios.post(`${API}/admin/reject-staging/${schemeId}`);
      loadDashboardData();
    } catch (err) {
      console.error('Failed to reject scheme:', err);
    }
  };

  const handlePublishPending = async (schemeId) => {
    try {
      await axios.post(`${API}/admin/publish/${schemeId}`);
      loadDashboardData();
    } catch (err) {
      console.error('Failed to publish scheme:', err);
    }
  };

  const handleRejectPending = async (schemeId) => {
    try {
      await axios.post(`${API}/admin/reject-pending/${schemeId}`);
      loadDashboardData();
    } catch (err) {
      console.error('Failed to reject scheme:', err);
    }
  };

  if (loading) {
    return <div className="admin-loading">Loading dashboard...</div>;
  }

  return (
    <div className="admin-dashboard">
      <header className="admin-header">
        <h1>Admin Dashboard</h1>
        <button onClick={loadDashboardData} className="btn-refresh">Refresh</button>
      </header>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-value">{stats.staging_count || 0}</div>
            <div className="stat-label">Staging Schemes</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.pending_count || 0}</div>
            <div className="stat-label">Pending Approval</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.live_count || 0}</div>
            <div className="stat-label">Live Schemes</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.total_approved || 0}</div>
            <div className="stat-label">Total Approved</div>
          </div>
        </div>
      )}

      <div className="admin-tabs">
        <button 
          className={`tab-btn ${activeTab === 'staging' ? 'active' : ''}`}
          onClick={() => setActiveTab('staging')}
        >
          Staging ({stagingSchemes.length})
        </button>
        <button 
          className={`tab-btn ${activeTab === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          Pending Approval ({pendingSchemes.length})
        </button>
      </div>

      <div className="admin-content">
        {activeTab === 'staging' && (
          <SchemeList 
            schemes={stagingSchemes}
            onApprove={handleApproveStaging}
            onReject={handleRejectStaging}
            type="staging"
          />
        )}
        {activeTab === 'pending' && (
          <SchemeList 
            schemes={pendingSchemes}
            onApprove={handlePublishPending}
            onReject={handleRejectPending}
            type="pending"
          />
        )}
      </div>
    </div>
  );
}

function SchemeList({ schemes, onApprove, onReject, type }) {
  if (schemes.length === 0) {
    return <div className="empty-state">No schemes in {type}</div>;
  }

  return (
    <div className="scheme-list">
      {schemes.map((scheme) => (
        <div key={scheme._id} className="scheme-item">
          <div className="scheme-info">
            <h3>{scheme.name}</h3>
            <p>{scheme.description}</p>
            <div className="scheme-meta">
              <span>Ministry: {scheme.ministry}</span>
              {scheme.state && <span>State: {scheme.state}</span>}
            </div>
          </div>
          <div className="scheme-actions">
            <button 
              onClick={() => onApprove(scheme._id)}
              className="btn-approve"
            >
              {type === 'staging' ? 'Send to Pending' : 'Publish'}
            </button>
            <button 
              onClick={() => onReject(scheme._id)}
              className="btn-reject"
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
