 import React, { useState, useEffect } from 'react'
 import {
   LayoutDashboard, TrendingUp, BarChart3, Activity,
   Bell, Play, Square, RefreshCw, Wifi, WifiOff
 } from 'lucide-react'
 import { useWebSocket } from './hooks/useWebSocket'
 import Dashboard from './components/Dashboard'
 import StrategyEditor from './components/StrategyEditor'
 import BacktestResults from './components/BacktestResults'
 import ActiveMonitor from './components/ActiveMonitor'
 import { api } from './api/api'
 
 const TABS = [
   { id: 'dashboard', label: '行情仪表盘', icon: LayoutDashboard },
   { id: 'strategies', label: '策略管理', icon: TrendingUp },
   { id: 'backtest', label: '回测分析', icon: BarChart3 },
   { id: 'monitor', label: '实时监控', icon: Activity },
 ]
 
 export default function App() {
   const [activeTab, setActiveTab] = useState('dashboard')
   const [serverStatus, setServerStatus] = useState({ futu_connected: false, monitor_running: false })
   const ws = useWebSocket()
 
   useEffect(() => {
     checkHealth()
     const interval = setInterval(checkHealth, 10000)
     return () => clearInterval(interval)
   }, [])
 
   async function checkHealth() {
     try {
       const res = await api.health()
       setServerStatus(res)
     } catch {
       setServerStatus({ futu_connected: false, monitor_running: false })
     }
   }
 
   function renderPage() {
     switch (activeTab) {
       case 'dashboard':
         return <Dashboard quotes={ws.quotes} onRefresh={ws.refreshQuotes} ws={ws} />
       case 'strategies':
         return <StrategyEditor />
       case 'backtest':
         return <BacktestResults />
       case 'monitor':
         return (
           <ActiveMonitor
             ws={ws}
             serverStatus={serverStatus}
             onRefreshStatus={checkHealth}
           />
         )
       default:
         return null
     }
   }
 
   return (
     <div className="layout">
       {/* Sidebar */}
       <nav className="sidebar">
         {TABS.map((tab) => (
           <button
             key={tab.id}
             className={`sidebar-btn ${activeTab === tab.id ? 'active' : ''}`}
             onClick={() => setActiveTab(tab.id)}
             title={tab.label}
           >
             <tab.icon size={20} />
           </button>
         ))}
         <div style={{ flex: 1 }} />
         <button
           className="sidebar-btn"
           onClick={ws.refreshQuotes}
           title="刷新行情"
         >
           <RefreshCw size={18} />
         </button>
       </nav>
 
       {/* Main */}
       <div className="main-content">
         <header className="header">
           <span className="header-title">港股期权套利 · 回测监控平台</span>
           <div className="header-status">
             {ws.monitorRunning && (
               <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                 <span className="status-dot running" />
                 监控运行中
               </span>
             )}
             <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
               {ws.connected ? (
                 <Wifi size={14} className="price-up" />
               ) : (
                 <WifiOff size={14} className="price-down" />
               )}
               {ws.connected ? '已连接' : '重连中...'}
             </span>
             <span className={`badge ${serverStatus.futu_connected ? 'badge-green' : 'badge-yellow'}`}>
               富途{serverStatus.futu_connected ? '已连' : '模拟'}
             </span>
           </div>
         </header>
 
         <div className="page">
           <div className="page-tabs">
             {TABS.map((tab) => (
               <button
                 key={tab.id}
                 className={`page-tab ${activeTab === tab.id ? 'active' : ''}`}
                 onClick={() => setActiveTab(tab.id)}
               >
                 {tab.label}
               </button>
             ))}
           </div>
           {renderPage()}
         </div>
       </div>
     </div>
   )
 }
