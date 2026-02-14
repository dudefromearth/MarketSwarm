// ui/src/components/EdgeLab/SetupList.tsx
import type { EdgeLabSetup } from '../../hooks/useEdgeLab';

interface SetupListProps {
  setups: EdgeLabSetup[];
  loading: boolean;
  onSelect: (setup: EdgeLabSetup) => void;
  onNewSetup: () => void;
}

function SignatureBadge({ sig }: { sig: string }) {
  const parts = sig.split('|').filter(Boolean);
  const short = parts.slice(0, 3).join(' / ');
  return (
    <span style={{ fontSize: 10, color: '#6b7280', background: '#1e293b', padding: '2px 6px', borderRadius: 3 }}>
      {short}
    </span>
  );
}

function StatusBadge({ setup }: { setup: EdgeLabSetup }) {
  const hasHypothesis = !!setup.hypothesis;
  const isLocked = setup.hypothesis?.isLocked;
  const hasOutcome = !!setup.outcome;
  const isConfirmed = setup.outcome?.isConfirmed;

  if (isConfirmed) return <span style={{ fontSize: 10, color: '#10b981' }}>Complete</span>;
  if (hasOutcome) return <span style={{ fontSize: 10, color: '#f59e0b' }}>Outcome Pending</span>;
  if (isLocked) return <span style={{ fontSize: 10, color: '#60a5fa' }}>Hypothesis Locked</span>;
  if (hasHypothesis) return <span style={{ fontSize: 10, color: '#818cf8' }}>Hypothesis Saved</span>;
  return <span style={{ fontSize: 10, color: '#6b7280' }}>Setup Only</span>;
}

export default function SetupList({ setups, loading, onSelect, onNewSetup }: SetupListProps) {
  if (loading) {
    return <div style={{ padding: 20, textAlign: 'center', color: '#888' }}>Loading setups...</div>;
  }

  if (setups.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <div style={{ color: '#888', fontSize: 14, marginBottom: 12 }}>No setups recorded yet</div>
        <div style={{ color: '#555', fontSize: 12, marginBottom: 20 }}>
          Start by recording a structural setup to track your edge over time.
        </div>
        <button onClick={onNewSetup}
          style={{ padding: '8px 20px', borderRadius: 4, border: 'none', background: '#2563eb', color: '#fff', cursor: 'pointer', fontSize: 13 }}>
          Create First Setup
        </button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 12, color: '#888' }}>{setups.length} setups</div>
        <button onClick={onNewSetup}
          style={{ padding: '6px 14px', borderRadius: 4, border: 'none', background: '#2563eb', color: '#fff', cursor: 'pointer', fontSize: 12 }}>
          + New Setup
        </button>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #333', color: '#888', fontSize: 11 }}>
            <th style={{ textAlign: 'left', padding: '6px 8px' }}>Date</th>
            <th style={{ textAlign: 'left', padding: '6px 8px' }}>Structure</th>
            <th style={{ textAlign: 'left', padding: '6px 8px' }}>Signature</th>
            <th style={{ textAlign: 'left', padding: '6px 8px' }}>Regime</th>
            <th style={{ textAlign: 'left', padding: '6px 8px' }}>Bias</th>
            <th style={{ textAlign: 'center', padding: '6px 8px' }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {setups.map(setup => (
            <tr key={setup.id}
              onClick={() => onSelect(setup)}
              style={{ borderBottom: '1px solid #222', cursor: 'pointer' }}
              onMouseEnter={e => (e.currentTarget.style.background = '#1a1a2e')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
              <td style={{ padding: '8px', color: '#e0e0e0' }}>{setup.setupDate}</td>
              <td style={{ padding: '8px', color: '#e0e0e0' }}>
                {setup.positionStructure.replace(/_/g, ' ')}
              </td>
              <td style={{ padding: '8px' }}>
                <SignatureBadge sig={setup.structureSignature} />
              </td>
              <td style={{ padding: '8px', color: '#aaa' }}>{setup.regime}</td>
              <td style={{ padding: '8px', color: '#aaa' }}>{setup.directionalBias}</td>
              <td style={{ padding: '8px', textAlign: 'center' }}>
                <StatusBadge setup={setup} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
