import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Boxes, CheckCircle2, Clock3, Minus, Plus, RefreshCw, ShieldCheck } from 'lucide-react'
import './InventoryManagement.css'

const API = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

type InventoryItem = {
    product_id: string
    name: string
    category: string
    merchant: string
    source: string
    on_hand: number
    reserved: number
    available: number
    low_stock_threshold: number
    stock_status: 'IN_STOCK' | 'LOW_STOCK' | 'OUT_OF_STOCK'
    updated_at: string
}
type Movement = {
    id: number
    product_id: string
    action: string
    quantity: number
    reference: string
    note: string
    created_at: string
}
type Reservation = {
    reservation_id: string
    order_id?: string | null
    status: string
    created_at: string
    expires_at: string
    completed_at?: string | null
}
type Snapshot = {
    summary: {
        sku_count: number
        on_hand: number
        reserved: number
        available: number
        low_stock_count: number
        out_of_stock_count: number
    }
    items: InventoryItem[]
    reservations: Reservation[]
    movements: Movement[]
    generated_at: string
}

function dateLabel(value?: string | null) {
    if (!value) return '—'
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function signedQuantity(value: number) {
    return `${value > 0 ? '+' : ''}${value}`
}

export default function InventoryManagement({ adminToken }: { adminToken: string }) {
    const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const [notice, setNotice] = useState('')
    const [busyProduct, setBusyProduct] = useState<string | null>(null)

    const loadInventory = useCallback(async () => {
        const token = adminToken.trim()
        if (!token) {
            setSnapshot(null)
            setError('Operator token is required to view inventory.')
            return
        }
        setLoading(true)
        setError('')
        try {
            const response = await fetch(`${API}/api/inventory`, {
                headers: { 'X-AgentPay-Admin-Token': token },
            })
            const data = await response.json()
            if (!response.ok) throw new Error(data.detail || `Inventory request failed (${response.status})`)
            setSnapshot(data as Snapshot)
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Could not load inventory.')
            setSnapshot(null)
        } finally {
            setLoading(false)
        }
    }, [adminToken])

    useEffect(() => {
        if (!adminToken.trim()) {
            setSnapshot(null)
            setError('Operator token is required to view inventory.')
            return
        }
        const timer = window.setTimeout(() => { void loadInventory() }, 350)
        return () => window.clearTimeout(timer)
    }, [adminToken, loadInventory])

    async function adjustStock(item: InventoryItem, delta: number) {
        if (!adminToken.trim()) {
            setError('Operator authentication is required.')
            return
        }
        if (delta < 0 && !window.confirm(`Remove ${Math.abs(delta)} unit(s) from ${item.name}?`)) return
        setBusyProduct(item.product_id)
        setError('')
        setNotice('')
        try {
            const response = await fetch(`${API}/api/inventory/adjust`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-AgentPay-Admin-Token': adminToken.trim(),
                },
                body: JSON.stringify({
                    product_id: item.product_id,
                    delta,
                    note: delta > 0 ? 'Manual stock replenishment from dashboard' : 'Manual stock reduction from dashboard',
                }),
            })
            const data = await response.json()
            if (!response.ok) throw new Error(data.detail || `Stock adjustment failed (${response.status})`)
            setNotice(`${item.name}: stock adjusted by ${signedQuantity(delta)} unit(s).`)
            await loadInventory()
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Stock adjustment failed.')
        } finally {
            setBusyProduct(null)
        }
    }

    const summary = snapshot?.summary

    return (
        <section className="inventory-card" id="inventory-management">
            <div className="inventory-heading">
                <div>
                    <span className="inventory-eyebrow"><Boxes size={14} /> AGENTPAY OPERATIONS</span>
                    <h2>Inventory management</h2>
                    <p>Track demo-catalog quantities, checkout reservations, completed sales and manual stock movements.</p>
                </div>
                <button className="inventory-refresh" type="button" onClick={() => void loadInventory()} disabled={loading || !adminToken.trim()}>
                    <RefreshCw size={14} className={loading ? 'inventory-spin' : ''} /> Refresh
                </button>
            </div>

            <div className="inventory-info-note">
                <ShieldCheck size={16} /> Quantity tracking applies to AgentPay's demo catalog. Channel3 retailer offers expose availability, not authoritative unit counts, so they are not deducted here.
            </div>

            {error && <div className="inventory-feedback inventory-error" role="alert"><AlertTriangle size={15} /> {error}</div>}
            {notice && <div className="inventory-feedback inventory-success" role="status"><CheckCircle2 size={15} /> {notice}</div>}

            <div className="inventory-kpis">
                <div><span>Tracked SKUs</span><strong>{summary?.sku_count ?? '—'}</strong></div>
                <div><span>On hand</span><strong>{summary?.on_hand ?? '—'}</strong></div>
                <div><span>Reserved</span><strong>{summary?.reserved ?? '—'}</strong></div>
                <div><span>Available</span><strong>{summary?.available ?? '—'}</strong></div>
                <div><span>Low stock</span><strong>{summary?.low_stock_count ?? '—'}</strong></div>
            </div>

            <div className="inventory-subheading">
                <div><h3>Stock by product</h3><span>{snapshot?.items.length ?? 0} quantity-managed products</span></div>
                {summary && summary.out_of_stock_count > 0 && <span className="inventory-out-pill">{summary.out_of_stock_count} out of stock</span>}
            </div>

            {snapshot?.items.length ? (
                <div className="inventory-table-wrap">
                    <table className="inventory-table">
                        <thead><tr><th>Product</th><th>On hand</th><th>Reserved</th><th>Available</th><th>Status</th><th>Adjust stock</th></tr></thead>
                        <tbody>
                            {snapshot.items.map(item => (
                                <tr key={item.product_id}>
                                    <td><strong>{item.name}</strong><small>{item.product_id} · {item.category}</small></td>
                                    <td>{item.on_hand}</td>
                                    <td>{item.reserved}</td>
                                    <td><strong>{item.available}</strong></td>
                                    <td><span className={`inventory-status inventory-status-${item.stock_status.toLowerCase()}`}>{item.stock_status.replace(/_/g, ' ')}</span></td>
                                    <td>
                                        <div className="inventory-adjust-actions">
                                            <button type="button" title="Remove one unit" aria-label={`Remove one ${item.name}`} onClick={() => void adjustStock(item, -1)} disabled={busyProduct === item.product_id || item.on_hand - item.reserved <= 0}><Minus size={13} /></button>
                                            <button type="button" title="Add one unit" aria-label={`Add one ${item.name}`} onClick={() => void adjustStock(item, 1)} disabled={busyProduct === item.product_id}><Plus size={13} /></button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="inventory-empty">{loading ? 'Loading inventory…' : 'Inventory data will appear after operator authentication.'}</div>
            )}

            <div className="inventory-bottom-grid">
                <div className="inventory-list-panel">
                    <div className="inventory-panel-heading"><h3>Recent reservations</h3><Clock3 size={15} /></div>
                    {snapshot?.reservations.length ? snapshot.reservations.slice(0, 8).map(row => (
                        <div className="inventory-log-row" key={row.reservation_id}>
                            <div><strong>{row.order_id || row.reservation_id.slice(0, 12)}</strong><small>{dateLabel(row.created_at)} · expires {dateLabel(row.expires_at)}</small></div>
                            <span className={`inventory-status inventory-status-${row.status.toLowerCase()}`}>{row.status}</span>
                        </div>
                    )) : <p className="inventory-muted">No reservations recorded yet.</p>}
                </div>
                <div className="inventory-list-panel">
                    <div className="inventory-panel-heading"><h3>Stock movement history</h3><span>{snapshot?.movements.length ?? 0} recent</span></div>
                    {snapshot?.movements.length ? snapshot.movements.slice(0, 8).map(row => (
                        <div className="inventory-log-row" key={row.id}>
                            <div><strong>{row.action.replace(/_/g, ' ')} · {signedQuantity(row.quantity)}</strong><small>{row.product_id} · {dateLabel(row.created_at)}</small></div>
                            <span title={row.note}>{row.reference ? row.reference.slice(0, 10) : 'Manual'}</span>
                        </div>
                    )) : <p className="inventory-muted">Stock adjustments and sales will appear here.</p>}
                </div>
            </div>
            <div className="inventory-footer">Reservations become eligible for release after 30 minutes and are released on the next inventory or checkout request. Stock is deducted only after PayPal confirms a completed capture. Dashboard data refreshed {snapshot ? dateLabel(snapshot.generated_at) : '—'}.</div>
        </section>
    )
}
