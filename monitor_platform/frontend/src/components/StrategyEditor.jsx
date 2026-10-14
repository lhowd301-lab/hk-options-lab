 import React, { useState, useEffect } from 'react'
 import { Plus, Save, Trash2, Play, Check, AlertTriangle } from 'lucide-react'
 import { api } from '../api/api'
 
 const STRATEGY_OPTIONS = [
   { value: 'custom', label: '自定义策略' },
   { value: 'covered_call', label: '备兑看涨 (Covered Call)' },
   { value: 'protective_put', label: '保护性看跌 (Protective Put)' },
   { value: 'straddle', label: '跨式套利 (Straddle)' },
   { value: 'strangle', label: '宽跨式套利 (Strangle)' },
   { value: 'bull_call_spread', label: '牛市看涨价差' },
   { value: 'bear_put_spread', label: '熊市看跌价差' },
   { value: 'box_spread', label: '盒式套利 (Box Spread)' },
   { value: 'conversion', label: '转换套利 (Conversion)' },
   { value: 'reverse_conversion', label: '反向转换套利' },
 ]
 
 const DEFAULT_CONDITION_CODE = `# 策略条件代码
# 可用变量: quotes, stock_codes, trigger, reason, price, stock_code
# 设置 trigger=True 来产生信号

for code in stock_codes:
    q = quotes.get(code)
    if q and abs(q.get('change_pct', 0)) > 2:
        trigger = True
        reason = f"{code} 价格波动 {q.get('change_pct', 0):.1f}%"
        stock_code = code
        price = q.get('price', 0)
        break
`
 
 const DEFAULT_LEG = {
   stock_code: 'HK.00700',
   option_type: 'CALL',
   strike_price: 380,
   expiry_date: '',
   action: 'BUY',
   quantity: 1,
 }
 
 export default function StrategyEditor() {
   const [strategies, setStrategies] = useState([])
   const [editing, setEditing] = useState(null)
   const [saving, setSaving] = useState(false)
   const [error, setError] = useState(null)
   const [editingId, setEditingId] = useState(null)
 
   useEffect(() => { loadStrategies() }, [])
 
   async function loadStrategies() {
     try {
       const res = await api.getStrategies()
       setStrategies(res.strategies || [])
     } catch (e) {
       setError('加载策略失败')
     }
   }
 
   function newStrategy() {
     setEditing({
       name: '',
       description: '',
       strategy_type: 'custom',
       stock_codes: ['HK.00700'],
       legs: [],
       condition_code: DEFAULT_CONDITION_CODE,
       execution_code: '',
       is_active: false,
     })
     setEditingId(null)
   }
 
   function editStrategy(s) {
     setEditing({ ...s })
     setEditingId(s.id)
   }
 
   function updateField(key, value) {
     setEditing(prev => ({ ...prev, [key]: value }))
   }
 
   function addLeg() {
     setEditing(prev => ({
       ...prev,
       legs: [...prev.legs, { ...DEFAULT_LEG }]
     }))
   }
 
   function updateLeg(i, field, value) {
     setEditing(prev => {
       const legs = [...prev.legs]
       legs[i] = { ...legs[i], [field]: value }
       return { ...prev, legs }
     })
   }
 
   function removeLeg(i) {
     setEditing(prev => ({
       ...prev,
       legs: prev.legs.filter((_, idx) => idx !== i)
     }))
   }
 
   async function handleSave() {
     if (!editing.name.trim()) { setError('请输入策略名称'); return }
     setSaving(true)
     setError(null)
     try {
       if (editingId) {
         await api.updateStrategy(editingId, editing)
       } else {
         await api.createStrategy(editing)
       }
       await loadStrategies()
       setEditing(null)
       setEditingId(null)
     } catch (e) {
       setError('保存失败: ' + e.message)
     }
     setSaving(false)
   }
 
   async function handleDelete(id) {
     if (!confirm('确定删除该策略？')) return
     try {
       await api.deleteStrategy(id)
       await loadStrategies()
       if (editingId === id) { setEditing(null); setEditingId(null) }
     } catch (e) {
       setError('删除失败')
     }
   }
 
   return (
     <div className="grid-2">
       {/* 左侧: 策略列表 */}
       <div>
         <div className="card">
           <div className="card-header">
             <span className="card-title">策略列表</span>
             <button className="btn btn-primary btn-sm" onClick={newStrategy}>
               <Plus size={14} /> 新策略
             </button>
           </div>
 
           {strategies.length === 0 ? (
             <div className="empty-state">
               <AlertTriangle size={32} />
               <p>暂无策略</p>
               <button className="btn btn-primary mt-12" onClick={newStrategy}>
                 创建第一个策略
               </button>
             </div>
           ) : (
             <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
               {strategies.map(s => (
                 <div key={s.id}
                   style={{
                     padding: 12, borderRadius: 6,
                     background: 'var(--bg-primary)',
                     cursor: 'pointer',
                     border: editingId === s.id ? '1px solid var(--accent-blue)' : '1px solid transparent',
                   }}
                   onClick={() => editStrategy(s)}
                 >
                   <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                     <div>
                       <span style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</span>
                       <span className={`badge ${s.is_active ? 'badge-green' : 'badge-yellow'}`}
                             style={{ marginLeft: 8, fontSize: 10 }}>
                         {s.is_active ? '启用' : '停用'}
                       </span>
                     </div>
                     <button className="btn btn-danger btn-sm" onClick={(e) => { e.stopPropagation(); handleDelete(s.id) }}>
                       <Trash2 size={12} />
                     </button>
                   </div>
                   <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                     {STRATEGY_OPTIONS.find(o => o.value === s.strategy_type)?.label || s.strategy_type}
                     {s.stock_codes?.length ? ` · ${s.stock_codes.length}只股票` : ''}
                   </div>
                   {s.description && (
                     <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                       {s.description}
                     </div>
                   )}
                 </div>
               ))}
             </div>
           )}
         </div>
       </div>
 
       {/* 右侧: 编辑区域 */}
       <div>
         {editing ? (
           <div className="card">
             <div className="card-header">
               <span className="card-title">{editingId ? '编辑策略' : '新建策略'}</span>
               <div className="flex-row">
                 <button className="btn btn-success btn-sm" onClick={handleSave} disabled={saving}>
                   <Save size={14} /> {saving ? '保存中...' : '保存'}
                 </button>
                 <button className="btn btn-outline btn-sm" onClick={() => { setEditing(null); setEditingId(null) }}>
                   取消
                 </button>
               </div>
             </div>
 
             {error && (
               <div style={{ padding: 8, marginBottom: 12, background: 'rgba(239,68,68,0.1)', borderRadius: 6, fontSize: 13, color: 'var(--accent-red)' }}>
                 {error}
               </div>
             )}
 
             <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
               <div>
                 <label className="label">策略名称</label>
                 <input className="input" value={editing.name}
                   onChange={e => updateField('name', e.target.value)}
                   placeholder="输入策略名称" />
               </div>
 
               <div>
                 <label className="label">策略类型</label>
                 <select className="select" value={editing.strategy_type}
                   onChange={e => updateField('strategy_type', e.target.value)}>
                   {STRATEGY_OPTIONS.map(opt => (
                     <option key={opt.value} value={opt.value}>{opt.label}</option>
                   ))}
                 </select>
               </div>
 
               <div>
                 <label className="label">描述</label>
                 <input className="input" value={editing.description}
                   onChange={e => updateField('description', e.target.value)}
                   placeholder="策略描述" />
               </div>
 
               <div>
                 <label className="label">监控股票 (HK.XXXXX)</label>
                 <input className="input" value={editing.stock_codes.join(', ')}
                   onChange={e => updateField('stock_codes', e.target.value.split(/[,，\s]+/).filter(Boolean))}
                   placeholder="HK.00700, HK.09988" />
               </div>
 
               {/* 策略腿 */}
               <div>
                 <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                   <label className="label" style={{ margin: 0 }}>策略腿 (Legs)</label>
                   <button className="btn btn-outline btn-sm" onClick={addLeg}>
                     <Plus size={12} /> 添加腿
                   </button>
                 </div>
                 {editing.legs.map((leg, i) => (
                   <div key={i} style={{
                     padding: 10, background: 'var(--bg-primary)', borderRadius: 6, marginBottom: 8,
                   }}>
                     <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                       <select className="select" style={{ width: 80 }} value={leg.action}
                         onChange={e => updateLeg(i, 'action', e.target.value)}>
                         <option value="BUY">买入</option>
                         <option value="SELL">卖出</option>
                       </select>
                       <input className="input" style={{ width: 110 }} value={leg.stock_code}
                         onChange={e => updateLeg(i, 'stock_code', e.target.value)}
                         placeholder="HK.00700" />
                       <select className="select" style={{ width: 80 }} value={leg.option_type || ''}
                         onChange={e => updateLeg(i, 'option_type', e.target.value)}>
                         <option value="">正股</option>
                         <option value="CALL">看涨</option>
                         <option value="PUT">看跌</option>
                       </select>
                       <input className="input" style={{ width: 80 }} type="number" value={leg.strike_price || ''}
                         onChange={e => updateLeg(i, 'strike_price', parseFloat(e.target.value) || 0)}
                         placeholder="行权价" />
                       <input className="input" style={{ width: 50 }} type="number" value={leg.quantity}
                         onChange={e => updateLeg(i, 'quantity', parseInt(e.target.value) || 1)} />
                       <button className="btn btn-danger btn-sm" onClick={() => removeLeg(i)}>
                         <Trash2 size={12} />
                       </button>
                     </div>
                   </div>
                 ))}
               </div>
 
               {/* 条件代码 */}
               <div>
                 <label className="label">触发条件 (Python代码)</label>
                 <textarea className="textarea" value={editing.condition_code}
                   onChange={e => updateField('condition_code', e.target.value)}
                   rows={12} style={{ fontFamily: 'monospace', fontSize: 12 }} />
               </div>
             </div>
           </div>
         ) : (
           <div className="card" style={{ height: '100%' }}>
             <div className="empty-state" style={{ paddingTop: 60 }}>
               <Play size={36} />
               <p>选择左侧策略进行编辑，或创建新策略</p>
               <p style={{ fontSize: 12, marginTop: 8, color: 'var(--text-muted)' }}>
                 您可以编写 Python 条件代码来自定义策略触发逻辑
               </p>
             </div>
           </div>
         )}
       </div>
     </div>
   )
 }
