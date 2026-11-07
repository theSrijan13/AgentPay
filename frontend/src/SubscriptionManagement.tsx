import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CalendarClock, ChevronLeft, ChevronRight, Eye, RefreshCw, Repeat2, Search, ShieldCheck, Users } from 'lucide-react'

type Money = { value?: string; currency_code?: string }
type Subscription = {
    id?: string
    status?: string
    plan_id?: string
    start_time?: string
    create_time?: string
    update_time?: string
    status_update_time?: string
    subscriber?: { name?: string; email_address?: string }
    billing_info?: {
        next_billing_time?: string
        failed_payments_count?: number
        last_payment?: { amount?: Money; time?: string }
        last_failed_payment?: { amount?: Money; time?: string; reason_code?: string; next_payment_retry_time?: string }
        outstanding_balance?: Money
    }
}
type SubscriptionDetail = Subscription & {
    status_change_note?: string
    quantity?: string
    plan?: {
        name?: string
        description?: string
        billing_cycles?: Array<{
            tenure_type?: string
            frequency?: { interval_unit?: string; interval_count?: number }
            fixed_price?: Money
        }>
    }
}
type SubscriptionResponse = {
    subscriptions?: Subscription[]
    page?: number
    page_size?: number
    has_next?: boolean
    has_previous?: boolean
}

const STATUS_OPTIONS = [
    ['ALL', 'All statuses'],
    ['ACTIVE', 'Active'],
    ['APPROVAL_PENDING', 'Approval pending'],
    ['APPROVED', 'Approved'],
    ['SUSPENDED', 'Suspended'],
    ['CANCELLED', 'Cancelled'],
    ['EXPIRED', 'Expired'],
] as const

function formatMoney(amount?: Money | null) {
    if (!amount?.value || !amount.currency_code) return '—'
    const value = Number(amount.value)
    if (!Number.isFinite(value)) return `${amount.value} ${amount.currency_code}`
    try {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: amount.currency_code }).format(value)
    } catch {
        return `${amount.value} ${amount.currency_code}`
    }
}

