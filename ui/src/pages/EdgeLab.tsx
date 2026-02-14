// ui/src/pages/EdgeLab.tsx
// Edge Lab — retrospective trade analysis surface
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useEdgeLab } from '../hooks/useEdgeLab';
import type { EdgeLabSetup, OutcomeSuggestion } from '../hooks/useEdgeLab';
import SetupForm from '../components/EdgeLab/SetupForm';
import SetupList from '../components/EdgeLab/SetupList';
import HypothesisForm from '../components/EdgeLab/HypothesisForm';
import OutcomeAttribution from '../components/EdgeLab/OutcomeAttribution';
import EdgeScoreCard from '../components/EdgeLab/EdgeScoreCard';
import RegimeChart from '../components/EdgeLab/RegimeChart';
import BiasOverlay from '../components/EdgeLab/BiasOverlay';

type Tab = 'setups' | 'analytics' | 'history';

export default function EdgeLabPage() {
  const navigate = useNavigate();
  const {
    setups, loading, edgeScore, edgeScoreStatus, regimeData, biasData, scoreHistory,
    fetchSetups, fetchSetup, createSetup, createHypothesis, lockHypothesis,
    createOutcome, confirmOutcome, suggestOutcome,
    fetchRegimeCorrelation, fetchBiasOverlay, fetchEdgeScore, fetchEdgeScoreHistory,
  } = useEdgeLab();

  const [activeTab, setActiveTab] = useState<Tab>('setups');
  const [showForm, setShowForm] = useState(false);
  const [selectedSetup, setSelectedSetup] = useState<EdgeLabSetup | null>(null);
  const [suggestion, setSuggestion] = useState<OutcomeSuggestion | null>(null);
  const [dateRange, setDateRange] = useState({
    start: new Date(Date.now() - 90 * 86400000).toISOString().split('T')[0],
    end: new Date().toISOString().split('T')[0],
  });

  // Load setups on mount
  useEffect(() => {
    fetchSetups();
  }, [fetchSetups]);

  // Load analytics when tab switches
  useEffect(() => {
    if (activeTab === 'analytics') {
      fetchRegimeCorrelation(dateRange.start, dateRange.end);
      fetchBiasOverlay(dateRange.start, dateRange.end);
      fetchEdgeScore(dateRange.start, dateRange.end);
    } else if (activeTab === 'history') {
      fetchEdgeScoreHistory(90);
    }
  }, [activeTab, dateRange, fetchRegimeCorrelation, fetchBiasOverlay, fetchEdgeScore, fetchEdgeScoreHistory]);

  const handleCreateSetup = useCallback(async (data: Record<string, unknown>) => {
    await createSetup(data);
    setShowForm(false);
  }, [createSetup]);

  const handleSelectSetup = useCallback(async (setup: EdgeLabSetup) => {
    const full = await fetchSetup(setup.id);
    setSelectedSetup(full);
    setSuggestion(null);
  }, [fetchSetup]);

  const handleCreateHypothesis = useCallback(async (data: Parameters<typeof createHypothesis>[0]) => {
    await createHypothesis(data);
    if (selectedSetup) {
      const full = await fetchSetup(selectedSetup.id);
      setSelectedSetup(full);
    }
  }, [createHypothesis, fetchSetup, selectedSetup]);

  const handleLockHypothesis = useCallback(async (id: string) => {
    await lockHypothesis(id);
    if (selectedSetup) {
      const full = await fetchSetup(selectedSetup.id);
      setSelectedSetup(full);
    }
  }, [lockHypothesis, fetchSetup, selectedSetup]);

  const handleSuggestOutcome = useCallback(async (setupId: string) => {
    const result = await suggestOutcome(setupId);
    setSuggestion(result);
  }, [suggestOutcome]);

  const handleCreateOutcome = useCallback(async (data: Record<string, unknown>) => {
    await createOutcome(data);
    if (selectedSetup) {
      const full = await fetchSetup(selectedSetup.id);
      setSelectedSetup(full);
    }
  }, [createOutcome, fetchSetup, selectedSetup]);

  const handleConfirmOutcome = useCallback(async (id: string) => {
    await confirmOutcome(id);
    if (selectedSetup) {
      const full = await fetchSetup(selectedSetup.id);
      setSelectedSetup(full);
    }
  }, [confirmOutcome, fetchSetup, selectedSetup]);

  const tabStyle = (t: Tab): React.CSSProperties => ({
    padding: '8px 20px', cursor: 'pointer', fontSize: 13,
    background: activeTab === t ? '#1e293b' : 'transparent',
    color: activeTab === t ? '#e0e0e0' : '#888',
    border: 'none', borderBottom: activeTab === t ? '2px solid #2563eb' : '2px solid transparent',
  });

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a14', color: '#e0e0e0', padding: '20px 24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>Edge Lab</h1>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: '#666' }}>
            Retrospective structural analysis — a mirror, not a coach
          </p>
        </div>
        <button onClick={() => navigate('/')}
          style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid #444', background: 'transparent', color: '#888', cursor: 'pointer', fontSize: 12 }}>
          Back to Dashboard
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid #333', marginBottom: 20 }}>
        <button onClick={() => setActiveTab('setups')} style={tabStyle('setups')}>Setups</button>
        <button onClick={() => setActiveTab('analytics')} style={tabStyle('analytics')}>Analytics</button>
        <button onClick={() => setActiveTab('history')} style={tabStyle('history')}>History</button>
      </div>

      {/* Setups Tab */}
      {activeTab === 'setups' && (
        <div style={{ display: 'grid', gridTemplateColumns: selectedSetup ? '1fr 1fr' : '1fr', gap: 20 }}>
          <div>
            {showForm ? (
              <SetupForm onSubmit={handleCreateSetup} onCancel={() => setShowForm(false)} />
            ) : (
              <SetupList setups={setups} loading={loading}
                onSelect={handleSelectSetup}
                onNewSetup={() => setShowForm(true)} />
            )}
          </div>

          {selectedSetup && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: 14, color: '#e0e0e0' }}>
                  Setup: {selectedSetup.setupDate}
                </h3>
                <button onClick={() => setSelectedSetup(null)}
                  style={{ fontSize: 11, color: '#666', background: 'transparent', border: 'none', cursor: 'pointer' }}>
                  Close
                </button>
              </div>

              {/* Setup details */}
              <div style={{ padding: 12, background: '#0d0d1a', borderRadius: 6, border: '1px solid #333', marginBottom: 12, fontSize: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, color: '#aaa' }}>
                  <div>Regime: <span style={{ color: '#e0e0e0' }}>{selectedSetup.regime}</span></div>
                  <div>GEX: <span style={{ color: '#e0e0e0' }}>{selectedSetup.gexPosture}</span></div>
                  <div>Vol: <span style={{ color: '#e0e0e0' }}>{selectedSetup.volState}</span></div>
                  <div>Time: <span style={{ color: '#e0e0e0' }}>{selectedSetup.timeStructure}</span></div>
                  <div>Heatmap: <span style={{ color: '#e0e0e0' }}>{selectedSetup.heatmapColor}</span></div>
                  <div>Structure: <span style={{ color: '#e0e0e0' }}>{selectedSetup.positionStructure}</span></div>
                  <div>Width: <span style={{ color: '#e0e0e0' }}>{selectedSetup.widthBucket}</span></div>
                  <div>Bias: <span style={{ color: '#e0e0e0' }}>{selectedSetup.directionalBias}</span></div>
                </div>
                {selectedSetup.entryLogic && (
                  <div style={{ marginTop: 8, color: '#888' }}>
                    Entry: <span style={{ color: '#ccc' }}>{selectedSetup.entryLogic}</span>
                  </div>
                )}
                {selectedSetup.exitLogic && (
                  <div style={{ marginTop: 4, color: '#888' }}>
                    Exit: <span style={{ color: '#ccc' }}>{selectedSetup.exitLogic}</span>
                  </div>
                )}
              </div>

              {/* Hypothesis */}
              <div style={{ marginBottom: 12 }}>
                <HypothesisForm
                  setupId={selectedSetup.id}
                  existing={selectedSetup.hypothesis}
                  onSubmit={handleCreateHypothesis}
                  onLock={handleLockHypothesis}
                />
              </div>

              {/* Outcome Attribution */}
              <OutcomeAttribution
                setupId={selectedSetup.id}
                existing={selectedSetup.outcome}
                suggestion={suggestion}
                onSuggest={handleSuggestOutcome}
                onSubmit={handleCreateOutcome}
                onConfirm={handleConfirmOutcome}
              />
            </div>
          )}
        </div>
      )}

      {/* Analytics Tab */}
      {activeTab === 'analytics' && (
        <div>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center' }}>
            <label style={{ fontSize: 12, color: '#888' }}>From:</label>
            <input type="date" value={dateRange.start}
              onChange={e => setDateRange(r => ({ ...r, start: e.target.value }))}
              style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #444', background: '#1a1a2e', color: '#e0e0e0', fontSize: 12 }} />
            <label style={{ fontSize: 12, color: '#888' }}>To:</label>
            <input type="date" value={dateRange.end}
              onChange={e => setDateRange(r => ({ ...r, end: e.target.value }))}
              style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #444', background: '#1a1a2e', color: '#e0e0e0', fontSize: 12 }} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
            <EdgeScoreCard score={edgeScore} status={edgeScoreStatus} history={scoreHistory} />
            <div style={{ padding: 16, background: '#0d0d1a', borderRadius: 8, border: '1px solid #333' }}>
              <div style={{ fontSize: 11, color: '#888', marginBottom: 12 }}>Edge Score Formula</div>
              <div style={{ fontSize: 12, color: '#aaa', lineHeight: 1.8 }}>
                <div>SI (35%) - Structural Integrity</div>
                <div>ED (30%) - Execution Discipline</div>
                <div>BI (15%) - Bias Interference (subtracted)</div>
                <div>RA (20%) - Regime Alignment</div>
                <div style={{ marginTop: 8, color: '#555', fontSize: 11 }}>
                  P&L is never used in this formula. Edge Score measures process quality.
                </div>
              </div>
            </div>
          </div>

          <div style={{ marginBottom: 20, padding: 16, background: '#0d0d1a', borderRadius: 8, border: '1px solid #333' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#e0e0e0' }}>Regime Correlation</h3>
            <RegimeChart data={regimeData} />
          </div>

          <div style={{ padding: 16, background: '#0d0d1a', borderRadius: 8, border: '1px solid #333' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#e0e0e0' }}>Bias Overlay</h3>
            <BiasOverlay data={biasData} />
          </div>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div>
          <EdgeScoreCard score={edgeScore} status={edgeScoreStatus} history={scoreHistory} />
          {scoreHistory.length > 0 ? (
            <div style={{ marginTop: 20 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #333', color: '#888', fontSize: 11 }}>
                    <th style={{ textAlign: 'left', padding: '6px 8px' }}>Period</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>Score</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>SI</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>ED</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>BI</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>RA</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {scoreHistory.map((s, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #222' }}>
                      <td style={{ padding: '8px', color: '#aaa' }}>{s.windowStart} to {s.windowEnd}</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#e0e0e0', fontWeight: 'bold' }}>
                        {(s.finalScore * 100).toFixed(1)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#2563eb' }}>{(s.structuralIntegrity * 100).toFixed(0)}%</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#10b981' }}>{(s.executionDiscipline * 100).toFixed(0)}%</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#ef4444' }}>{(s.biasInterferenceRate * 100).toFixed(0)}%</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#8b5cf6' }}>{(s.regimeAlignment * 100).toFixed(0)}%</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#888' }}>{s.sampleSize}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ padding: 20, textAlign: 'center', color: '#555', fontSize: 13, marginTop: 20 }}>
              No score history yet.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
