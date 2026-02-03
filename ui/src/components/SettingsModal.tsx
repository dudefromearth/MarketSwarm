// src/components/SettingsModal.tsx
import { useState, useEffect, useCallback } from 'react';
import { usePath } from '../contexts/PathContext';

const JOURNAL_API = 'http://localhost:3002';

interface Symbol {
  symbol: string;
  name: string;
  asset_type: string;
  multiplier: number;
  enabled: boolean;
  is_default: boolean;
}

interface SettingsModalProps {
  onClose: () => void;
}

type SettingsTab = 'profile' | 'symbols' | 'tags' | 'trading' | 'user' | 'display' | 'alerts';

interface Tag {
  id: string;
  user_id: number;
  name: string;
  description: string | null;
  is_retired: boolean;
  is_example: boolean;
  usage_count: number;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

interface Profile {
  display_name: string;
  email: string;
  issuer: string;
  wp_user_id: number;
  is_admin: boolean;
  roles: string[];
  subscription_tier: string | null;
  last_login_at: string;
  created_at: string;
}
type AssetTypeFilter = 'all' | 'index_option' | 'etf_option' | 'future' | 'stock';

export default function SettingsModal({ onClose }: SettingsModalProps) {
  const { tourCompleted, resetTour } = usePath();
  const [activeTab, setActiveTab] = useState<SettingsTab>('profile');
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [loading, setLoading] = useState(true);
  const [assetFilter, setAssetFilter] = useState<AssetTypeFilter>('all');
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  // New symbol form
  const [showAddSymbol, setShowAddSymbol] = useState(false);
  const [newSymbol, setNewSymbol] = useState({
    symbol: '',
    name: '',
    asset_type: 'stock',
    multiplier: 100
  });
  const [addError, setAddError] = useState<string | null>(null);

  // Trading settings
  const [tradingSettings, setTradingSettings] = useState<Record<string, any>>({});
  const [userSettings, setUserSettings] = useState<Record<string, any>>({});

  // Tags (Vocabulary System)
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagsLoading, setTagsLoading] = useState(true);
  const [tagsSortBy, setTagsSortBy] = useState<'recent' | 'alpha'>('recent');
  const [showRetiredTags, setShowRetiredTags] = useState(false);
  const [showAddTag, setShowAddTag] = useState(false);
  const [newTag, setNewTag] = useState({ name: '', description: '' });
  const [tagError, setTagError] = useState<string | null>(null);
  const [editingTagId, setEditingTagId] = useState<string | null>(null);
  const [editingTagData, setEditingTagData] = useState({ name: '', description: '' });

