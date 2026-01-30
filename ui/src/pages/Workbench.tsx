// ui/src/pages/Workbench.tsx
import { useNavigate } from "react-router-dom";

export default function WorkbenchPage() {
  const navigate = useNavigate();

  return (
    <div className="workbench-page">
      <div className="workbench-content">
        <div className="workbench-card">
          <button className="back-btn" onClick={() => navigate("/")}>
            <span>←</span> Dashboard
          </button>
          <h1>Workbench</h1>
          <p className="coming-soon">Coming Soon</p>
          <p className="desc">Advanced trading tools and analysis will be available here.</p>
        </div>
      </div>

      <style>{`
        .workbench-page {
          min-height: 100vh;
          background: #09090b;
          color: #f1f5f9;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 2rem;
        }
        .workbench-content {
          text-align: center;
        }
        .workbench-card {
          padding: 3rem;
          background: rgba(24, 24, 27, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 1.5rem;
          backdrop-filter: blur(12px);
        }
        .back-btn {
          background: rgba(255,255,255,0.08);
          border: 1px solid rgba(255,255,255,0.12);
          color: #94a3b8;
          padding: 0.5rem 1rem;
          border-radius: 0.75rem;
          font-size: 0.875rem;
          cursor: pointer;
          margin-bottom: 1.5rem;
          transition: all 0.15s;
        }
        .back-btn:hover { background: rgba(255,255,255,0.12); color: #f1f5f9; }
        h1 { font-size: 2rem; margin: 0 0 0.5rem; }
        .coming-soon {
          display: inline-block;
          background: linear-gradient(135deg, rgba(34,211,238,0.2), rgba(99,102,241,0.2));
          color: #22d3ee;
          padding: 0.25rem 1rem;
          border-radius: 9999px;
          font-size: 0.875rem;
          font-weight: 500;
          margin-bottom: 1rem;
        }
        .desc { color: #64748b; font-size: 0.9rem; margin: 0; }
      `}</style>
    </div>
  );
}
