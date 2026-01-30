// src/components/SettingsModal.tsx
import { useState, useEffect, useCallback } from 'react';

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

type SettingsTab = 'symbols' | 'trading' | 'user' | 'display' | 'alerts';
type AssetTypeFilter = 'all' | 'index_option' | 'etf_option' | 'future' | 'stock';

export default function SettingsModal({ onClose }: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('symbols');
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [loading, setLoading] = useState(true);
  const [assetFilter, setAssetFilter] = useState<AssetTypeFilter>('all');

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

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchSymbols(), fetchSettings()]);
      setLoading(false);
    };
    loadData();
  }, [fetchSymbols, fetchSettings]);

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
    <div className="modal-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="btn-close" onClick={onClose}>&times;</button>
        </div>

        <div className="settings-tabs">
          <button
            className={`settings-tab ${activeTab === 'symbols' ? 'active' : ''}`}
            onClick={() => setActiveTab('symbols')}
          >
            Symbols
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
