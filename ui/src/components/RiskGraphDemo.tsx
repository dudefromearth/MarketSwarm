/**
 * RiskGraphDemo - Test harness for Risk Graph
 * Press Ctrl+Shift+G to toggle
 */

import { useState } from 'react';
import RiskGraph from './RiskGraph';
import type { Strategy } from '../hooks/useRiskGraphCalculations';

const SAMPLE_STRATEGIES: Record<string, Strategy> = {
  butterfly: { id: 'bf-1', strike: 6000, width: 20, side: 'call', strategy: 'butterfly', debit: 3.50, visible: true, dte: 1 },
  bullCall: { id: 'bc-1', strike: 5980, width: 30, side: 'call', strategy: 'vertical', debit: 8.00, visible: true, dte: 1 },
  bearPut: { id: 'bp-1', strike: 6020, width: 30, side: 'put', strategy: 'vertical', debit: 7.50, visible: true, dte: 1 },
};

export default function RiskGraphDemo() {
  const [spot] = useState(6000);
  const [vix, setVix] = useState(18);
  const [activeStrategies, setActiveStrategies] = useState<string[]>(['butterfly']);
  const [timeMachine, setTimeMachine] = useState(false);
  const [simTime, setSimTime] = useState(0);
  const [simVol, setSimVol] = useState(0);

  const strategies = activeStrategies.map(key => SAMPLE_STRATEGIES[key]);

  const toggle = (key: string) => {
    setActiveStrategies(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  };

  return (
    <div className="risk-graph-echarts-demo">
      <h2>Risk Graph</h2>

      <div className="controls">
        {Object.entries(SAMPLE_STRATEGIES).map(([key, s]) => (
          <button key={key} className={activeStrategies.includes(key) ? 'active' : ''} onClick={() => toggle(key)}>
            {s.strategy === 'butterfly' ? 'BF' : s.strategy === 'vertical' ? (s.side === 'call' ? 'Bull' : 'Bear') : ''} {s.strike}/{s.width}w
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: '16px', marginBottom: '12px', alignItems: 'center', fontSize: '12px', color: '#888' }}>
        <label><input type="checkbox" checked={timeMachine} onChange={e => setTimeMachine(e.target.checked)} /> Time Machine</label>
        {timeMachine && (
          <>
            <label>+{simTime}h <input type="range" min="0" max="8" step="0.5" value={simTime} onChange={e => setSimTime(+e.target.value)} style={{ width: 60 }} /></label>
            <label>Vol {simVol >= 0 ? '+' : ''}{simVol} <input type="range" min="-10" max="10" value={simVol} onChange={e => setSimVol(+e.target.value)} style={{ width: 60 }} /></label>
          </>
        )}
        <label>VIX {vix} <input type="range" min="10" max="40" value={vix} onChange={e => setVix(+e.target.value)} style={{ width: 60 }} /></label>
      </div>

      <div style={{ height: '450px', background: '#0a0a0a', borderRadius: '6px' }}>
        <RiskGraph
          strategies={strategies}
          spotPrice={spot}
          vix={vix}
          symbol="SPX"
          timeMachineEnabled={timeMachine}
          simVolatilityOffset={simVol}
          simTimeOffsetHours={simTime}
        />
      </div>

      <div style={{ marginTop: '12px', fontSize: '10px', color: '#555' }}>
        Scroll = Y zoom | Shift+Scroll = X zoom | Drag = Pan
      </div>
    </div>
  );
}
