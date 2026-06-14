import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { 
  Terminal, Shield, RefreshCw, Cpu, Activity, Key, BarChart3, Clock, 
  AlertTriangle, Users, Plus, Clipboard, AlertCircle, Trash2, Settings, 
  ShieldAlert, Award, FileText, Bell, Check, Edit3, X 
} from 'lucide-react';
import JobSubmitForm from './components/JobSubmitForm';
import JobTable from './components/JobTable';
import Login from './components/Login';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard', 'tenants', 'vault', 'proxy_keys', 'usage'
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedJobDetails, setSelectedJobDetails] = useState(null);
  const [apiKey, setApiKey] = useState('');
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  
  // Multi-tenancy states
  const [isAdmin, setIsAdmin] = useState(false);
  const [tenants, setTenants] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState(''); // Empty means "All Tenants"
  
  // Tenant metrics for the admin tab
  const [tenantMetrics, setTenantMetrics] = useState([]);
  
  // Form states for creating tenants and keys
  const [newTenantName, setNewTenantName] = useState('');
  const [newTenantSlug, setNewTenantSlug] = useState('');
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyTenantId, setNewKeyTenantId] = useState('');
  const [newKeyScopes, setNewKeyScopes] = useState(['task:sleep_task', 'priority:default']);
  const [generatedKey, setGeneratedKey] = useState(null);
  
  // Forms and lists for Vault Keys
  const [vaultKeys, setVaultKeys] = useState([]);
  const [newVaultTenantId, setNewVaultTenantId] = useState('');
  const [newVaultProvider, setNewVaultProvider] = useState('openai');
  const [newVaultKey, setNewVaultKey] = useState('');
  const [rotatingKeyId, setRotatingKeyId] = useState(null);
  const [rotatingKeyValue, setRotatingKeyValue] = useState('');

  // Forms and lists for Proxy Keys
  const [proxyKeys, setProxyKeys] = useState([]);
  const [newProxyName, setNewProxyName] = useState('');
  const [newProxyTenantId, setNewProxyTenantId] = useState('');
  const [newProxyProviders, setNewProxyProviders] = useState(['openai']);
  const [newProxyCap, setNewProxyCap] = useState(10.0);
  const [generatedProxyKey, setGeneratedProxyKey] = useState(null);
  const [editingFallbackKeyId, setEditingFallbackKeyId] = useState(null);
  const [fallbackMappingsStr, setFallbackMappingsStr] = useState('{}');

  // Usage & Telemetry States
  const [usageLogs, setUsageLogs] = useState([]);
  const [usageSummary, setUsageSummary] = useState({
    total_cost_usd: 0.0,
    total_requests: 0,
    cost_by_provider: {},
    cost_by_model: {},
    cost_by_project: {},
    daily_chart: []
  });
  const [alerts, setAlerts] = useState([]);

  const [formError, setFormError] = useState('');
  const [formSuccess, setFormSuccess] = useState('');

  const [metrics, setMetrics] = useState({ throughput: 0, avg_duration_seconds: 0.0, failure_rate: 0.0 });
  const [apiConnected, setApiConnected] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const logsEndRef = useRef(null);
  const logWsRef = useRef(null);
  const statusWsRef = useRef(null);

  // Helper for Axios config
  const getAuthConfig = () => {
    const config = {
      headers: { Authorization: `Bearer ${apiKey}` }
    };
    if (selectedTenantId) {
      config.headers['x-tenant-id'] = selectedTenantId;
    }
    return config;
  };

  // Check admin status and load tenants list
  const checkAdminAndLoadTenants = async () => {
    if (!apiKey) return;
    try {
      const res = await axios.get('/api/tenants/', getAuthConfig());
      setTenants(res.data);
      setIsAdmin(true);
    } catch (err) {
      setIsAdmin(false);
      setTenants([]);
      setSelectedTenantId('');
      setActiveTab('dashboard'); // Fallback
    }
  };

  // Fetch tenant list & metrics when active tab is 'tenants'
  const fetchTenantMetrics = async () => {
    if (!isAdmin) return;
    try {
      const res = await axios.get('/api/metrics/tenants', getAuthConfig());
      setTenantMetrics(res.data);
    } catch (err) {
      console.error("Failed to fetch tenant metrics:", err);
    }
  };

  // Fetch Vault Keys
  const fetchVaultKeys = async () => {
    if (!apiKey) return;
    try {
      let url = '/api/vault/';
      if (selectedTenantId) {
        url += `?tenant_id=${selectedTenantId}`;
      }
      const res = await axios.get(url, getAuthConfig());
      setVaultKeys(res.data);
    } catch (err) {
      console.error("Failed to fetch vault keys:", err);
    }
  };

  // Fetch Proxy Keys
  const fetchProxyKeys = async () => {
    if (!apiKey) return;
    try {
      let url = '/api/proxy-keys/';
      if (selectedTenantId) {
        url += `?tenant_id=${selectedTenantId}`;
      }
      const res = await axios.get(url, getAuthConfig());
      setProxyKeys(res.data);
    } catch (err) {
      console.error("Failed to fetch proxy keys:", err);
    }
  };

  // Fetch Usage Telemetry
  const fetchUsageData = async () => {
    if (!apiKey) return;
    try {
      let summaryUrl = '/api/usage/summary';
      let logsUrl = '/api/usage/?limit=50';
      if (selectedTenantId) {
        summaryUrl += `?tenant_id=${selectedTenantId}`;
        logsUrl += `&tenant_id=${selectedTenantId}`;
      }
      const [summaryRes, logsRes] = await Promise.all([
        axios.get(summaryUrl, getAuthConfig()),
        axios.get(logsUrl, getAuthConfig())
      ]);
      setUsageSummary(summaryRes.data);
      setUsageLogs(logsRes.data);
    } catch (err) {
      console.error("Failed to fetch usage data:", err);
    }
  };

  // Fetch Alerts
  const fetchAlerts = async () => {
    if (!apiKey) return;
    try {
      const res = await axios.get('/api/usage/alerts', getAuthConfig());
      setAlerts(res.data);
    } catch (err) {
      console.error("Failed to fetch alerts:", err);
    }
  };

  // Mark Alert Read
  const handleMarkAlertRead = async (alertId) => {
    try {
      await axios.post(`/api/usage/alerts/${alertId}/read`, {}, getAuthConfig());
      fetchAlerts();
    } catch (err) {
      console.error("Failed to mark alert as read:", err);
    }
  };

  // Fetch Metrics
  const fetchMetrics = async () => {
    if (!apiKey) return;
    try {
      let url = '/api/metrics/';
      if (selectedTenantId) {
        url += `?tenant_id=${selectedTenantId}`;
      }
      const res = await axios.get(url, getAuthConfig());
      setMetrics(res.data);
    } catch (err) {
      console.error("Failed to fetch metrics:", err);
    }
  };
  const fetchUserProfile = async (tokenVal = apiKey) => {
    if (!tokenVal) return;
    try {
      const res = await axios.get('/api/auth/me', {
        headers: { Authorization: `Bearer ${tokenVal}` }
      });
      setUser(res.data);
      setIsAdmin(res.data.is_admin);
      setTenants(res.data.tenants || []);
      setIsAuthenticated(true);
      
      // Auto-select first tenant if none is currently selected
      if (res.data.tenants && res.data.tenants.length > 0 && !selectedTenantId) {
        setSelectedTenantId(res.data.tenants[0].id);
      }
    } catch (err) {
      console.error("Failed to fetch user profile:", err);
      handleLogout();
    }
  };

  const handleLoginSuccess = (token) => {
    localStorage.setItem('auth_token', token);
    setApiKey(token);
    fetchUserProfile(token);
  };

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    setApiKey('');
    setUser(null);
    setIsAdmin(false);
    setTenants([]);
    setSelectedTenantId('');
    setIsAuthenticated(false);
  };

  // On mount: check for token in query params or local storage
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get('token');
    
    let activeToken = null;
    if (urlToken) {
      localStorage.setItem('auth_token', urlToken);
      activeToken = urlToken;
      setApiKey(urlToken);
      window.history.replaceState({}, document.title, window.location.pathname);
    } else {
      const storedToken = localStorage.getItem('auth_token');
      if (storedToken) {
        activeToken = storedToken;
        setApiKey(storedToken);
      }
    }
    
    if (activeToken) {
      fetchUserProfile(activeToken);
    } else {
      setIsAuthenticated(false);
    }
  }, []);

  // Initial and periodic fetches
  useEffect(() => {
    if (isAuthenticated) {
      fetchAlerts();
    } else if (apiKey && !user) {
      // Static key fallback
      checkAdminAndLoadTenants();
      fetchAlerts();
    }
  }, [apiKey, isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated || apiKey) {
      fetchJobs(true);
      fetchMetrics();
    }
  }, [apiKey, selectedTenantId, isAuthenticated]);

  // Periodic updates
  useEffect(() => {
    if (isAuthenticated || apiKey) {
      fetchMetrics();
      fetchAlerts();
      const interval = setInterval(() => {
        fetchMetrics();
        fetchAlerts();
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [apiKey, selectedTenantId, isAuthenticated]);

  useEffect(() => {
    if (activeTab === 'tenants') {
      fetchTenantMetrics();
    } else if (activeTab === 'vault') {
      fetchVaultKeys();
    } else if (activeTab === 'proxy_keys') {
      fetchProxyKeys();
    } else if (activeTab === 'usage') {
      fetchUsageData();
    }
  }, [activeTab, apiKey, selectedTenantId]);

  // WebSocket 1: Global Status updates (authenticated via WS token)
  useEffect(() => {
    let active = true;
    let ws = null;
    let reconnectTimeout = null;

    const connectStatusWs = async () => {
      if (!apiKey) return;
      try {
        setApiConnected(false);
        const tokenRes = await axios.post('/api/auth/ws-token', {}, getAuthConfig());
        if (!active) return;

        const token = tokenRes.data.token;
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        const wsUrl = `${wsProtocol}//${wsHost}/api/jobs/stream?token=${token}`;

        console.log("Connecting to global status WebSocket...");
        ws = new WebSocket(wsUrl);
        statusWsRef.current = ws;

        ws.onopen = () => {
          if (active) setApiConnected(true);
        };

        ws.onmessage = (event) => {
          if (!active) return;
          try {
            const update = JSON.parse(event.data);
            setJobs(prevJobs => prevJobs.map(job => 
              job.id === update.job_id 
                ? { ...job, status: update.status, progress: update.progress } 
                : job
            ));

            setSelectedJobDetails(prevDetails => {
              if (prevDetails && prevDetails.id === update.job_id) {
                return { ...prevDetails, status: update.status, progress: update.progress };
              }
              return prevDetails;
            });

            if (['DONE', 'FAILED', 'CANCELLED'].includes(update.status)) {
              fetchMetrics();
              if (activeTab === 'tenants') fetchTenantMetrics();
            }
          } catch (err) {
            console.error("Failed to parse status update:", err);
          }
        };

        ws.onclose = () => {
          if (!active) return;
          console.log("Global status WebSocket closed. Reconnecting in 5s...");
          setApiConnected(false);
          reconnectTimeout = setTimeout(connectStatusWs, 5000);
        };
      } catch (err) {
        if (!active) return;
        console.error("WebSocket auth token exchange failed:", err);
        setApiConnected(false);
        reconnectTimeout = setTimeout(connectStatusWs, 5000);
      }
    };

    connectStatusWs();

    return () => {
      active = false;
      if (ws) ws.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [apiKey]);

  // WebSocket 2: Job-Specific Log Streaming (authenticated via WS token)
  useEffect(() => {
    if (!selectedJobId || !apiKey) {
      setSelectedJobDetails(null);
      return;
    }

    let active = true;
    let ws = null;

    const connectLogsWs = async () => {
      try {
        const tokenRes = await axios.post('/api/auth/ws-token', {}, getAuthConfig());
        if (!active) return;

        const token = tokenRes.data.token;
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        const wsUrl = `${wsProtocol}//${wsHost}/api/jobs/${selectedJobId}/stream?token=${token}`;

        console.log(`Connecting to job logs WebSocket for: ${selectedJobId}`);
        const initialJobObj = jobs.find(j => j.id === selectedJobId);
        setSelectedJobDetails(initialJobObj ? { ...initialJobObj, logs: [] } : { id: selectedJobId, logs: [] });

        ws = new WebSocket(wsUrl);
        logWsRef.current = ws;

        ws.onmessage = (event) => {
          if (!active) return;
          try {
            const logLine = JSON.parse(event.data);
            setSelectedJobDetails(prevDetails => {
              if (!prevDetails || prevDetails.id !== logLine.job_id) return prevDetails;
              const exists = prevDetails.logs.some(l => l.id === logLine.id);
              if (exists) return prevDetails;
              return {
                ...prevDetails,
                logs: [...prevDetails.logs, logLine]
              };
            });
          } catch (err) {
            console.error("Failed to parse log line:", err);
          }
        };

        ws.onclose = () => {
          console.log(`Job logs WebSocket closed for: ${selectedJobId}`);
        };
      } catch (err) {
        console.error("Log WebSocket token exchange failed:", err);
      }
    };

    connectLogsWs();

    return () => {
      active = false;
      if (ws) ws.close();
    };
  }, [selectedJobId, apiKey]);

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [selectedJobDetails?.logs]);

  const fetchJobs = async (showLoading = false) => {
    if (!apiKey) return;
    if (showLoading) setIsRefreshing(true);
    try {
      let url = '/api/jobs/';
      if (selectedTenantId) {
        url += `?tenant_id=${selectedTenantId}`;
      }
      const response = await axios.get(url, getAuthConfig());
      setJobs(response.data);
      setApiConnected(true);
    } catch (err) {
      console.error(err);
      setApiConnected(false);
    } finally {
      if (showLoading) setIsRefreshing(false);
    }
  };

  const handleJobSubmitted = (newJob) => {
    setJobs(prevJobs => [newJob, ...prevJobs]);
    setSelectedJobId(newJob.id); // Auto-select to view log console
    fetchMetrics();
  };

  const handleCancelJob = async (jobId) => {
    try {
      const response = await axios.delete(`/api/jobs/${jobId}`, getAuthConfig());
      setJobs(prevJobs => prevJobs.map(j => j.id === jobId ? response.data : j));
      if (selectedJobId === jobId) {
        setSelectedJobDetails(prev => prev ? { ...prev, status: response.data.status, progress: 0 } : null);
      }
      fetchMetrics();
    } catch (err) {
      console.error("Failed to cancel job:", err);
    }
  };

  // Create Tenant handler
  const handleCreateTenant = async (e) => {
    e.preventDefault();
    setFormError('');
    setFormSuccess('');
    if (!newTenantName || !newTenantSlug) {
      setFormError('Tenant name and slug are required.');
      return;
    }
    try {
      const res = await axios.post('/api/tenants/', {
        name: newTenantName,
        slug: newTenantSlug
      }, getAuthConfig());
      
      setFormSuccess(`Tenant "${res.data.name}" registered successfully.`);
      setNewTenantName('');
      setNewTenantSlug('');
      checkAdminAndLoadTenants();
      fetchTenantMetrics();
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to register tenant.');
    }
  };

  // Generate Task Scope Key handler
  const handleGenerateKey = async (e) => {
    e.preventDefault();
    setFormError('');
    setFormSuccess('');
    setGeneratedKey(null);
    if (!newKeyTenantId || !newKeyName) {
      setFormError('Tenant and Key name are required.');
      return;
    }
    try {
      const res = await axios.post(`/api/tenants/${newKeyTenantId}/keys`, {
        name: newKeyName,
        scopes: newKeyScopes
      }, getAuthConfig());
      
      setGeneratedKey(res.data);
      setNewKeyName('');
      fetchTenantMetrics();
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to generate key.');
    }
  };

  // Create Provider Key in Vault
  const handleCreateVaultKey = async (e) => {
    e.preventDefault();
    setFormError('');
    setFormSuccess('');
    if (!newVaultTenantId || !newVaultProvider || !newVaultKey) {
      setFormError('Tenant, Provider, and API Key are required.');
      return;
    }
    try {
      await axios.post('/api/vault/', {
        tenant_id: newVaultTenantId,
        provider: newVaultProvider,
        key: newVaultKey
      }, getAuthConfig());
      
      setFormSuccess(`Provider key for ${newVaultProvider.toUpperCase()} stored successfully.`);
      setNewVaultKey('');
      fetchVaultKeys();
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to store provider key.');
    }
  };

  // Rotate Provider Key
  const handleRotateVaultKey = async (keyId) => {
    if (!rotatingKeyValue) {
      alert("Please enter the new key value first.");
      return;
    }
    try {
      await axios.put(`/api/vault/${keyId}`, {
        key: rotatingKeyValue
      }, getAuthConfig());
      setRotatingKeyId(null);
      setRotatingKeyValue('');
      alert("API key successfully rotated in the vault.");
      fetchVaultKeys();
    } catch (err) {
      alert("Failed to rotate key: " + (err.response?.data?.detail || err.message));
    }
  };

  // Delete Provider Key
  const handleDeleteVaultKey = async (keyId) => {
    if (!confirm("Are you sure you want to revoke this provider key?")) return;
    try {
      await axios.delete(`/api/vault/${keyId}`, getAuthConfig());
      fetchVaultKeys();
    } catch (err) {
      alert("Failed to delete key: " + (err.response?.data?.detail || err.message));
    }
  };

  // Create Proxy Key
  const handleCreateProxyKey = async (e) => {
    e.preventDefault();
    setFormError('');
    setFormSuccess('');
    setGeneratedProxyKey(null);
    if (!newProxyTenantId || !newProxyName) {
      setFormError('Tenant and key description name are required.');
      return;
    }
    try {
      const res = await axios.post('/api/proxy-keys/', {
        tenant_id: newProxyTenantId,
        name: newProxyName,
        allowed_providers: newProxyProviders,
        monthly_cap_usd: parseFloat(newProxyCap)
      }, getAuthConfig());

      setGeneratedProxyKey(res.data);
      setNewProxyName('');
      fetchProxyKeys();
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to generate project proxy key.');
    }
  };

  // Update Fallback mappings
  const handleUpdateFallback = async (keyId) => {
    try {
      const parsed = JSON.parse(fallbackMappingsStr);
      await axios.put(`/api/proxy-keys/${keyId}/fallback`, {
        fallback_mappings: parsed
      }, getAuthConfig());
      setEditingFallbackKeyId(null);
      alert("Fallback rules updated successfully.");
      fetchProxyKeys();
    } catch (err) {
      alert("Invalid JSON format or update failed: " + err.message);
    }
  };

  // Delete Proxy Key
  const handleDeleteProxyKey = async (keyId) => {
    if (!confirm("Are you sure you want to revoke this project proxy key? All applications using this key will immediately fail.")) return;
    try {
      await axios.delete(`/api/proxy-keys/${keyId}`, getAuthConfig());
      fetchProxyKeys();
    } catch (err) {
      alert("Failed to revoke key: " + (err.response?.data?.detail || err.message));
    }
  };

  const toggleScope = (scope) => {
    if (newKeyScopes.includes(scope)) {
      setNewKeyScopes(newKeyScopes.filter(s => s !== scope));
    } else {
      setNewKeyScopes([...newKeyScopes, scope]);
    }
  };

  const toggleProxyProvider = (prov) => {
    if (newProxyProviders.includes(prov)) {
      setNewProxyProviders(newProxyProviders.filter(p => p !== prov));
    } else {
      setNewProxyProviders([...newProxyProviders, prov]);
    }
  };

  const copyKeyToClipboard = (txt) => {
    navigator.clipboard.writeText(txt);
    alert('Key copied to clipboard!');
  };

  const formatLogTime = (dateString) => {
    try {
      const d = new Date(dateString);
      return (
        d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) +
        '.' +
        String(d.getMilliseconds()).padStart(3, '0')
      );
    } catch {
      return '';
    }
  };

  // Custom SVG Chart Calculation
  const unreadAlerts = alerts.filter(a => !a.is_read);
  const maxCost = Math.max(...usageSummary.daily_chart.map(d => d.cost), 0.01);
  const chartHeight = 120;
  const chartWidth = 600;
  
  const points = usageSummary.daily_chart.map((d, i) => {
    const x = (i / Math.max(usageSummary.daily_chart.length - 1, 1)) * chartWidth;
    const y = chartHeight - (d.cost / maxCost) * (chartHeight - 15);
    return `${x},${y}`;
  }).join(' ');

  const pathD = points ? `M ${points}` : '';
  const areaD = points ? `${pathD} L ${chartWidth},${chartHeight} L 0,${chartHeight} Z` : '';

  if (!isAuthenticated && !apiKey) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans selection:bg-blue-500/30">
      {/* Top Header */}
      <header className="border-b border-slate-900 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Activity className="text-white" size={18} />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight flex items-center gap-1.5">
                Dev Dashboard
                <span className="text-xs font-normal text-slate-500">v4.0</span>
              </h1>
              <p className="text-xs text-slate-400">LLM Proxy Vault & Task Platform</p>
            </div>
          </div>
          
          <div className="flex flex-col sm:flex-row items-center gap-4 w-full sm:w-auto">
            {/* Tenant Switcher */}
            {(isAdmin || tenants.length > 0) && (
              <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 w-full sm:w-56 focus-within:ring-2 focus-within:ring-blue-500 transition">
                <Users size={14} className="text-slate-500" />
                <select
                  value={selectedTenantId}
                  onChange={(e) => setSelectedTenantId(e.target.value)}
                  className="bg-transparent text-xs text-white focus:outline-none w-full cursor-pointer"
                >
                  {isAdmin && <option value="" className="bg-slate-950">All Tenants (Global)</option>}
                  {tenants.map(t => (
                    <option key={t.id} value={t.id} className="bg-slate-950">
                      {t.name} ({t.slug})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Auth Info / Fallback API Key Input */}
            {isAuthenticated ? (
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-400 font-semibold">{user?.email}</span>
                <button
                  onClick={handleLogout}
                  className="px-3 py-1.5 bg-slate-900 border border-slate-800 hover:bg-slate-800 hover:border-slate-700 text-slate-300 hover:text-white text-xs font-semibold rounded-lg cursor-pointer transition"
                >
                  Logout
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 w-full sm:w-64 focus-within:ring-2 focus-within:ring-blue-500 transition">
                <Key size={14} className="text-slate-500" />
                <input
                  type="password"
                  value={apiKey}
                  placeholder="API Authorization Key"
                  onChange={(e) => setApiKey(e.target.value)}
                  className="bg-transparent text-xs text-white focus:outline-none w-full font-mono"
                />
              </div>
            )}
            
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${apiConnected ? 'bg-emerald-500 shadow-md shadow-emerald-500/50' : 'bg-red-500 animate-pulse'} `}></span>
                <span className="text-xs font-medium text-slate-400">
                  {apiConnected ? 'WebSockets Live' : 'Offline'}
                </span>
              </div>
              
              <button 
                onClick={() => {
                  fetchJobs(true);
                  if (activeTab === 'tenants') fetchTenantMetrics();
                  if (activeTab === 'vault') fetchVaultKeys();
                  if (activeTab === 'proxy_keys') fetchProxyKeys();
                  if (activeTab === 'usage') fetchUsageData();
                }}
                disabled={isRefreshing}
                className="p-1.5 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900/60 hover:bg-slate-900 text-slate-400 hover:text-white transition disabled:opacity-40 cursor-pointer"
              >
                <RefreshCw size={15} className={isRefreshing ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Grid Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-6">
        
        {/* Unread Alerts Banner */}
        {unreadAlerts.length > 0 && (
          <div className="bg-amber-950/40 border border-amber-900/40 rounded-xl p-4 relative overflow-hidden animate-pulse">
            <div className="absolute top-0 left-0 bottom-0 w-[4px] bg-amber-500"></div>
            <div className="flex items-start gap-3">
              <div className="p-1.5 rounded-lg bg-amber-900/40 text-amber-400 mt-0.5">
                <Bell size={16} />
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-bold text-white mb-1.5">Spend Warning Notifications</h4>
                <div className="divide-y divide-amber-900/25 max-h-32 overflow-y-auto text-xs text-slate-300">
                  {unreadAlerts.map(a => (
                    <div key={a.id} className="py-2 flex justify-between items-center gap-4">
                      <span>{a.message}</span>
                      <button
                        onClick={() => handleMarkAlertRead(a.id)}
                        className="text-amber-400 hover:text-white underline cursor-pointer text-[11px] whitespace-nowrap"
                      >
                        Mark Read
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Real-time Metrics Panels */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-slate-900/35 border border-slate-900 rounded-xl p-4 flex items-center gap-4 relative overflow-hidden">
            <div className="h-10 w-10 rounded-lg bg-blue-950/60 flex items-center justify-center text-blue-400">
              <BarChart3 size={20} />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-semibold uppercase">Throughput (Total)</p>
              <h4 className="text-xl font-bold text-white mt-0.5">{metrics.throughput} Jobs</h4>
            </div>
            <div className="absolute right-2 -bottom-2 opacity-5 text-blue-400">
              <BarChart3 size={80} />
            </div>
          </div>
          
          <div className="bg-slate-900/35 border border-slate-900 rounded-xl p-4 flex items-center gap-4 relative overflow-hidden">
            <div className="h-10 w-10 rounded-lg bg-emerald-950/60 flex items-center justify-center text-emerald-400">
              <Clock size={20} />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-semibold uppercase">Avg Job Duration</p>
              <h4 className="text-xl font-bold text-white mt-0.5">{metrics.avg_duration_seconds}s</h4>
            </div>
            <div className="absolute right-2 -bottom-2 opacity-5 text-emerald-400">
              <Clock size={80} />
            </div>
          </div>
          
          <div className="bg-slate-900/35 border border-slate-900 rounded-xl p-4 flex items-center gap-4 relative overflow-hidden">
            <div className="h-10 w-10 rounded-lg bg-red-950/50 flex items-center justify-center text-red-400">
              <AlertTriangle size={20} />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-semibold uppercase">Failure Rate</p>
              <h4 className="text-xl font-bold text-white mt-0.5">{metrics.failure_rate}%</h4>
            </div>
            <div className="absolute right-2 -bottom-2 opacity-5 text-red-400">
              <AlertTriangle size={80} />
            </div>
          </div>
        </div>

        {/* Tab Navigation (Visible to Admin and Tenant-Scoped Users) */}
        {(isAdmin || tenants.length > 0) && (
          <div className="flex flex-wrap border-b border-slate-900 gap-1 mb-2">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`py-2 px-4 font-bold text-xs transition-all rounded-t-lg border-t-2 cursor-pointer ${
                activeTab === 'dashboard'
                  ? 'bg-slate-900/40 border-t-blue-500 text-white'
                  : 'border-t-transparent text-slate-450 hover:text-slate-200'
              }`}
            >
              Task Dashboard
            </button>
            <button
              onClick={() => setActiveTab('tenants')}
              className={`py-2 px-4 font-bold text-xs transition-all rounded-t-lg border-t-2 cursor-pointer ${
                activeTab === 'tenants'
                  ? 'bg-slate-900/40 border-t-blue-500 text-white'
                  : 'border-t-transparent text-slate-450 hover:text-slate-200'
              }`}
            >
              Tenants & Tasks
            </button>
            <button
              onClick={() => setActiveTab('vault')}
              className={`py-2 px-4 font-bold text-xs transition-all rounded-t-lg border-t-2 cursor-pointer ${
                activeTab === 'vault'
                  ? 'bg-slate-900/40 border-t-blue-500 text-white'
                  : 'border-t-transparent text-slate-450 hover:text-slate-200'
              }`}
            >
              Key Vault
            </button>
            <button
              onClick={() => setActiveTab('proxy_keys')}
              className={`py-2 px-4 font-bold text-xs transition-all rounded-t-lg border-t-2 cursor-pointer ${
                activeTab === 'proxy_keys'
                  ? 'bg-slate-900/40 border-t-blue-500 text-white'
                  : 'border-t-transparent text-slate-450 hover:text-slate-200'
              }`}
            >
              Project Proxy Keys
            </button>
            <button
              onClick={() => setActiveTab('usage')}
              className={`py-2 px-4 font-bold text-xs transition-all rounded-t-lg border-t-2 cursor-pointer ${
                activeTab === 'usage'
                  ? 'bg-slate-900/40 border-t-blue-500 text-white'
                  : 'border-t-transparent text-slate-450 hover:text-slate-200'
              }`}
            >
              Proxy Usage Analytics
            </button>
          </div>
        )}

        {/* Dashboard Tab Content */}
        {activeTab === 'dashboard' && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
              {/* Submit Panel */}
              <div className="lg:col-span-1">
                <JobSubmitForm onJobSubmitted={handleJobSubmitted} apiKey={apiKey} />
              </div>

              {/* Job List Panel */}
              <div className="lg:col-span-2 space-y-6">
                <JobTable 
                  jobs={jobs} 
                  selectedJobId={selectedJobId} 
                  onSelectJob={setSelectedJobId} 
                  onCancelJob={handleCancelJob} 
                />
              </div>
            </div>

            {/* Live Logs Terminal Panel */}
            <div className="bg-slate-950 border border-slate-900 rounded-xl overflow-hidden shadow-2xl flex flex-col h-[380px]">
              <div className="bg-slate-900/50 px-4 py-3 border-b border-slate-900/85 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Terminal size={16} className="text-blue-400" />
                  <h3 className="text-sm font-bold text-white">Live Log Console</h3>
                  {selectedJobDetails && (
                    <span className="text-xs font-mono text-slate-500">
                      - Job {selectedJobDetails.id}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-600"></span>
                  <span className="text-xs text-slate-500 font-mono">STDOUT (WEBSOCKETS)</span>
                </div>
              </div>
              
              <div className="flex-1 p-4 bg-slate-950 font-mono text-xs overflow-y-auto leading-relaxed select-text">
                {selectedJobDetails ? (
                  <div className="space-y-1.5">
                    <div className="text-slate-650 mb-2">--- Streaming logs for job {selectedJobDetails.id} ---</div>
                    
                    {selectedJobDetails.logs && selectedJobDetails.logs.length > 0 ? (
                      selectedJobDetails.logs.map((log) => {
                        let levelColor = "text-blue-400";
                        if (log.level === 'WARNING') levelColor = "text-amber-400";
                        if (log.level === 'ERROR') levelColor = "text-red-450";
                        
                        return (
                          <div key={log.id} className="flex items-start gap-3 hover:bg-slate-900/40 py-0.5 rounded px-1 transition-colors">
                            <span className="text-slate-600 select-none">{formatLogTime(log.created_at)}</span>
                            <span className={`font-bold ${levelColor} select-none w-14`}>[{log.level}]</span>
                            <span className="text-slate-300 break-all">{log.message}</span>
                          </div>
                        );
                      })
                    ) : (
                      <div className="text-slate-650 italic">No logs recorded yet.</div>
                    )}
                    
                    {['PENDING', 'RUNNING'].includes(selectedJobDetails.status) && (
                      <div className="flex items-center gap-2 text-slate-500 italic mt-2">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping"></span>
                        Running... progress: {selectedJobDetails.progress || 0}%
                      </div>
                    )}
                    
                    <div ref={logsEndRef} />
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-slate-600 select-none">
                    <Terminal size={32} className="mb-2 opacity-50 text-slate-650" />
                    <p className="text-sm">Select a job from the table to inspect execution logs in real-time.</p>
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        {/* Tenants Management Tab Content */}
        {activeTab === 'tenants' && (
          <div className="space-y-6">
            {generatedKey && (
              <div className="bg-blue-950/50 border border-blue-800 rounded-xl p-6 relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-blue-500 to-indigo-500"></div>
                <div className="flex items-start gap-4">
                  <div className="p-2 rounded-lg bg-blue-900/40 text-blue-400 mt-1">
                    <AlertCircle size={20} />
                  </div>
                  <div className="space-y-2 flex-1">
                    <h4 className="text-md font-bold text-white">New Scoped API Key Generated Successfully!</h4>
                    <p className="text-xs text-slate-400">
                      Copy this key value now. For security purposes, <strong>it will not be shown again</strong>.
                    </p>
                    <div className="flex items-center gap-2 bg-slate-950 border border-slate-900 rounded-lg p-3 font-mono text-xs max-w-2xl select-all select-none">
                      <span className="text-emerald-400 flex-1 truncate">{generatedKey.key}</span>
                      <button
                        onClick={() => copyKeyToClipboard(generatedKey.key)}
                        className="p-1 rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition cursor-pointer"
                        title="Copy to clipboard"
                      >
                        <Plus size={14} className="rotate-45" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl overflow-hidden shadow-xl">
              <div className="px-6 py-4 border-b border-slate-800/80 bg-slate-950/20 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users size={18} className="text-blue-400" />
                  <h3 className="text-md font-bold text-white">Tenants List & Metrics</h3>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800/80 bg-slate-950/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                      <th className="py-3.5 px-6">Name</th>
                      <th className="py-3.5 px-6">Slug</th>
                      <th className="py-3.5 px-6">Status</th>
                      <th className="py-3.5 px-6">Throughput</th>
                      <th className="py-3.5 px-6">Success Rate</th>
                      <th className="py-3.5 px-6">Avg Duration</th>
                      <th className="py-3.5 px-6">Embeddings</th>
                      <th className="py-3.5 px-6">Active Keys</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40 text-sm text-slate-300">
                    {tenantMetrics.map((t) => (
                      <tr key={t.tenant_id} className="hover:bg-slate-800/10 transition">
                        <td className="py-3.5 px-6 font-bold text-white">{t.name}</td>
                        <td className="py-3.5 px-6 font-mono text-xs text-slate-400">{t.slug}</td>
                        <td className="py-3.5 px-6">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                            t.is_active 
                              ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-900/30' 
                              : 'bg-red-950/50 text-red-400 border border-red-900/30'
                          }`}>
                            {t.is_active ? 'Active' : 'Suspended'}
                          </span>
                        </td>
                        <td className="py-3.5 px-6 font-mono">{t.throughput} Jobs</td>
                        <td className="py-3.5 px-6 font-mono">{t.success_rate}%</td>
                        <td className="py-3.5 px-6 font-mono">{t.avg_duration_seconds}s</td>
                        <td className="py-3.5 px-6 font-mono">{t.document_count} chunks</td>
                        <td className="py-3.5 px-6 font-mono">{t.active_keys}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Register Tenant Form */}
              <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-6 shadow-xl relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-[2px] bg-blue-500"></div>
                <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
                  <Users size={16} className="text-blue-400" /> Register New Tenant
                </h3>
                <form onSubmit={handleCreateTenant} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Tenant Name</label>
                    <input
                      type="text"
                      value={newTenantName}
                      placeholder="e.g., Career Guidance"
                      onChange={(e) => setNewTenantName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Tenant Slug (URL-Safe)</label>
                    <input
                      type="text"
                      value={newTenantSlug}
                      placeholder="e.g., career-guidance"
                      onChange={(e) => setNewTenantSlug(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition font-mono"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full bg-slate-900 hover:bg-slate-850 border border-slate-800 text-white font-bold py-2 rounded-lg text-xs transition cursor-pointer"
                  >
                    Register Tenant
                  </button>
                </form>
              </div>

              {/* Generate Key Form */}
              <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-6 shadow-xl relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-[2px] bg-indigo-500"></div>
                <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
                  <Key size={16} className="text-indigo-400" /> Issue Scoped Task Key
                </h3>
                <form onSubmit={handleGenerateKey} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Target Tenant</label>
                    <select
                      value={newKeyTenantId}
                      onChange={(e) => setNewKeyTenantId(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition cursor-pointer"
                      required
                    >
                      <option value="">Select a Tenant</option>
                      {tenants.map(t => (
                        <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Key Description Name</label>
                    <input
                      type="text"
                      value={newKeyName}
                      placeholder="e.g., Guidance Server Key"
                      onChange={(e) => setNewKeyName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                      required
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5">Authorized Scopes</label>
                    <div className="grid grid-cols-2 gap-2 bg-slate-950 p-3 rounded-lg border border-slate-900 text-xs">
                      {[
                        { val: 'task:sleep_task', lbl: 'Run Sleep Task' },
                        { val: 'task:repo_ingestion', lbl: 'Run Ingest Task' },
                        { val: 'task:embedding_pipeline', lbl: 'Run Embed Pipeline' },
                        { val: 'priority:high', lbl: 'Allow High Queue' },
                        { val: 'priority:default', lbl: 'Allow Default Queue' },
                        { val: 'priority:low', lbl: 'Allow Low Queue' },
                        { val: '*', lbl: 'Full Admin Scope (*)' }
                      ].map(s => {
                        const checked = newKeyScopes.includes(s.val);
                        return (
                          <label key={s.val} className="flex items-center gap-2 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleScope(s.val)}
                              className="accent-indigo-500"
                            />
                            <span className="text-slate-350">{s.lbl}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                  
                  {formError && <div className="text-xs text-red-400 bg-red-950/40 p-2 rounded border border-red-900/50">{formError}</div>}
                  {formSuccess && <div className="text-xs text-emerald-400 bg-emerald-950/40 p-2 rounded border border-emerald-900/50">{formSuccess}</div>}

                  <button
                    type="submit"
                    className="w-full bg-indigo-900/40 hover:bg-indigo-900/60 border border-indigo-900 text-white font-bold py-2 rounded-lg text-xs transition cursor-pointer"
                  >
                    Generate Task Key
                  </button>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Vault Management Tab Content */}
        {activeTab === 'vault' && (
          <div className="space-y-6">
            <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl overflow-hidden shadow-xl">
              <div className="px-6 py-4 border-b border-slate-800/80 bg-slate-950/20">
                <h3 className="text-md font-bold text-white flex items-center gap-2">
                  <ShieldAlert size={18} className="text-blue-400" /> Decrypted Key Vault (Real Provider Keys)
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800/80 bg-slate-950/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                      <th className="py-3.5 px-6">Tenant</th>
                      <th className="py-3.5 px-6">Provider</th>
                      <th className="py-3.5 px-6">Key Hint</th>
                      <th className="py-3.5 px-6">Status</th>
                      <th className="py-3.5 px-6">Created At</th>
                      <th className="py-3.5 px-6 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40 text-sm text-slate-300">
                    {vaultKeys.map((vk) => {
                      const tenantName = tenants.find(t => t.id === vk.tenant_id)?.name || "Unknown Tenant";
                      return (
                        <tr key={vk.id} className="hover:bg-slate-800/10 transition">
                          <td className="py-3.5 px-6 font-bold text-white">{tenantName}</td>
                          <td className="py-3.5 px-6 font-mono uppercase text-xs text-blue-400">{vk.provider}</td>
                          <td className="py-3.5 px-6 font-mono text-xs">•••• •••• •••• {vk.key_hint}</td>
                          <td className="py-3.5 px-6">
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-950/50 text-emerald-400 border border-emerald-900/30">
                              Active
                            </span>
                          </td>
                          <td className="py-3.5 px-6 text-slate-500 font-mono text-xs">{new Date(vk.created_at).toLocaleString()}</td>
                          <td className="py-3.5 px-6 text-right">
                            <div className="flex justify-end items-center gap-2">
                              {rotatingKeyId === vk.id ? (
                                <div className="flex items-center gap-2">
                                  <input
                                    type="password"
                                    placeholder="Paste rotated key..."
                                    value={rotatingKeyValue}
                                    onChange={(e) => setRotatingKeyValue(e.target.value)}
                                    className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono w-44"
                                  />
                                  <button
                                    onClick={() => handleRotateVaultKey(vk.id)}
                                    className="p-1.5 rounded bg-emerald-950 hover:bg-emerald-900 text-emerald-400 hover:text-white transition cursor-pointer"
                                    title="Save Key"
                                  >
                                    <Check size={13} />
                                  </button>
                                  <button
                                    onClick={() => setRotatingKeyId(null)}
                                    className="p-1.5 rounded bg-red-950 hover:bg-red-900 text-red-400 hover:text-white transition cursor-pointer"
                                    title="Cancel"
                                  >
                                    <X size={13} />
                                  </button>
                                </div>
                              ) : (
                                <>
                                  <button
                                    onClick={() => {
                                      setRotatingKeyId(vk.id);
                                      setRotatingKeyValue('');
                                    }}
                                    className="flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition cursor-pointer"
                                  >
                                    <Settings size={12} /> Rotate
                                  </button>
                                  <button
                                    onClick={() => handleDeleteVaultKey(vk.id)}
                                    className="p-1 rounded hover:bg-red-950/30 text-slate-550 hover:text-red-400 transition cursor-pointer"
                                    title="Delete/Revoke"
                                  >
                                    <Trash2 size={14} />
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {vaultKeys.length === 0 && (
                      <tr>
                        <td colSpan="6" className="py-8 text-center text-slate-500 italic">No keys stored in the vault yet. Configure your first provider key below.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Configure Vault Key Form */}
            <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-6 shadow-xl relative overflow-hidden max-w-xl">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-blue-500"></div>
              <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
                <Plus size={16} className="text-blue-400" /> Store Provider Key
              </h3>
              <form onSubmit={handleCreateVaultKey} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1">Target Tenant</label>
                  <select
                    value={newVaultTenantId}
                    onChange={(e) => setNewVaultTenantId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition cursor-pointer"
                    required
                  >
                    <option value="">Select a Tenant</option>
                    {tenants.map(t => (
                      <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>
                    ))}
                  </select>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Provider</label>
                    <select
                      value={newVaultProvider}
                      onChange={(e) => setNewVaultProvider(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition cursor-pointer"
                    >
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="groq">Groq</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1">API Key value (stored encrypted)</label>
                  <input
                    type="password"
                    placeholder="sk-..."
                    value={newVaultKey}
                    onChange={(e) => setNewVaultKey(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition font-mono"
                    required
                  />
                </div>

                {formError && <div className="text-xs text-red-400 bg-red-950/40 p-2 rounded border border-red-900/50">{formError}</div>}
                {formSuccess && <div className="text-xs text-emerald-400 bg-emerald-950/40 p-2 rounded border border-emerald-900/50">{formSuccess}</div>}

                <button
                  type="submit"
                  className="bg-blue-900/40 hover:bg-blue-900/60 border border-blue-900 text-white font-bold py-2 px-6 rounded-lg text-xs transition cursor-pointer"
                >
                  Encrypt & Save Key
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Proxy Keys Management Content */}
        {activeTab === 'proxy_keys' && (
          <div className="space-y-6">
            
            {generatedProxyKey && (
              <div className="bg-blue-950/50 border border-blue-800 rounded-xl p-6 relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-blue-500 to-indigo-500"></div>
                <div className="flex items-start gap-4">
                  <div className="p-2 rounded-lg bg-blue-900/40 text-blue-400 mt-1">
                    <AlertCircle size={20} />
                  </div>
                  <div className="space-y-2 flex-1">
                    <h4 className="text-md font-bold text-white">New Scoped Project Proxy Key Generated!</h4>
                    <p className="text-xs text-slate-450">
                      Copy this key now. It replaces your `OPENAI_API_KEY` (or other provider keys) in your project's `.env`. <strong>It will not be shown again</strong>.
                    </p>
                    <div className="flex items-center gap-2 bg-slate-950 border border-slate-900 rounded-lg p-3 font-mono text-sm max-w-2xl select-all select-none">
                      <span className="text-emerald-400 flex-1 truncate">{generatedProxyKey.key}</span>
                      <button
                        onClick={() => copyKeyToClipboard(generatedProxyKey.key)}
                        className="p-1 rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition cursor-pointer"
                        title="Copy to clipboard"
                      >
                        <Plus size={14} className="rotate-45" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl overflow-hidden shadow-xl">
              <div className="px-6 py-4 border-b border-slate-800/80 bg-slate-950/20">
                <h3 className="text-md font-bold text-white flex items-center gap-2">
                  <Key size={18} className="text-indigo-400" /> Scoped Project Proxy Keys
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800/80 bg-slate-950/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                      <th className="py-3.5 px-6">Name / Description</th>
                      <th className="py-3.5 px-6">Key Hint</th>
                      <th className="py-3.5 px-6">Allowed Providers</th>
                      <th className="py-3.5 px-6">Monthly Budget</th>
                      <th className="py-3.5 px-6">Fallback Rules</th>
                      <th className="py-3.5 px-6 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40 text-sm text-slate-300">
                    {proxyKeys.map((pk) => (
                      <tr key={pk.id} className="hover:bg-slate-800/10 transition">
                        <td className="py-3.5 px-6 font-bold text-white">{pk.name}</td>
                        <td className="py-3.5 px-6 font-mono text-xs text-slate-400">{pk.key_hint}</td>
                        <td className="py-3.5 px-6">
                          <div className="flex gap-1.5 flex-wrap">
                            {pk.allowed_providers.map(p => (
                              <span key={p} className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 font-mono text-[10px] uppercase text-slate-350">
                                {p}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="py-3.5 px-6 font-mono font-semibold text-emerald-450">
                          {pk.monthly_cap_usd > 0 ? `$${pk.monthly_cap_usd.toFixed(2)}/mo` : 'Unlimited'}
                        </td>
                        <td className="py-3.5 px-6 text-xs font-mono">
                          {editingFallbackKeyId === pk.id ? (
                            <div className="flex items-center gap-2">
                              <textarea
                                value={fallbackMappingsStr}
                                onChange={(e) => setFallbackMappingsStr(e.target.value)}
                                className="bg-slate-950 border border-slate-850 rounded px-2 py-1 text-[11px] text-white focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono w-60 h-16 resize-none"
                              />
                              <div className="flex flex-col gap-1">
                                <button
                                  onClick={() => handleUpdateFallback(pk.id)}
                                  className="p-1.5 rounded bg-emerald-950 text-emerald-450 hover:text-white transition cursor-pointer"
                                  title="Save"
                                >
                                  <Check size={12} />
                                </button>
                                <button
                                  onClick={() => setEditingFallbackKeyId(null)}
                                  className="p-1.5 rounded bg-red-950 text-red-450 hover:text-white transition cursor-pointer"
                                  title="Cancel"
                                >
                                  <X size={12} />
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <span className="truncate max-w-xs text-slate-500">
                                {Object.keys(pk.fallback_mappings).length > 0 
                                  ? `${Object.keys(pk.fallback_mappings).length} rule(s) configured` 
                                  : 'None'}
                              </span>
                              <button
                                onClick={() => {
                                  setEditingFallbackKeyId(pk.id);
                                  setFallbackMappingsStr(JSON.stringify(pk.fallback_mappings, null, 2));
                                }}
                                className="text-indigo-400 hover:text-white underline cursor-pointer text-[11px]"
                              >
                                Edit
                              </button>
                            </div>
                          )}
                        </td>
                        <td className="py-3.5 px-6 text-right">
                          <button
                            onClick={() => handleDeleteProxyKey(pk.id)}
                            className="p-1.5 rounded hover:bg-red-950/30 text-slate-550 hover:text-red-400 transition cursor-pointer"
                            title="Revoke Key"
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {proxyKeys.length === 0 && (
                      <tr>
                        <td colSpan="6" className="py-8 text-center text-slate-500 italic">No proxy keys issued yet. Create one below to scope and rate limit your client applications.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Create Proxy Key Form */}
            <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-6 shadow-xl relative overflow-hidden max-w-xl">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-indigo-500"></div>
              <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
                <Plus size={16} className="text-indigo-400" /> Issue Project Proxy Key
              </h3>
              <form onSubmit={handleCreateProxyKey} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1">Target Tenant</label>
                  <select
                    value={newProxyTenantId}
                    onChange={(e) => setNewProxyTenantId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition cursor-pointer"
                    required
                  >
                    <option value="">Select a Tenant</option>
                    {tenants.map(t => (
                      <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1">Key Name / Description</label>
                  <input
                    type="text"
                    placeholder="e.g. Career Guidance Server"
                    value={newProxyName}
                    onChange={(e) => setNewProxyName(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                    required
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">Monthly Spend Cap (USD)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={newProxyCap}
                      onChange={(e) => setNewProxyCap(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition font-mono"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5">Authorized Providers</label>
                    <div className="flex items-center gap-3 bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs">
                      {['openai', 'anthropic', 'groq'].map(p => {
                        const checked = newProxyProviders.includes(p);
                        return (
                          <label key={p} className="flex items-center gap-1.5 cursor-pointer uppercase font-mono text-[10px] select-none text-slate-300">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleProxyProvider(p)}
                              className="accent-indigo-500"
                            />
                            {p}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {formError && <div className="text-xs text-red-400 bg-red-950/40 p-2 rounded border border-red-900/50">{formError}</div>}
                {formSuccess && <div className="text-xs text-emerald-400 bg-emerald-950/40 p-2 rounded border border-emerald-900/50">{formSuccess}</div>}

                <button
                  type="submit"
                  className="bg-indigo-900/40 hover:bg-indigo-900/60 border border-indigo-900 text-white font-bold py-2 px-6 rounded-lg text-xs transition cursor-pointer"
                >
                  Generate Proxy Key
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Proxy Usage Analytics Content */}
        {activeTab === 'usage' && (
          <div className="space-y-6">
            
            {/* Usage Aggregate Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-slate-900/35 border border-slate-900 rounded-xl p-4 flex items-center gap-4 relative overflow-hidden">
                <div className="h-10 w-10 rounded-lg bg-emerald-950/60 flex items-center justify-center text-emerald-400">
                  <Activity size={20} />
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-semibold uppercase">Total Proxy Spend</p>
                  <h4 className="text-xl font-bold text-white mt-0.5">${usageSummary.total_cost_usd.toFixed(4)}</h4>
                </div>
              </div>

              <div className="bg-slate-900/35 border border-slate-900 rounded-xl p-4 flex items-center gap-4 relative overflow-hidden">
                <div className="h-10 w-10 rounded-lg bg-blue-950/60 flex items-center justify-center text-blue-400">
                  <FileText size={20} />
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-semibold uppercase">Total Proxied Requests</p>
                  <h4 className="text-xl font-bold text-white mt-0.5">{usageSummary.total_requests} calls</h4>
                </div>
              </div>

              <div className="bg-slate-900/35 border border-slate-900 rounded-xl p-4 flex items-center gap-4 relative overflow-hidden">
                <div className="h-10 w-10 rounded-lg bg-indigo-950/60 flex items-center justify-center text-indigo-400">
                  <Cpu size={20} />
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-semibold uppercase">Active Models</p>
                  <h4 className="text-xl font-bold text-white mt-0.5">{Object.keys(usageSummary.cost_by_model).length} active</h4>
                </div>
              </div>

              <div className="bg-slate-900/35 border border-slate-900 rounded-xl p-4 flex items-center gap-4 relative overflow-hidden">
                <div className="h-10 w-10 rounded-lg bg-amber-950/60 flex items-center justify-center text-amber-400">
                  <Bell size={20} />
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-semibold uppercase">Active Spend Warnings</p>
                  <h4 className="text-xl font-bold text-white mt-0.5">{alerts.length} registered</h4>
                </div>
              </div>
            </div>

            {/* Daily Line Chart & Summaries */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Daily Chart (SVG-based) */}
              <div className="lg:col-span-2 bg-slate-900/40 border border-slate-800/80 rounded-xl p-6 shadow-xl relative overflow-hidden">
                <h3 className="text-sm font-bold text-white mb-4">Daily Spend Chart (Last {usageSummary.daily_chart.length} days)</h3>
                
                {usageSummary.daily_chart.length > 0 ? (
                  <div className="mt-2 space-y-4">
                    <div className="bg-slate-950 border border-slate-900 rounded-lg p-4 h-40 flex flex-col justify-end">
                      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-full text-blue-500">
                        <defs>
                          <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="rgb(59, 130, 246)" stopOpacity="0.25"/>
                            <stop offset="100%" stopColor="rgb(59, 130, 246)" stopOpacity="0.0"/>
                          </linearGradient>
                        </defs>
                        {areaD && <path d={areaD} fill="url(#chartGrad)" />}
                        {pathD && <path d={pathD} fill="none" stroke="currentColor" strokeWidth="2.5" />}
                        
                        {/* Dot indicators */}
                        {usageSummary.daily_chart.map((d, i) => {
                          const x = (i / Math.max(usageSummary.daily_chart.length - 1, 1)) * chartWidth;
                          const y = chartHeight - (d.cost / maxCost) * (chartHeight - 15);
                          return (
                            <circle key={i} cx={x} cy={y} r="4" fill="rgb(59, 130, 246)" className="hover:scale-150 transition-transform cursor-pointer" />
                          );
                        })}
                      </svg>
                    </div>
                    {/* X-Axis Dates */}
                    <div className="flex justify-between text-[10px] text-slate-550 font-mono px-2">
                      {usageSummary.daily_chart.map((d, i) => {
                        const dateParts = d.date.split("-");
                        const label = `${dateParts[1]}/${dateParts[2]}`;
                        return <span key={i}>{label}</span>;
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="h-40 flex items-center justify-center text-slate-500 italic">No usage recorded yet.</div>
                )}
              </div>

              {/* Cost breakdowns */}
              <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-6 shadow-xl space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-1.5">
                    <Shield size={14} className="text-indigo-400" /> Cost By Provider
                  </h3>
                  <div className="space-y-2 text-xs">
                    {Object.entries(usageSummary.cost_by_provider).map(([prov, cost]) => (
                      <div key={prov} className="flex justify-between items-center py-1 border-b border-slate-850">
                        <span className="font-mono uppercase text-slate-350">{prov}</span>
                        <span className="font-mono font-bold text-white">${cost.toFixed(4)}</span>
                      </div>
                    ))}
                    {Object.keys(usageSummary.cost_by_provider).length === 0 && (
                      <div className="text-slate-500 italic">No data yet.</div>
                    )}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-1.5">
                    <Key size={14} className="text-blue-400" /> Cost By Project (Proxy Key)
                  </h3>
                  <div className="space-y-2 text-xs">
                    {Object.entries(usageSummary.cost_by_project).map(([proj, cost]) => (
                      <div key={proj} className="flex justify-between items-center py-1 border-b border-slate-850">
                        <span className="truncate max-w-xs text-slate-350">{proj}</span>
                        <span className="font-mono font-bold text-white">${cost.toFixed(4)}</span>
                      </div>
                    ))}
                    {Object.keys(usageSummary.cost_by_project).length === 0 && (
                      <div className="text-slate-500 italic">No data yet.</div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Recent Proxy Logs Table */}
            <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl overflow-hidden shadow-xl">
              <div className="px-6 py-4 border-b border-slate-800/80 bg-slate-950/20 flex items-center justify-between">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Terminal size={16} className="text-blue-400" /> Recent Proxied Telemetry Logs
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800/80 bg-slate-950/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                      <th className="py-3 px-6">Timestamp</th>
                      <th className="py-3 px-6">Project (Proxy Key)</th>
                      <th className="py-3 px-6">Provider</th>
                      <th className="py-3 px-6">Model</th>
                      <th className="py-3 px-6">Tokens (In / Out)</th>
                      <th className="py-3 px-6">Latency</th>
                      <th className="py-3 px-6">Cost</th>
                      <th className="py-3 px-6">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40 text-sm text-slate-300">
                    {usageLogs.map((l) => (
                      <tr key={l.id} className="hover:bg-slate-800/10 transition text-xs font-mono">
                        <td className="py-3 px-6 text-slate-500">{new Date(l.created_at).toLocaleTimeString()}</td>
                        <td className="py-3 px-6 font-sans font-bold text-white">{l.proxy_key_name}</td>
                        <td className="py-3 px-6 uppercase text-blue-400 text-[10px]">{l.provider}</td>
                        <td className="py-3 px-6 text-slate-350">{l.model}</td>
                        <td className="py-3 px-6 text-slate-350">{l.prompt_tokens} / {l.completion_tokens}</td>
                        <td className="py-3 px-6 text-slate-350">{l.latency_ms}ms</td>
                        <td className="py-3 px-6 text-emerald-450">${l.estimated_cost_usd.toFixed(5)}</td>
                        <td className="py-3 px-6">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            l.status_code < 400 ? 'bg-emerald-950/40 text-emerald-400' : 'bg-red-950/40 text-red-400'
                          }`}>
                            {l.status_code}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {usageLogs.length === 0 && (
                      <tr>
                        <td colSpan="8" className="py-8 text-center text-slate-500 italic">No usage recorded yet. Calls through the proxy will stream telemetry here.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900/60 bg-slate-950 py-4 text-center text-xs text-slate-650">
        Dev Dashboard © 2026. Built with FastAPI, Celery, and React + TailwindCSS v4.
      </footer>
    </div>
  );
}
