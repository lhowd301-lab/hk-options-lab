 import React, { useState } from 'react'
 import { ChevronDown, ChevronUp } from 'lucide-react'
 
 export default function OptionsChain({ data, stockName, loading }) {
   const [showCalls, setShowCalls] = useState(true)
   const [showPuts, setShowPuts] = useState(true)
 
   if (loading) {
     return <div className="card"><div className="empty-state">加载期权数据...</div></div>
   }
 
   if (!data || (!data.calls?.length && !data.puts?.length)) {
     return (
       <div className="card">
         <div className="card-header">
           <span className="card-title">{stockName} - 期权链</span>
         </div>
         <div className="empty-state">暂无期权数据</div>
       </div>
     )
   }
 
   function renderOptions(options, type) {
     return options.map((opt, i) => (
       <div key={i} className="option-item">
         <span>
           <span className={`badge ${opt.option_type === 'CALL' ? 'badge-green' : 'badge-red'}`}
                 style={{ marginRight: 6, fontSize: 10 }}>
             {opt.option_type}
           </span>
           {opt.strike_price.toFixed(1)}
         </span>
         <span style={{ fontFamily: 'monospace' }}>
           {opt.last_price.toFixed(2)}
           <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 4 }}>
             IV:{opt.implied_vol.toFixed(1)}
           </span>
         </span>
       </div>
     ))
   }
 
   return (
     <div className="card">
       <div className="card-header">
         <span className="card-title">{stockName} - 期权链</span>
         <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
           到期: {data.expiry_date || '近月'}
         </span>
       </div>
 
       {/* 看涨期权 */}
       <div style={{ marginBottom: 8 }}>
         <div
           style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '4px 0', marginBottom: 4 }}
           onClick={() => setShowCalls(!showCalls)}
         >
           {showCalls ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
           <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-green)' }}>
             看涨期权 ({data.calls?.length || 0})
           </span>
         </div>
         {showCalls && data.calls && (
           <div className="options-grid">
             {renderOptions(data.calls, 'CALL')}
           </div>
         )}
       </div>
 
       {/* 看跌期权 */}
       <div>
         <div
           style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '4px 0', marginBottom: 4 }}
           onClick={() => setShowPuts(!showPuts)}
         >
           {showPuts ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
           <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-red)' }}>
             看跌期权 ({data.puts?.length || 0})
           </span>
         </div>
         {showPuts && data.puts && (
           <div className="options-grid">
             {renderOptions(data.puts, 'PUT')}
           </div>
         )}
       </div>
     </div>
   )
 }
