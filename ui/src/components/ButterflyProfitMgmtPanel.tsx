// src/components/ButterflyProfitMgmtPanel.tsx
/**
 * Panel for displaying butterfly profit management status.
 * Shows current profit vs HWM, risk score gauge, and recommendation badge.
 */

import type { ButterflyProfitMgmtAlert, MgmtRecommendation } from '../types/alerts';
import '../styles/alert-modal.css';

interface ButterflyProfitMgmtPanelProps {
  alert: ButterflyProfitMgmtAlert;
  currentDebit?: number;
  currentProfit?: number;
}

// Risk score color coding
function getRiskScoreColor(score: number): string {
  if (score >= 80) return '#ef4444'; // red - critical
  if (score >= 60) return '#f97316'; // orange - elevated
  if (score >= 40) return '#eab308'; // yellow - moderate
  return '#22c55e'; // green - low
}

// Recommendation badge styling
const RECOMMENDATION_STYLES: Record<MgmtRecommendation, { color: string; bgColor: string; label: string }> = {
  HOLD: {
    color: '#22c55e',
    bgColor: '#14532d',
    label: 'HOLD',
  },
  TIGHTEN: {
    color: '#f59e0b',
    bgColor: '#78350f',
    label: 'TIGHTEN',
  },
  EXIT: {
    color: '#ef4444',
    bgColor: '#7f1d1d',
    label: 'EXIT',
  },
};

// Risk factor breakdown (matches Python weights)
interface RiskFactors {
  timeRisk: number;      // 35%
  gammaRisk: number;     // 30%
  drawdownRisk: number;  // 20%
  vixRisk: number;       // 15%
}

function estimateRiskFactors(alert: ButterflyProfitMgmtAlert, currentProfit?: number): RiskFactors {
  const dte = alert.mgmtInitialDte ?? 7;
  const hwm = alert.mgmtHighWaterMark ?? 0;
  const profit = currentProfit ?? 0;

  // Time risk (accelerates as DTE -> 0)
  const timeRisk = dte === 0 ? 100 : Math.max(0, 100 - dte * 15);

  // Gamma risk - approximate without spot/strike data
  const gammaRisk = 50; // Default middle

  // Drawdown risk
  const drawdownRisk = hwm > 0 ? ((hwm - profit) / hwm) * 100 : 0;

  // VIX risk - approximate
  const vixRisk = 25; // Default moderate

  return { timeRisk, gammaRisk, drawdownRisk, vixRisk };
}