  const fetchSymbols = useCallback(async () => {
    try {
      const res = await fetch(`${JOURNAL_API}/api/symbols?include_disabled=true`);
      const data = await res.json();
      if (data.success) {
        setSymbols(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch symbols:', err);
    }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${JOURNAL_API}/api/settings`);
      const data = await res.json();
      if (data.success) {
        setTradingSettings(data.data.trading || {});
        setUserSettings(data.data.user || {});
      }
    } catch (err) {
      console.error('Failed to fetch settings:', err);
    }
  }, []);

  const fetchProfile = useCallback(async () => {
    setProfileLoading(true);
    try {
      const res = await fetch('/api/profile/me', { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setProfile(data);
      }
    } catch (err) {
      console.error('Failed to fetch profile:', err);
    } finally {
      setProfileLoading(false);
    }
  }, []);

  const fetchTags = useCallback(async () => {
    setTagsLoading(true);
    try {
      const res = await fetch(`${JOURNAL_API}/api/tags?include_retired=true`, {
        credentials: 'include'
      });
      const data = await res.json();
      if (data.success) {
        setTags(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch tags:', err);
    } finally {
      setTagsLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchSymbols(), fetchSettings(), fetchProfile(), fetchTags()]);
      setLoading(false);
    };
    loadData();
  }, [fetchSymbols, fetchSettings, fetchProfile, fetchTags]);

  const handleAddSymbol = async () => {
    setAddError(null);

    if (!newSymbol.symbol.trim()) {
      setAddError('Symbol is required');
      return;
    }
    if (!newSymbol.name.trim()) {
      setAddError('Name is required');
      return;
    }

    try {
      const res = await fetch(`${JOURNAL_API}/api/symbols`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSymbol)
      });
      const data = await res.json();

      if (data.success) {
        setSymbols([...symbols, data.data]);
        setShowAddSymbol(false);
        setNewSymbol({ symbol: '', name: '', asset_type: 'stock', multiplier: 100 });
      } else {
        setAddError(data.error || 'Failed to add symbol');
      }
    } catch (err) {
      setAddError('Failed to add symbol');
    }
  };

  const handleToggleSymbol = async (symbol: string, enabled: boolean) => {
    try {
      await fetch(`${JOURNAL_API}/api/symbols/${symbol}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled })
      });
      setSymbols(symbols.map(s =>
        s.symbol === symbol ? { ...s, enabled } : s
      ));
    } catch (err) {
      console.error('Failed to toggle symbol:', err);
    }
  };

  const handleDeleteSymbol = async (symbol: string) => {
    if (!confirm(`Delete symbol ${symbol}?`)) return;

    try {
      const res = await fetch(`${JOURNAL_API}/api/symbols/${symbol}`, {
        method: 'DELETE'
      });
      const data = await res.json();

      if (data.success) {
        setSymbols(symbols.filter(s => s.symbol !== symbol));
      }
    } catch (err) {
      console.error('Failed to delete symbol:', err);
    }
  };

  const handleSaveSetting = async (key: string, value: any, category: string) => {
    try {
      await fetch(`${JOURNAL_API}/api/settings/${key}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value, category })
      });

      if (category === 'trading') {
        setTradingSettings({ ...tradingSettings, [key]: value });
      } else if (category === 'user') {
        setUserSettings({ ...userSettings, [key]: value });
      }
    } catch (err) {
      console.error('Failed to save setting:', err);
    }
  };

  // Tag management handlers
  const handleAddTag = async () => {
    setTagError(null);
    if (!newTag.name.trim()) {
      setTagError('Tag name is required');
      return;
    }

    try {
      const res = await fetch(`${JOURNAL_API}/api/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: newTag.name.trim(),
          description: newTag.description.trim() || null
        })
      });
      const data = await res.json();

      if (data.success) {
        setTags([data.data, ...tags]);
        setShowAddTag(false);
        setNewTag({ name: '', description: '' });
      } else {
        setTagError(data.error || 'Failed to add tag');
      }
    } catch (err) {
      setTagError('Failed to add tag');
    }
  };

  const handleUpdateTag = async (tagId: string) => {
    setTagError(null);
    if (!editingTagData.name.trim()) {
      setTagError('Tag name is required');
      return;
    }

    try {
      const res = await fetch(`${JOURNAL_API}/api/tags/${tagId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: editingTagData.name.trim(),
          description: editingTagData.description.trim() || null
        })
      });
      const data = await res.json();

      if (data.success) {
        setTags(tags.map(t => t.id === tagId ? data.data : t));
        setEditingTagId(null);
      } else {
        setTagError(data.error || 'Failed to update tag');
      }
    } catch (err) {
      setTagError('Failed to update tag');
    }
  };

  const handleRetireTag = async (tagId: string) => {
    try {
      const res = await fetch(`${JOURNAL_API}/api/tags/${tagId}/retire`, {
        method: 'PUT',
        credentials: 'include'
      });
      const data = await res.json();

      if (data.success) {
        setTags(tags.map(t => t.id === tagId ? data.data : t));
      }
    } catch (err) {
      console.error('Failed to retire tag:', err);
    }
  };

  const handleRestoreTag = async (tagId: string) => {
    try {
      const res = await fetch(`${JOURNAL_API}/api/tags/${tagId}/restore`, {
        method: 'PUT',
        credentials: 'include'
      });
      const data = await res.json();

      if (data.success) {
        setTags(tags.map(t => t.id === tagId ? data.data : t));
      }
    } catch (err) {
      console.error('Failed to restore tag:', err);
    }
  };

  const handleDeleteTag = async (tag: Tag) => {
    if (tag.usage_count > 0) {
      alert('Cannot delete a tag that has been used. Retire it instead.');
      return;
    }
    if (!confirm(`Delete tag "${tag.name}"?`)) return;

    try {
      const res = await fetch(`${JOURNAL_API}/api/tags/${tag.id}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      const data = await res.json();

      if (data.success) {
        setTags(tags.filter(t => t.id !== tag.id));
      }
    } catch (err) {
      console.error('Failed to delete tag:', err);
    }
  };

  const startEditingTag = (tag: Tag) => {
    setEditingTagId(tag.id);
    setEditingTagData({ name: tag.name, description: tag.description || '' });
    setTagError(null);
  };

  const cancelEditingTag = () => {
    setEditingTagId(null);
    setEditingTagData({ name: '', description: '' });
    setTagError(null);
  };

  // Filter and sort tags
  const activeTags = tags.filter(t => !t.is_retired);
  const retiredTags = tags.filter(t => t.is_retired);

  const sortedActiveTags = [...activeTags].sort((a, b) => {
    if (tagsSortBy === 'alpha') {
      return a.name.localeCompare(b.name);
    }
    // Sort by most recently used, then by created date
    if (a.last_used_at && b.last_used_at) {
      return new Date(b.last_used_at).getTime() - new Date(a.last_used_at).getTime();
    }
    if (a.last_used_at) return -1;
    if (b.last_used_at) return 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const filteredSymbols = symbols.filter(s =>
    assetFilter === 'all' || s.asset_type === assetFilter
  );

  const getAssetTypeLabel = (type: string) => {
    switch (type) {
      case 'index_option': return 'Index';
      case 'etf_option': return 'ETF';
      case 'future': return 'Future';
      case 'stock': return 'Stock';
      default: return type;
    }
  };

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="btn-close" onClick={onClose}>&times;</button>
        </div>

        <div className="settings-tabs">
          <button
            className={`settings-tab ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('profile')}
          >
            Profile
          </button>
          <button
            className={`settings-tab ${activeTab === 'symbols' ? 'active' : ''}`}
            onClick={() => setActiveTab('symbols')}
          >
            Symbols
          </button>
          <button
            className={`settings-tab ${activeTab === 'tags' ? 'active' : ''}`}
            onClick={() => setActiveTab('tags')}
          >
            Tags
          </button>
          <button
            className={`settings-tab ${activeTab === 'trading' ? 'active' : ''}`}
            onClick={() => setActiveTab('trading')}
          >
            Trading
          </button>
          <button
            className={`settings-tab ${activeTab === 'user' ? 'active' : ''}`}
            onClick={() => setActiveTab('user')}
          >
            User
          </button>
          <button
            className={`settings-tab ${activeTab === 'display' ? 'active' : ''}`}
            onClick={() => setActiveTab('display')}
          >
            Display
          </button>
          <button
            className={`settings-tab ${activeTab === 'alerts' ? 'active' : ''}`}
            onClick={() => setActiveTab('alerts')}
          >
            Alerts
          </button>
        </div>

        <div className="settings-content">
          {loading ? (
            <div className="settings-loading">Loading...</div>
          ) : (
            <>
              {activeTab === 'profile' && (
                <div className="settings-profile">
                  {profileLoading ? (
                    <div className="settings-loading">Loading profile...</div>
                  ) : profile ? (
                    <>
                      <div className="profile-header">
                        <div className="profile-avatar">
                          {profile.display_name.charAt(0).toUpperCase()}
                        </div>
                        <div className="profile-identity">
                          <h3 className="profile-name">{profile.display_name}</h3>
                          <span className="profile-email">{profile.email}</span>
                        </div>
                      </div>

                      <div className="settings-group">
                        <h4>Account</h4>
                        <div className="profile-info-row">
                          <span className="profile-label">Platform</span>
                          <span className="profile-value">{profile.issuer}</span>
                        </div>
                        <div className="profile-info-row">
                          <span className="profile-label">Subscription</span>
                          <span className={`profile-value subscription-tier ${profile.subscription_tier || 'free'}`}>
                            {profile.subscription_tier || 'Free'}
                          </span>
                        </div>
                        {profile.is_admin && (
                          <div className="profile-info-row">
                            <span className="profile-label">Role</span>
                            <span className="profile-value admin-badge">Administrator</span>
                          </div>
                        )}
                      </div>

                      <div className="settings-group">
                        <h4>Activity</h4>
                        <div className="profile-info-row">
                          <span className="profile-label">Member Since</span>
                          <span className="profile-value">
                            {new Date(profile.created_at).toLocaleDateString('en-US', {
                              year: 'numeric',
                              month: 'long',
                              day: 'numeric'
                            })}
                          </span>
                        </div>
                        <div className="profile-info-row">
                          <span className="profile-label">Last Login</span>
                          <span className="profile-value">
                            {new Date(profile.last_login_at).toLocaleDateString('en-US', {
                              year: 'numeric',
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit'
                            })}
                          </span>
                        </div>
                      </div>

                      <div className="profile-actions">
                        <button
                          className="btn-logout"
                          onClick={() => {
                            window.location.href = '/api/logout';
                          }}
                        >
                          Sign Out
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="profile-error">
                      <p>Unable to load profile</p>
                      <button onClick={fetchProfile}>Retry</button>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'symbols' && (
                <div className="settings-symbols">
                  <div className="symbols-toolbar">
                    <div className="asset-filter">
                      <label>Filter:</label>
                      <select
                        value={assetFilter}
                        onChange={e => setAssetFilter(e.target.value as AssetTypeFilter)}
                      >
                        <option value="all">All Types</option>
                        <option value="index_option">Index Options</option>
                        <option value="etf_option">ETF Options</option>
                        <option value="future">Futures</option>
                        <option value="stock">Stocks</option>
                      </select>
                    </div>
                    <button
                      className="btn-add-symbol"
                      onClick={() => setShowAddSymbol(true)}
                    >
                      + Add Symbol
                    </button>
                  </div>

                  {showAddSymbol && (
                    <div className="add-symbol-form">
                      <h4>Add Custom Symbol</h4>
                      <div className="form-row">
                        <div className="form-group">
                          <label>Symbol</label>
                          <input
                            type="text"
                            value={newSymbol.symbol}
                            onChange={e => setNewSymbol({ ...newSymbol, symbol: e.target.value.toUpperCase() })}
                            placeholder="AAPL"
                            maxLength={10}
                          />
                        </div>
                        <div className="form-group">
                          <label>Name</label>
                          <input
                            type="text"
                            value={newSymbol.name}
                            onChange={e => setNewSymbol({ ...newSymbol, name: e.target.value })}
                            placeholder="Apple Inc"
                          />
                        </div>
                      </div>
                      <div className="form-row">
                        <div className="form-group">
                          <label>Asset Type</label>
                          <select
                            value={newSymbol.asset_type}
                            onChange={e => setNewSymbol({ ...newSymbol, asset_type: e.target.value })}
                          >
                            <option value="stock">Stock</option>
                            <option value="etf_option">ETF Option</option>
                            <option value="index_option">Index Option</option>
                            <option value="future">Future</option>
                          </select>
                        </div>
                        <div className="form-group">
                          <label>Multiplier</label>
                          <input
                            type="number"
                            value={newSymbol.multiplier}
                            onChange={e => setNewSymbol({ ...newSymbol, multiplier: parseInt(e.target.value) || 100 })}
                            min={1}
                          />
                        </div>
                      </div>
                      {addError && <div className="form-error">{addError}</div>}
                      <div className="form-actions">
                        <button className="btn-cancel" onClick={() => setShowAddSymbol(false)}>
                          Cancel
                        </button>
                        <button className="btn-save" onClick={handleAddSymbol}>
                          Add Symbol
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="symbols-table-container">
                    <table className="symbols-table">
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th>Name</th>
                          <th>Type</th>
                          <th>Multiplier</th>
                          <th>Enabled</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSymbols.map(sym => (
                          <tr key={sym.symbol} className={!sym.enabled ? 'disabled' : ''}>
                            <td className="symbol-ticker">{sym.symbol}</td>
                            <td className="symbol-name">{sym.name}</td>
                            <td className="symbol-type">
                              <span className={`type-badge ${sym.asset_type}`}>
                                {getAssetTypeLabel(sym.asset_type)}
                              </span>
                            </td>
                            <td className="symbol-multiplier">{sym.multiplier}</td>
                            <td className="symbol-enabled">
                              <input
                                type="checkbox"
                                checked={sym.enabled}
                                onChange={e => handleToggleSymbol(sym.symbol, e.target.checked)}
                              />
                            </td>
                            <td className="symbol-actions">
                              {!sym.is_default && (
                                <button
                                  className="btn-delete-symbol"
                                  onClick={() => handleDeleteSymbol(sym.symbol)}
                                  title="Delete symbol"
                                >
                                  &times;
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="symbols-summary">
                    {filteredSymbols.length} symbols ({symbols.filter(s => s.enabled).length} enabled)
                  </div>
                </div>
              )}

              {activeTab === 'tags' && (
                <div className="settings-tags">
                  <div className="tags-intro">
                    <p><strong>Example tags</strong> — common patterns professionals notice.<br />Edit, rename, or delete freely.</p>
                  </div>

                  <div className="tags-toolbar">
                    <div className="tags-sort">
                      <label>Sort:</label>
                      <select
                        value={tagsSortBy}
                        onChange={e => setTagsSortBy(e.target.value as 'recent' | 'alpha')}
                      >
                        <option value="recent">Most Recent</option>
                        <option value="alpha">Alphabetical</option>
                      </select>
                    </div>
                    <button
                      className="btn-add-tag"
                      onClick={() => setShowAddTag(true)}
                    >
                      + New Tag
                    </button>
                  </div>

                  {showAddTag && (
                    <div className="add-tag-form">
                      <h4>Create Tag</h4>
                      <div className="form-group">
                        <label>Name</label>
                        <input
                          type="text"
                          value={newTag.name}
                          onChange={e => setNewTag({ ...newTag, name: e.target.value })}
                          placeholder="e.g., overtrading"
                          maxLength={100}
                          autoFocus
                        />
                      </div>
                      <div className="form-group">
                        <label>Description (optional)</label>
                        <input
                          type="text"
                          value={newTag.description}
                          onChange={e => setNewTag({ ...newTag, description: e.target.value })}
                          placeholder="What this tag means to you"
                        />
                      </div>
                      {tagError && <div className="form-error">{tagError}</div>}
                      <div className="form-actions">
                        <button className="btn-cancel" onClick={() => { setShowAddTag(false); setNewTag({ name: '', description: '' }); setTagError(null); }}>
                          Cancel
                        </button>
                        <button className="btn-save" onClick={handleAddTag}>
                          Create
                        </button>
                      </div>
                    </div>
                  )}

                  {tagsLoading ? (
                    <div className="settings-loading">Loading tags...</div>
                  ) : (
                    <>
                      <div className="tags-list">
                        {sortedActiveTags.length === 0 ? (
                          <div className="tags-empty">
                            <p>No tags yet. Create your first tag to start building your vocabulary.</p>
                          </div>
                        ) : (
                          sortedActiveTags.map(tag => (
                            <div key={tag.id} className={`tag-item ${tag.is_example ? 'example' : ''}`}>
                              {editingTagId === tag.id ? (
                                <div className="tag-edit-form">
                                  <div className="form-group">
                                    <input
                                      type="text"
                                      value={editingTagData.name}
                                      onChange={e => setEditingTagData({ ...editingTagData, name: e.target.value })}
                                      placeholder="Tag name"
                                      autoFocus
                                    />
                                  </div>
                                  <div className="form-group">
                                    <input
                                      type="text"
                                      value={editingTagData.description}
                                      onChange={e => setEditingTagData({ ...editingTagData, description: e.target.value })}
                                      placeholder="Description (optional)"
                                    />
                                  </div>
                                  {tagError && <div className="form-error">{tagError}</div>}
                                  <div className="tag-edit-actions">
                                    <button className="btn-cancel" onClick={cancelEditingTag}>Cancel</button>
                                    <button className="btn-save" onClick={() => handleUpdateTag(tag.id)}>Save</button>
                                  </div>
                                </div>
                              ) : (
                                <>
                                  <div className="tag-info">
                                    <span className="tag-name">{tag.name}</span>
                                    {tag.is_example && <span className="tag-example-badge">(example)</span>}
                                    <span className="tag-usage">{tag.usage_count} uses</span>
                                  </div>
                                  {tag.description && (
                                    <div className="tag-description">{tag.description}</div>
                                  )}
                                  <div className="tag-actions">
                                    <button
                                      className="btn-edit-tag"
                                      onClick={() => startEditingTag(tag)}
                                      title="Edit tag"
                                    >
                                      Edit
                                    </button>
                                    <button
                                      className="btn-retire-tag"
                                      onClick={() => handleRetireTag(tag.id)}
                                      title="Retire tag"
                                    >
                                      Retire
                                    </button>
                                    {tag.usage_count === 0 && (
                                      <button
                                        className="btn-delete-tag"
                                        onClick={() => handleDeleteTag(tag)}
                                        title="Delete tag"
                                      >
                                        Delete
                                      </button>
                                    )}
                                  </div>
                                </>
                              )}
                            </div>
                          ))
                        )}
                      </div>

                      {retiredTags.length > 0 && (
                        <div className="retired-tags-section">
                          <button
                            className="retired-tags-toggle"
                            onClick={() => setShowRetiredTags(!showRetiredTags)}
                          >
                            <span className="collapse-icon">{showRetiredTags ? '▼' : '▶'}</span>
                            Retired Tags ({retiredTags.length})
                          </button>
                          {showRetiredTags && (
                            <>
                              <p className="retired-tags-hint">Retired tags remain attached to historical content but are hidden from suggestions.</p>
                              <div className="tags-list retired">
                                {retiredTags.map(tag => (
                                  <div key={tag.id} className="tag-item retired">
                                    <div className="tag-info">
                                      <span className="tag-name">{tag.name}</span>
                                      <span className="tag-usage">{tag.usage_count} uses</span>
                                    </div>
                                    {tag.description && (
                                      <div className="tag-description">{tag.description}</div>
                                    )}
                                    <div className="tag-actions">
                                      <button
                                        className="btn-restore-tag"
                                        onClick={() => handleRestoreTag(tag.id)}
                                        title="Restore tag"
                                      >
                                        Restore
                                      </button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                        </div>
                      )}

                      <div className="tags-summary">
                        {activeTags.length} active tag{activeTags.length !== 1 ? 's' : ''}
                        {retiredTags.length > 0 && ` · ${retiredTags.length} retired`}
                      </div>
                    </>
                  )}
                </div>
              )}

              {activeTab === 'trading' && (
                <div className="settings-trading">
                  <div className="settings-group">
                    <h4>Risk Management</h4>
                    <div className="setting-item">
                      <label>Default Risk per Trade ($)</label>
                      <input
                        type="number"
                        value={tradingSettings.default_risk_per_trade || ''}
                        onChange={e => handleSaveSetting('default_risk_per_trade', parseInt(e.target.value) || 0, 'trading')}
                        placeholder="500"
                      />
                      <span className="setting-hint">Used when no specific risk is set for a trade</span>
                    </div>
                    <div className="setting-item">
                      <label>Max Position Size</label>
                      <input
                        type="number"
                        value={tradingSettings.max_position_size || ''}
                        onChange={e => handleSaveSetting('max_position_size', parseInt(e.target.value) || 0, 'trading')}
                        placeholder="10"
                      />
                      <span className="setting-hint">Maximum contracts per position</span>
                    </div>
                    <div className="setting-item">
                      <label>Max Daily Loss ($)</label>
                      <input
                        type="number"
                        value={tradingSettings.max_daily_loss || ''}
                        onChange={e => handleSaveSetting('max_daily_loss', parseInt(e.target.value) || 0, 'trading')}
                        placeholder="1000"
                      />
                      <span className="setting-hint">Stop trading for the day after this loss</span>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'user' && (
                <div className="settings-user">
                  <div className="settings-group">
                    <h4>Profile</h4>
                    <div className="setting-item">
                      <label>Trading Style</label>
                      <select
                        value={userSettings.trading_style || ''}
                        onChange={e => handleSaveSetting('trading_style', e.target.value, 'user')}
                      >
                        <option value="">Select...</option>
                        <option value="convexity">Convexity / Asymmetric</option>
                        <option value="income">Income / Premium Selling</option>
                        <option value="directional">Directional</option>
                        <option value="scalping">Scalping</option>
                        <option value="swing">Swing Trading</option>
                      </select>
                      <span className="setting-hint">Helps AI tailor suggestions to your style</span>
                    </div>
                    <div className="setting-item">
                      <label>Experience Level</label>
                      <select
                        value={userSettings.experience_level || ''}
                        onChange={e => handleSaveSetting('experience_level', e.target.value, 'user')}
                      >
                        <option value="">Select...</option>
                        <option value="beginner">Beginner (0-2 years)</option>
                        <option value="intermediate">Intermediate (2-5 years)</option>
                        <option value="advanced">Advanced (5-10 years)</option>
                        <option value="expert">Expert (10+ years)</option>
                      </select>
                    </div>
                    <div className="setting-item">
                      <label>Preferred Instruments</label>
                      <input
                        type="text"
                        value={userSettings.preferred_instruments || ''}
                        onChange={e => handleSaveSetting('preferred_instruments', e.target.value, 'user')}
                        placeholder="SPX, ES, NDX"
                      />
                      <span className="setting-hint">Comma-separated list of symbols you trade most</span>
                    </div>
                  </div>

                  <div className="settings-group">
                    <h4>AI Interaction</h4>
                    <div className="setting-item">
                      <label>AI Commentary Style</label>
                      <select
                        value={userSettings.ai_style || ''}
                        onChange={e => handleSaveSetting('ai_style', e.target.value, 'user')}
                      >
                        <option value="">Select...</option>
                        <option value="concise">Concise - Just the facts</option>
                        <option value="detailed">Detailed - Full explanations</option>
                        <option value="educational">Educational - Teaching mode</option>
                        <option value="socratic">Socratic - Questions to guide</option>
                      </select>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'display' && (
                <div className="settings-display">
                  <div className="settings-group">
                    <h4>Path Indicator</h4>
                    <div className="setting-item">
                      <label>Welcome Tour</label>
                      <button
                        className="btn-reset-tour"
                        onClick={resetTour}
                        disabled={!tourCompleted}
                        style={{
                          padding: '6px 12px',
                          fontSize: '11px',
                          background: tourCompleted ? '#3b82f6' : '#444',
                          border: 'none',
                          borderRadius: '4px',
                          color: tourCompleted ? '#fff' : '#888',
                          cursor: tourCompleted ? 'pointer' : 'not-allowed',
                        }}
                      >
                        {tourCompleted ? 'Show Again' : 'Already Showing'}
                      </button>
                      <span className="setting-hint">Re-show the welcome tour explaining the 5-stage path</span>
                    </div>
                  </div>

                  <div className="settings-group">
                    <h4>Trade Log Display</h4>
                    <div className="setting-item">
                      <label>Default Page Size</label>
                      <select
                        value={userSettings.default_page_size || 25}
                        onChange={e => handleSaveSetting('default_page_size', parseInt(e.target.value), 'user')}
                      >
                        <option value={10}>10</option>
                        <option value={25}>25</option>
                        <option value={50}>50</option>
                      </select>
                    </div>
                    <div className="setting-item">
                      <label>Default Sort Order</label>
                      <select
                        value={userSettings.default_sort_order || 'recent'}
                        onChange={e => handleSaveSetting('default_sort_order', e.target.value, 'user')}
                      >
                        <option value="recent">Most Recent First</option>
                        <option value="oldest">Oldest First</option>
                      </select>
                    </div>
                  </div>

                  <div className="settings-group">
                    <h4>Charts</h4>
                    <div className="setting-item">
                      <label>Default Time Range</label>
                      <select
                        value={userSettings.default_time_range || 'ALL'}
                        onChange={e => handleSaveSetting('default_time_range', e.target.value, 'user')}
                      >
                        <option value="1M">1 Month</option>
                        <option value="3M">3 Months</option>
                        <option value="ALL">All Time</option>
                      </select>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'alerts' && (
                <div className="settings-alerts">
                  <div className="settings-group">
                    <h4>Alert Delivery</h4>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={userSettings.alerts_sound !== false}
                          onChange={e => handleSaveSetting('alerts_sound', e.target.checked, 'user')}
                        />
                        Sound Alerts
                      </label>
                      <span className="setting-hint">Play audio when alerts trigger</span>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={userSettings.alerts_browser === true}
                          onChange={e => {
                            if (e.target.checked && 'Notification' in window) {
                              Notification.requestPermission().then(permission => {
                                handleSaveSetting('alerts_browser', permission === 'granted', 'user');
                              });
                            } else {
                              handleSaveSetting('alerts_browser', false, 'user');
                            }
                          }}
                        />
                        Browser Notifications
                      </label>
                      <span className="setting-hint">Show system notifications (requires permission)</span>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={userSettings.alerts_visual !== false}
                          onChange={e => handleSaveSetting('alerts_visual', e.target.checked, 'user')}
                        />
                        Visual Alerts
                      </label>
                      <span className="setting-hint">Flash/highlight triggered alerts in UI</span>
                    </div>
                  </div>

                  <div className="settings-group">
                    <h4>Strategy Alerts</h4>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={userSettings.alerts_strategy_price !== false}
                          onChange={e => handleSaveSetting('alerts_strategy_price', e.target.checked, 'user')}
                        />
                        Price Alerts
                      </label>
                      <span className="setting-hint">Alert when spot reaches target price</span>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={userSettings.alerts_strategy_debit !== false}
                          onChange={e => handleSaveSetting('alerts_strategy_debit', e.target.checked, 'user')}
                        />
                        Debit Alerts
                      </label>
                      <span className="setting-hint">Alert when debit reaches target</span>
                    </div>
                  </div>

                  <div className="settings-group">
                    <h4>Trade Log Alerts</h4>
                    <p className="setting-hint">Coming soon: Profit target, stop loss, and time-based alerts for open positions</p>
                  </div>

                  <div className="settings-group">
                    <h4>Routine Alerts</h4>
                    <p className="setting-hint">Coming soon: Daily logging reminders, weekly reviews, and journaling prompts</p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
