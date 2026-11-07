import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AllCommunityModule, themeQuartz } from 'ag-grid-community'
import { AgGridProvider, AgGridReact } from 'ag-grid-react'
import {
  ArrowRight, ArrowUpRight, Bank, ChartBar, ChartLineUp, ChatCircleText,
  Check, CheckCircle, CreditCard, Cube, Fingerprint, GlobeHemisphereWest, Lightning,
  ListChecks, LockKey, Package, QrCode, Receipt, Robot, SealCheck, ShieldCheck,
  Sparkle, SquaresFour, TrendUp, Truck, Wallet, WarningCircle,
} from '@phosphor-icons/react'

const modules = [AllCommunityModule]

const SUBAGENTS = ['procurement', 'customs', 'logistics', 'compliance', 'treasury', 'payments']
const LABEL = {
  delegado: 'Delegated', abastecimiento_ok: 'Sourced', tesoreria_ok: 'Treasury ok',
  esperando_aprobacion: 'Awaiting approval', aprobado: 'Approved', completado: 'Completed',
  rechazado: 'Rejected', cancelado: 'Canceled', error: 'Error', error_captura: 'Capture failed',
}
const COLOR = { completado: '#16a34a', esperando_aprobacion: '#d97706', rechazado: '#dc2626', cancelado: '#6b7280' }

const usd = p => p.value == null ? '' : '$' + Number(p.value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const fmt = v => '$' + Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const gridTheme = themeQuartz.withParams({
  accentColor: '#2563EB',
  backgroundColor: '#FFFFFF',
  foregroundColor: '#1E293B',
  borderColor: 'rgba(148, 163, 184, 0.28)',
  chromeBackgroundColor: '#F8FAFC',
  headerBackgroundColor: '#F8FAFC',
  headerTextColor: '#475569',
  headerFontWeight: 600,
  rowHoverColor: 'rgba(37, 99, 235, 0.06)',
  selectedRowBackgroundColor: 'rgba(37, 99, 235, 0.10)',
  fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
  fontSize: 13,
  borderRadius: 10,
  wrapperBorderRadius: 14,
})

const FEATURES = [
  {
    Icon: Cube, tone: 'blue', agent: 'procurement',
    title: 'Channel3 sourcing',
    copy: 'Live product discovery with stock-aware offers, or a deterministic wholesale catalog when offline.',
  },
  {
    Icon: Receipt, tone: 'indigo', agent: 'customs',
    title: 'Landed cost upfront',
    copy: 'HS codes, duties, import tax and brokerage rolled into one total before a single dollar moves.',
  },
  {
    Icon: Truck, tone: 'teal', agent: 'logistics',
    title: 'Consolidated logistics',
    copy: 'Courier, air or ocean routing with multi-supplier consolidation discounts and a clear ETA.',
  },
  {
    Icon: ShieldCheck, tone: 'green', agent: 'compliance',
    title: 'Compliance screening',
    copy: 'Sanctions, restricted origins and export permits checked on every line item automatically.',
  },
  {
    Icon: Wallet, tone: 'amber', agent: 'treasury',
    title: 'Treasury guardrails',
    copy: 'Budget, per-item caps and payment schedules enforced by the agents, not by trust.',
  },
  {
    Icon: Fingerprint, tone: 'rose', agent: 'payments',
    title: 'Human-approved payment',
    copy: 'The workflow pauses for approval in PayPal, then captures only the amount you authorised.',
  },
]

const PLANS = [
  {
    name: 'Explore',
    price: '$0',
    cadence: 'sandbox forever',
    tag: 'For evaluation',
    copy: 'Prove the delegated flow with simulated payments and the local wholesale catalog.',
    features: ['1 workspace', 'Sandbox payments', 'Local catalog fallback', 'Full audit trail'],
    cta: 'Try the sandbox',
    href: '#console',
    featured: false,
  },
  {
    name: 'Growth',
    price: '$499',
    cadence: 'per month',
    tag: 'Most popular',
    copy: 'Run real procurement teams with live product search and Pay Later financing.',
    features: ['Live Channel3 search', 'Up to $250k per mandate', 'Pay Later in 4 installments', 'Priority support'],
    cta: 'Start free trial',
    href: '#console',
    featured: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    cadence: 'annual agreement',
    tag: 'For scaled operations',
    copy: 'Custom limits, dedicated compliance rules and integration support for global teams.',
    features: ['Custom delegation limits', 'SSO and role controls', 'Tailored compliance rules', 'Dedicated success manager'],
    cta: 'Request access',
    href: '#console',
    featured: false,
  },
]

const TRUST = [
  { Icon: CreditCard, label: 'PayPal sandbox' },
  { Icon: GlobeHemisphereWest, label: 'Channel3 catalog' },
  { Icon: LockKey, label: 'HS256 signed QR' },
  { Icon: Fingerprint, label: 'Human in the loop' },
  { Icon: ListChecks, label: 'Full audit trail' },
]

const Sparkline = memo(function Sparkline({ values }) {
  const data = values.length > 1 ? values : [1, 1]
  const W = 560
  const H = 168
  const pad = 14
  const max = Math.max(...data)
  const min = Math.min(...data, 0)
  const span = max - min || 1
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (W - pad * 2)
    const y = H - pad - ((v - min) / span) * (H - pad * 2)
    return [x, y]
  })
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')
  const area = `${line} L ${W - pad} ${H} L ${pad} ${H} Z`

  return (
    <svg className="sparkline" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label="Spend trend across recent delegations">
      <defs>
        <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2563EB" stopOpacity="0.32" />
          <stop offset="100%" stopColor="#2563EB" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="sparkLine" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#2563EB" />
          <stop offset="100%" stopColor="#EA580C" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map(f => (
        <line key={f} className="spark-grid" x1={pad} x2={W - pad}
          y1={pad + f * (H - pad * 2)} y2={pad + f * (H - pad * 2)} />
      ))}
      <path d={area} fill="url(#sparkFill)" />
      <path d={line} fill="none" stroke="url(#sparkLine)" strokeWidth="3"
        strokeLinecap="round" strokeLinejoin="round" />
      {pts.map((p, i) => (
        <circle key={i} className={i === pts.length - 1 ? 'spark-dot live' : 'spark-dot'}
          cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 5 : 2.5} />
      ))}
    </svg>
  )
})

