import React, { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, RefreshCw } from 'lucide-react'
import { api } from '../api/api'
import OptionsChain from './OptionsChain'

const STOCK_META = {
  "HK.00700": { name: "\u817e\u8baf\u63a7\u80a1", sector: "\u4e92\u8054\u7f51" },
  "HK.09988": { name: "\u963f\u91cc\u5df4\u5df4", sector: "\u7535\u5546" },
  "HK.03690": { name: "\u7f8e\u56e2", sector: "\u672c\u5730\u751f\u6d3b" },
  "HK.01810": { name: "\u5c0f\u7c73\u96c6\u56e2", sector: "\u6d88\u8d39\u7535\u5b50" },
  "HK.09618": { name: "\u4eac\u4e1c\u96c6\u56e2", sector: "\u7535\u5546" },
  "HK.09961": { name: "\u643a\u7a0b\u96c6\u56e2", sector: "\u65c5\u6e38" },
  "HK.09888": { name: "\u767e\u5ea6\u96c6\u56e2", sector: "AI/\u641c\u7d22" },
  "HK.01024": { name: "\u5feb\u624b", sector: "\u77ed\u89c6\u9891" },
  "HK.09999": { name: "\u7f51\u6613", sector: "\u6e38\u620f" },
  "HK.02015": { name: "\u7406\u60f3\u6c7d\u8f66", sector: "\u65b0\u80fd\u6e90\u8f66" },
  "HK.09866": { name: "\u851a\u6765", sector: "\u65b0\u80fd\u6e90\u8f66" },
  "HK.09626": { name: "\u54d4\u54e9\u54d4\u54e9", sector: "\u89c6\u9891" },
  "HK.03888": { name: "\u91d1\u5c71\u8f6f\u4ef6", sector: "\u8f6f\u4ef6" },
  "HK.06618": { name: "\u4eac\u4e1c\u5065\u5eb7", sector: "\u533b\u7597\u5065\u5eb7" },
  "HK.00020": { name: "\u5546\u6c64\u79d1\u6280", sector: "AI" },
  "HK.03033": { name: "\u6052\u751f\u79d1\u6280ETF", sector: "ETF" },
}

export default function Dashboard({ quotes, onRefresh, ws }) {
  const [selectedStock, setSelectedStock] = useState(null)
  const [optionsData, setOptionsData] = useState(null)
  const [loadingOptions, setLoadingOptions] = useState(false)

  const quoteList = Object.values(quotes).filter(q => q.code && q.price)

  async function handleSelectStock(code) {
    setSelectedStock(code)
    setLoadingOptions(true)
    try {
      const res = await api.getOptionsChain(code.replace('HK.', ''))
      setOptionsData(res)
    } catch (e) {
      console.error('Failed to fetch options:', e)
      setOptionsData(null)
    }
    setLoadingOptions(false)
  }

  if (quoteList.length === 0) {
    return (
      <div className="empty-state" style={{ marginTop: 40 }}>
        <RefreshCw size={48} />
        <p style={{ marginTop: 12 }}>{"\u6b63\u5728\u52a0\u8f7d\u884c\u60c5\u6570\u636e..."}</p>
        <button className="btn btn-primary mt-12" onClick={onRefresh}>
          <RefreshCw size={14} /> {"\u624b\u52a8\u5237\u65b0"}
        </button>
      </div>
    )
  }

  const upCount = quoteList.filter(q => q.change_pct > 0).length
  const downCount = quoteList.filter(q => q.change_pct < 0).length
  const avgChange = quoteList.reduce((s, q) => s + (q.change_pct || 0), 0) / quoteList.length

  return (
    <div>
      <div className="grid-4" style={{ marginBottom: 16 }}>
        <div className="card stat-card">
          <div className="stat-label">{"\u6052\u751f\u79d1\u6280\u6210\u4efd"}</div>
          <div className="stat-value">{quoteList.length}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-label">{"\u4e0a\u6da8"}</div>
          <div className="stat-value price-up">{upCount}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-label">{"\u4e0b\u8dcc"}</div>
          <div className="stat-value price-down">{downCount}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-label">{"\u5e73\u5747\u6da8\u8dcc\u5e45"}</div>
          <div className={"stat-value " + (avgChange >= 0 ? "price-up" : "price-down")}>
            {avgChange >= 0 ? "+" : ""}{avgChange.toFixed(2)}%
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">{"\u6052\u751f\u79d1\u6280\u6210\u4efd\u80a1\u5b9e\u65f6\u884c\u60c5"}</span>
            <button className="btn btn-outline btn-sm" onClick={onRefresh}>
              <RefreshCw size={12} /> {"\u5237\u65b0"}
            </button>
          </div>
          <div className="scroll-x">
            <table className="stock-table">
              <thead>
                <tr>
                  <th>{"\u4ee3\u7801"}</th>
                  <th>{"\u540d\u79f0"}</th>
                  <th>{"\u6700\u65b0\u4ef7"}</th>
                  <th>{"\u6da8\u8dcc\u5e45"}</th>
                  <th>{"\u6700\u9ad8"}</th>
                  <th>{"\u6700\u4f4e"}</th>
                  <th>{"\u6210\u4ea4\u91cf"}</th>
                  <th>{"\u671f\u6743"}</th>
                </tr>
              </thead>
              <tbody>
                {quoteList.map((q) => {
                  const meta = STOCK_META[q.code] || {}
                  const isUp = q.change_pct > 0
                  const isDown = q.change_pct < 0
                  return (
                    <tr key={q.code}>
                      <td style={{ fontFamily: "monospace", fontSize: 12 }}>{q.code.replace("HK.", "")}</td>
                      <td>
                        <div>{meta.name || q.code}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{meta.sector || ""}</div>
                      </td>
                      <td className={isUp ? "price-up" : isDown ? "price-down" : ""} style={{ fontWeight: 600 }}>
                        {q.price.toFixed(2)}
                      </td>
                      <td>
                        <span className={"badge " + (isUp ? "badge-green" : isDown ? "badge-red" : "")}
                          style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                          {isUp ? <TrendingUp size={12} /> : isDown ? <TrendingDown size={12} /> : null}
                          {q.change_pct >= 0 ? "+" : ""}{q.change_pct.toFixed(2)}%
                        </span>
                      </td>
                      <td className="price-up">{q.high_price.toFixed(2)}</td>
                      <td className="price-down">{q.low_price.toFixed(2)}</td>
                      <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        {(q.volume / 10000).toFixed(0)}{"\u4e07"}
                      </td>
                      <td>
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => handleSelectStock(q.code)}
                        >
                          {"\u671f\u6743\u94fe"}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          {selectedStock && optionsData ? (
            <OptionsChain
              data={optionsData}
              stockName={STOCK_META[selectedStock]?.name || selectedStock}
              loading={loadingOptions}
            />
          ) : (
            <div className="card" style={{ height: "100%" }}>
              <div className="card-header">
                <span className="card-title">{"\u671f\u6743\u94fe"}</span>
              </div>
              <div className="empty-state">
                <TrendingUp size={36} />
                <p>{"\u70b9\u51fb\u67d0\u53ea\u80a1\u7968\u7684\u201c\u671f\u6743\u94fe\u201d\u6309\u94ae\u67e5\u770b\u8be6\u60c5"}</p>
                <p style={{ fontSize: 12, marginTop: 8, color: "var(--text-muted)" }}>
                  {"\u5305\u542b\u6240\u6709\u5230\u671f\u65e5\u548c\u884c\u6743\u4ef7\u7684\u770b\u6da8/\u770b\u8dcc\u671f\u6743"}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}