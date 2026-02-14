/**
 * FOTW Path Stage Content
 *
 * Declarative content for the 5-stage trading path.
 * Content is informative, not instructional or motivational.
 */

export type Stage = 'discovery' | 'analysis' | 'action' | 'reflection' | 'distillation';

export interface StageContent {
  icon: string;
  title: string;
  description: string;
  notYet: string;
  tools: string[];
  feedsInto: string;
  videoId?: string; // Optional video reference
}

export const STAGES: Record<Stage, StageContent> = {
  discovery: {
    icon: '🔭',
    title: 'Discovery',
    description: 'This is where you observe and orient. You\'re building a sense of the environment before forming opinions.',
    notYet: 'Do not make decisions here.\nDo not search for trades.',
    tools: ['Market context', 'Volatility regime', 'Structure', 'Commentary'],
    feedsInto: 'What you notice here informs what is worth evaluating next.',
  },
  analysis: {
    icon: '🔬',
    title: 'Analysis',
    description: 'This is where you evaluate structure and risk. You\'re asking whether an idea is worth expressing.',
    notYet: 'Do not execute trades here.\nDo not rush to certainty.',
    tools: ['Risk Graphs', 'Strategy selection', 'Convexity and decay analysis'],
    feedsInto: 'Clear analysis defines what kind of action, if any, is appropriate.',
  },
  action: {
    icon: '⚡',
    title: 'Action',
    description: 'This is where you act with intent. Risk is taken deliberately, with structure already defined.',
    notYet: 'Do not second-guess the decision while executing.\nDo not improvise.',
    tools: ['Trade entry', 'Alert creation', 'Execution handoff'],
    feedsInto: 'Every action creates material for reflection.',
  },
  reflection: {
    icon: '📝',
    title: 'Reflection',
    description: 'This is where you review what happened and how you experienced it. Outcome is observed, not judged.',
    notYet: 'Do not be harsh or congratulatory.\nDo not rewrite history.',
    tools: ['Trade log', 'Journal entries', 'Session review'],
    feedsInto: 'Honest reflection reveals patterns worth carrying forward.',
    videoId: 'reflection-intro', // Optional video
  },
  distillation: {
    icon: '💎',
    title: 'Distillation',
    description: 'This is where lessons are extracted. You\'re deciding what is worth remembering beyond this session.',
    notYet: 'Do not rush back to the market.\nDo not turn one outcome into a rule.',
    tools: ['Journal synthesis', 'Pattern notes', 'Playbook updates'],
    feedsInto: 'Distilled insight shapes how you observe the next environment.',
  },
};

export const STAGE_ORDER: Stage[] = ['discovery', 'analysis', 'action', 'reflection', 'distillation'];

/**
 * Panel-to-stage mapping for automatic inference
 * The system infers stage from active UI context, never forces it
 */
export const PANEL_STAGE_MAP: Record<string, Stage> = {
  // Discovery - observation tools
  'heatmap': 'discovery',
  'gex-chart': 'discovery',
  'vexy': 'discovery',
  'spot-display': 'discovery',
  'indicators': 'discovery',
  'observer': 'discovery',
  'market-mode': 'discovery',
  'vix-regime': 'discovery',
  'bias-lfi': 'discovery',

  // Analysis - evaluation tools
  'risk-graph': 'analysis',
  'trade-selector': 'analysis',
  'trade-recommendations': 'analysis',
  'convexity': 'analysis',

  // Action - execution tools
  'trade-entry-modal': 'action',
  'alert-creation-modal': 'action',
  'tos-import': 'action',

  // Reflection - review tools
  'trade-log': 'reflection',
  'trade-detail': 'reflection',
  'reporting': 'reflection',
  'edge-lab': 'reflection',

  // Distillation - synthesis tools
  'journal': 'distillation',
  'journal-entry': 'distillation',
  'playbook': 'distillation',
};

/**
 * Global philosophy line shown at the top of expanded panel
 */
export const PATH_PHILOSOPHY =
  'The path is not linear. You may move backward, skip stages, or linger anywhere. ' +
  'The system reflects where you are — it does not tell you where to go.';

/**
 * Welcome tour content
 */
export const WELCOME_CONTENT = {
  headline: 'Welcome to FOTW',
  videoPlaceholder: 'How to think about the path',
  intro: 'This is not a traditional trading app.',
  pathIntro: 'We built this system around a path:',
  pathSummary: 'Discovery → Analysis → Action → Reflection → Distillation',
  philosophy: [
    'The system won\'t tell you what to do.',
    'It will help you notice where you are.',
  ],
  beginButton: 'Begin',
  skipButton: 'Skip',
};
