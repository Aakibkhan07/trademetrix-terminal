export interface DemoStrategy {
  id: string
  name: string
  type: string
  is_active: boolean
  created_at: string
  metrics: {
    returns: string
    drawdown: string
    winRate: string
    sharpe: string
    trades: number
    profit: number
  }
}

export interface DemoTrade {
  id: string
  symbol: string
  side: 'BUY' | 'SELL'
  quantity: number
  price: number
  pnl: number
  status: 'filled' | 'pending' | 'rejected'
  timestamp: string
  strategy: string
}

export interface DemoRun {
  id: string
  strategy_id: string
  strategy_name: string
  symbol: string
  status: 'running' | 'stopped' | 'error'
  started_at: string
  pnl: number
}

export const DEMO_STRATEGIES: DemoStrategy[] = [
  { id: 's1', name: 'Momentum Pro', type: 'Trend Following', is_active: true, created_at: '2026-03-15',
    metrics: { returns: '+32.4%', drawdown: '-8.2%', winRate: '68%', sharpe: '2.1', trades: 847, profit: 124500 } },
  { id: 's2', name: 'Mean Reversion', type: 'Statistical Arbitrage', is_active: true, created_at: '2026-04-01',
    metrics: { returns: '+24.8%', drawdown: '-5.1%', winRate: '72%', sharpe: '1.8', trades: 1241, profit: 89200 } },
  { id: 's3', name: 'Breakout Hunter', type: 'Momentum', is_active: false, created_at: '2026-05-10',
    metrics: { returns: '+45.2%', drawdown: '-15.3%', winRate: '55%', sharpe: '1.5', trades: 312, profit: 198000 } },
  { id: 's4', name: 'Options Alpha', type: 'Options', is_active: true, created_at: '2026-02-20',
    metrics: { returns: '+28.6%', drawdown: '-6.8%', winRate: '65%', sharpe: '1.9', trades: 563, profit: 156000 } },
  { id: 's5', name: 'Scalper X', type: 'Intraday', is_active: false, created_at: '2026-06-01',
    metrics: { returns: '+38.1%', drawdown: '-12.4%', winRate: '61%', sharpe: '1.3', trades: 2890, profit: 67500 } },
]

export const DEMO_RUNS: DemoRun[] = [
  { id: 'r1', strategy_id: 's1', strategy_name: 'Momentum Pro', symbol: 'NIFTY', status: 'running', started_at: '2026-06-28T09:15:00', pnl: 12450 },
  { id: 'r2', strategy_id: 's2', strategy_name: 'Mean Reversion', symbol: 'BANKNIFTY', status: 'running', started_at: '2026-06-28T09:20:00', pnl: 6780 },
  { id: 'r4', strategy_id: 's4', strategy_name: 'Options Alpha', symbol: 'NIFTY', status: 'running', started_at: '2026-06-28T09:00:00', pnl: -2340 },
]

export const DEMO_TRADES: DemoTrade[] = [
  { id: 't1', symbol: 'NIFTY', side: 'BUY', quantity: 75, price: 24580, pnl: 3240, status: 'filled', timestamp: '2026-06-28T10:30:00', strategy: 'Momentum Pro' },
  { id: 't2', symbol: 'BANKNIFTY', side: 'SELL', quantity: 50, price: 52150, pnl: 1850, status: 'filled', timestamp: '2026-06-28T10:45:00', strategy: 'Mean Reversion' },
  { id: 't3', symbol: 'RELIANCE', side: 'BUY', quantity: 200, price: 2850, pnl: -1200, status: 'filled', timestamp: '2026-06-28T11:00:00', strategy: 'Scalper X' },
  { id: 't4', symbol: 'TCS', side: 'BUY', quantity: 100, price: 4120, pnl: 2800, status: 'filled', timestamp: '2026-06-28T11:30:00', strategy: 'Momentum Pro' },
  { id: 't5', symbol: 'NIFTY', side: 'SELL', quantity: 75, price: 24600, pnl: -450, status: 'filled', timestamp: '2026-06-28T12:00:00', strategy: 'Options Alpha' },
  { id: 't6', symbol: 'HDFCBANK', side: 'BUY', quantity: 150, price: 1680, pnl: 4200, status: 'filled', timestamp: '2026-06-28T12:30:00', strategy: 'Breakout Hunter' },
]

export const DEMO_BROKER_CREDENTIALS = [
  { broker: 'zerodha', name: 'Zerodha', connected_at: '2026-06-01T10:00:00', is_active: true },
  { broker: 'angel', name: 'Angel One', connected_at: '2026-06-15T14:00:00', is_active: true },
]

export const DEMO_BACKTEST_RESULT = {
  total_pnl: 184500,
  win_rate: 68.5,
  total_trades: 847,
  sharpe_ratio: 2.1,
  max_drawdown: -8.2,
  candles_analyzed: 152000,
  avg_win: 4250,
  avg_loss: -1820,
  largest_win: 28400,
  largest_loss: -12300,
  trades: DEMO_TRADES,
}

export const EQUITY_CURVE_POINTS = [
  100000, 101200, 102800, 101500, 103400, 105200, 104100,
  106800, 108300, 107500, 109800, 111200, 110400, 112900,
  114100, 113200, 115600, 117800, 116500, 118200, 120000,
  119100, 121400, 123000, 122200, 124500,
]