function formatDate(value?: string | null) {
    if (!value) return 'Not available'
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

function statusClass(status?: string) {
    const value = (status || '').toUpperCase()
    if (value === 'ACTIVE' || value === 'APPROVED') return 'subscription-status subscription-status-good'
    if (value === 'SUSPENDED' || value === 'APPROVAL_PENDING') return 'subscription-status subscription-status-warn'
    return 'subscription-status subscription-status-muted'
}

function fullName(subscriber?: Subscription['subscriber']) {
    return subscriber?.name || subscriber?.email_address || 'Subscriber details unavailable'
}

export default function SubscriptionManagement({ adminToken }: { adminToken: string }) {
    const [subscriptions, setSubscriptions] = useState<Subscription[]>([])
    const [status, setStatus] = useState('ALL')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)
    const [hasNext, setHasNext] = useState(false)
    const [busy, setBusy] = useState(false)
    const [loaded, setLoaded] = useState(false)
    const [error, setError] = useState('')
    const [detail, setDetail] = useState<SubscriptionDetail | null>(null)
    const [detailBusy, setDetailBusy] = useState(false)
    const [detailError, setDetailError] = useState('')

    useEffect(() => {
        if (adminToken.trim()) {
            void loadSubscriptions(1, status)
        }
    }, [adminToken, status])

    async function loadSubscriptions(nextPage = page, nextStatus = status) {
        if (!adminToken.trim()) {
            setError('Enter your AgentPay operator token above before loading subscription data.')
            return
        }
        setBusy(true)
        setError('')
        try {
            const params = new URLSearchParams({ page: String(nextPage), page_size: '20' })
            if (nextStatus !== 'ALL') params.set('status', nextStatus)
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/subscriptions?${params.toString()}`, {
                headers: { 'X-AgentPay-Admin-Token': adminToken.trim() },
            })
            const data = await response.json()
            if (!response.ok) throw new Error(data.detail || `Subscription request failed (${response.status})`)
            const result = data as SubscriptionResponse
            setSubscriptions(Array.isArray(result.subscriptions) ? result.subscriptions : [])
            setPage(Number(result.page || nextPage))
            setHasNext(Boolean(result.has_next))
            setLoaded(true)
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Could not load subscriptions from PayPal.')
            setSubscriptions([])
            setLoaded(false)
            setHasNext(false)
        } finally {
            setBusy(false)
        }
    }

    async function openDetails(subscriptionId?: string) {
        if (!subscriptionId) return
        setDetailBusy(true)
        setDetailError('')
        setDetail(null)
        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/subscriptions/${encodeURIComponent(subscriptionId)}`, {
                headers: { 'X-AgentPay-Admin-Token': adminToken.trim() },
            })
            const data = await response.json()
            if (!response.ok) throw new Error(data.detail || 'Could not load subscription details.')
            setDetail(data as SubscriptionDetail)
        } catch (err) {
            setDetailError(err instanceof Error ? err.message : 'Could not load subscription details.')
        } finally {
            setDetailBusy(false)
        }
    }

    const visibleSubscriptions = useMemo(() => {
        const query = search.trim().toLowerCase()
        if (!query) return subscriptions
        return subscriptions.filter(item => [item.id, item.plan_id, item.status, item.subscriber?.name, item.subscriber?.email_address]
            .some(value => String(value || '').toLowerCase().includes(query)))
    }, [subscriptions, search])

    const counts = useMemo(() => subscriptions.reduce((acc, item) => {
        const key = (item.status || 'UNKNOWN').toUpperCase()
        acc[key] = (acc[key] || 0) + 1
        return acc
    }, {} as Record<string, number>), [subscriptions])

    const regularCycle = detail?.plan?.billing_cycles?.find(cycle => cycle.tenure_type === 'REGULAR') || detail?.plan?.billing_cycles?.[0]
    const cadence = regularCycle?.frequency
        ? `Every ${regularCycle.frequency.interval_count || 1} ${(regularCycle.frequency.interval_unit || 'period').toLowerCase()}${(regularCycle.frequency.interval_count || 1) > 1 ? 's' : ''}`
        : 'Billing cadence unavailable'

    return <section className="subscription-management-card" id="subscription-management">
        <div className="subscription-heading">
            <div>
                <span className="eyebrow">PAYPAL SUBSCRIPTIONS · LIVE ACCOUNT DATA</span>
                <h2>Subscription management</h2>
                <p>Read-only visibility into recurring customers, subscription status, payment health and upcoming billing.</p>
            </div>
            <div className="subscription-heading-actions">
                <span className="subscription-mode"><span /> SANDBOX · READ ONLY</span>
                <button className="secondary-btn" onClick={() => void loadSubscriptions(1, status)} disabled={busy || !adminToken.trim()}><RefreshCw size={13} />{busy ? 'Refreshing…' : 'Refresh'}</button>
            </div>
        </div>

        <div className="subscription-kpis">
            <div className="subscription-kpi"><span><Users size={15} /> On this page</span><strong>{subscriptions.length}</strong><small>PayPal subscriptions returned</small></div>
            <div className="subscription-kpi"><span><ShieldCheck size={15} /> Active</span><strong>{counts.ACTIVE || 0}</strong><small>Current page only</small></div>
            <div className="subscription-kpi"><span><AlertCircle size={15} /> Payment issues</span><strong>{subscriptions.filter(item => Number(item.billing_info?.failed_payments_count || 0) > 0).length}</strong><small>Failed-payment count above zero</small></div>
            <div className="subscription-kpi"><span><CalendarClock size={15} /> Suspended</span><strong>{counts.SUSPENDED || 0}</strong><small>Current page only</small></div>
        </div>

        <div className="subscription-toolbar">
            <div className="subscription-filter-wrap">
                <label htmlFor="subscription-status-filter">Status</label>
                <select id="subscription-status-filter" value={status} onChange={event => { setStatus(event.target.value); setSearch(''); void loadSubscriptions(1, event.target.value) }} disabled={busy}>
                    {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
            </div>
            <div className="subscription-search"><Search size={15} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search this page by name, email, ID or plan" aria-label="Search subscriptions on this page" /></div>
            <span className="subscription-page-label">Page {page} · {visibleSubscriptions.length} shown</span>
        </div>

        {!adminToken.trim() && <div className="subscription-empty"><ShieldCheck size={20} /><strong>Operator authentication required</strong><span>Operator token is needed to view merchant subscription data.</span></div>}
        {adminToken.trim() && error && <div className="subscription-error"><AlertCircle size={16} /><span>{error}</span></div>}
        {adminToken.trim() && !error && busy && <div className="subscription-empty"><RefreshCw size={19} className="subscription-spin" /><strong>Connecting to PayPal…</strong><span>Fetching subscriptions from your configured Sandbox merchant account.</span></div>}
        {adminToken.trim() && !busy && loaded && visibleSubscriptions.length > 0 && <div className="subscription-table-wrap">
            <table className="subscription-table">
                <thead><tr><th>Subscriber</th><th>Plan / Subscription</th><th>Status</th><th>Next billing</th><th>Last payment</th><th></th></tr></thead>
                <tbody>{visibleSubscriptions.map(item => <tr key={item.id || `${item.plan_id}-${item.create_time}`}>
                    <td><strong>{fullName(item.subscriber)}</strong><span>{item.subscriber?.email_address || 'Email not shared by PayPal'}</span></td>
                    <td><strong>{item.plan_id || 'Plan unavailable'}</strong><span>{item.id || 'Subscription ID unavailable'}</span></td>
                    <td><span className={statusClass(item.status)}>{(item.status || 'UNKNOWN').replace(/_/g, ' ')}</span></td>
                    <td>{item.billing_info?.next_billing_time ? formatDate(item.billing_info.next_billing_time) : 'Not scheduled'}</td>
                    <td>{item.billing_info?.last_payment?.amount ? formatMoney(item.billing_info.last_payment.amount) : '—'}<span>{formatDate(item.billing_info?.last_payment?.time)}</span></td>
                    <td><button className="subscription-detail-button" onClick={() => void openDetails(item.id)} disabled={!item.id || detailBusy}><Eye size={14} /> Details</button></td>
                </tr>)}</tbody>
            </table>
        </div>}
        {adminToken.trim() && !busy && loaded && visibleSubscriptions.length === 0 && <div className="subscription-empty"><Repeat2 size={20} /><strong>{subscriptions.length ? 'No matches on this page' : 'No subscriptions found'}</strong><span>{subscriptions.length ? 'Try a different search term.' : 'No records were returned for this Sandbox merchant and status filter. Create and approve a test subscription in the same PayPal Sandbox business account to populate this dashboard.'}</span></div>}
        {adminToken.trim() && !loaded && !busy && !error && <div className="subscription-empty"><Repeat2 size={20} /><strong>Connect your PayPal subscription account</strong><span>Load the first page of subscriptions from the Sandbox business account configured in backend/.env.</span><button className="primary-btn" onClick={() => void loadSubscriptions(1, status)} disabled={!adminToken.trim()}>Load subscriptions <ChevronRight size={15} /></button></div>}

        <div className="subscription-footer"><span>Subscription KPIs describe the visible page, not the entire merchant account. No subscription is modified by this dashboard.</span><div><button className="secondary-btn" onClick={() => void loadSubscriptions(Math.max(1, page - 1), status)} disabled={busy || page <= 1 || !adminToken.trim()}><ChevronLeft size={14} /> Previous</button><button className="secondary-btn" onClick={() => void loadSubscriptions(page + 1, status)} disabled={busy || !hasNext || !adminToken.trim()}>Next <ChevronRight size={14} /></button></div></div>

        {(detailBusy || detail || detailError) && <div className="subscription-modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) { setDetail(null); setDetailError('') } }}>
            <div className="subscription-modal" role="dialog" aria-modal="true" aria-labelledby="subscription-detail-title">
                <div className="subscription-modal-heading"><div><span className="eyebrow">PAYPAL SUBSCRIPTION RECORD</span><h3 id="subscription-detail-title">Subscription details</h3></div><button className="icon-button" onClick={() => { setDetail(null); setDetailError('') }} aria-label="Close details">×</button></div>
                {detailBusy && <div className="subscription-empty"><RefreshCw size={18} className="subscription-spin" /><span>Loading detailed subscription and billing information…</span></div>}
                {detailError && <div className="subscription-error"><AlertCircle size={16} /><span>{detailError}</span></div>}
                {detail && <>
                    <div className="subscription-detail-top"><div><strong>{fullName(detail.subscriber)}</strong><span>{detail.subscriber?.email_address || 'Email unavailable'}</span></div><span className={statusClass(detail.status)}>{(detail.status || 'UNKNOWN').replace(/_/g, ' ')}</span></div>
                    <div className="subscription-detail-grid">
                        <div><small>Subscription ID</small><strong>{detail.id || '—'}</strong></div>
                        <div><small>Plan</small><strong>{detail.plan?.name || detail.plan_id || '—'}</strong></div>
                        <div><small>Recurring price</small><strong>{formatMoney(regularCycle?.fixed_price)}</strong></div>
                        <div><small>Billing frequency</small><strong>{cadence}</strong></div>
                        <div><small>Next billing</small><strong>{formatDate(detail.billing_info?.next_billing_time)}</strong></div>
                        <div><small>Last payment</small><strong>{formatMoney(detail.billing_info?.last_payment?.amount)}</strong></div>
                        <div><small>Failed payments</small><strong>{detail.billing_info?.failed_payments_count ?? 0}</strong></div>
                        <div><small>Outstanding balance</small><strong>{formatMoney(detail.billing_info?.outstanding_balance)}</strong></div>
                        <div><small>Created</small><strong>{formatDate(detail.create_time)}</strong></div>
                        <div><small>Last updated</small><strong>{formatDate(detail.update_time || detail.status_update_time)}</strong></div>
                    </div>
                    {detail.billing_info?.last_failed_payment && <div className="subscription-failure-note"><strong>Last failed payment</strong><span>{detail.billing_info.last_failed_payment.reason_code || 'Reason not supplied'} · {formatDate(detail.billing_info.last_failed_payment.time)}</span>{detail.billing_info.last_failed_payment.next_payment_retry_time && <span>Next retry: {formatDate(detail.billing_info.last_failed_payment.next_payment_retry_time)}</span>}</div>}
                    <p className="subscription-safety-note">Read-only record from PayPal Sandbox. Payment-source and card details are intentionally not displayed.</p>
                </>}
            </div>
        </div>}
    </section>
}
