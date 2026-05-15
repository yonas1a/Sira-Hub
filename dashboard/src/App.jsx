import React, { useState, useEffect, useMemo } from 'react';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend
} from 'recharts';
import { 
  Users, Briefcase, Activity, Send, Star, UserCheck, 
  MessageSquare, LayoutDashboard, Clock, FileText, Settings, Zap, Globe, Radio
} from 'lucide-react';

const API_BASE = "http://localhost:8000/api";

function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [chartData, setChartData] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [customGroups, setCustomGroups] = useState([]);
  const [selectedUsers, setSelectedUsers] = useState(new Set());
  const [newGroupName, setNewGroupName] = useState('');
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [loading, setLoading] = useState(true);

  // Scraper settings state
  const [scraperCfg, setScraperCfg] = useState({
    scrape_interval_minutes: '5',
    web_enabled: '1',
    web_base_url: 'https://www.hahu.jobs/jobs?min_yoe=0&max_yoe=100&page=',
    web_start_page: '1',
    web_end_page: '5',
    tg_enabled: '1',
    tg_channels: 'freelance_ethio',
    tg_message_limit: '30',
    tg_api_id: '',
    tg_api_hash: '',
    tg_session: 'my_session',
  });
  const [scraperSaving, setScraperSaving] = useState(false);
  const [scraperTriggering, setScraperTriggering] = useState(false);
  const [sourceData, setSourceData] = useState([]);

  // Notification form state
  const [messageConditions, setMessageConditions] = useState({
    access_type: 'all',
    age_range: 'all',
    job_type: 'all',
    category: 'all'
  });
  const [messageText, setMessageText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [notification, setNotification] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statsRes, usersRes, chartRes, jobsRes, groupsRes, scraperRes, sourceRes] = await Promise.all([
        fetch(`${API_BASE}/stats`),
        fetch(`${API_BASE}/users`),
        fetch(`${API_BASE}/jobs-chart`),
        fetch(`${API_BASE}/jobs`),
        fetch(`${API_BASE}/groups`),
        fetch(`${API_BASE}/scraper-config`),
        fetch(`${API_BASE}/jobs/by-source`),
      ]);
      setStats(await statsRes.json());
      setUsers(await usersRes.json());
      setChartData(await chartRes.json());
      setJobs(await jobsRes.json());
      setCustomGroups(await groupsRes.json());
      const sc = await scraperRes.json();
      if (sc && typeof sc === 'object') setScraperCfg(prev => ({ ...prev, ...sc }));
      try { const sd = await sourceRes.json(); setSourceData(Array.isArray(sd) ? sd.map(r => ({name: r.source==='web'?'Hahu Jobs':r.source==='telegram'?'Telegram':r.source, value: r.count})) : []); } catch(e) {}
    } catch (error) {
      console.error("Failed to fetch data", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveScraperConfig = async (e) => {
    e.preventDefault();
    setScraperSaving(true);
    try {
      const res = await fetch(`${API_BASE}/scraper-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scraperCfg),
      });
      if (res.ok) showNotification('✅ Scraper settings saved!');
      else showNotification('❌ Failed to save settings');
    } catch { showNotification('❌ Network error'); }
    finally { setScraperSaving(false); }
  };

  const handleTriggerScraper = async () => {
    setScraperTriggering(true);
    try {
      const res = await fetch(`${API_BASE}/scraper/trigger`, { method: 'POST' });
      if (res.ok) showNotification('🕷️ Scrape cycle triggered!');
      else showNotification('❌ Failed to trigger scraper');
    } catch { showNotification('❌ Network error'); }
    finally { setTimeout(() => setScraperTriggering(false), 2000); }
  };

  const showNotification = (msg) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!messageText.trim()) return;
    
    setIsSending(true);
    try {
      const res = await fetch(`${API_BASE}/send-message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conditions: messageConditions, message: messageText })
      });
      if (res.ok) {
        showNotification("Message sending started in background");
        setMessageText('');
      } else {
        throw new Error("Failed");
      }
    } catch (error) {
      console.error(error);
      showNotification("Failed to send message");
    } finally {
      setIsSending(false);
    }
  };

  const toggleUserSelection = (chatId) => {
    const newSet = new Set(selectedUsers);
    if (newSet.has(chatId)) newSet.delete(chatId);
    else newSet.add(chatId);
    setSelectedUsers(newSet);
  };

  const toggleAllUsers = () => {
    if (selectedUsers.size === users.length) {
      setSelectedUsers(new Set());
    } else {
      setSelectedUsers(new Set(users.map(u => u.chat_id)));
    }
  };

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/groups`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newGroupName })
      });
      if (res.ok) {
        showNotification("Custom group created");
        setNewGroupName('');
        fetchData();
      } else {
        showNotification("Failed or group exists");
      }
    } catch (error) {
      showNotification("Error creating group");
    }
  };

  const handleAddToGroup = async () => {
    if (!selectedGroupId || selectedUsers.size === 0) return;
    try {
      const res = await fetch(`${API_BASE}/groups/${selectedGroupId}/add-users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_ids: Array.from(selectedUsers) })
      });
      if (res.ok) {
        showNotification(`Added ${selectedUsers.size} users to group`);
        setSelectedUsers(new Set());
        fetchData();
      }
    } catch (error) {
      showNotification("Error adding to group");
    }
  };

  const colors = ['#BA00FF', '#CC50FF', '#450087', '#9333ea', '#7c3aed', '#a855f7', '#d946ef', '#c026d3'];

  const getCategoryOptions = () => {
    if (!chartData.length) return [];
    return chartData.map(c => c.category);
  };

  const userAgeData = useMemo(() => {
    const groups = { '<18': 0, '18-24': 0, '25-34': 0, '35+': 0, 'Unknown': 0 };
    users.forEach(u => {
      const age = parseInt(u.age);
      if (isNaN(age)) groups['Unknown']++;
      else if (age < 18) groups['<18']++;
      else if (age <= 24) groups['18-24']++;
      else if (age <= 34) groups['25-34']++;
      else groups['35+']++;
    });
    return Object.entries(groups).map(([name, value]) => ({ name, value })).filter(d => d.value > 0);
  }, [users]);

  const userTypeData = useMemo(() => {
    const premium = users.filter(u => u.is_premium).length;
    const standard = users.length - premium;
    return [
      { name: 'Premium Users', value: premium },
      { name: 'Standard Users', value: standard }
    ].filter(d => d.value > 0);
  }, [users]);

  const userJobTypeData = useMemo(() => {
    const counts = {};
    users.forEach(u => {
      (u.job_types || []).forEach(jt => {
        counts[jt] = (counts[jt] || 0) + 1;
      });
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value })).sort((a,b) => b.value - a.value).slice(0, 5);
  }, [users]);

  if (loading && !stats) {
    return (
      <div className="dashboard-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div className="loader"></div>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          {/* PLACE YOUR LOGO HERE: dashboard/src/assets/logo.png */}
          <img src="/logo.png" alt="SiraHub" style={{ height: '32px', display: 'none' }} id="sidebarLogo" onError={(e) => e.target.style.display='none'} />
          <Activity color="#BA00FF" size={28} />
          SiraHub
        </div>
        
        <div className="nav-menu">
          <div 
            className={`nav-item ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            <LayoutDashboard size={20} />
            Overview
          </div>
          <div 
            className={`nav-item ${activeTab === 'users' ? 'active' : ''}`}
            onClick={() => setActiveTab('users')}
          >
            <Users size={20} />
            Users
          </div>
          <div 
            className={`nav-item ${activeTab === 'jobs' ? 'active' : ''}`}
            onClick={() => setActiveTab('jobs')}
          >
            <Briefcase size={20} />
            Jobs
          </div>
          <div 
            className={`nav-item ${activeTab === 'messages' ? 'active' : ''}`}
            onClick={() => setActiveTab('messages')}
          >
            <MessageSquare size={20} />
            Broadcast
          </div>
          <div 
            className={`nav-item ${activeTab === 'scraper' ? 'active' : ''}`}
            onClick={() => setActiveTab('scraper')}
          >
            <Settings size={20} />
            Scraper Settings
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <div className="header">
          <h1>
            {activeTab === 'overview' && 'SiraHub Overview'}
            {activeTab === 'users' && 'User Management'}
            {activeTab === 'jobs' && 'Scraped Jobs'}
            {activeTab === 'messages' && 'Broadcast Messages'}
            {activeTab === 'scraper' && 'Scraper Settings'}
          </h1>
          <p>Control center for SiraHub Telegram bot</p>
        </div>

        {activeTab === 'overview' && (
          <>
            <div className="stats-grid">
              <div className="glass-card stat-card animate-fade-in delay-1">
                <div className="stat-icon"><Briefcase size={24} /></div>
                <div className="stat-info">
                  <div className="stat-value">{stats?.total_jobs || 0}</div>
                  <div className="stat-title">Total Jobs</div>
                </div>
              </div>
              <div className="glass-card stat-card animate-fade-in delay-2">
                <div className="stat-icon"><Clock size={24} /></div>
                <div className="stat-info">
                  <div className="stat-value">{stats?.jobs_today || 0}</div>
                  <div className="stat-title">New Today</div>
                </div>
              </div>
              <div className="glass-card stat-card animate-fade-in delay-3">
                <div className="stat-icon"><Users size={24} /></div>
                <div className="stat-info">
                  <div className="stat-value">{stats?.active_subscribers || 0}</div>
                  <div className="stat-title">Active Users</div>
                </div>
              </div>
              <div className="glass-card stat-card animate-fade-in delay-4">
                <div className="stat-icon"><Star size={24} /></div>
                <div className="stat-info">
                  <div className="stat-value">{stats?.premium_users || 0}</div>
                  <div className="stat-title">Premium</div>
                </div>
              </div>
            </div>

            <div className="dashboard-grid">
              <div className="glass-card animate-fade-in delay-1">
                <h2 className="card-title">Jobs by Category</h2>
                <div style={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                      <XAxis dataKey="category" stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
                      <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}
                        itemStyle={{ color: '#fff' }}
                      />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {chartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              
              <div className="glass-card animate-fade-in delay-2">
                <h2 className="card-title">Quick Actions</h2>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <button className="btn" onClick={() => setActiveTab('messages')}>
                    <Send size={18} /> Send Broadcast
                  </button>
                  <button className="btn" style={{ background: 'rgba(255,255,255,0.05)', color: 'white' }} onClick={fetchData}>
                    Refresh Data
                  </button>
                </div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
              <div className="glass-card animate-fade-in delay-3">
                <h2 className="card-title">User Types</h2>
                <div style={{ height: 250 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={userTypeData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={80}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {userTypeData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={index === 0 ? '#f59e0b' : '#3b82f6'} />
                        ))}
                      </Pie>
                      <Tooltip 
                        contentStyle={{ backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}
                        itemStyle={{ color: '#fff' }}
                      />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="glass-card animate-fade-in delay-4">
                <h2 className="card-title">Top Job Type Preferences</h2>
                <div style={{ height: 250 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={userJobTypeData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" horizontal={false} />
                      <XAxis type="number" stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
                      <YAxis dataKey="name" type="category" stroke="#94a3b8" tick={{ fill: '#94a3b8' }} width={80} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}
                        itemStyle={{ color: '#fff' }}
                      />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {userJobTypeData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={colors[(index + 3) % colors.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {sourceData.length > 0 && (
              <div className="glass-card animate-fade-in delay-1" style={{ marginBottom: '2rem' }}>
                <h2 className="card-title">Jobs by Source Platform</h2>
                <div style={{ height: 280 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={sourceData} cx="50%" cy="50%" innerRadius={60} outerRadius={95} paddingAngle={4} dataKey="value" label={({name, percent}) => `${name} ${(percent*100).toFixed(0)}%`}>
                        {sourceData.map((entry, index) => (
                          <Cell key={`src-${index}`} fill={['#3b82f6','#8b5cf6','#10b981','#f59e0b','#ec4899'][index % 5]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }} itemStyle={{ color: '#fff' }} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === 'users' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="glass-card animate-fade-in delay-1">
              <h2 className="card-title">User Demographics (Age)</h2>
              <div style={{ height: 250 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={userAgeData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                    <XAxis dataKey="name" stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
                    <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}
                      itemStyle={{ color: '#fff' }}
                    />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {userAgeData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="glass-card animate-fade-in delay-2">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '1rem' }}>
                <h2 className="card-title" style={{ margin: 0 }}><UserCheck size={20} /> Detailed User Activity</h2>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  <input 
                    type="text" 
                    placeholder="New Group Name" 
                    className="form-select" 
                    style={{ width: '150px', padding: '0.5rem' }}
                    value={newGroupName}
                    onChange={(e) => setNewGroupName(e.target.value)}
                  />
                  <button className="btn" style={{ padding: '0.5rem 1rem' }} onClick={handleCreateGroup}>Create Group</button>
                  
                  <span style={{ color: 'var(--text-secondary)', margin: '0 0.5rem' }}>|</span>
                  
                  <select 
                    className="form-select" 
                    style={{ width: '150px', padding: '0.5rem' }}
                    value={selectedGroupId}
                    onChange={(e) => setSelectedGroupId(e.target.value)}
                  >
                    <option value="">Select Group...</option>
                    {customGroups.map(g => (
                      <option key={g.id} value={g.id}>{g.name}</option>
                    ))}
                  </select>
                  <button 
                    className="btn" 
                    style={{ padding: '0.5rem 1rem' }} 
                    onClick={handleAddToGroup}
                    disabled={selectedUsers.size === 0 || !selectedGroupId}
                  >
                    Add Selected ({selectedUsers.size})
                  </button>
                </div>
              </div>
              <div className="table-container">
                <table className="users-table">
                  <thead>
                    <tr>
                      <th style={{ width: '40px' }}>
                        <input type="checkbox" checked={users.length > 0 && selectedUsers.size === users.length} onChange={toggleAllUsers} />
                      </th>
                      <th>User</th>
                      <th>Status</th>
                      <th>Type</th>
                      <th>Age</th>
                      <th>Preferences</th>
                      <th>Jobs Sent (Today)</th>
                      <th>Joined</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(user => (
                      <tr key={user.chat_id} className={selectedUsers.has(user.chat_id) ? 'selected-row' : ''}>
                        <td>
                          <input type="checkbox" checked={selectedUsers.has(user.chat_id)} onChange={() => toggleUserSelection(user.chat_id)} />
                        </td>
                        <td>
                          <div style={{ fontWeight: 500 }}>{user.first_name || 'Unknown'}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>@{user.username || 'No username'}</div>
                        </td>
                        <td>
                          <span className={`badge ${user.active ? 'active' : 'inactive'}`}>
                            {user.active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${user.is_premium ? 'premium' : 'standard'}`}>
                            {user.is_premium ? 'Premium' : 'Standard'}
                          </span>
                        </td>
                        <td>{user.age || 'N/A'}</td>
                        <td>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            {(user.job_categories || []).map((cat, i) => (
                              <span key={`cat-${i}`} style={{ fontSize: '0.7rem', background: 'rgba(59, 130, 246, 0.2)', color: '#60a5fa', padding: '2px 6px', borderRadius: '4px' }}>
                                {cat.split(' ').pop()}
                              </span>
                            ))}
                            {(user.job_types || []).map((type, i) => (
                              <span key={`type-${i}`} style={{ fontSize: '0.7rem', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', padding: '2px 6px', borderRadius: '4px' }}>
                                {type}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td>{user.jobs_sent_today || 0}</td>
                        <td style={{ fontSize: '0.875rem' }}>
                          {new Date(user.joined_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                    {users.length === 0 && (
                      <tr>
                        <td colSpan="8" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
                          No users found
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'jobs' && (
          <div className="glass-card animate-fade-in delay-1">
            <h2 className="card-title"><Briefcase size={20} /> Recent Jobs</h2>
            <div className="table-container">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Company</th>
                    <th>Location</th>
                    <th>Source</th>
                    <th>Scraped At</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map(job => (
                    <tr key={job.id}>
                      <td>
                        <div style={{ fontWeight: 500 }}>{job.title}</div>
                        <a href={job.url} target="_blank" rel="noreferrer" style={{ fontSize: '0.75rem', color: 'var(--accent-color)', textDecoration: 'none' }}>View Job ↗</a>
                      </td>
                      <td>{job.company || 'Unknown'}</td>
                      <td>{job.location || 'Unknown'}</td>
                      <td>
                        <span style={{ fontSize: '0.75rem', padding: '4px 8px', borderRadius: '4px',
                          background: job.source === 'telegram' ? 'rgba(139,92,246,0.2)' : 'rgba(59,130,246,0.2)',
                          color: job.source === 'telegram' ? '#a78bfa' : '#60a5fa' }}>
                          {job.source === 'telegram' ? '📡 Telegram' : '🌐 Hahu Jobs'}
                        </span>
                      </td>
                      <td style={{ fontSize: '0.875rem' }}>
                        {new Date(job.scraped_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                  {jobs.length === 0 && (
                    <tr>
                      <td colSpan="5" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
                        No jobs found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'messages' && (
          <div className="glass-card animate-fade-in delay-1" style={{ maxWidth: '600px' }}>
            <h2 className="card-title"><MessageSquare size={20} /> Broadcast Message</h2>
            <form onSubmit={handleSendMessage}>
              <div className="form-group" style={{ marginBottom: '1rem', paddingBottom: '1rem', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                <label className="form-label">Target Custom Group (Overrides filters below)</label>
                <select 
                  className="form-select"
                  value={messageConditions.custom_group_id || ''}
                  onChange={(e) => setMessageConditions({...messageConditions, custom_group_id: e.target.value ? parseInt(e.target.value) : null})}
                >
                  <option value="">None (Use filters below)</option>
                  {customGroups.map(g => (
                    <option key={g.id} value={g.id}>{g.name} ({g.member_count} users)</option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', opacity: messageConditions.custom_group_id ? 0.4 : 1, pointerEvents: messageConditions.custom_group_id ? 'none' : 'auto' }}>
                <div className="form-group">
                  <label className="form-label">Access Type</label>
                  <select 
                    className="form-select"
                    value={messageConditions.access_type}
                    onChange={(e) => setMessageConditions({...messageConditions, access_type: e.target.value})}
                  >
                    <option value="all">All Users</option>
                    <option value="premium">Premium Only</option>
                    <option value="standard">Standard Only</option>
                  </select>
                </div>
                
                <div className="form-group">
                  <label className="form-label">Age Range</label>
                  <select 
                    className="form-select"
                    value={messageConditions.age_range}
                    onChange={(e) => setMessageConditions({...messageConditions, age_range: e.target.value})}
                  >
                    <option value="all">Any Age</option>
                    <option value="<18">Under 18</option>
                    <option value="18-24">18-24</option>
                    <option value="25-34">25-34</option>
                    <option value="35+">35 and older</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Job Type Preference</label>
                  <select 
                    className="form-select"
                    value={messageConditions.job_type}
                    onChange={(e) => setMessageConditions({...messageConditions, job_type: e.target.value})}
                  >
                    <option value="all">Any Type</option>
                    <option value="Remote">Remote</option>
                    <option value="Full-time">Full-time</option>
                    <option value="Part-time">Part-time</option>
                    <option value="Freelance">Freelance</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Category</label>
                  <select 
                    className="form-select"
                    value={messageConditions.category}
                    onChange={(e) => setMessageConditions({...messageConditions, category: e.target.value})}
                  >
                    <option value="all">Any Category</option>
                    {getCategoryOptions().map(cat => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>
              </div>
              
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Message Text (HTML supported)</label>
                <textarea 
                  className="form-textarea"
                  placeholder="Hello users, we have a new update! 🚀"
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  required
                ></textarea>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                  Supports basic HTML tags like &lt;b&gt;, &lt;i&gt;, &lt;a href="..."&gt;
                </div>
              </div>
              
              <button type="submit" className="btn" disabled={isSending}>
                {isSending ? <div className="loader" style={{ width: '16px', height: '16px', borderWidth: '2px' }}></div> : <Send size={18} />}
                {isSending ? 'Sending...' : 'Send Broadcast'}
              </button>
            </form>
          </div>
        )}

        {activeTab === 'scraper' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

            {/* Header action */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
              <button
                className="btn"
                onClick={handleTriggerScraper}
                disabled={scraperTriggering}
                style={{ background: 'linear-gradient(135deg,#f59e0b,#ef4444)' }}
              >
                <Zap size={16} />
                {scraperTriggering ? 'Triggering…' : 'Run Scraper Now'}
              </button>
            </div>

            <form onSubmit={handleSaveScraperConfig} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

              {/* General */}
              <div className="glass-card animate-fade-in delay-1">
                <h2 className="card-title"><Settings size={18}/> General</h2>
                <div className="form-group">
                  <label className="form-label">Scrape Interval (minutes)</label>
                  <input
                    type="number" min="1" max="1440"
                    className="form-select"
                    value={scraperCfg.scrape_interval_minutes}
                    onChange={e => setScraperCfg({...scraperCfg, scrape_interval_minutes: e.target.value})}
                  />
                  <div style={{ fontSize:'0.75rem', color:'var(--text-secondary)', marginTop:'0.4rem' }}>
                    Both the scraper and the bot notification cycle run every 5 minutes by default.
                  </div>
                </div>
              </div>

              {/* Web Scraper */}
              <div className="glass-card animate-fade-in delay-2">
                <h2 className="card-title"><Globe size={18}/> Web Scraper (Hahu Jobs)</h2>
                <div style={{ display:'flex', alignItems:'center', gap:'0.75rem', marginBottom:'1rem' }}>
                  <label className="form-label" style={{margin:0}}>Enabled</label>
                  <input
                    type="checkbox"
                    checked={scraperCfg.web_enabled === '1'}
                    onChange={e => setScraperCfg({...scraperCfg, web_enabled: e.target.checked ? '1' : '0'})}
                    style={{width:'18px',height:'18px',cursor:'pointer'}}
                  />
                </div>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'1rem', opacity: scraperCfg.web_enabled==='1'?1:0.4, pointerEvents: scraperCfg.web_enabled==='1'?'auto':'none' }}>
                  <div className="form-group" style={{gridColumn:'1/-1'}}>
                    <label className="form-label">Base URL</label>
                    <input
                      type="text" className="form-select"
                      value={scraperCfg.web_base_url}
                      onChange={e => setScraperCfg({...scraperCfg, web_base_url: e.target.value})}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Start Page</label>
                    <input type="number" min="1" className="form-select"
                      value={scraperCfg.web_start_page}
                      onChange={e => setScraperCfg({...scraperCfg, web_start_page: e.target.value})}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">End Page</label>
                    <input type="number" min="1" className="form-select"
                      value={scraperCfg.web_end_page}
                      onChange={e => setScraperCfg({...scraperCfg, web_end_page: e.target.value})}
                    />
                  </div>
                </div>
              </div>

              {/* Telegram Scraper */}
              <div className="glass-card animate-fade-in delay-3">
                <h2 className="card-title"><Radio size={18}/> Telegram Channel Scraper</h2>
                <div style={{ display:'flex', alignItems:'center', gap:'0.75rem', marginBottom:'1rem' }}>
                  <label className="form-label" style={{margin:0}}>Enabled</label>
                  <input
                    type="checkbox"
                    checked={scraperCfg.tg_enabled === '1'}
                    onChange={e => setScraperCfg({...scraperCfg, tg_enabled: e.target.checked ? '1' : '0'})}
                    style={{width:'18px',height:'18px',cursor:'pointer'}}
                  />
                </div>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'1rem', opacity: scraperCfg.tg_enabled==='1'?1:0.4, pointerEvents: scraperCfg.tg_enabled==='1'?'auto':'none' }}>
                  <div className="form-group" style={{gridColumn:'1/-1'}}>
                    <label className="form-label">Channels (comma-separated, no @)</label>
                    <input type="text" className="form-select"
                      placeholder="freelance_ethio, another_channel"
                      value={scraperCfg.tg_channels}
                      onChange={e => setScraperCfg({...scraperCfg, tg_channels: e.target.value})}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Messages to Fetch per Channel</label>
                    <input type="number" min="5" max="200" className="form-select"
                      value={scraperCfg.tg_message_limit}
                      onChange={e => setScraperCfg({...scraperCfg, tg_message_limit: e.target.value})}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Session Name</label>
                    <input type="text" className="form-select"
                      value={scraperCfg.tg_session}
                      onChange={e => setScraperCfg({...scraperCfg, tg_session: e.target.value})}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">API ID (my.telegram.org)</label>
                    <input type="text" className="form-select"
                      value={scraperCfg.tg_api_id}
                      onChange={e => setScraperCfg({...scraperCfg, tg_api_id: e.target.value})}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">API Hash</label>
                    <input type="password" className="form-select"
                      value={scraperCfg.tg_api_hash}
                      onChange={e => setScraperCfg({...scraperCfg, tg_api_hash: e.target.value})}
                    />
                  </div>
                </div>
              </div>

              <button type="submit" className="btn" disabled={scraperSaving}
                style={{ alignSelf:'flex-start' }}>
                {scraperSaving
                  ? <div className="loader" style={{width:'16px',height:'16px',borderWidth:'2px'}}></div>
                  : <Settings size={16}/>}
                {scraperSaving ? 'Saving…' : 'Save Settings'}
              </button>
            </form>
          </div>
        )}
      </main>

      {notification && (
        <div className="notification">
          <UserCheck size={18} />
          {notification}
        </div>
      )}
    </div>
  );
}

export default App;
