 import React, { useState, useEffect } from 'react'
 import { Play, BarChart3, TrendingUp, TrendingDown, RefreshCw, Trash2 } from 'lucide-react'
 import { api } from '../api/api'
 import {
   LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
   ResponsiveContainer, Area, AreaChart
 } from 'recharts'
 
 export default function BacktestResults() {
   const [strategies, setStrategies] = useState([])
   const [results, setResults] = useState([])
   const [selectedStrategy, setSelectedStrategy] = useState('')
   const [backtestParams, setBacktestParams] = useState({
     start_date: '2024-01-01',
     end_date: '2024-12-31',
     initial_capital: 1000000,
     commission_rate: 0.0008,
   })
   const [running, setRunning] = useState(false)
   const [activeResult, setActiveResult] = useState(null)
 
   useEffect(() => {
     api.getStrategies().then(r => setStrategies(r.strategies || [])).catch(() => {})
     loadResults()
   }, [])
 
   async function loadResults() {
     try {
       const r = await api.getBacktestResults()
       setResults(r.results || [])
     } catch {}
   }
 
   async function runBacktest() {
     if (!selectedStrategy) return
     setRunning(true)
     try {
       const res = await api.runBacktest({
         strategy_id: parseInt(selectedStrategy),
         ...backtestParams,
       })
       setActiveResult(res.result)
       await loadResults()
     } catch (e) {
       alert('回测失败: ' + e.message)
     }
     setRunning(false)
   }

   async function handleDelete(id) {
     if (!window.confirm("确定删除此回测记录?")) return
     try {
       await api.deleteBacktestResult(id)
       await loadResults()
       if (activeResult?.id === id) setActiveResult(null)
     } catch (err) {
       console.error("Delete failed:", err)
     }
   }

   function viewResult(r) {
     setActiveResult(r)
   }
 
   return (
     <div className="grid-2">
       {/* 左侧: 参数 & 结果列表 */}
       <div>
         <div className="card" style={{ marginBottom: 16 }}>
           <div className="card-header">
             <span className="card-title">回测参数</span>
           </div>
           <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
             <div>
               <label className="label">选择策略</label>
               <select className="select" value={selectedStrategy}
                 onChange={e => setSelectedStrategy(e.target.value)}>
                 <option value="">-- 选择策略 --</option>
                 {strategies.map(s => (
                   <option key={s.id} value={s.id}>{s.name}</option>
                 ))}
               </select>
             </div>
             <div className="flex-row">
               <div style={{ flex: 1 }}>
                 <label className="label">开始日期</label>
                 <input className="input" type="date" value={backtestParams.start_date}
                   onChange={e => setBacktestParams(p => ({ ...p, start_date: e.target.value }))} />
               </div>
               <div style={{ flex: 1 }}>
                 <label className="label">结束日期</label>
                 <input className="input" type="date" value={backtestParams.end_date}
                   onChange={e => setBacktestParams(p => ({ ...p, end_date: e.target.value }))} />
               </div>
             </div>
             <div className="flex-row">
               <div style={{ flex: 1 }}>
                 <label className="label">初始资金 (HKD)</label>
                 <input className="input" type="number" value={backtestParams.initial_capital}
                   onChange={e => setBacktestParams(p => ({ ...p, initial_capital: parseFloat(e.target.value) || 0 }))} />
               </div>
               <div style={{ flex: 1 }}>
                 <label className="label">手续费率</label>
                 <input className="input" type="number" step="0.0001" value={backtestParams.commission_rate}
                   onChange={e => setBacktestParams(p => ({ ...p, commission_rate: parseFloat(e.target.value) || 0 }))} />
               </div>
             </div>
             <button className="btn btn-primary" onClick={runBacktest} disabled={running || !selectedStrategy}>
               {running ? '回测执行中...' : <><Play size={14} /> 执行回测</>}
             </button>
           </div>
         </div>
 
         <div className="card">
           <div className="card-header">
             <span className="card-title">历史回测结果</span>
             <button className="btn btn-outline btn-sm" onClick={loadResults}>
               <RefreshCw size={12} />
             </button>
           </div>
           {results.length === 0 ? (
             <div className="empty-state">
               <BarChart3 size={28} />
               <p style={{ fontSize: 13 }}>暂无回测记录</p>
             </div>
           ) : (
             <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
               {results.map(r => (
                 <div key={r.id}
                   onClick={() => viewResult(r)}
                   style={{
                     padding: 10, borderRadius: 6, cursor: 'pointer',
                     background: activeResult?.id === r.id ? 'rgba(59,130,246,0.1)' : 'var(--bg-primary)',
                     border: activeResult?.id === r.id ? '1px solid var(--accent-blue)' : '1px solid transparent',
                   }}>
                   <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                     <div style={{ fontSize: 13, fontWeight: 600 }}>{r.strategy_name}</div>
                     <button onClick={(e) => { e.stopPropagation(); handleDelete(r.id) }}
                       style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 2 }}
                       title="删除此回测记录">
                       <Trash2 size={14} />
                     </button>
                   </div>
                   <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                     {r.start_date} ~ {r.end_date}
                   </div>
                   <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 12 }}>
                     <span>收益: <span className={r.total_return >= 0 ? 'price-up' : 'price-down'}>{r.total_return.toFixed(1)}%</span></span>
                     <span>夏普: {r.sharpe_ratio?.toFixed(2) || 'N/A'}</span>
                     <span>交易: {r.total_trades || 0}笔</span>
                   </div>
                 </div>
               ))}
             </div>
           )}
         </div>
       </div>
 
       {/* 右侧: 回测详情 */}
       <div>
         {activeResult ? (
           <div>
             {/* 绩效指标 */}
             <div className="grid-2" style={{ marginBottom: 16 }}>
               <div className="card stat-card">
                 <div className="stat-label">总收益率</div>
                 <div className={`stat-value ${activeResult.total_return >= 0 ? 'price-up' : 'price-down'}`}>
                   {activeResult.total_return >= 0 ? '+' : ''}{activeResult.total_return.toFixed(2)}%
                 </div>
               </div>
               <div className="card stat-card">
                 <div className="stat-label">年化收益率</div>
                 <div className={`stat-value ${activeResult.annual_return >= 0 ? 'price-up' : 'price-down'}`}>
                   {activeResult.annual_return >= 0 ? '+' : ''}{activeResult.annual_return.toFixed(2)}%
                 </div>
               </div>
               <div className="card stat-card">
                 <div className="stat-label">最大回撤</div>
                 <div className="stat-value price-down">{activeResult.max_drawdown.toFixed(2)}%</div>
               </div>
               <div className="card stat-card">
                 <div className="stat-label">夏普比率</div>
                 <div className="stat-value" style={{ color: activeResult.sharpe_ratio > 1 ? 'var(--accent-green)' : 'var(--accent-yellow)' }}>
                   {activeResult.sharpe_ratio.toFixed(2)}
                 </div>
               </div>
               <div className="card stat-card">
                 <div className="stat-label">胜率</div>
                 <div className="stat-value">{activeResult.win_rate.toFixed(1)}%</div>
               </div>
               <div className="card stat-card">
                 <div className="stat-label">交易次数</div>
                 <div className="stat-value">{activeResult.total_trades || 0}</div>
               </div>
             </div>
 
             {/* 净值曲线 */}
             <div className="card" style={{ marginBottom: 16 }}>
               <div className="card-header">
                 <span className="card-title">净值曲线</span>
               </div>
               {activeResult.equity_curve?.length > 0 ? (
                 <ResponsiveContainer width="100%" height={240}>
                   <AreaChart data={activeResult.equity_curve}>
                     <defs>
                       <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                         <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                         <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                       </linearGradient>
                     </defs>
                     <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                     <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#64748b' }} />
                     <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
                     <Tooltip
                       contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }}
                       labelStyle={{ color: '#f1f5f9' }}
                     />
                     <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="url(#colorEquity)" strokeWidth={2} />
                   </AreaChart>
                 </ResponsiveContainer>
               ) : (
                 <div className="empty-state" style={{ height: 200 }}>
                   <p>无净值数据</p>
                 </div>
               )}
             </div>
 
             {/* 交易记录 */}
             <div className="card">
               <div className="card-header">
                 <span className="card-title">交易记录 ({activeResult.trades?.length || 0})</span>
               </div>
               <div className="scroll-x">
                 <table className="stock-table">
                   <thead>
                     <tr>
                       <th>日期</th>
                       <th>股票</th>
                       <th>方向</th>
                       <th>价格</th>
                       <th>数量</th>
                       <th>累计盈亏</th>
                     </tr>
                   </thead>
                   <tbody>
                     {activeResult.trades?.slice(-50).map((t, i) => (
                       <tr key={i}>
                         <td style={{ fontSize: 12 }}>{t.date}</td>
                         <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.stock_code?.replace('HK.', '')}</td>
                         <td>
                           <span className={`badge ${t.action === 'BUY' ? 'badge-green' : 'badge-red'}`}>
                             {t.action}
                           </span>
                         </td>
                         <td>{t.price?.toFixed(2)}</td>
                         <td>{t.quantity}</td>
                         <td className={t.total_pnl >= 0 ? 'price-up' : 'price-down'}>
                           {t.total_pnl >= 0 ? '+' : ''}{t.total_pnl?.toFixed(2)}
                         </td>
                       </tr>
                     ))}
                   </tbody>
                 </table>
               </div>
             </div>
           </div>
         ) : (
           <div className="card" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
             <div className="empty-state">
               <TrendingUp size={36} />
               <p>选择策略并执行回测</p>
               <p style={{ fontSize: 12, marginTop: 8, color: 'var(--text-muted)' }}>
                 或点击左侧历史回测结果查看详情
               </p>
             </div>
           </div>
         )}
       </div>
     </div>
   )
 }
