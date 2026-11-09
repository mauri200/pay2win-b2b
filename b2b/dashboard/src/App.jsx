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
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug']
const compactUsd = v => {
  const n = Number(v || 0)
  if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M'
  if (Math.abs(n) >= 1e3) return '$' + Math.round(n / 1e3) + 'k'
  return '$' + Math.round(n)
}

const STATUS_LABEL = {
  ...LABEL,
  captured: 'Captured', pending: 'Pending', verified: 'Verified', unverified: 'Unverified',
  paypal_sandbox: 'PayPal sandbox', simulated: 'Simulated',
}
const pretty = v => v ? String(v).replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase()) : ''
const statusLabel = v => STATUS_LABEL[v] || pretty(v)

function buildPaymentOps(rows) {
  const out = []
  for (const row of rows) {
    const payments = row.payments || []
    const last = payments[payments.length - 1] || {}
    const trace = row.trace || []
    for (let n = trace.length - 1; n >= 0; n -= 1) {
      const t = trace[n]
      if (t.agent !== 'treasury' && t.agent !== 'payments') continue
      const data = t.data || {}
      const isPayment = t.agent === 'payments'
      const summary = t.summary || ''
      let operation = isPayment ? 'Create PayPal order' : 'Authorize spend'
      if (isPayment && /captur/i.test(summary)) operation = 'Capture payment'
      else if (isPayment && /error|fallo|bloquead/i.test(summary)) operation = 'Payment error'
      else if (!isPayment && /insuficiente|bloquead/i.test(summary)) operation = 'Budget blocked'
      out.push({
        id: `${row.thread_id}-trace-${n}`,
        time: t.ts || row.created,
        subagent: t.agent,
        operation,
        objective: row.objective || '—',
        order_id: data.order_id || row.order_id || '',
        mode: data.mode || row.payment_mode || 'simulated',
        amount: Number((isPayment ? last.amount : row.grand_total) || 0),
        status: isPayment ? (last.captured ? 'captured' : (last.paypal_status || 'pending')) : row.status,
      })
    }
    const events = row.paypal_events || []
    for (let n = events.length - 1; n >= 0; n -= 1) {
      const e = events[n]
      out.push({
        id: `${row.thread_id}-event-${n}`,
        time: e.ts || row.created,
        subagent: 'paypal-webhook',
        operation: e.event_type || 'PayPal event',
        objective: row.objective || '—',
        order_id: e.order_id || row.order_id || '',
        mode: 'paypal_sandbox',
        amount: Number(e.amount || 0),
        status: e.verified ? 'verified' : 'unverified',
      })
    }
  }
  return out
}

function buildSourcingUsage(rows) {
  const out = []
  for (const row of rows) {
    const items = row.items || []
    for (let n = 0; n < items.length; n += 1) {
      const i = items[n]
      const qty = Number(i.qty || 0)
      const unit = Number(i.unit_price || 0)
      out.push({
        id: `${row.thread_id}-item-${n}`,
        time: row.created,
        product: i.name || '—',
        objective: row.objective || '—',
        supplier: i.supplier || '—',
        qty,
        unit_price: unit,
        line_total: Math.round(qty * unit * 100) / 100,
        source: i.source || 'local',
        stock: Number(i.stock || 0),
        origin: i.origin || '—',
        hs_code: i.hs_code || '—',
      })
    }
  }
  return out
}

function buildRevenueSeries(rows) {
  const list = rows
    .filter(r => r && r.created_ts)
    .slice()
    .sort((a, b) => Number(a.created_ts) - Number(b.created_ts))
    .slice(-10)
  if (list.length >= 2) {
    return {
      sample: false,
      data: list.map(r => ({
        label: r.created || new Date(Number(r.created_ts) * 1000)
          .toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        committed: Number(r.grand_total || 0),
        captured: r.status === 'completado' ? Number(r.grand_total || 0) : 0,
      })),
    }
  }
  const base = list.length ? Number(list[0].grand_total || 0) : 4200
  return {
    sample: true,
    data: MONTHS.map((label, i) => {
      const committed = Math.round(base * (0.9 + i * 0.14))
      return { label, committed, captured: Math.round(committed * (0.6 + (i % 3) * 0.08)) }
    }),
  }
}