export default function ButterflyProfitMgmtPanel({
  alert,
  currentDebit,
  currentProfit: propCurrentProfit,
}: ButterflyProfitMgmtPanelProps) {
  const entryDebit = alert.entryDebit ?? 0;
  const currentProfit = propCurrentProfit ?? (currentDebit !== undefined ? entryDebit - currentDebit : 0);
  const hwm = alert.mgmtHighWaterMark ?? 0;
  const riskScore = alert.mgmtRiskScore ?? 0;
  const recommendation = alert.mgmtRecommendation ?? 'HOLD';
  const activationThreshold = alert.mgmtActivationThreshold ?? 0.75;

  // Calculate profit percentage
  const profitPct = entryDebit > 0 ? (currentProfit / entryDebit) * 100 : 0;
  const hwmPct = entryDebit > 0 ? (hwm / entryDebit) * 100 : 0;
  const activationPct = activationThreshold * 100;

  // Is management active?
  const isActive = profitPct >= activationPct;

  // Risk factors breakdown
  const factors = estimateRiskFactors(alert, currentProfit);

  const recommendationStyle = RECOMMENDATION_STYLES[recommendation as MgmtRecommendation] ?? RECOMMENDATION_STYLES.HOLD;

  return (
    <div className="profit-mgmt-panel" style={{
      backgroundColor: '#1a1a2e',
      borderRadius: '8px',
      padding: '16px',
      border: isActive ? '1px solid #3b82f6' : '1px solid #374151',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <span style={{ color: '#9ca3af', fontSize: '12px', textTransform: 'uppercase' }}>
          Profit Management
        </span>
        {isActive && (
          <span style={{
            backgroundColor: recommendationStyle.bgColor,
            color: recommendationStyle.color,
            padding: '4px 12px',
            borderRadius: '4px',
            fontSize: '12px',
            fontWeight: 'bold',
          }}>
            {recommendationStyle.label}
          </span>
        )}
      </div>

      {/* Activation Status */}
      {!isActive && (
        <div style={{
          backgroundColor: '#374151',
          borderRadius: '4px',
          padding: '12px',
          marginBottom: '16px',
          textAlign: 'center',
        }}>
          <span style={{ color: '#9ca3af' }}>
            Activates at {activationPct.toFixed(0)}% profit ({(activationPct - profitPct).toFixed(1)}% away)
          </span>
        </div>
      )}

      {/* Profit vs HWM Visualization */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ color: '#d1d5db', fontSize: '13px' }}>Current Profit</span>
          <span style={{ color: profitPct >= 0 ? '#22c55e' : '#ef4444', fontSize: '13px', fontWeight: 'bold' }}>
            ${currentProfit.toFixed(2)} ({profitPct.toFixed(1)}%)
          </span>
        </div>
        <div style={{
          height: '8px',
          backgroundColor: '#374151',
          borderRadius: '4px',
          overflow: 'hidden',
          position: 'relative',
        }}>
          {/* HWM marker */}
          {hwmPct > 0 && (
            <div style={{
              position: 'absolute',
              left: `${Math.min(hwmPct, 100)}%`,
              top: 0,
              bottom: 0,
              width: '2px',
              backgroundColor: '#3b82f6',
              zIndex: 2,
            }} />
          )}
          {/* Current profit bar */}
          <div style={{
            width: `${Math.min(Math.max(profitPct, 0), 100)}%`,
            height: '100%',
            backgroundColor: profitPct >= hwmPct * 0.5 ? '#22c55e' : '#f97316',
            transition: 'width 0.3s ease',
          }} />
        </div>
        {hwm > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
            <span style={{ color: '#6b7280', fontSize: '11px' }}>0%</span>
            <span style={{ color: '#3b82f6', fontSize: '11px' }}>
              HWM: ${hwm.toFixed(2)} ({hwmPct.toFixed(1)}%)
            </span>
          </div>
        )}
      </div>

      {/* Risk Score Gauge */}
      {isActive && (
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ color: '#d1d5db', fontSize: '13px' }}>Risk Score</span>
            <span style={{
              color: getRiskScoreColor(riskScore),
              fontSize: '13px',
              fontWeight: 'bold',
            }}>
              {riskScore.toFixed(0)}/100
            </span>
          </div>
          <div style={{
            height: '12px',
            backgroundColor: '#374151',
            borderRadius: '4px',
            overflow: 'hidden',
            display: 'flex',
          }}>
            {/* Gradient background showing risk zones */}
            <div style={{
              width: '40%',
              height: '100%',
              backgroundColor: '#14532d',
            }} />
            <div style={{
              width: '20%',
              height: '100%',
              backgroundColor: '#422006',
            }} />
            <div style={{
              width: '20%',
              height: '100%',
              backgroundColor: '#78350f',
            }} />
            <div style={{
              width: '20%',
              height: '100%',
              backgroundColor: '#7f1d1d',
            }} />
          </div>
          {/* Risk score indicator */}
          <div style={{ position: 'relative', height: '8px' }}>
            <div style={{
              position: 'absolute',
              left: `calc(${Math.min(riskScore, 100)}% - 4px)`,
              top: '-4px',
              width: 0,
              height: 0,
              borderLeft: '6px solid transparent',
              borderRight: '6px solid transparent',
              borderBottom: `8px solid ${getRiskScoreColor(riskScore)}`,
            }} />
          </div>
        </div>
      )}

      {/* Risk Factor Breakdown */}
      {isActive && (
        <div style={{
          backgroundColor: '#111827',
          borderRadius: '4px',
          padding: '12px',
        }}>
          <span style={{ color: '#6b7280', fontSize: '11px', textTransform: 'uppercase' }}>
            Risk Factors
          </span>
          <div style={{ marginTop: '8px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            <RiskFactorRow label="Time (35%)" value={factors.timeRisk} />
            <RiskFactorRow label="Gamma (30%)" value={factors.gammaRisk} />
            <RiskFactorRow label="Drawdown (20%)" value={factors.drawdownRisk} />
            <RiskFactorRow label="VIX (15%)" value={factors.vixRisk} />
          </div>
        </div>
      )}

      {/* Last Assessment */}
      {alert.mgmtLastAssessment && (
        <div style={{ marginTop: '12px', textAlign: 'right' }}>
          <span style={{ color: '#6b7280', fontSize: '10px' }}>
            Last: {new Date(alert.mgmtLastAssessment).toLocaleTimeString()}
          </span>
        </div>
      )}
    </div>
  );
}

// Helper component for risk factor rows
function RiskFactorRow({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{ color: '#9ca3af', fontSize: '11px', flex: 1 }}>{label}</span>
      <div style={{
        width: '40px',
        height: '4px',
        backgroundColor: '#374151',
        borderRadius: '2px',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${Math.min(value, 100)}%`,
          height: '100%',
          backgroundColor: getRiskScoreColor(value),
        }} />
      </div>
      <span style={{
        color: getRiskScoreColor(value),
        fontSize: '11px',
        minWidth: '24px',
        textAlign: 'right',
      }}>
        {value.toFixed(0)}
      </span>
    </div>
  );
}
