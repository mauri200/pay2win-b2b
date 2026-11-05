import { useEffect, useMemo, useRef, useState } from 'react'
import { AllCommunityModule } from 'ag-grid-community'
import { AgGridProvider, AgGridReact } from 'ag-grid-react'

const modules = [AllCommunityModule]
const LABEL = { completado: 'Completed', rechazado: 'Rejected', esperando_aprobacion: 'Awaiting approval',
  error: 'Error', error_captura: 'Capture failed', cancelado: 'Canceled' }
const COLOR = { completado: '#16a34a', rechazado: '#dc2626', esperando_aprobacion: '#d97706' }

export default function App() {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const grid = useRef(null)

  useEffect(() => {
    const load = () => fetch('/api/orders').then(r => r.json()).then(setRows).catch(() => {})
    load()
    const id = setInterval(load, 3000)   // live refresh
    return () => clearInterval(id)
  }, [])

  const cols = useMemo(() => [
    { field: 'creado', headerName: 'Time', width: 100 },
    { field: 'producto', headerName: 'Product', flex: 2, filter: true },
    { field: 'monto', headerName: 'USD', width: 110, filter: 'agNumberColumnFilter', valueFormatter: p => p.value == null ? '' : '$' + Number(p.value).toFixed(2) },
    { field: 'financiamiento', headerName: 'Financing', width: 120 },
    { field: 'estado', headerName: 'Status', width: 180, filter: true,
      valueFormatter: p => LABEL[p.value] || p.value,
      cellStyle: p => ({ color: COLOR[p.value] || 'inherit', fontWeight: 600 }) },
    { field: 'order_id', headerName: 'PayPal order', width: 190 },
    { field: 'mensaje', headerName: 'Details', flex: 3, wrapText: true, autoHeight: true },
  ], [])

  const paid = rows.filter(r => r.estado === 'completado')
  const total = paid.reduce((s, r) => s + (r.monto || 0), 0)

  return (
    <AgGridProvider modules={modules}>
      <div style={{ padding: 24 }}>
        <h1 style={{ margin: 0 }}>Pay2Win payments dashboard</h1>
        <p style={{ color: '#6b7280' }}>
          {rows.length} orders · {paid.length} completed · ${total.toFixed(2)} paid · refreshes every 3 s
        </p>
        <div style={{ display: 'flex', gap: 8, margin: '12px 0' }}>
          <input placeholder="Quick filter..." value={q} onChange={e => setQ(e.target.value)}
                 style={{ flex: 1, padding: 8, borderRadius: 8, border: '1px solid #e5e7eb' }} />
          <button onClick={() => grid.current.api.exportDataAsCsv()}
                  style={{ padding: '8px 14px', borderRadius: 8, border: 0, background: '#111827', color: '#fff', cursor: 'pointer' }}>
            Export CSV
          </button>
        </div>
        <div style={{ height: 520 }}>
          <AgGridReact ref={grid} rowData={rows} columnDefs={cols} quickFilterText={q}
                       pagination paginationPageSize={10}
                       defaultColDef={{ sortable: true, resizable: true }}
                       getRowId={p => p.data.thread_id} />
        </div>
      </div>
    </AgGridProvider>
  )
}