function buildTrafficSources(sourceRows, opsRows) {
  const data = [
    { label: 'Channel3 live', value: sourceRows.filter(r => r.source === 'channel3').length, color: '#2563EB' },
    { label: 'Local catalog', value: sourceRows.filter(r => r.source === 'local').length, color: '#EA580C' },
    { label: 'PayPal operations', value: opsRows.filter(r => r.subagent === 'payments').length, color: '#0D9488' },
    { label: 'Webhook events', value: opsRows.filter(r => r.subagent === 'paypal-webhook').length, color: '#4F46E5' },
  ]
  const sum = data.reduce((s, d) => s + d.value, 0)
  if (sum > 0) return { data, sample: false }
  return {
    sample: true,
    data: [
      { label: 'Channel3 live', value: 46, color: '#2563EB' },
      { label: 'Local catalog', value: 28, color: '#EA580C' },
      { label: 'PayPal operations', value: 18, color: '#0D9488' },
      { label: 'Webhook events', value: 8, color: '#4F46E5' },
    ],
  }
}

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

const RevenueTrendChart = memo(function RevenueTrendChart({ rows }) {
  const { data, sample } = useMemo(() => buildRevenueSeries(rows), [rows])
  const W = 760
  const H = 240
  const pad = { l: 54, r: 18, t: 16, b: 32 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const max = Math.max(1, ...data.map(d => Math.max(d.committed, d.captured)))
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  const px = i => pad.l + (data.length > 1 ? (i / (data.length - 1)) * innerW : innerW / 2)
  const py = v => pad.t + (1 - v / max) * innerH
  const lineFor = key => data.map((d, i) => `${i ? 'L' : 'M'}${px(i).toFixed(1)} ${py(d[key]).toFixed(1)}`).join(' ')
  const areaFor = key => `${lineFor(key)} L ${px(data.length - 1).toFixed(1)} ${pad.t + innerH} L ${px(0).toFixed(1)} ${pad.t + innerH} Z`
  const labelEvery = data.length > 8 ? 2 : 1

  return (
    <div className="revenue-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={sample ? 'Sample revenue trend' : 'Revenue trend across recent delegations'}>
        <defs>
          <linearGradient id="revCommittedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563EB" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#2563EB" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="revCapturedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#EA580C" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#EA580C" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map(t => {
          const y = pad.t + (1 - t) * innerH
          return (
            <g key={t}>
              <line className="rev-grid" x1={pad.l} x2={W - pad.r} y1={y} y2={y} />
              <text className="rev-axis" x={pad.l - 10} y={y + 4} textAnchor="end">{compactUsd(max * t)}</text>
            </g>
          )
        })}
        <path d={areaFor('committed')} fill="url(#revCommittedFill)" />
        <path d={areaFor('captured')} fill="url(#revCapturedFill)" />
        <path d={lineFor('committed')} className="rev-line committed" />
        <path d={lineFor('captured')} className="rev-line captured" />
        {data.map((d, i) => (
          <g key={i}>
            <circle className="rev-dot committed" cx={px(i)} cy={py(d.committed)} r="3.5">
              <title>{`${d.label} · committed ${fmt(d.committed)}`}</title>
            </circle>
            {d.captured > 0 && (
              <circle className="rev-dot captured" cx={px(i)} cy={py(d.captured)} r="3.5">
                <title>{`${d.label} · captured ${fmt(d.captured)}`}</title>
              </circle>
            )}
            {(i % labelEvery === 0 || i === data.length - 1) && (
              <text className="rev-axis" x={px(i)} y={H - 8} textAnchor="middle">{d.label}</text>
            )}
          </g>
        ))}
      </svg>
    </div>
  )
})

