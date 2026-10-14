 import React, { useState, useEffect } from 'react'
 import { Activity, Play, Square, Bell, BellOff, AlertTriangle, Check } from 'lucide-react'
 import { api } from '../api/api'
 
 export default function ActiveMonitor({ ws, serverStatus, onRefreshStatus }) {
   const [rules, setRules] = useState([])
   const [alerts, setAlerts] = useState([])
   const [signals, setSignals] = useState([])
   const [newRule, setNewRule] = useState({ name: '', strategy_id: '', stock_codes: '', check_interval: 5 })
   const [showNewForm, setShowNewForm] = useState(false)
 
   useEffect(() => {
     loadData()
     const interval = setInterval(loadAlerts, 5000)
     return () => clearInterval(interval)
   }, [])
 
   async function loadData() {
     try {
       const [rulesRes, alertsRes, signalsRes] = await Promise.all([
         api.getMonitorRules(),
         api.getAlerts(),
         api.getSignals(),
       ])
       setRules(rulesRes.rules || [])
       setAlerts(alertsRes.alerts || [])
       setSignals(signalsRes.signals || [])
     } catch {}
   }
 
   async function loadAlerts() {
     try {
       const res = await api.getAlerts()
       setAlerts(res.alerts || [])
     } catch {}
   }
 
   async function toggleRule(ruleId, currentActive) {
     try {
       await api.toggleMonitorRule(ruleId, !currentActive)
       await loadData()
     } catch {}
   }
 
   async function handleStartMonitor() {
     await api.startMonitor()
     ws.startMonitor()
     onRefreshStatus()
   }
 
   async function handleStopMonitor() {
     await api.stopMonitor()
     ws.stopMonitor()
     onRefreshStatus()
   }
 
   async function createRule() {
     if (!newRule.name || !newRule.strategy_id) return
     try {
       await api.createMonitorRule({
         name: newRule.name,
         strategy_id: parseInt(newRule.strategy_id),
         stock_codes: newRule.stock_codes.split(/[,，\s]+/).filter(Boolean),
         check_interval: parseInt(newRule.check_interval) || 5,
       })
       setNewRule({ name: '', strategy_id: '', stock_codes: '', check_interval: 5 })
       setShowNewForm(false)
       await loadData()
     } catch {}
   }
 
   async function acknowledgeAlert(alertId) {
     try {
       await api.acknowledgeAlert(alertId)
       setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, acknowledged: 1 } : a))
     } catch {}
   }
 
   const unacknowledgedAlerts = alerts.filter(a => !a.acknowledged)
 
   return (
     <div>
       {/* 监控控制栏 */}
       <div className="card" style={{ marginBottom: 16 }}>
         <div className="card-header">
           <span className="card-title">监控控制</span>
           <div className="flex-row">
             {ws.monitorRunning ? (
               <button className="btn btn-danger btn-sm" onClick={handleStopMonitor}>
                 <Square size={14} /> 停止监控
               </button>
             ) : (
               <button className="btn btn-success btn-sm" onClick={handleStartMonitor}>
                 <Play size={14} /> 启动监控
               </button>
             )}
             <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
               富途: {serverStatus.futu_connected ? '已连接' : '模拟模式'}
             </span>
           </div>
         </div>
         <div style={{ display: 'flex', gap: 16, alignItems: 'center', fontSize: 13 }}>
           <span>状态: {ws.monitorRunning
             ? <span className="badge badge-green"><Activity size={12} /> 运行中</span>
             : <span className="badge badge-yellow">已停止</span>
           }</span>
           <span>告警: <span className={`badge ${unacknowledgedAlerts.length > 0 ? 'badge-red' : 'badge-green'}`}>
             {unacknowledgedAlerts.length}
           </span></span>
           <span>信号: {signals.length}</span>
         </div>
       </div>
 
       <div className="grid-2">
         {/* 左侧: 监控规则 */}
         <div>
           <div className="card" style={{ marginBottom: 16 }}>
             <div className="card-header">
               <span className="card-title">监控规则</span>
               <button className="btn btn-primary btn-sm" onClick={() => setShowNewForm(!showNewForm)}>
                 {showNewForm ? '取消' : '新建规则'}
               </button>
             </div>
 
             {showNewForm && (
               <div style={{ marginBottom: 12, padding: 12, background: 'var(--bg-primary)', borderRadius: 6 }}>
                 <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                   <input className="input" placeholder="规则名称" value={newRule.name}
                     onChange={e => setNewRule(p => ({ ...p, name: e.target.value }))} />
                   <input className="input" placeholder="策略ID" type="number" value={newRule.strategy_id}
                     onChange={e => setNewRule(p => ({ ...p, strategy_id: e.target.value }))} />
                   <input className="input" placeholder="股票代码 (逗号分隔)" value={newRule.stock_codes}
                     onChange={e => setNewRule(p => ({ ...p, stock_codes: e.target.value }))} />
                   <input className="input" placeholder="检查间隔(秒)" type="number" value={newRule.check_interval}
                     onChange={e => setNewRule(p => ({ ...p, check_interval: e.target.value }))} />
                   <button className="btn btn-success btn-sm" onClick={createRule}>创建规则</button>
                 </div>
               </div>
             )}
 
             {rules.length === 0 ? (
               <div className="empty-state">
                 <BellOff size={28} />
                 <p>暂无监控规则</p>
               </div>
             ) : (
               <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                 {rules.map(rule => (
                   <div key={rule.id} style={{
                     padding: 10, borderRadius: 6,
                     background: 'var(--bg-primary)',
                     display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                   }}>
                     <div>
                       <div style={{ fontSize: 13, fontWeight: 500 }}>
                         {rule.name}
                         <span className={`badge ${rule.is_active ? 'badge-green' : 'badge-yellow'}`}
                               style={{ marginLeft: 8, fontSize: 10 }}>
                           {rule.is_active ? '监控中' : '已暂停'}
                         </span>
                       </div>
                       <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                         {rule.stock_codes?.length || 0} 只股票 · 每{rule.check_interval || 5}秒
                       </div>
                     </div>
                     <button className={`toggle ${rule.is_active ? 'active' : ''}`}
                       onClick={() => toggleRule(rule.id, rule.is_active)} />
                   </div>
                 ))}
               </div>
             )}
           </div>
 
           {/* 信号记录 */}
           <div className="card">
             <div className="card-header">
               <span className="card-title">策略信号</span>
             </div>
             {signals.length === 0 ? (
               <div className="empty-state">
                 <AlertTriangle size={24} />
                 <p style={{ fontSize: 13 }}>暂无信号</p>
               </div>
             ) : (
               <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 400, overflowY: 'auto' }}>
                 {signals.map((s, i) => (
                   <div key={s.id || i} className="alert-item" style={{ borderLeftColor: s.signal_type === 'ENTRY' ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                     <div>
                       <div className="alert-title">{s.strategy_name}</div>
                       <div className="alert-desc">
                         [{s.signal_type}] {s.stock_code} @ {s.price?.toFixed(2)} - {s.reason}
                       </div>
                       <div className="alert-time">{s.timestamp}</div>
                     </div>
                   </div>
                 ))}
               </div>
             )}
           </div>
         </div>
 
         {/* 右侧: 告警事件 */}
         <div>
           <div className="card" style={{ height: '100%' }}>
             <div className="card-header">
               <span className="card-title">
                 告警事件
                 {unacknowledgedAlerts.length > 0 && (
                   <span className="badge badge-red" style={{ marginLeft: 8 }}>{unacknowledgedAlerts.length} 未确认</span>
                 )}
               </span>
             </div>
             {alerts.length === 0 ? (
               <div className="empty-state">
                 <Bell size={28} />
                 <p>暂无告警</p>
                 <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>监控到套利机会时会在此显示告警</p>
               </div>
             ) : (
               <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 600, overflowY: 'auto' }}>
                 {alerts.map((a, i) => (
                   <div key={a.id || i} className="alert-item"
                     style={{
                       borderLeftColor: a.signal_type === 'ENTRY' ? 'var(--accent-green)' : 'var(--accent-red)',
                       opacity: a.acknowledged ? 0.6 : 1,
                     }}>
                     <div style={{ flex: 1 }}>
                       <div className="alert-title">{a.strategy_name}</div>
                       <div className="alert-desc">
                         <span className={`badge ${a.signal_type === 'ENTRY' ? 'badge-green' : 'badge-red'}`}
                               style={{ marginRight: 6, fontSize: 10 }}>
                           {a.signal_type}
                         </span>
                         {a.stock_name || a.stock_code} @ {a.price?.toFixed(2)}
                       </div>
                       <div className="alert-desc">{a.reason}</div>
                       <div className="alert-time">{a.timestamp}</div>
                     </div>
                     {!a.acknowledged && (
                       <button className="btn btn-outline btn-sm" onClick={() => acknowledgeAlert(a.id)}
                         title="确认告警">
                         <Check size={12} />
                       </button>
                     )}
                   </div>
                 ))}
               </div>
             )}
           </div>
         </div>
       </div>
     </div>
   )
 }
