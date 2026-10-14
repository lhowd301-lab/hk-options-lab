 const API_BASE = '/api'
 
 async function request(path, options = {}) {
   const url = `${API_BASE}${path}`
   const res = await fetch(url, {
     headers: { 'Content-Type': 'application/json', ...options.headers },
     ...options,
   })
   if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
   return res.json()
 }
 
 export const api = {
   // 行情
   getQuotes: () => request('/quotes'),
   getQuote: (code) => request(`/quotes/${code}`),
   getOptionsChain: (code, expiry) =>
     request(`/options/${code}${expiry ? `?expiry=${expiry}` : ''}`),
 
   // 策略
   getStrategies: () => request('/strategies'),
   getStrategy: (id) => request(`/strategies/${id}`),
   createStrategy: (data) =>
     request('/strategies', { method: 'POST', body: JSON.stringify(data) }),
   updateStrategy: (id, data) =>
     request(`/strategies/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
   deleteStrategy: (id) =>
     request(`/strategies/${id}`, { method: 'DELETE' }),
   identifyStrategy: (name, desc, code, legs) =>
     request('/strategies/identify', {
       method: 'POST',
       body: JSON.stringify({ name, description: desc, code, legs }),
     }),
 
   // 回测
   runBacktest: (data) =>
     request('/backtest', { method: 'POST', body: JSON.stringify(data) }),
   deleteBacktestResult: (id) => request('/backtest/results/' + id, { method: 'DELETE' }),
  getBacktestResults: (strategyId) =>
     request(`/backtest/results${strategyId ? `?strategy_id=${strategyId}` : ''}`),
 
   // 监控
   getMonitorRules: () => request('/monitor/rules'),
   createMonitorRule: (data) =>
     request('/monitor/rules', { method: 'POST', body: JSON.stringify(data) }),
   toggleMonitorRule: (id, active) =>
     request(`/monitor/rules/${id}/toggle`, {
       method: 'POST',
       body: JSON.stringify({ is_active: active }),
     }),
   startMonitor: () => request('/monitor/start', { method: 'POST' }),
   stopMonitor: () => request('/monitor/stop', { method: 'POST' }),
   getMonitorStatus: () => request('/monitor/status'),
 
   // 信号 & 告警
   getSignals: (strategyId) =>
     request(`/signals${strategyId ? `?strategy_id=${strategyId}` : ''}`),
   getAlerts: () => request('/alerts'),
   acknowledgeAlert: (id) =>
     request(`/alerts/${id}/acknowledge`, { method: 'POST' }),
 
   // 数据
   refreshData: () => request('/data/refresh'),
   health: () => request('/health'),
 }
