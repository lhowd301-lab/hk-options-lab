 import { useState, useEffect, useRef, useCallback } from 'react'
 
 export function useWebSocket() {
   const [connected, setConnected] = useState(false)
   const [quotes, setQuotes] = useState({})
   const [alerts, setAlerts] = useState([])
   const [monitorRunning, setMonitorRunning] = useState(false)
   const wsRef = useRef(null)
   const reconnectRef = useRef(null)
 
   const connect = useCallback(() => {
     if (wsRef.current?.readyState === WebSocket.OPEN) return
 
     const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
     const host = window.location.host
     const wsUrl = `${protocol}//${host}/ws`
 
     const ws = new WebSocket(wsUrl)
     wsRef.current = ws
 
     ws.onopen = () => {
       setConnected(true)
       if (reconnectRef.current) {
         clearTimeout(reconnectRef.current)
         reconnectRef.current = null
       }
     }
 
     ws.onmessage = (event) => {
       try {
         const msg = JSON.parse(event.data)
         switch (msg.type) {
           case 'quote':
             setQuotes(msg.data)
             break
           case 'alert':
             setAlerts((prev) => [msg.data, ...prev].slice(0, 200))
             break
           case 'status':
             setMonitorRunning(msg.data.monitor)
             break
         }
       } catch (e) {
         console.error('WS parse error:', e)
       }
     }
 
     ws.onclose = () => {
       setConnected(false)
       wsRef.current = null
       reconnectRef.current = setTimeout(connect, 3000)
     }
 
     ws.onerror = () => {
       ws.close()
     }
   }, [])
 
   const send = useCallback((data) => {
     if (wsRef.current?.readyState === WebSocket.OPEN) {
       wsRef.current.send(JSON.stringify(data))
     }
   }, [])
 
   const refreshQuotes = useCallback(() => {
     send({ type: 'refresh_quotes' })
   }, [send])
 
   const startMonitor = useCallback(() => {
     send({ type: 'start_monitor' })
     setMonitorRunning(true)
   }, [send])
 
   const stopMonitor = useCallback(() => {
     send({ type: 'stop_monitor' })
     setMonitorRunning(false)
   }, [send])
 
   const subscribeQuotes = useCallback((codes) => {
     send({ type: 'subscribe_quotes', codes })
   }, [send])
 
   useEffect(() => {
     connect()
     return () => {
       if (wsRef.current) wsRef.current.close()
       if (reconnectRef.current) clearTimeout(reconnectRef.current)
     }
   }, [connect])
 
   return {
     connected,
     quotes,
     alerts,
     monitorRunning,
     refreshQuotes,
     startMonitor,
     stopMonitor,
     subscribeQuotes,
   }
 }