const TrafficSources = memo(function TrafficSources({ sourceRows, opsRows }) {
  const { data, sample } = useMemo(() => buildTrafficSources(sourceRows, opsRows), [sourceRows, opsRows])
  const total = data.reduce((s, d) => s + d.value, 0)
  return (
    <div className="source-chart">
      <div className="source-total">
        <span>Total signals</span>
        <b>{total.toLocaleString('en-US')}</b>
      </div>
      <div className="source-list">
        {data.map(d => {
          const pct = total ? Math.round((d.value / total) * 100) : 0
          return (
            <div className="source-row" key={d.label}>
              <div className="source-top">
                <span className="source-name"><i style={{ background: d.color }} aria-hidden="true" />{d.label}</span>
                <span className="source-value">{d.value}<em>{pct}%</em></span>
              </div>
              <div className="source-track">
                <div className="source-fill" style={{ width: `${pct}%`, background: d.color }} />
              </div>
            </div>
          )
        })}
      </div>
      {sample && <p className="analytics-note">Sample distribution until the first delegations land.</p>}
    </div>
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

const TagCell = memo(function TagCell(params) {
  const text = String(params.valueFormatted ?? params.value ?? '')
  const tone = /error|fail|reject|unverified|blocked/i.test(text) ? 'bad'
    : /channel3|sandbox|captur|complet|verif|approved|treasury ok/i.test(text) ? 'ok'
      : /local|simulat|await|pending/i.test(text) ? 'warn'
        : 'neutral'
  return <span className={`tag tag-${tone}`}>{text}</span>
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
  const [qOps, setQOps] = useState('')
  const [qSource, setQSource] = useState('')
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
  const opsGrid = useRef(null)
  const sourceGrid = useRef(null)

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

  const opsRows = useMemo(() => buildPaymentOps(rows), [rows])
  const sourceRows = useMemo(() => buildSourcingUsage(rows), [rows])

  const opsCols = useMemo(() => [
    { field: 'time', headerName: 'Time', width: 92 },
    { field: 'subagent', headerName: 'Subagent', width: 128, filter: true, valueFormatter: p => pretty(p.value) },
    { field: 'operation', headerName: 'Operation', width: 178, filter: true },
    { field: 'objective', headerName: 'Delegation', flex: 2, minWidth: 190, filter: true, tooltipValueGetter: p => p.value },
    { field: 'order_id', headerName: 'Order', width: 164, filter: true },
    { field: 'mode', headerName: 'Mode', width: 140, filter: true, valueFormatter: p => statusLabel(p.value), cellRenderer: TagCell },
    { field: 'amount', headerName: 'Amount', width: 116, filter: 'agNumberColumnFilter', valueFormatter: usd, cellStyle: { fontWeight: 600 } },
    { field: 'status', headerName: 'Status', width: 148, filter: true, valueFormatter: p => statusLabel(p.value), cellRenderer: TagCell },
  ], [])

  const sourceCols = useMemo(() => [
    { field: 'time', headerName: 'Time', width: 92 },
    { field: 'product', headerName: 'Product', flex: 2, minWidth: 190, filter: true },
    { field: 'objective', headerName: 'Delegation', flex: 2, minWidth: 170, filter: true, tooltipValueGetter: p => p.value },
    { field: 'supplier', headerName: 'Supplier', flex: 1, minWidth: 140, filter: true },
    { field: 'qty', headerName: 'Qty', width: 74, filter: 'agNumberColumnFilter' },
    { field: 'unit_price', headerName: 'Unit', width: 100, filter: 'agNumberColumnFilter', valueFormatter: usd },
    { field: 'line_total', headerName: 'Line total', width: 112, filter: 'agNumberColumnFilter', valueFormatter: usd, cellStyle: { fontWeight: 600 } },
    { field: 'source', headerName: 'Source', width: 142, filter: true, valueFormatter: p => p.value === 'channel3' ? 'Channel3 live' : 'Local fallback', cellRenderer: TagCell },
    { field: 'stock', headerName: 'Stock', width: 84, filter: 'agNumberColumnFilter' },
    { field: 'origin', headerName: 'Origin', width: 84 },
    { field: 'hs_code', headerName: 'HS code', width: 100, filter: true },
  ], [])

  const opsRowId = useCallback(p => p.data.id, [])
  const sourceRowId = useCallback(p => p.data.id, [])

  const channel3Live = sourceRows.filter(r => r.source === 'channel3').length
  const localFallback = sourceRows.filter(r => r.source === 'local').length
  const suppliers = new Set(sourceRows.map(r => r.supplier).filter(Boolean)).size

  const paid = rows.filter(r => r.status === 'completado')
  const awaiting = rows.filter(r => r.status === 'esperando_aprobacion')
  const delegated = rows.reduce((s, r) => s + (r.budget || 0), 0)
  const committed = rows.filter(r => r.status !== 'rechazado').reduce((s, r) => s + (r.grand_total || 0), 0)
  const spent = paid.reduce((s, r) => s + (r.grand_total || 0), 0)
  const selected = rows.find(r => r.thread_id === selectedId) || null
  const totals = { delegated, committed, paid: spent, awaiting: awaiting.length, count: rows.length }
  const avgOrder = paid.length ? spent / paid.length : 0
  const captureRate = rows.length ? Math.round((paid.length / rows.length) * 100) : 0

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
            <a href="#activity">Activity</a>
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

          <section className="section activity-section" id="activity">
            <div className="section-head activity-head">
              <div>
                <span className="eyebrow"><ChartLineUp size={15} weight="fill" aria-hidden="true" /> Live operations</span>
                <h2>Payments and sourcing, streamed.</h2>
                <p>Every PayPal sandbox action from the subagents and every Channel3 lookup, refreshed in place.</p>
              </div>
              <span className={`live-pill ${rows.length ? '' : 'sample'}`} role="status" aria-live="polite">
                <span className="pulse" aria-hidden="true" />
                {rows.length ? `${opsRows.length} operations` : 'Sample'}
              </span>
            </div>

            <div className="activity-widgets">
              <div className="kpi glass">
                <span className="kpi-icon"><CreditCard size={18} weight="duotone" aria-hidden="true" /></span>
                <small>PayPal operations</small>
                <b>{opsRows.length}</b>
                <span className="kpi-note">subagent + webhook events</span>
              </div>
              <div className="kpi glass">
                <span className="kpi-icon"><CheckCircle size={18} weight="duotone" aria-hidden="true" /></span>
                <small>Captured</small>
                <b>{fmt(spent)}</b>
                <span className="kpi-note">{paid.length} completed delegation{paid.length === 1 ? '' : 's'}</span>
              </div>
              <div className="kpi glass">
                <span className="kpi-icon"><GlobeHemisphereWest size={18} weight="duotone" aria-hidden="true" /></span>
                <small>Channel3 live</small>
                <b>{channel3Live}</b>
                <span className="kpi-note">{localFallback} local fallback</span>
              </div>
              <div className="kpi glass">
                <span className="kpi-icon"><Package size={18} weight="duotone" aria-hidden="true" /></span>
                <small>Suppliers</small>
                <b>{suppliers}</b>
                <span className="kpi-note">{sourceRows.length} sourced line items</span>
              </div>
            </div>

            <section className="analytics-block" aria-labelledby="analytics-heading">
              <div className="analytics-head">
                <span className="eyebrow"><ChartBar size={15} weight="fill" aria-hidden="true" /> Analytics Overview</span>
                <h2 id="analytics-heading">Revenue and traffic at a glance.</h2>
                <p>Captured revenue, delegation value and the channel mix behind every subagent operation.</p>
              </div>

              <div className="analytics-stats">
                <div className="stat glass">
                  <span className="stat-label">Captured revenue</span>
                  <b>{fmt(spent)}</b>
                  <span className="stat-note">{paid.length} completed delegation{paid.length === 1 ? '' : 's'}</span>
                </div>
                <div className="stat glass">
                  <span className="stat-label">Avg. order value</span>
                  <b>{fmt(avgOrder)}</b>
                  <span className="stat-note">per captured delegation</span>
                </div>
                <div className="stat glass">
                  <span className="stat-label">Capture rate</span>
                  <b>{captureRate}%</b>
                  <span className="stat-note">{paid.length} of {rows.length} delegations</span>
                </div>
                <div className="stat glass">
                  <span className="stat-label">Active suppliers</span>
                  <b>{suppliers}</b>
                  <span className="stat-note">{sourceRows.length} sourced line items</span>
                </div>
              </div>

              <div className="analytics-charts">
                <div className="card glass analytics-card">
                  <div className="analytics-card-head">
                    <div>
                      <h2><ChartLineUp size={16} weight="fill" aria-hidden="true" /> Revenue Trend</h2>
                      <p className="muted">Committed vs captured value across recent delegations.</p>
                    </div>
                    <div className="chart-legend inline">
                      <span><i className="legend-dot" style={{ background: '#2563EB' }} aria-hidden="true" />Committed</span>
                      <span><i className="legend-dot" style={{ background: '#EA580C' }} aria-hidden="true" />Captured</span>
                    </div>
                  </div>
                  <RevenueTrendChart rows={rows} />
                </div>
                <div className="card glass analytics-card">
                  <div className="analytics-card-head">
                    <div>
                      <h2><GlobeHemisphereWest size={16} weight="fill" aria-hidden="true" /> Traffic Sources</h2>
                      <p className="muted">Where sourcing and PayPal volume originates.</p>
                    </div>
                  </div>
                  <TrafficSources sourceRows={sourceRows} opsRows={opsRows} />
                </div>
              </div>
            </section>

            <div className="card glass activity-card">
              <div className="activity-card-head">
                <div>
                  <h2><CreditCard size={16} weight="fill" aria-hidden="true" /> PayPal sandbox operations</h2>
                  <p className="muted">Order creation, capture and webhook notifications emitted by the payments subagent.</p>
                </div>
                <div className="toolbar">
                  <input aria-label="Filter PayPal operations" placeholder="Filter operations…" value={qOps} onChange={e => setQOps(e.target.value)} />
                  <button className="btn btn-ghost btn-sm" onClick={() => opsGrid.current?.api?.exportDataAsCsv()}>
                    Export CSV <ArrowUpRight size={15} weight="bold" aria-hidden="true" />
                  </button>
                </div>
              </div>
              <div className="grid-wrap activity-grid">
                <AgGridReact
                  ref={opsGrid}
                  theme={gridTheme}
                  rowData={opsRows}
                  columnDefs={opsCols}
                  defaultColDef={defaultColDef}
                  quickFilterText={qOps}
                  getRowId={opsRowId}
                  pagination
                  paginationPageSize={8}
                />
              </div>
            </div>

            <div className="card glass activity-card">
              <div className="activity-card-head">
                <div>
                  <h2><GlobeHemisphereWest size={16} weight="fill" aria-hidden="true" /> Channel3 sourcing usage</h2>
                  <p className="muted">Product discovery and stock returned per line item, with local fallback flagged.</p>
                </div>
                <div className="toolbar">
                  <input aria-label="Filter Channel3 usage" placeholder="Filter sourcing…" value={qSource} onChange={e => setQSource(e.target.value)} />
                  <button className="btn btn-ghost btn-sm" onClick={() => sourceGrid.current?.api?.exportDataAsCsv()}>
                    Export CSV <ArrowUpRight size={15} weight="bold" aria-hidden="true" />
                  </button>
                </div>
              </div>
              <div className="grid-wrap activity-grid">
                <AgGridReact
                  ref={sourceGrid}
                  theme={gridTheme}
                  rowData={sourceRows}
                  columnDefs={sourceCols}
                  defaultColDef={defaultColDef}
                  quickFilterText={qSource}
                  getRowId={sourceRowId}
                  pagination
                  paginationPageSize={8}
                />
              </div>
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
            <a href="#activity">Activity</a>
          </div>
        </footer>
      </div>
    </AgGridProvider>
  )
}