function IconBadge({ Icon, tone = 'blue' }) {
  return (
    <span className={`icon-badge tone-${tone}`} aria-hidden="true">
      <Icon size={22} weight="duotone" />
    </span>
  )
}

function TrustChip({ Icon, label }) {
  return (
    <span className="trust-chip">
      <Icon size={18} weight="bold" aria-hidden="true" />
      {label}
    </span>
  )
}

const ApproveButton = memo(function ApproveButton(params) {
  const { data, onApprove } = params
  if (!data || data.status !== 'esperando_aprobacion') return null
  return (
    <button className="mini" onClick={e => { e.stopPropagation(); onApprove(data.thread_id) }}>
      Approve
    </button>
  )
})

function Detail({ row }) {
  if (!row) return <div className="card glass detail"><p className="muted">Select a delegation to inspect the team&apos;s decisions.</p></div>
  const t = row.treasury || {}
  const schedule = t.schedule || []
  return (
    <div className="card glass detail">
      <h2>{row.objective}</h2>
      <p className="muted">
        {row.items_count || 0} units · {row.suppliers || '—'} · {row.financing || '—'} ·{' '}
        <span className={'pill ' + (row.status === 'completado' ? 'completed' : row.status === 'esperando_aprobacion' ? 'pending' : row.status === 'rechazado' ? 'rejected' : '')}>
          {LABEL[row.status] || row.status}
        </span>
      </p>

      <h3>Items</h3>
      <table>
        <thead><tr><th>Product</th><th>Qty</th><th>Unit</th><th>Supplier</th><th>Stock</th><th>Source</th></tr></thead>
        <tbody>
          {(row.items || []).map((i, n) => (
            <tr key={n}>
              <td>{i.name}</td><td>{i.qty}</td><td>{fmt(i.unit_price)}</td>
              <td>{i.supplier}</td><td>{i.stock}</td><td>{i.source}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Budget allocation</h3>
      <table>
        <tbody>
          <tr><td>Goods</td><td>{fmt(row.goods_total)}</td></tr>
          <tr><td>Duties + import tax</td><td>{fmt((row.duties_total || 0) + (row.tax_total || 0))}</td></tr>
          <tr><td>Shipping ({(row.logistics || {}).carrier || '—'})</td><td>{fmt(row.shipping_total)}</td></tr>
          <tr><td>Brokerage + payment fees</td><td>{fmt(row.fees_total)}</td></tr>
          <tr><td><b>Total committed</b></td><td><b>{fmt(row.grand_total)}</b></td></tr>
          <tr><td>Delegated budget</td><td>{fmt(row.budget)}</td></tr>
          <tr><td>Budget left</td><td><b>{fmt(row.remaining)}</b></td></tr>
        </tbody>
      </table>

      {schedule.length > 0 && (
        <>
          <h3>Payment schedule ({(row.treasury || {}).payment_mode})</h3>
          <table>
            <tbody>{schedule.map((p, n) => <tr key={n}><td>{p.label}</td><td>{fmt(p.amount)}</td></tr>)}</tbody>
          </table>
        </>
      )}

      {(row.compliance || {}).flags?.length > 0 && (
        <>
          <h3>Compliance</h3>
          <p className="muted">Risk score {(row.compliance || {}).risk_score}/100</p>
          <ul className="trace">{(row.compliance.flags || []).map((f, n) => <li key={n}>{f}</li>)}</ul>
        </>
      )}

      {(row.paypal_events || []).length > 0 && (
        <>
          <h3>PayPal notifications</h3>
          <ul className="trace">
            {(row.paypal_events || []).map((e, n) => (
              <li key={n}>
                <b>{e.event_type}</b> · {e.ts} — {e.verified ? 'signature verified' : 'unverified (demo)'}
                {e.amount ? ` · ${fmt(e.amount)}` : ''}
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>Subagent audit trail</h3>
      <ol className="trace">
        {(row.trace || []).map((t, n) => (
          <li key={n}><b>{t.agent}</b> · {t.ts} — {t.summary}</li>
        ))}
      </ol>

      {row.order_id && (
        <p className="muted">
          order {row.order_id} ·{' '}
          <a href="https://developer.paypal.com/dashboard/notifications" target="_blank" rel="noreferrer">
            Sandbox email notifications
          </a>
          {row.approve_url && row.status === 'esperando_aprobacion' && (
            <> · <a href={row.approve_url} target="_blank" rel="noreferrer">Open PayPal approval</a></>
          )}
          {(row.payments || []).length > 0 && (row.payments || []).slice(-1)[0].paypal_status && (
            <> · PayPal status <b>{(row.payments || []).slice(-1)[0].paypal_status}</b></>
          )}
        </p>
      )}
      {row.message && <p className="muted">{row.message}</p>}
    </div>
  )
}

function HeroPanel({ rows, totals }) {
  const chartValues = rows.length
    ? [...rows].slice(0, 8).reverse().map(r => r.grand_total || r.budget || 0)
    : [18, 26, 22, 34, 30, 42, 38, 52]
  const latest = rows[0]
  const trace = latest?.trace || []
  const feed = SUBAGENTS.map(name => {
    const entry = [...trace].reverse().find(t => t.agent === name)
    return { name, summary: entry?.summary || 'Ready for the next mandate', ts: entry?.ts || '—', done: !!entry }
  })
  const committedPct = totals.delegated
    ? Math.min(100, Math.round((totals.committed / totals.delegated) * 100))
    : 0

  return (
    <div className="hero-panel glass">
      <div className="panel-head">
        <div>
          <p className="panel-kicker">Live delegation control</p>
          <h2>Spend, without the guesswork</h2>
        </div>
        <span className={`live-pill ${rows.length ? '' : 'sample'}`}>
          <span className="pulse" aria-hidden="true" />
          {rows.length ? 'Live' : 'Sample'}
        </span>
      </div>

      <div className="hero-metrics">
        <div className="metric">
          <span className="metric-label">Delegated</span>
          <strong>{fmt(totals.delegated)}</strong>
          <span className="metric-note">{totals.count} mandate{totals.count === 1 ? '' : 's'}</span>
        </div>
        <div className="metric">
          <span className="metric-label">Paid</span>
          <strong>{fmt(totals.paid)}</strong>
          <span className="metric-note">{totals.awaiting} awaiting approval</span>
        </div>
      </div>

      <div className="chart-wrap">
        <Sparkline values={chartValues} />
        <div className="chart-legend">
          <span><i className="legend-dot blue" aria-hidden="true" />Commitment trend</span>
          <span>{rows.length ? 'Last 8 delegations' : 'Sample series'}</span>
        </div>
      </div>

      <div className="budget-bar">
        <div className="budget-meta">
          <span>Committed vs delegated</span>
          <b>{committedPct}%</b>
        </div>
        <div className="bar-track">
          <div className="bar-fill" style={{ width: `${committedPct}%` }} />
        </div>
      </div>

      <div className="agent-feed">
        {feed.map(({ name, summary, ts, done }) => (
          <div className="agent-row" key={name}>
            <span className={`agent-dot ${done ? 'done' : ''}`} aria-hidden="true" />
            <div>
              <b>{name}</b>
              <span>{summary}</span>
            </div>
            <time>{ts}</time>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const [rows, setRows] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [mandate, setMandate] = useState(null)
  const [chatMsg, setChatMsg] = useState('Compra 20 laptops empresariales y 10 monitores 4K para la nueva oficina')
  const [chatReply, setChatReply] = useState('')
  const [form, setForm] = useState({
    objective: 'Compra 20 laptops empresariales y 10 monitores 4K para la nueva oficina',
    budget: 50000,
    cap: 1500,
    financing: 'pay_in_4',
    scope: SUBAGENTS,
  })
  const grid = useRef(null)

  const load = useCallback(() => {
    fetch('/api/b2b/orders').then(r => r.json()).then(setRows).catch(() => {})
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 4000)
    return () => clearInterval(id)
  }, [load])

  const createMandate = useCallback(async () => {
    setBusy(true); setError(''); setChatReply('')
    try {
      const p = new URLSearchParams({
        objective: form.objective,
        budget: form.budget,
        per_item_cap: form.cap,
        financing: form.financing,
        scope: form.scope.join(','),
      })
      const r = await fetch('/api/b2b/qr?' + p).then(r => r.json())
      if (r.detail) throw new Error(r.detail)
      setMandate(r)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }, [form])

  const runTeam = useCallback(async () => {
    if (!mandate) return
    setBusy(true); setError('')
    try {
      const row = await fetch('/api/b2b/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: mandate.token }),
      }).then(r => r.json())
      if (row.detail) throw new Error(row.detail)
      setSelectedId(row.thread_id)
      load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }, [mandate, load])

  const approveOrder = useCallback(async tid => {
    setBusy(true); setError('')
    try {
      const row = await fetch('/api/b2b/approve/' + tid, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true }),
      }).then(r => r.json())
      if (row.detail) throw new Error(row.detail)
      setSelectedId(tid)
      load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }, [load])

  const sendChat = useCallback(async () => {
    setBusy(true); setError(''); setChatReply('')
    try {
      const r = await fetch('/api/b2b/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: chatMsg, budget: Number(form.budget) }),
      }).then(r => r.json())
      if (r.detail) throw new Error(r.detail)
      setChatReply(r.reply || '')
      if (r.mandate) setMandate(r.mandate)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }, [chatMsg, form.budget])

  const toggleScope = name => setForm(f => ({
    ...f,
    scope: f.scope.includes(name) ? f.scope.filter(x => x !== name) : [...f.scope, name],
  }))

  const cols = useMemo(() => [
    { field: 'created', headerName: 'Time', width: 86 },
    { field: 'objective', headerName: 'Objective', flex: 2, minWidth: 220, filter: true, wrapText: true, autoHeight: true },
    { field: 'items_count', headerName: 'Units', width: 78, filter: 'agNumberColumnFilter' },
    { field: 'suppliers', headerName: 'Suppliers', flex: 1, minWidth: 140, filter: true },
    { field: 'budget', headerName: 'Budget', width: 110, filter: 'agNumberColumnFilter', valueFormatter: usd },
    { field: 'goods_total', headerName: 'Goods', width: 104, filter: 'agNumberColumnFilter', valueFormatter: usd },
    { colId: 'duties_tax', headerName: 'Duties+tax', width: 112, filter: 'agNumberColumnFilter', valueGetter: p => (p.data.duties_total || 0) + (p.data.tax_total || 0), valueFormatter: usd },
    { field: 'shipping_total', headerName: 'Shipping', width: 104, filter: 'agNumberColumnFilter', valueFormatter: usd },
    { field: 'fees_total', headerName: 'Fees', width: 92, filter: 'agNumberColumnFilter', valueFormatter: usd },
    { field: 'grand_total', headerName: 'Total', width: 118, filter: 'agNumberColumnFilter', valueFormatter: usd, cellStyle: { fontWeight: 700 } },
    { field: 'remaining', headerName: 'Budget left', width: 116, filter: 'agNumberColumnFilter', valueFormatter: usd, cellStyle: p => ({ color: p.value < 0 ? '#dc2626' : '#166534' }) },
    { field: 'status', headerName: 'Status', width: 168, filter: true,
      valueFormatter: p => LABEL[p.value] || p.value,
      cellStyle: p => ({ color: COLOR[p.value] || 'inherit', fontWeight: 600 }) },
    { field: 'financing', headerName: 'Financing', width: 106 },
    { field: 'order_id', headerName: 'PayPal order', width: 166 },
    { colId: 'paypal_event', headerName: 'PayPal event', width: 186, filter: true,
      valueGetter: p => (p.data.last_paypal_event || {}).event_type || '' },
    { headerName: '', width: 108, sortable: false, filter: false, cellRenderer: ApproveButton, cellRendererParams: { onApprove: approveOrder } },
  ], [approveOrder])

  const defaultColDef = useMemo(() => ({ sortable: true, resizable: true }), [])
  const getRowId = useCallback(p => p.data.thread_id, [])

  const paid = rows.filter(r => r.status === 'completado')
  const awaiting = rows.filter(r => r.status === 'esperando_aprobacion')
  const delegated = rows.reduce((s, r) => s + (r.budget || 0), 0)
  const committed = rows.filter(r => r.status !== 'rechazado').reduce((s, r) => s + (r.grand_total || 0), 0)
  const spent = paid.reduce((s, r) => s + (r.grand_total || 0), 0)
  const selected = rows.find(r => r.thread_id === selectedId) || null
  const totals = { delegated, committed, paid: spent, awaiting: awaiting.length, count: rows.length }

  return (
    <AgGridProvider modules={modules}>
      <div className="page">
        <header className="topbar glass">
          <a className="brand" href="#top" aria-label="Pay2Win B2B home">
            <span className="brand-mark"><QrCode size={20} weight="bold" aria-hidden="true" /></span>
            <span>Pay2Win <b>B2B</b></span>
          </a>
          <nav className="nav-links" aria-label="Primary">
            <a href="#platform">Platform</a>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#console">Console</a>
          </nav>
          <a className="btn btn-primary btn-sm" href="#console">
            Launch console <ArrowRight size={16} weight="bold" aria-hidden="true" />
          </a>
        </header>

        <main>
          <section className="hero" id="top">
            <div className="hero-copy">
              <span className="eyebrow"><Sparkle size={15} weight="fill" aria-hidden="true" /> Delegated commerce infrastructure</span>
              <h1>Procurement that runs itself, <span className="gradient-text">inside your budget.</span></h1>
              <p className="lede">
                Scan one signed QR to hand a specialist agent team a budget, a per-item cap and a
                goal. They source, clear customs, ship, screen compliance and pay — only after you approve.
              </p>
              <div className="hero-actions">
                <a className="btn btn-primary" href="#console">
                  Delegate a budget <ArrowRight size={17} weight="bold" aria-hidden="true" />
                </a>
                <a className="btn btn-ghost" href="#features">
                  <ChartLineUp size={17} weight="bold" aria-hidden="true" /> See how it works
                </a>
              </div>
              <div className="hero-trust">
                <span><CheckCircle size={16} weight="fill" aria-hidden="true" /> No overspend</span>
                <span><CheckCircle size={16} weight="fill" aria-hidden="true" /> Human-approved</span>
                <span><CheckCircle size={16} weight="fill" aria-hidden="true" /> Fully auditable</span>
              </div>
            </div>
            <HeroPanel rows={rows} totals={totals} />
          </section>

          <section className="trust-band" aria-label="Integrations and safeguards">
            <span className="trust-label">Built on</span>
            <div className="trust-grid">
              {TRUST.map(t => <TrustChip key={t.label} {...t} />)}
            </div>
          </section>

          <section className="section" id="platform">
            <div className="section-head">
              <span className="eyebrow"><Robot size={15} weight="fill" aria-hidden="true" /> Supervisor + 6 specialists</span>
              <h2>One mandate. A whole procurement department.</h2>
              <p>The supervisor validates the signed QR, then dispatches each specialist in sequence with the same budget guardrails.</p>
            </div>
            <div className="flow-row" aria-label="Agent pipeline">
              {['QR mandate', 'Supervisor', 'Procurement', 'Customs', 'Logistics', 'Compliance', 'Treasury', 'PayPal'].map((step, i, arr) => (
                <div className="flow-step" key={step}>
                  <span>{String(i + 1).padStart(2, '0')}</span>
                  <b>{step}</b>
                  {i < arr.length - 1 && <ArrowRight size={14} weight="bold" aria-hidden="true" />}
                </div>
              ))}
            </div>
          </section>

          <section className="section" id="features">
            <div className="section-head">
              <span className="eyebrow"><SquaresFour size={15} weight="fill" aria-hidden="true" /> Platform capabilities</span>
              <h2>Every cost, decision and approval in one place.</h2>
              <p>Clear guardrails and a complete audit trail, from sourcing to capture.</p>
            </div>
            <div className="feature-grid">
              {FEATURES.map(({ Icon, tone, agent, title, copy }) => (
                <article className="feature-card glass" key={title}>
                  <IconBadge Icon={Icon} tone={tone} />
                  <h3>{title}</h3>
                  <p>{copy}</p>
                  <span className="agent-tag">{agent}</span>
                </article>
              ))}
            </div>
          </section>

          <section className="section" id="pricing">
            <div className="section-head">
              <span className="eyebrow"><ChartBar size={15} weight="fill" aria-hidden="true" /> Transparent pricing</span>
              <h2>Start in the sandbox. Scale when it works.</h2>
              <p>No hidden spend — the platform never moves more than the mandate you sign.</p>
            </div>
            <div className="pricing-grid">
              {PLANS.map(plan => (
                <article className={`price-card glass ${plan.featured ? 'featured' : ''}`} key={plan.name}>
                  <div className="price-top">
                    <span className="plan-tag">{plan.tag}</span>
                    <h3>{plan.name}</h3>
                    <p className="plan-copy">{plan.copy}</p>
                  </div>
                  <div className="price">
                    <strong>{plan.price}</strong>
                    <span>{plan.cadence}</span>
                  </div>
                  <ul className="plan-list">
                    {plan.features.map(f => (
                      <li key={f}><Check size={16} weight="bold" aria-hidden="true" /> {f}</li>
                    ))}
                  </ul>
                  <a className={`btn ${plan.featured ? 'btn-accent' : 'btn-ghost'} btn-block`} href={plan.href}>
                    {plan.cta} <ArrowUpRight size={16} weight="bold" aria-hidden="true" />
                  </a>
                </article>
              ))}
            </div>
          </section>

          <section className="section console-section" id="console">
            <div className="section-head">
              <span className="eyebrow"><SealCheck size={15} weight="fill" aria-hidden="true" /> Delegation console</span>
              <h2>Run a delegation end to end.</h2>
              <p>Generate a signed QR, launch the team, inspect every agent decision and approve the PayPal order.</p>
            </div>

            <div className="console-grid">
              <aside className="console-side">
                <section className="card glass">
                  <h2>Delegate a budget</h2>
                  <label htmlFor="objective">Purchase objective</label>
                  <textarea id="objective" value={form.objective} onChange={e => setForm({ ...form, objective: e.target.value })} />
                  <div className="row" style={{ marginTop: 10 }}>
                    <div className="grow">
                      <label htmlFor="budget">Total budget (USD)</label>
                      <input id="budget" type="number" min="1" value={form.budget} onChange={e => setForm({ ...form, budget: Number(e.target.value) })} />
                    </div>
                    <div className="grow">
                      <label htmlFor="cap">Per-item cap (USD)</label>
                      <input id="cap" type="number" min="1" value={form.cap} onChange={e => setForm({ ...form, cap: Number(e.target.value) })} />
                    </div>
                  </div>
                  <label htmlFor="financing">Financing</label>
                  <select id="financing" value={form.financing} onChange={e => setForm({ ...form, financing: e.target.value })}>
                    <option value="pay_in_4">Pay Later (4 installments)</option>
                    <option value="none">Pay in full</option>
                  </select>
                  <span className="field-label">Delegate to subagents</span>
                  <div className="scope">
                    {SUBAGENTS.map(s => (
                      <label key={s}>
                        <input type="checkbox" checked={form.scope.includes(s)} onChange={() => toggleScope(s)} />
                        {s}
                      </label>
                    ))}
                  </div>
                  <button className="btn btn-primary btn-block" onClick={createMandate} disabled={busy} style={{ marginTop: 14 }}>
                    Generate signed QR mandate <QrCode size={17} weight="bold" aria-hidden="true" />
                  </button>

                  {mandate && (
                    <div className="qr">
                      <img src={mandate.png} alt="B2B mandate QR code" />
                      <ul className="preview">
                        {(mandate.preview || []).map((i, n) => (
                          <li key={n}><span>{i.qty} × {i.name}</span><span>{fmt(i.unit_price)}</span></li>
                        ))}
                      </ul>
                      <p className="muted" style={{ margin: '8px 0' }}>
                        Budget {fmt(mandate.budget)} · cap {fmt(mandate.per_item_cap)} ·{' '}
                        {mandate.scope.length} subagents · {mandate.channel3_live ? 'Channel3 live' : 'fallback catalog'}
                      </p>
                      <button className="btn btn-accent btn-block" onClick={runTeam} disabled={busy}>
                        Run the agent team <Lightning size={17} weight="bold" aria-hidden="true" />
                      </button>
                    </div>
                  )}
                </section>

                <section className="card glass">
                  <h2>Buy with chat</h2>
                  <label htmlFor="chat">Tell the agent what the business needs</label>
                  <textarea id="chat" value={chatMsg} onChange={e => setChatMsg(e.target.value)} />
                  <button className="btn btn-ghost btn-block" onClick={sendChat} disabled={busy} style={{ marginTop: 10 }}>
                    Interpret &amp; prepare mandate <ChatCircleText size={17} weight="bold" aria-hidden="true" />
                  </button>
                  {chatReply && <p className="muted">{chatReply}</p>}
                </section>

                {error && <p className="error" role="alert"><WarningCircle size={16} weight="fill" aria-hidden="true" /> {error}</p>}
              </aside>

              <section className="console-main">
                <div className="kpis">
                  <div className="kpi glass"><span className="kpi-icon"><Bank size={18} weight="duotone" aria-hidden="true" /></span><small>Delegated</small><b>{fmt(delegated)}</b></div>
                  <div className="kpi glass"><span className="kpi-icon"><TrendUp size={18} weight="duotone" aria-hidden="true" /></span><small>Committed</small><b>{fmt(committed)}</b></div>
                  <div className="kpi glass"><span className="kpi-icon"><CheckCircle size={18} weight="duotone" aria-hidden="true" /></span><small>Paid</small><b>{fmt(spent)}</b></div>
                  <div className="kpi glass"><span className="kpi-icon"><Lightning size={18} weight="duotone" aria-hidden="true" /></span><small>Awaiting approval</small><b>{awaiting.length}</b></div>
                  <div className="kpi glass"><span className="kpi-icon"><Package size={18} weight="duotone" aria-hidden="true" /></span><small>Delegations</small><b>{rows.length}</b></div>
                </div>

                <div className="card glass grid-card">
                  <div className="toolbar">
                    <input aria-label="Quick filter delegations" placeholder="Quick filter…" value={q} onChange={e => setQ(e.target.value)} />
                    <button className="btn btn-ghost btn-sm" onClick={() => grid.current?.api?.exportDataAsCsv()}>
                      Export CSV <ArrowUpRight size={15} weight="bold" aria-hidden="true" />
                    </button>
                  </div>
                  <div className="grid-wrap">
                    <AgGridReact
                      ref={grid}
                      theme={gridTheme}
                      rowData={rows}
                      columnDefs={cols}
                      defaultColDef={defaultColDef}
                      quickFilterText={q}
                      getRowId={getRowId}
                      onRowClicked={e => setSelectedId(e.data.thread_id)}
                      rowSelection="single"
                      pagination
                      paginationPageSize={10}
                    />
                  </div>
                </div>

                <Detail row={selected} />
              </section>
            </div>
          </section>
        </main>

        <footer className="footer">
          <div className="footer-brand">
            <span className="brand-mark"><QrCode size={18} weight="bold" aria-hidden="true" /></span>
            <span>Pay2Win <b>B2B</b></span>
          </div>
          <p>Demo environment · payments run in PayPal sandbox or simulation · built for delegated procurement.</p>
          <div className="footer-links">
            <a href="#platform">Platform</a>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#console">Console</a>
          </div>
        </footer>
      </div>
    </AgGridProvider>
  )
}
