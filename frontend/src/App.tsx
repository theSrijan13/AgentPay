// import { useCallback, useEffect, useMemo, useState } from 'react'
// import { AgGridProvider, AgGridReact } from 'ag-grid-react'
// import { AllCommunityModule, type ColDef, type ICellRendererParams, themeQuartz } from 'ag-grid-community'
// import {
//   PayPalProvider,
//   PayPalOneTimePaymentButton,
//   usePayPal,
//   useEligibleMethods,
//   INSTANCE_LOADING_STATE,
// } from '@paypal/react-paypal-js/sdk-v6'
// import {
//   Activity, ArrowRight, Bot, CheckCircle2, CircleHelp, CreditCard, ExternalLink,
//   MessageCircle, RefreshCw, Search, ShieldCheck, ShoppingBag, SlidersHorizontal,
//   Sparkles, WandSparkles,
// } from 'lucide-react'

// const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
// const VITE_PAYPAL_CLIENT_ID = import.meta.env.VITE_PAYPAL_CLIENT_ID || ''
// const AG_GRID_MODULES = [AllCommunityModule]

// type ProductOffer = { merchant: string; price: number; currency: string; availability: string; condition: string; url: string }
// type Product = {
//   id: string; name: string; category: string; brand?: string | null; price: number; currency: string
//   rating?: number | null; review_count?: number | null; stock?: number | null; availability?: string
//   features: string[]; image_url?: string | null; offer_url?: string | null; merchant?: string | null
//   offers?: ProductOffer[]; source?: 'channel3' | 'demo'; description?: string | null; channel3_product_id?: string
// }
// type CartItem = { product: Product; quantity: number }
// type OrderResult = { orderID: string; status: string; total: string; currency: string; captureID?: string }
// type OfferRow = {
//   rowId: string; sourceProductId: string; productName: string; brand: string; category: string
//   merchant: string; price: number; currency: string; availability: string; condition: string
//   buyUrl: string; source: 'channel3' | 'demo'; product: Product
// }
// type TelemetryEvent = { event_id?: string; timestamp?: string; event_type?: string; message?: string; details?: Record<string, unknown> }
// type ElasticStatus = { configured: boolean; connected: boolean; event_store: string; index?: string | null; message: string; channel3_configured?: boolean; paypal_sandbox_configured?: boolean }

// const money = (value: number | string) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))
// const gridDate = (value?: string) => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''


// type PayPalCheckoutControlsProps = {
//   disabled: boolean
//   createOrder: () => Promise<string>
//   onApprove: (orderId: string) => Promise<void>
//   onCancel: () => void
//   onError: (message: string) => void
// }

// function getPayPalErrorMessage(value: unknown, fallback: string): string {
//   if (value instanceof Error && value.message.trim()) return value.message
//   if (typeof value === 'object' && value !== null && 'message' in value) {
//     const message = (value as { message?: unknown }).message
//     if (typeof message === 'string' && message.trim()) return message
//   }
//   return fallback
// }

// /** Must render inside PayPalProvider so SDK and eligibility hooks are available. */
// function PayPalCheckoutControls({
//   disabled,
//   createOrder,
//   onApprove,
//   onCancel,
//   onError,
// }: PayPalCheckoutControlsProps) {
//   const { loadingStatus, error: sdkError } = usePayPal()
//   const {
//     eligiblePaymentMethods,
//     isLoading: eligibilityLoading,
//     error: eligibilityError,
//   } = useEligibleMethods({ payload: { currencyCode: 'USD' } })

//   if (loadingStatus === INSTANCE_LOADING_STATE.REJECTED || sdkError) {
//     return (
//       <div className="credential-help">
//         <strong>PayPal SDK could not initialize</strong>
//         <span>{getPayPalErrorMessage(sdkError, 'Check the Sandbox Client ID, app environment, and browser console.')}</span>
//       </div>
//     )
//   }

//   if (loadingStatus === INSTANCE_LOADING_STATE.PENDING || eligibilityLoading) {
//     return <div className="paypal-loading">Loading PayPal checkout and checking buyer eligibility…</div>
//   }

//   if (eligibilityError) {
//     return (
//       <div className="credential-help">
//         <strong>Could not check PayPal eligibility</strong>
//         <span>{getPayPalErrorMessage(eligibilityError, 'Retry after checking the network and Sandbox configuration.')}</span>
//       </div>
//     )
//   }

//   if (!eligiblePaymentMethods?.isEligible('paypal')) {
//     return (
//       <div className="credential-help">
//         <strong>PayPal checkout isn't eligible in this session</strong>
//         <span>Check the Sandbox app configuration and try a Personal Sandbox buyer account. Eligibility can depend on the buyer and currency.</span>
//       </div>
//     )
//   }

//   return (
//     <PayPalOneTimePaymentButton
//       type="pay"
//       presentationMode="auto"
//       disabled={disabled}
//       createOrder={async () => ({ orderId: await createOrder() })}
//       onApprove={async data => {
//         await onApprove(data.orderId)
//       }}
//       onCancel={onCancel}
//       onError={error => onError(getPayPalErrorMessage(error, 'Please retry or check the Sandbox configuration.'))}
//     />
//   )
// }

// export default function App() {
//   const [products, setProducts] = useState<Product[]>([])
//   const [catalogSource, setCatalogSource] = useState<'channel3' | 'demo'>('demo')
//   const [paypalClientId, setPaypalClientId] = useState<string>(VITE_PAYPAL_CLIENT_ID)
//   const [cart, setCart] = useState<CartItem[]>([])
//   const [prompt, setPrompt] = useState('Build me a work-from-home setup under $80. Prioritize reliability and strong reviews.')
//   const [budget, setBudget] = useState<number | null>(80)
//   const [events, setEvents] = useState<string[]>(['AgentPay workspace initialized', 'Audit events use Elastic when configured'])
//   const [busy, setBusy] = useState(false)
//   const [message, setMessage] = useState('')
//   const [basketValidated, setBasketValidated] = useState(false)
//   const [orderResult, setOrderResult] = useState<OrderResult | null>(null)
//   const [validatedTotal, setValidatedTotal] = useState<string | null>(null)
//   const [conversationId, setConversationId] = useState<string | null>(null)
//   const [followUp, setFollowUp] = useState('Can you find a cheaper option with the same features?')
//   const [chatReply, setChatReply] = useState('')
//   const [elasticStatus, setElasticStatus] = useState<ElasticStatus | null>(null)
//   const [elasticEvents, setElasticEvents] = useState<TelemetryEvent[]>([])
//   const [traceQuery, setTraceQuery] = useState('')
//   const [telemetrySource, setTelemetrySource] = useState('memory')

//   const total = useMemo(() => cart.reduce((sum, item) => sum + item.product.price * item.quantity, 0), [cart])

//   const offerRows = useMemo<OfferRow[]>(() => products.flatMap(product => {
//     const offers = product.offers?.length
//       ? product.offers
//       : [{
//         merchant: product.merchant || (product.source === 'channel3' ? 'Retailer' : 'AgentPay demo catalog'),
//         price: product.price, currency: product.currency || 'USD',
//         availability: product.availability || (product.source === 'channel3' ? 'Unknown' : 'Demo item'),
//         condition: 'unknown', url: product.offer_url || '',
//       }]
//     return offers.map((offer, index) => ({
//       rowId: `${product.id}-${offer.merchant}-${offer.price}-${index}`,
//       sourceProductId: product.id,
//       productName: product.name,
//       brand: product.brand || product.category,
//       category: product.category,
//       merchant: offer.merchant,
//       price: Number(offer.price),
//       currency: offer.currency || 'USD',
//       availability: offer.availability,
//       condition: offer.condition || 'unknown',
//       buyUrl: offer.url || '',
//       source: product.source || 'demo',
//       product,
//     }))
//   }), [products])

//   const refreshTelemetry = useCallback(async (query = traceQuery) => {
//     try {
//       const [statusResponse, eventsResponse] = await Promise.all([
//         fetch(`${API}/api/observability/status`),
//         fetch(`${API}/api/observability/events?limit=12${query.trim() ? `&q=${encodeURIComponent(query.trim())}` : ''}`),
//       ])
//       if (statusResponse.ok) setElasticStatus(await statusResponse.json())
//       if (eventsResponse.ok) {
//         const data = await eventsResponse.json()
//         setElasticEvents(data.events || [])
//         setTelemetrySource(data.source || 'memory')
//       }
//     } catch {
//       setElasticStatus({ configured: false, connected: false, event_store: 'memory', message: 'Observability API is unavailable.' })
//     }
//   }, [traceQuery])

//   useEffect(() => {
//     // Runtime public config is a fallback for cases where Vite was launched from
//     // a different working directory and did not load frontend/.env. The endpoint
//     // returns the public Client ID only; the PayPal secret never leaves FastAPI.
//     fetch(`${API}/api/public-config`)
//       .then(async response => { if (!response.ok) throw new Error('Public configuration unavailable'); return response.json() })
//       .then(data => { if (typeof data.paypal_client_id === 'string' && data.paypal_client_id.trim()) setPaypalClientId(data.paypal_client_id.trim()) })
//       .catch(() => { /* Keep the Vite public Client ID fallback if available. */ })

//     fetch(`${API}/api/agent/search`)
//       .then(async r => { if (!r.ok) throw new Error('Could not load product catalog'); return r.json() })
//       .then(data => {
//         setProducts(data.items || [])
//         setCatalogSource(data.source === 'channel3' ? 'channel3' : 'demo')
//         if (data.message) setMessage(data.message)
//       })
//       .catch(() => setMessage('API unavailable. Start the FastAPI backend on port 8000.'))
//     void refreshTelemetry('')
//   }, []) // initial bootstrap only

//   function resetCheckoutState() {
//     setBasketValidated(false)
//     setOrderResult(null)
//     setValidatedTotal(null)
//   }

//   async function planShopping() {
//     setBusy(true); setMessage(''); resetCheckoutState(); setConversationId(null); setChatReply('')
//     try {
//       // Start a real Channel3 Conversational Agent turn first. This returns the
//       // conversation ID required for follow-ups such as "show something cheaper".
//       // A normal /search call alone cannot establish conversational context.
//       try {
//         const response = await fetch(`${API}/api/agent/chat`, {
//           method: 'POST', headers: { 'Content-Type': 'application/json' },
//           body: JSON.stringify({ message: prompt, conversation_id: null, budget: null, user_id: 'agentpay-web-demo' }),
//         })
//         const data = await response.json()
//         if (!response.ok) throw new Error(data.detail || 'Channel3 Conversational Agent request failed')
//         if (data.conversation_id) setConversationId(data.conversation_id)
//         if (typeof data.constraints?.max_price === 'number') setBudget(data.constraints.max_price)
//         else setBudget(null)
//         let items: Product[] = Array.isArray(data.items) ? data.items : []
//         let source: 'channel3' | 'demo' = data.source === 'channel3' ? 'channel3' : 'demo'
//         let reply = data.text || 'Shopping conversation started.'

//         // Some valid conversational turns may answer in text before returning
//         // product cards. Keep their conversation ID and fill the grid from search.
//         if (!items.length) {
//           const searchResponse = await fetch(`${API}/api/agent/plan`, {
//             method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }),
//           })
//           const searchData = await searchResponse.json()
//           if (searchResponse.ok && Array.isArray(searchData.items) && searchData.items.length) {
//             items = searchData.items
//             source = searchData.source === 'channel3' ? 'channel3' : 'demo'
//           }
//         }
//         setProducts(items)
//         setCatalogSource(source)
//         setChatReply(reply)
//         setEvents(old => [...old, `Channel3 conversation started: ${items.length} product matches`])
//         setMessage(data.conversation_id
//           ? 'Shopping plan ready. Follow-up requests will use this conversation context.'
//           : 'Shopping results loaded, but Channel3 did not return a conversation ID. Contextual follow-ups may not persist.')
//       } catch (conversationError) {
//         // Search remains useful if the conversational endpoint is unavailable,
//         // but tell the user clearly that contextual follow-ups are not active.
//         const response = await fetch(`${API}/api/agent/plan`, {
//           method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }),
//         })
//         const data = await response.json()
//         if (!response.ok) throw new Error(data.detail || 'Shopping plan could not be created')
//         const items: Product[] = data.items || []
//         setProducts(items)
//         setCatalogSource(data.source === 'channel3' ? 'channel3' : 'demo')
//         setBudget(typeof data.constraints?.max_price === 'number' ? data.constraints.max_price : null)
//         setChatReply(`Contextual shopping session could not start: ${conversationError instanceof Error ? conversationError.message : 'Channel3 conversation unavailable'}`)
//         setMessage(`${data.message || 'Search results ready.'} Contextual follow-ups are not active yet.`)
//         setEvents(old => [...old, `${data.source === 'channel3' ? 'Channel3 search' : 'Demo catalog search'}: ${items.length} matches`])
//       }
//       await refreshTelemetry('')
//     } catch (error) {
//       setMessage(error instanceof Error ? error.message : 'Could not create a shopping plan')
//     } finally { setBusy(false) }
//   }

//   const addToCart = useCallback((product: Product) => {
//     setCart(old => {
//       const existing = old.find(item => item.product.id === product.id)
//       return existing
//         ? old.map(item => item.product.id === product.id
//           ? { ...item, quantity: product.stock == null ? item.quantity + 1 : Math.min(item.quantity + 1, product.stock) }
//           : item)
//         : [...old, { product, quantity: 1 }]
//     })
//     resetCheckoutState()
//     setEvents(old => [...old, `Added ${product.name}${product.merchant ? ` from ${product.merchant}` : ''} to basket`])
//   }, [])

//   const addOfferToCart = useCallback(async (row: OfferRow) => {
//     setBusy(true); setMessage('')
//     try {
//       let product = row.product
//       if (row.source === 'channel3') {
//         const response = await fetch(`${API}/api/catalog/select-offer`, {
//           method: 'POST', headers: { 'Content-Type': 'application/json' },
//           body: JSON.stringify({ product_id: row.sourceProductId, merchant: row.merchant }),
//         })
//         const data = await response.json()
//         if (!response.ok) throw new Error(data.detail || 'Could not select that retailer offer')
//         product = data.product
//       }
//       addToCart(product)
//       setMessage(`Added ${product.name} from ${product.merchant || 'the demo catalog'} to your basket.`)
//       await refreshTelemetry('')
//     } catch (error) {
//       setMessage(error instanceof Error ? error.message : 'Could not add that offer')
//     } finally { setBusy(false) }
//   }, [addToCart, refreshTelemetry])

//   const columnDefs = useMemo<ColDef<OfferRow>[]>(() => [
//     { headerName: 'Product', field: 'productName', minWidth: 190, flex: 2, filter: 'agTextColumnFilter' },
//     { headerName: 'Brand / type', field: 'brand', minWidth: 120, flex: 1 },
//     { headerName: 'Retailer', field: 'merchant', minWidth: 130, flex: 1.2, filter: 'agTextColumnFilter' },
//     { headerName: 'Price', field: 'price', minWidth: 105, maxWidth: 125, sort: 'asc', valueFormatter: params => money(Number(params.value)) },
//     { headerName: 'Availability', field: 'availability', minWidth: 125, flex: 0.9 },
//     { headerName: 'Condition', field: 'condition', minWidth: 100, flex: 0.7 },
//     {
//       headerName: 'Action', minWidth: 145, maxWidth: 155, sortable: false, filter: false,
//       cellRenderer: (params: ICellRendererParams<OfferRow>) => params.data
//         ? <button className="grid-add-button" disabled={busy} onClick={() => void addOfferToCart(params.data!)}>Add to basket</button>
//         : null,
//     },
//   ], [addOfferToCart, busy])

//   function removeFromCart(id: string) {
//     setCart(old => old.filter(item => item.product.id !== id))
//     resetCheckoutState()
//   }

//   async function validateBasket() {
//     setBusy(true); setMessage(''); resetCheckoutState()
//     try {
//       const response = await fetch(`${API}/api/cart/validate`, {
//         method: 'POST', headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({ items: cart.map(item => ({ product_id: item.product.id, quantity: item.quantity })), budget }),
//       })
//       const data = await response.json()
//       if (!response.ok) throw new Error(data.detail || 'Basket validation failed')
//       setCart(old => old.map(cartItem => {
//         const refreshed = data.items.find((item: any) => item.product_id === cartItem.product.id)
//         return refreshed ? { ...cartItem, product: { ...cartItem.product, price: Number(refreshed.unit_price), offer_url: refreshed.offer_url || cartItem.product.offer_url, merchant: refreshed.merchant || cartItem.product.merchant } } : cartItem
//       }))
//       setValidatedTotal(String(data.total)); setBasketValidated(true)
//       setMessage(`Basket validated by server. Total: ${money(data.total)}. Live retailer offers were refreshed; review and approve the PayPal Sandbox payment below.`)
//       setEvents(old => [...old, `Basket validated: ${money(data.total)}`, 'Waiting for explicit buyer approval'])
//       await refreshTelemetry('')
//     } catch (error) { setMessage(error instanceof Error ? error.message : 'Validation failed') }
//     finally { setBusy(false) }
//   }

//   async function createPayPalOrder() {
//     const response = await fetch(`${API}/api/payments/create-order`, {
//       method: 'POST', headers: { 'Content-Type': 'application/json' },
//       body: JSON.stringify({ items: cart.map(item => ({ product_id: item.product.id, quantity: item.quantity })), budget, expected_total: validatedTotal === null ? null : Number(validatedTotal) }),
//     })
//     const data = await response.json()
//     if (!response.ok) throw new Error(data.detail || 'Could not create PayPal order')
//     setEvents(old => [...old, `PayPal Sandbox order created: ${data.orderID}`])
//     await refreshTelemetry('')
//     return data.orderID as string
//   }

//   async function capturePayPalOrder(orderID: string) {
//     const response = await fetch(`${API}/api/payments/capture/${encodeURIComponent(orderID)}`, { method: 'POST' })
//     const data = await response.json()
//     if (!response.ok) throw new Error(data.detail || 'Could not verify PayPal capture')
//     const capture = data.purchase_units?.flatMap((unit: any) => unit.payments?.captures || [])[0]
//     if (data.status !== 'COMPLETED' || capture?.status !== 'COMPLETED') throw new Error('PayPal did not confirm a completed capture. Do not treat this order as paid.')
//     const result: OrderResult = { orderID, status: data.status, total: String(capture.amount?.value || total.toFixed(2)), currency: capture.amount?.currency_code || 'USD', captureID: capture.id }
//     setOrderResult(result); setBasketValidated(false)
//     setMessage(`Payment successful in Sandbox. PayPal confirmed ${money(result.total)} as ${result.status}.`)
//     setEvents(old => [...old, `Payment capture completed: ${result.captureID || orderID}`])
//     await refreshTelemetry('')
//   }

//   async function sendFollowUp() {
//     const text = followUp.trim()
//     if (!text) return
//     setBusy(true); setChatReply('')
//     const messageToSend = conversationId ? text : `${prompt}\n\nFollow-up requirement: ${text}`
//     try {
//       const response = await fetch(`${API}/api/agent/chat`, {
//         method: 'POST', headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({ message: messageToSend, conversation_id: conversationId, budget, user_id: 'agentpay-web-demo' }),
//       })
//       const data = await response.json()
//       if (!response.ok) throw new Error(data.detail || 'Channel3 Conversational Agent request failed')
//       if (data.conversation_id) setConversationId(data.conversation_id)
//       if (Array.isArray(data.items) && data.items.length) {
//         setProducts(data.items)
//         setCatalogSource('channel3')
//         resetCheckoutState()
//       }
//       if (typeof data.constraints?.max_price === 'number') setBudget(data.constraints.max_price)
//       setChatReply(data.text || 'Channel3 returned the conversation turn. Check the offer table for product cards.')
//       setEvents(old => [...old, `Channel3 conversation turn: ${(data.items || []).length} product cards`])
//       await refreshTelemetry('')
//     } catch (error) {
//       setChatReply(error instanceof Error ? error.message : 'Conversational refinement failed')
//     } finally { setBusy(false) }
//   }

//   return <div className="app-shell">
//     <aside className="sidebar">
//       <div className="brand"><div className="brand-mark"><WandSparkles size={20} /></div><div><strong>agentpay</strong><span>AI commerce agent</span></div></div>
//       <div className="workspace-label">WORKSPACE</div>
//       <button className="nav-item active" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}><ShoppingBag size={17} /> Shopping agent</button>
//       <button className="nav-item" onClick={() => document.getElementById('basket')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}><CreditCard size={17} /> Orders & payments</button>
//       <button className="nav-item" onClick={() => document.getElementById('observability')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}><Activity size={17} /> Observability</button>
//       <div className="sidebar-bottom"><ShieldCheck size={17} /><div><strong>Human-approved payments</strong><span>AgentPay never pays without your approval.</span></div></div>
//     </aside>

//     <main className="main">
//       <header className="topbar"><div><span className="eyebrow">YOUR PERSONAL SHOPPING AGENT</span><h1>Let's find your best fit.</h1><p>Tell AgentPay what you need. It will research, compare, and help you check out.</p></div><div className="sandbox-pill"><span /> PayPal Sandbox demo · USD</div></header>
//       {message && <div className={`notice ${orderResult ? 'success-notice' : ''}`} role="status">{orderResult ? <CheckCircle2 size={17} /> : <CircleHelp size={17} />}<span>{message}</span><button onClick={() => setMessage('')} aria-label="Dismiss">×</button></div>}

//       <section className="prompt-card">
//         <div className="section-icon"><Sparkles size={19} /></div>
//         <div className="prompt-content"><label htmlFor="shopping-prompt">WHAT ARE YOU LOOKING FOR?</label><textarea id="shopping-prompt" value={prompt} onChange={e => setPrompt(e.target.value)} rows={3} /><div className="prompt-footer"><span>{catalogSource === 'channel3' ? 'Channel3 agentic search · in-stock USD offers · prices may change.' : 'Demo catalog prices are illustrative USD amounts for Sandbox checkout.'}</span><button className="primary-btn" onClick={() => void planShopping()} disabled={busy || prompt.trim().length < 3}>{busy ? 'Working…' : 'Build my plan'} <ArrowRight size={16} /></button></div></div>
//       </section>

//       <div className="content-grid">
//         <section className="catalog-section">
//           <div className="section-heading"><div><span className="eyebrow">CURATED FOR YOUR NEEDS</span><h2>Product matches</h2></div><span className={`count-pill ${catalogSource === 'channel3' ? 'live-badge' : ''}`}>{catalogSource === 'channel3' ? 'CHANNEL3 LIVE' : 'DEMO CATALOG'} · {products.length}</span></div>
//           <div className="product-grid">
//             {products.map((p, index) => <article className="product-card" key={p.id}>
//               <div className={`product-art art-${index % 4}`}><div className="product-symbol">{p.category.toLowerCase().includes('headphone') || p.category.toLowerCase().includes('audio') ? '◖' : p.category.toLowerCase().includes('keyboard') ? '▤' : p.category.toLowerCase().includes('mouse') ? '◒' : '◇'}</div>{p.image_url && <img className="channel3-image" src={p.image_url} alt={p.name} loading="lazy" onError={event => { event.currentTarget.style.display = 'none' }} />}<span className="match-tag">{catalogSource === 'channel3' ? (index === 0 ? 'CHANNEL3 PICK' : 'LIVE RESULT') : (index === 0 ? 'TOP MATCH' : `${Math.max(78, 94 - index * 7)}% MATCH`)}</span></div>
//               <div className="product-info"><span className="category">{p.brand || p.category}</span><h3>{p.name}</h3>{typeof p.rating === 'number' ? <div className="rating">★ <strong>{p.rating.toFixed(1)}</strong> {typeof p.review_count === 'number' && <span>({p.review_count} reviews)</span>}</div> : <div className="rating live-offer">● <strong>{p.availability || 'Catalog offer'}</strong>{p.merchant && <span> · {p.merchant}</span>}</div>}<div className="product-features">{(p.features || []).slice(0, 2).join(' · ') || p.description || (p.merchant ? `Offer from ${p.merchant}` : 'Demo product catalog')}</div>{p.offer_url && <a className="offer-link" href={p.offer_url} target="_blank" rel="noreferrer">View {p.merchant || 'retailer'} offer ↗</a>}<div className="product-bottom"><strong>{money(p.price)}</strong><button className="add-btn" onClick={() => addToCart(p)}>Add <span>+</span></button></div></div>
//             </article>)}
//             {!products.length && <div className="empty-state">No products found yet. Try another request.</div>}
//           </div>

//           <section className="grid-card" id="offers-table">
//             <div className="grid-card-heading"><div><span className="eyebrow">POWERED BY AG GRID COMMUNITY</span><h2>Retailer offer intelligence</h2><p>Sort and filter offers, compare in-stock prices, then add the exact merchant offer to your basket.</p></div><span className="count-pill">{offerRows.length} offers</span></div>
//             <div className="ag-grid-wrap">
//               <AgGridProvider modules={AG_GRID_MODULES}>
//                 <AgGridReact<OfferRow>
//                   rowData={offerRows}
//                   columnDefs={columnDefs}
//                   defaultColDef={{ sortable: true, filter: true, resizable: true }}
//                   theme={themeQuartz}
//                   getRowId={params => params.data.rowId}
//                   pagination
//                   paginationPageSize={5}
//                   animateRows
//                   suppressCellFocus={false}
//                 />
//               </AgGridProvider>
//             </div>
//             <div className="grid-note">Retailer prices are discovered via Channel3 and can change. PayPal Sandbox checkout is a payment-flow demo, not a retailer order.</div>
//           </section>

//           <section className="conversation-card">
//             <div className="grid-card-heading"><div><span className="eyebrow">CHANNEL3 CONVERSATIONAL AGENT</span><h2>Refine your shopping plan</h2><p>Ask for alternatives, a different color, or a cheaper option. Follow-ups reuse the conversation when Channel3 returns a conversation ID.</p></div><MessageCircle size={22} /></div>
//             <div className="follow-up-row"><input value={followUp} onChange={e => setFollowUp(e.target.value)} aria-label="Follow-up shopping request" onKeyDown={event => { if (event.key === 'Enter') void sendFollowUp() }} placeholder="e.g. Show me a cheaper option" /><button className="primary-btn" onClick={() => void sendFollowUp()} disabled={busy || !followUp.trim()}>{busy ? 'Thinking…' : 'Refine results'} <ArrowRight size={16} /></button></div>
//             {chatReply && <div className="chat-reply"><Bot size={16} /><p>{chatReply}</p></div>}
//             {conversationId && <div className="conversation-meta">Conversation active · {conversationId}</div>}
//           </section>
//         </section>

//         <aside className="right-rail">
//           <section className="basket-card" id="basket">
//             <div className="rail-heading"><div><ShoppingBag size={18} /><h2>Your basket</h2></div><span className="count-pill">{cart.reduce((s, i) => s + i.quantity, 0)}</span></div>
//             {cart.length ? <div className="basket-items">{cart.map(item => <div className="basket-row" key={item.product.id}><div className="mini-art"><ShoppingBag size={17} /></div><div className="basket-copy"><strong>{item.product.name}</strong><span>Qty {item.quantity}{item.product.merchant ? ` · ${item.product.merchant}` : ''}</span></div><div className="basket-price">{money(item.product.price * item.quantity)}<button onClick={() => removeFromCart(item.product.id)}>Remove</button></div></div>)}</div> : <div className="basket-empty"><ShoppingBag size={24} /><strong>Your basket is waiting</strong><span>Add products or retailer offers to start building your setup.</span></div>}
//             <div className="total-row"><span>Estimated total</span><strong>{money(total)}</strong></div>
//             <button className="checkout-btn" disabled={!cart.length || busy || Boolean(orderResult)} onClick={() => void validateBasket()}>{busy ? 'Working…' : basketValidated ? 'Revalidate basket' : 'Validate basket'} <ArrowRight size={16} /></button>
//             {basketValidated && cart.length > 0 && !orderResult && <div className="paypal-panel">
//               <div className="paypal-panel-title"><ShieldCheck size={16} /> Approve payment securely with PayPal</div>
//               {paypalClientId ? <PayPalProvider
//                 key={`paypal-v6-${paypalClientId}`}
//                 clientId={paypalClientId}
//                 environment="sandbox"
//                 components={['paypal-payments']}
//                 pageType="checkout"
//               >
//                 <PayPalCheckoutControls
//                   disabled={busy}
//                   createOrder={async () => {
//                     try {
//                       setBusy(true)
//                       setMessage('Creating a PayPal Sandbox order…')
//                       return await createPayPalOrder()
//                     } catch (error) {
//                       const detail = getPayPalErrorMessage(error, 'Could not create PayPal order')
//                       setMessage(detail)
//                       throw error
//                     } finally {
//                       setBusy(false)
//                     }
//                   }}
//                   onApprove={async orderId => {
//                     try {
//                       setBusy(true)
//                       setMessage('Buyer approved. Verifying capture with PayPal…')
//                       await capturePayPalOrder(orderId)
//                     } catch (error) {
//                       setMessage(getPayPalErrorMessage(error, 'Capture could not be verified'))
//                     } finally {
//                       setBusy(false)
//                     }
//                   }}
//                   onCancel={() => {
//                     setMessage('Checkout cancelled. No completed payment was recorded.')
//                     setEvents(old => [...old, 'Buyer cancelled PayPal checkout'])
//                   }}
//                   onError={detail => {
//                     setMessage(`PayPal Checkout error: ${detail}`)
//                     setEvents(old => [...old, 'PayPal Checkout reported an error'])
//                   }}
//                 />
//               </PayPalProvider> : <div className="credential-help"><strong>Sandbox Client ID unavailable</strong><span>AgentPay checks the public Client ID from FastAPI first, then <code>VITE_PAYPAL_CLIENT_ID</code> in <code>frontend/.env</code>. Verify <code>PAYPAL_CLIENT_ID</code> in <code>backend/.env</code>, then restart FastAPI. Never put the secret in frontend configuration.</span></div>}
//               <p className="sandbox-warning">Sandbox demo payment only: this does not place or fulfill an order with the retailer. Use the retailer offer link to visit the store. Use a Sandbox buyer account, never real payment credentials.</p>
//             </div>}
//             {orderResult && <div className="order-success"><CheckCircle2 size={22} /><div><strong>Sandbox payment completed</strong><span>Order: {orderResult.orderID}</span><span>Capture: {orderResult.captureID || 'Verified by PayPal'}</span><span>{money(orderResult.total)} · {orderResult.status}</span></div></div>}
//             <div className="trust-note"><ShieldCheck size={15} /> Server-validated · Buyer approval required</div>
//           </section>

//           <section className="activity-card"><div className="rail-heading"><div><SlidersHorizontal size={17} /><h2>Agent activity</h2></div><span className="live-dot">LIVE</span></div><div className="timeline">{events.slice(-7).reverse().map((event, i) => <div className="timeline-event" key={`${event}-${i}`}><span className={i === 0 ? 'timeline-dot current' : 'timeline-dot'} /><p>{event}</p></div>)}</div></section>

//           <section className="observability-card" id="observability">
//             <div className="rail-heading"><div><Activity size={17} /><h2>Elastic trace explorer</h2></div><span className={`elastic-pill ${elasticStatus?.connected ? 'is-connected' : ''}`}>{elasticStatus?.connected ? 'CONNECTED' : elasticStatus?.configured ? 'OFFLINE' : 'LOCAL FALLBACK'}</span></div>
//             <p className="elastic-description">{elasticStatus?.message || 'Checking optional Elastic telemetry…'}</p>
//             <div className="trace-search"><input value={traceQuery} onChange={event => setTraceQuery(event.target.value)} placeholder="Search events" aria-label="Search Elastic events" onKeyDown={event => { if (event.key === 'Enter') void refreshTelemetry(traceQuery) }} /><button onClick={() => void refreshTelemetry(traceQuery)} title="Search events"><Search size={15} /></button><button onClick={() => void refreshTelemetry(traceQuery)} title="Refresh"><RefreshCw size={14} /></button></div>
//             <div className="trace-source">Showing {telemetrySource === 'elasticsearch' ? 'Elastic indexed events' : 'local fallback events'}</div>
//             {elasticEvents.length ? <div className="elastic-events">{elasticEvents.slice(0, 8).map((event, index) => <div className="elastic-event" key={event.event_id || `${event.event_type}-${index}`}><span className="event-time">{gridDate(event.timestamp)}</span><strong>{event.event_type || 'event'}</strong><p>{event.message || ''}</p></div>)}</div> : <div className="elastic-empty">No events yet. Search or validate a basket to create an audit event.</div>}
//             {!elasticStatus?.connected && <><p className="elastic-config-note">{elasticStatus?.configured ? 'Elastic settings are present, but the connection check failed. Use the status message above, verify the Elasticsearch endpoint (not Kibana URL) and API key, then reconnect.' : 'Set ELASTICSEARCH_URL and ELASTIC_API_KEY in backend/.env, then restart FastAPI to enable Elasticsearch indexing.'}</p><button className="elastic-reconnect-btn" onClick={async () => { try { const response = await fetch(`${API}/api/observability/reconnect`, { method: 'POST' }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Elastic reconnect failed'); setElasticStatus(data); await refreshTelemetry(traceQuery) } catch (error) { setMessage(error instanceof Error ? error.message : 'Elastic reconnect failed') } }}><RefreshCw size={13} /> Retry Elastic connection</button></>}
//           </section>
//         </aside>
//       </div>
//       <footer>AgentPay · Hackathon prototype <span>{catalogSource === 'channel3' ? 'Channel3 live discovery · AG Grid offer intelligence · PayPal Sandbox · Elastic optional' : 'Demo catalog · AG Grid · PayPal Sandbox · configure Channel3 for live products'}</span></footer>
//     </main>
//   </div>
// }

import type { ChangeEvent, DragEvent } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AgGridProvider, AgGridReact } from 'ag-grid-react'
import { AllCommunityModule, type ColDef, type ICellRendererParams, themeQuartz } from 'ag-grid-community'
import {
  PayPalProvider,
  PayPalOneTimePaymentButton,
  usePayPal,
  useEligibleMethods,
  INSTANCE_LOADING_STATE,
} from '@paypal/react-paypal-js/sdk-v6'
import {
  Activity, ArrowRight, Bot, CheckCircle2, CircleHelp, CreditCard, ExternalLink,
  FileImage, ImagePlus, MessageCircle, RefreshCw, Search, ShieldCheck, ShoppingBag, SlidersHorizontal,
  Sparkles, Upload, WandSparkles, Workflow, Wrench, RotateCcw, X,
} from 'lucide-react'

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const VITE_PAYPAL_CLIENT_ID = import.meta.env.VITE_PAYPAL_CLIENT_ID || ''
const AG_GRID_MODULES = [AllCommunityModule]

type ProductOffer = { merchant: string; price: number; currency: string; availability: string; condition: string; url: string }
type Product = {
  id: string; name: string; category: string; brand?: string | null; price: number; currency: string
  rating?: number | null; review_count?: number | null; stock?: number | null; availability?: string
  features: string[]; image_url?: string | null; offer_url?: string | null; merchant?: string | null
  offers?: ProductOffer[]; source?: 'channel3' | 'demo'; description?: string | null; channel3_product_id?: string
}
type CartItem = { product: Product; quantity: number }
type OrderResult = { orderID: string; status: string; total: string; currency: string; captureID?: string }
type OfferRow = {
  rowId: string; sourceProductId: string; productName: string; brand: string; category: string
  merchant: string; price: number; currency: string; availability: string; condition: string
  buyUrl: string; source: 'channel3' | 'demo'; product: Product
}
type TelemetryEvent = { event_id?: string; timestamp?: string; event_type?: string; message?: string; details?: Record<string, unknown> }
type ElasticStatus = { configured: boolean; connected: boolean; event_store: string; index?: string | null; message: string; channel3_configured?: boolean; paypal_sandbox_configured?: boolean }
type PaymentRecord = { order_id: string; status: string; total: string; currency: string; capture_id?: string | null; refunded_total: string; refund_status?: string | null; updated_at?: string | null }
type AutomationRun = { order_id: string; status: string; message: string; timestamp?: string; http_status?: number }
type AutomationStatus = { configured: boolean; mode: string; message: string; runs: AutomationRun[] }
type PayPalMcpStatus = { configured: boolean; enabled: boolean; mode: string; message: string }
type PayPalMcpTool = { name: string; description?: string; inputSchema?: Record<string, unknown> }

const money = (value: number | string) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))
const gridDate = (value?: string) => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''


type PayPalCheckoutControlsProps = {
  disabled: boolean
  createOrder: () => Promise<string>
  onApprove: (orderId: string) => Promise<void>
  onCancel: () => void
  onError: (message: string) => void
}

function getPayPalErrorMessage(value: unknown, fallback: string): string {
  if (value instanceof Error && value.message.trim()) return value.message
  if (typeof value === 'object' && value !== null && 'message' in value) {
    const message = (value as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
  return fallback
}

/** Must render inside PayPalProvider so SDK and eligibility hooks are available. */
function PayPalCheckoutControls({
  disabled,
  createOrder,
  onApprove,
  onCancel,
  onError,
}: PayPalCheckoutControlsProps) {
  const { loadingStatus, error: sdkError } = usePayPal()
  const {
    eligiblePaymentMethods,
    isLoading: eligibilityLoading,
    error: eligibilityError,
  } = useEligibleMethods({ payload: { currencyCode: 'USD' } })

  if (loadingStatus === INSTANCE_LOADING_STATE.REJECTED || sdkError) {
    return (
      <div className="credential-help">
        <strong>PayPal SDK could not initialize</strong>
        <span>{getPayPalErrorMessage(sdkError, 'Check the Sandbox Client ID, app environment, and browser console.')}</span>
      </div>
    )
  }

  if (loadingStatus === INSTANCE_LOADING_STATE.PENDING || eligibilityLoading) {
    return <div className="paypal-loading">Loading PayPal checkout and checking buyer eligibility…</div>
  }

  if (eligibilityError) {
    return (
      <div className="credential-help">
        <strong>Could not check PayPal eligibility</strong>
        <span>{getPayPalErrorMessage(eligibilityError, 'Retry after checking the network and Sandbox configuration.')}</span>
      </div>
    )
  }

  if (!eligiblePaymentMethods?.isEligible('paypal')) {
    return (
      <div className="credential-help">
        <strong>PayPal checkout isn't eligible in this session</strong>
        <span>Check the Sandbox app configuration and try a Personal Sandbox buyer account. Eligibility can depend on the buyer and currency.</span>
      </div>
    )
  }

  return (
    <PayPalOneTimePaymentButton
      type="pay"
      presentationMode="auto"
      disabled={disabled}
      createOrder={async () => ({ orderId: await createOrder() })}
      onApprove={async data => {
        await onApprove(data.orderId)
      }}
      onCancel={onCancel}
      onError={error => onError(getPayPalErrorMessage(error, 'Please retry or check the Sandbox configuration.'))}
    />
  )
}

export default function App() {
  const [products, setProducts] = useState<Product[]>([])
  const [catalogSource, setCatalogSource] = useState<'channel3' | 'demo'>('demo')
  const [paypalClientId, setPaypalClientId] = useState<string>(VITE_PAYPAL_CLIENT_ID)
  const [cart, setCart] = useState<CartItem[]>([])
  const [prompt, setPrompt] = useState('Build me a work-from-home setup under $80. Prioritize reliability and strong reviews.')
  const [budget, setBudget] = useState<number | null>(80)
  const [events, setEvents] = useState<string[]>(['AgentPay workspace initialized', 'Audit events use Elastic when configured'])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [basketValidated, setBasketValidated] = useState(false)
  const [orderResult, setOrderResult] = useState<OrderResult | null>(null)
  const [validatedTotal, setValidatedTotal] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [followUp, setFollowUp] = useState('Can you find a cheaper option with the same features?')
  const [chatReply, setChatReply] = useState('')
  const [elasticStatus, setElasticStatus] = useState<ElasticStatus | null>(null)
  const [elasticEvents, setElasticEvents] = useState<TelemetryEvent[]>([])
  const [traceQuery, setTraceQuery] = useState('')
  const [telemetrySource, setTelemetrySource] = useState('memory')
  const [photoDataUrl, setPhotoDataUrl] = useState('')
  const [photoFilename, setPhotoFilename] = useState('')
  const [photoPrompt, setPhotoPrompt] = useState('Find products similar to the items in this photo. Keep the setup under $200.')
  const [photoBusy, setPhotoBusy] = useState(false)
  const [photoDragging, setPhotoDragging] = useState(false)
  const [recentOrders, setRecentOrders] = useState<PaymentRecord[]>([])
  const [refundAmounts, setRefundAmounts] = useState<Record<string, string>>({})
  const [refundNote, setRefundNote] = useState('Refund requested by customer')
  const [refundMessage, setRefundMessage] = useState('')
  const [adminToken, setAdminToken] = useState('')
  const [refundBusyOrder, setRefundBusyOrder] = useState<string | null>(null)
  const [automationState, setAutomationState] = useState<AutomationStatus | null>(null)
  const [mcpState, setMcpState] = useState<PayPalMcpStatus | null>(null)
  const [mcpTools, setMcpTools] = useState<PayPalMcpTool[]>([])
  const [mcpSelectedTool, setMcpSelectedTool] = useState('')
  const [mcpArguments, setMcpArguments] = useState('{\n  \"order_id\": \"\"\n}')
  const [mcpResult, setMcpResult] = useState('')
  const [mcpBusy, setMcpBusy] = useState(false)

  const total = useMemo(() => cart.reduce((sum, item) => sum + item.product.price * item.quantity, 0), [cart])

  const offerRows = useMemo<OfferRow[]>(() => products.flatMap(product => {
    const offers = product.offers?.length
      ? product.offers
      : [{
        merchant: product.merchant || (product.source === 'channel3' ? 'Retailer' : 'AgentPay demo catalog'),
        price: product.price, currency: product.currency || 'USD',
        availability: product.availability || (product.source === 'channel3' ? 'Unknown' : 'Demo item'),
        condition: 'unknown', url: product.offer_url || '',
      }]
    return offers.map((offer, index) => ({
      rowId: `${product.id}-${offer.merchant}-${offer.price}-${index}`,
      sourceProductId: product.id,
      productName: product.name,
      brand: product.brand || product.category,
      category: product.category,
      merchant: offer.merchant,
      price: Number(offer.price),
      currency: offer.currency || 'USD',
      availability: offer.availability,
      condition: offer.condition || 'unknown',
      buyUrl: offer.url || '',
      source: product.source || 'demo',
      product,
    }))
  }), [products])

  const refreshTelemetry = useCallback(async (query = traceQuery) => {
    try {
      const [statusResponse, eventsResponse, historyResponse, automationResponse, mcpResponse] = await Promise.all([
        fetch(`${API}/api/observability/status`),
        fetch(`${API}/api/observability/events?limit=12${query.trim() ? `&q=${encodeURIComponent(query.trim())}` : ''}`),
        fetch(`${API}/api/payments/history?limit=20`, { headers: { 'X-AgentPay-Admin-Token': adminToken.trim() } }),
        fetch(`${API}/api/automation/status`),
        fetch(`${API}/api/paypal-mcp/status`),
      ])
      if (statusResponse.ok) setElasticStatus(await statusResponse.json())
      if (eventsResponse.ok) {
        const data = await eventsResponse.json()
        setElasticEvents(data.events || [])
        setTelemetrySource(data.source || 'memory')
      }
      if (historyResponse.ok) { const data = await historyResponse.json(); setRecentOrders(data.orders || []) }
      if (automationResponse.ok) setAutomationState(await automationResponse.json())
      if (mcpResponse.ok) setMcpState(await mcpResponse.json())
    } catch {
      setElasticStatus({ configured: false, connected: false, event_store: 'memory', message: 'Observability API is unavailable.' })
    }
  }, [traceQuery, adminToken])

  useEffect(() => {
    // Runtime public config is a fallback for cases where Vite was launched from
    // a different working directory and did not load frontend/.env. The endpoint
    // returns the public Client ID only; the PayPal secret never leaves FastAPI.
    fetch(`${API}/api/public-config`)
      .then(async response => { if (!response.ok) throw new Error('Public configuration unavailable'); return response.json() })
      .then(data => { if (typeof data.paypal_client_id === 'string' && data.paypal_client_id.trim()) setPaypalClientId(data.paypal_client_id.trim()) })
      .catch(() => { /* Keep the Vite public Client ID fallback if available. */ })

    fetch(`${API}/api/agent/search`)
      .then(async r => { if (!r.ok) throw new Error('Could not load product catalog'); return r.json() })
      .then(data => {
        setProducts(data.items || [])
        setCatalogSource(data.source === 'channel3' ? 'channel3' : 'demo')
        if (data.message) setMessage(data.message)
      })
      .catch(() => setMessage('API unavailable. Start the FastAPI backend on port 8000.'))
    void refreshTelemetry('')
  }, []) // initial bootstrap only

  function resetCheckoutState() {
    setBasketValidated(false)
    setOrderResult(null)
    setValidatedTotal(null)
  }

  async function planShopping() {
    setBusy(true); setMessage(''); resetCheckoutState(); setConversationId(null); setChatReply('')
    try {
      // Start a real Channel3 Conversational Agent turn first. This returns the
      // conversation ID required for follow-ups such as "show something cheaper".
      // A normal /search call alone cannot establish conversational context.
      try {
        const response = await fetch(`${API}/api/agent/chat`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: prompt, conversation_id: null, budget: null, user_id: 'agentpay-web-demo' }),
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Channel3 Conversational Agent request failed')
        if (data.conversation_id) setConversationId(data.conversation_id)
        if (typeof data.constraints?.max_price === 'number') setBudget(data.constraints.max_price)
        else setBudget(null)
        let items: Product[] = Array.isArray(data.items) ? data.items : []
        let source: 'channel3' | 'demo' = data.source === 'channel3' ? 'channel3' : 'demo'
        let reply = data.text || 'Shopping conversation started.'

        // Some valid conversational turns may answer in text before returning
        // product cards. Keep their conversation ID and fill the grid from search.
        if (!items.length) {
          const searchResponse = await fetch(`${API}/api/agent/plan`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }),
          })
          const searchData = await searchResponse.json()
          if (searchResponse.ok && Array.isArray(searchData.items) && searchData.items.length) {
            items = searchData.items
            source = searchData.source === 'channel3' ? 'channel3' : 'demo'
          }
        }
        setProducts(items)
        setCatalogSource(source)
        setChatReply(reply)
        setEvents(old => [...old, `Channel3 conversation started: ${items.length} product matches`])
        setMessage(data.conversation_id
          ? 'Shopping plan ready. Follow-up requests will use this conversation context.'
          : 'Shopping results loaded, but Channel3 did not return a conversation ID. Contextual follow-ups may not persist.')
      } catch (conversationError) {
        // Search remains useful if the conversational endpoint is unavailable,
        // but tell the user clearly that contextual follow-ups are not active.
        const response = await fetch(`${API}/api/agent/plan`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }),
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Shopping plan could not be created')
        const items: Product[] = data.items || []
        setProducts(items)
        setCatalogSource(data.source === 'channel3' ? 'channel3' : 'demo')
        setBudget(typeof data.constraints?.max_price === 'number' ? data.constraints.max_price : null)
        setChatReply(`Contextual shopping session could not start: ${conversationError instanceof Error ? conversationError.message : 'Channel3 conversation unavailable'}`)
        setMessage(`${data.message || 'Search results ready.'} Contextual follow-ups are not active yet.`)
        setEvents(old => [...old, `${data.source === 'channel3' ? 'Channel3 search' : 'Demo catalog search'}: ${items.length} matches`])
      }
      await refreshTelemetry('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not create a shopping plan')
    } finally { setBusy(false) }
  }

  const addToCart = useCallback((product: Product) => {
    setCart(old => {
      const existing = old.find(item => item.product.id === product.id)
      return existing
        ? old.map(item => item.product.id === product.id
          ? { ...item, quantity: product.stock == null ? item.quantity + 1 : Math.min(item.quantity + 1, product.stock) }
          : item)
        : [...old, { product, quantity: 1 }]
    })
    resetCheckoutState()
    setEvents(old => [...old, `Added ${product.name}${product.merchant ? ` from ${product.merchant}` : ''} to basket`])
  }, [])

  const addOfferToCart = useCallback(async (row: OfferRow) => {
    setBusy(true); setMessage('')
    try {
      let product = row.product
      if (row.source === 'channel3') {
        const response = await fetch(`${API}/api/catalog/select-offer`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_id: row.sourceProductId, merchant: row.merchant }),
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Could not select that retailer offer')
        product = data.product
      }
      addToCart(product)
      setMessage(`Added ${product.name} from ${product.merchant || 'the demo catalog'} to your basket.`)
      await refreshTelemetry('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not add that offer')
    } finally { setBusy(false) }
  }, [addToCart, refreshTelemetry])

  const columnDefs = useMemo<ColDef<OfferRow>[]>(() => [
    { headerName: 'Product', field: 'productName', minWidth: 190, flex: 2, filter: 'agTextColumnFilter' },
    { headerName: 'Brand / type', field: 'brand', minWidth: 120, flex: 1 },
    { headerName: 'Retailer', field: 'merchant', minWidth: 130, flex: 1.2, filter: 'agTextColumnFilter' },
    { headerName: 'Price', field: 'price', minWidth: 105, maxWidth: 125, sort: 'asc', valueFormatter: params => money(Number(params.value)) },
    { headerName: 'Availability', field: 'availability', minWidth: 125, flex: 0.9 },
    { headerName: 'Condition', field: 'condition', minWidth: 100, flex: 0.7 },
    {
      headerName: 'Action', minWidth: 145, maxWidth: 155, sortable: false, filter: false,
      cellRenderer: (params: ICellRendererParams<OfferRow>) => params.data
        ? <button className="grid-add-button" disabled={busy} onClick={() => void addOfferToCart(params.data!)}>Add to basket</button>
        : null,
    },
  ], [addOfferToCart, busy])

  function removeFromCart(id: string) {
    setCart(old => old.filter(item => item.product.id !== id))
    resetCheckoutState()
  }

  async function validateBasket() {
    setBusy(true); setMessage(''); resetCheckoutState()
    try {
      const response = await fetch(`${API}/api/cart/validate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: cart.map(item => ({ product_id: item.product.id, quantity: item.quantity })), budget }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Basket validation failed')
      setCart(old => old.map(cartItem => {
        const refreshed = data.items.find((item: any) => item.product_id === cartItem.product.id)
        return refreshed ? { ...cartItem, product: { ...cartItem.product, price: Number(refreshed.unit_price), offer_url: refreshed.offer_url || cartItem.product.offer_url, merchant: refreshed.merchant || cartItem.product.merchant } } : cartItem
      }))
      setValidatedTotal(String(data.total)); setBasketValidated(true)
      setMessage(`Basket validated by server. Total: ${money(data.total)}. Live retailer offers were refreshed; review and approve the PayPal Sandbox payment below.`)
      setEvents(old => [...old, `Basket validated: ${money(data.total)}`, 'Waiting for explicit buyer approval'])
      await refreshTelemetry('')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Validation failed') }
    finally { setBusy(false) }
  }

  async function createPayPalOrder() {
    const response = await fetch(`${API}/api/payments/create-order`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: cart.map(item => ({ product_id: item.product.id, quantity: item.quantity })), budget, expected_total: validatedTotal === null ? null : Number(validatedTotal) }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Could not create PayPal order')
    setEvents(old => [...old, `PayPal Sandbox order created: ${data.orderID}`])
    await refreshTelemetry('')
    return data.orderID as string
  }

  async function capturePayPalOrder(orderID: string) {
    const response = await fetch(`${API}/api/payments/capture/${encodeURIComponent(orderID)}`, { method: 'POST' })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Could not verify PayPal capture')
    const capture = data.purchase_units?.flatMap((unit: any) => unit.payments?.captures || [])[0]
    if (data.status !== 'COMPLETED' || capture?.status !== 'COMPLETED') throw new Error('PayPal did not confirm a completed capture. Do not treat this order as paid.')
    const result: OrderResult = { orderID, status: data.status, total: String(capture.amount?.value || total.toFixed(2)), currency: capture.amount?.currency_code || 'USD', captureID: capture.id }
    setOrderResult(result); setBasketValidated(false)
    setMessage(`Payment successful in Sandbox. PayPal confirmed ${money(result.total)} as ${result.status}.`)
    setEvents(old => [...old, `Payment capture completed: ${result.captureID || orderID}`])
    await refreshTelemetry('')
  }

  function loadPhotoFile(file?: File | null) {
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setMessage('Use a JPEG, PNG, or WebP photo.')
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      setMessage('Photo must be 8 MB or smaller.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setPhotoDataUrl(reader.result)
        setPhotoFilename(file.name)
        setMessage('Photo ready. AgentPay will send it to Channel3 for visual product discovery.')
      }
    }
    reader.onerror = () => setMessage('Could not read that image file. Try another photo.')
    reader.readAsDataURL(file)
  }

  function handlePhotoFile(event: ChangeEvent<HTMLInputElement>) {
    loadPhotoFile(event.target.files?.[0])
    // Allows choosing the same photo again after removing it.
    event.target.value = ''
  }

  function handlePhotoDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setPhotoDragging(false)
    loadPhotoFile(event.dataTransfer.files?.[0])
  }

  async function searchFromPhoto() {
    if (!photoDataUrl) { setMessage('Choose a photo first.'); return }
    setPhotoBusy(true); setBusy(true); setMessage('Analyzing your photo with Channel3…'); resetCheckoutState()
    try {
      const response = await fetch(`${API}/api/agent/photo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_data_url: photoDataUrl, prompt: photoPrompt, user_id: 'agentpay-web-demo' }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Photo search failed')
      const items: Product[] = Array.isArray(data.items) ? data.items : []
      setProducts(items)
      setCatalogSource('channel3')
      setConversationId(data.conversation_id || null)
      setBudget(typeof data.constraints?.max_price === 'number' ? data.constraints.max_price : null)
      setPrompt(photoPrompt)
      setChatReply(data.text || (data.detected_objects?.length ? `Detected: ${data.detected_objects.join(', ')}` : 'Visual search completed.'))
      setMessage(data.message || `Channel3 returned ${items.length} visual matches.`)
      setEvents(old => [...old, `Photo shopping search: ${items.length} live matches`])
      await refreshTelemetry('')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Photo search failed') }
    finally { setPhotoBusy(false); setBusy(false) }
  }

  async function refundPayment(order: PaymentRecord, amount?: number) {
    const remaining = Math.max(0, Number(order.total) - Number(order.refunded_total || '0'))
    if (!order.capture_id || remaining <= 0) { setRefundMessage('This order has no remaining refundable captured balance.'); return }
    if (amount !== undefined && (!Number.isFinite(amount) || amount <= 0 || amount > remaining)) {
      setRefundMessage(`Enter an amount greater than $0 and no more than ${money(remaining)}.`); return
    }
    const amountText = amount === undefined ? `the remaining ${money(remaining)}` : `${money(amount)}`
    const confirmed = window.confirm(`Submit a PayPal Sandbox refund for ${amountText} on order ${order.order_id}? This action cannot be cancelled.`)
    if (!confirmed) return
    setRefundBusyOrder(order.order_id); setRefundMessage('Submitting refund to PayPal Sandbox…')
    try {
      const response = await fetch(`${API}/api/payments/refund/${encodeURIComponent(order.order_id)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-AgentPay-Admin-Token': adminToken.trim() },
        body: JSON.stringify({ amount: amount ?? null, note_to_payer: refundNote.trim() || 'AgentPay Sandbox refund', confirm: true }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Refund request failed')
      setRefundMessage(`Refund ${data.status}: ${data.refund_id || 'ID pending'} · ${money(data.amount)}. Refunded total: ${money(data.refunded_total)}.`)
      setEvents(old => [...old, `PayPal refund ${data.status}: ${data.refund_id || order.order_id}`])
      await refreshTelemetry('')
    } catch (error) { setRefundMessage(error instanceof Error ? error.message : 'Refund request failed') }
    finally { setRefundBusyOrder(null) }
  }

  async function discoverPayPalMcpTools() {
    setMcpBusy(true); setMcpResult('Discovering read-only tools from the official PayPal MCP server…')
    try {
      const response = await fetch(`${API}/api/paypal-mcp/tools`, { headers: { 'X-AgentPay-Admin-Token': adminToken.trim() } })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'PayPal MCP discovery failed')
      const tools: PayPalMcpTool[] = Array.isArray(data.tools) ? data.tools : []
      setMcpTools(tools)
      setMcpSelectedTool(current => tools.some(tool => tool.name === current) ? current : (tools[0]?.name || ''))
      setMcpResult(`Discovered ${tools.length} read-only PayPal MCP tool(s).`)
      await refreshTelemetry('')
    } catch (error) { setMcpResult(error instanceof Error ? error.message : 'PayPal MCP discovery failed') }
    finally { setMcpBusy(false) }
  }

  async function runPayPalMcpTool() {
    if (!mcpSelectedTool) { setMcpResult('Discover tools and choose a read-only tool first.'); return }
    let args: Record<string, unknown>
    try {
      args = JSON.parse(mcpArguments || '{}') as Record<string, unknown>
      if (!args || Array.isArray(args) || typeof args !== 'object') throw new Error('Arguments must be a JSON object.')
    } catch (error) { setMcpResult(error instanceof Error ? error.message : 'Arguments must be valid JSON.'); return }
    setMcpBusy(true); setMcpResult('Calling the PayPal MCP tool…')
    try {
      const response = await fetch(`${API}/api/paypal-mcp/call`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-AgentPay-Admin-Token': adminToken.trim() },
        body: JSON.stringify({ tool_name: mcpSelectedTool, arguments: args }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'PayPal MCP call failed')
      setMcpResult(JSON.stringify(data, null, 2))
      await refreshTelemetry('')
    } catch (error) { setMcpResult(error instanceof Error ? error.message : 'PayPal MCP call failed') }
    finally { setMcpBusy(false) }
  }

  async function retryAutomation(orderId: string) {
    if (!adminToken.trim()) { setRefundMessage('Enter the AgentPay operator token before retrying external automations.'); return }
    setRefundMessage(`Retrying post-purchase event for ${orderId}…`)
    try {
      const response = await fetch(`${API}/api/automation/retry/${encodeURIComponent(orderId)}`, {
        method: 'POST', headers: { 'X-AgentPay-Admin-Token': adminToken.trim() },
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Automation retry failed')
      setRefundMessage(`Post-purchase workflow ${data.status}: ${data.message}`)
      await refreshTelemetry('')
    } catch (error) {
      setRefundMessage(error instanceof Error ? error.message : 'Automation retry failed')
    }
  }

  async function sendFollowUp() {
    const text = followUp.trim()
    if (!text) return
    setBusy(true); setChatReply('')
    const messageToSend = conversationId ? text : `${prompt}\n\nFollow-up requirement: ${text}`
    try {
      const response = await fetch(`${API}/api/agent/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageToSend, conversation_id: conversationId, budget, user_id: 'agentpay-web-demo' }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Channel3 Conversational Agent request failed')
      if (data.conversation_id) setConversationId(data.conversation_id)
      if (Array.isArray(data.items) && data.items.length) {
        setProducts(data.items)
        setCatalogSource('channel3')
        resetCheckoutState()
      }
      if (typeof data.constraints?.max_price === 'number') setBudget(data.constraints.max_price)
      setChatReply(data.text || 'Channel3 returned the conversation turn. Check the offer table for product cards.')
      setEvents(old => [...old, `Channel3 conversation turn: ${(data.items || []).length} product cards`])
      await refreshTelemetry('')
    } catch (error) {
      setChatReply(error instanceof Error ? error.message : 'Conversational refinement failed')
    } finally { setBusy(false) }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><WandSparkles size={20} /></div><div><strong>agentpay</strong><span>AI commerce agent</span></div></div>
      <div className="workspace-label">WORKSPACE</div>
      <button className="nav-item active" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}><ShoppingBag size={17} /> Shopping agent</button>
      <button className="nav-item" onClick={() => document.getElementById('basket')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}><CreditCard size={17} /> Orders & payments</button>
      <button className="nav-item" onClick={() => document.getElementById('observability')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}><Activity size={17} /> Observability</button>
      <div className="sidebar-bottom"><ShieldCheck size={17} /><div><strong>Human-approved payments</strong><span>AgentPay never pays without your approval.</span></div></div>
    </aside>

    <main className="main">
      <header className="topbar"><div><span className="eyebrow">YOUR PERSONAL SHOPPING AGENT</span><h1>Let's find your best fit.</h1><p>Tell AgentPay what you need. It will research, compare, and help you check out.</p></div><div className="sandbox-pill"><span /> PayPal Sandbox demo · USD</div></header>
      {message && <div className={`notice ${orderResult ? 'success-notice' : ''}`} role="status">{orderResult ? <CheckCircle2 size={17} /> : <CircleHelp size={17} />}<span>{message}</span><button onClick={() => setMessage('')} aria-label="Dismiss">×</button></div>}

      <section className="prompt-card">
        <div className="section-icon"><Sparkles size={19} /></div>
        <div className="prompt-content"><label htmlFor="shopping-prompt">WHAT ARE YOU LOOKING FOR?</label><textarea id="shopping-prompt" value={prompt} onChange={e => setPrompt(e.target.value)} rows={3} /><div className="prompt-footer"><span>{catalogSource === 'channel3' ? 'Channel3 agentic search · in-stock USD offers · prices may change.' : 'Demo catalog prices are illustrative USD amounts for Sandbox checkout.'}</span><button className="primary-btn" onClick={() => void planShopping()} disabled={busy || prompt.trim().length < 3}>{busy ? 'Working…' : 'Build my plan'} <ArrowRight size={16} /></button></div></div>
      </section>

      <section className="photo-search-card photo-studio-card" id="photo-shopping">
        <div className="photo-studio-header">
          <div className="photo-card-heading">
            <div className="section-icon photo-studio-icon"><ImagePlus size={20} /></div>
            <div>
              <span className="eyebrow">VISUAL SHOPPING AGENT · IMAGE TO PRODUCT</span>
              <h2>Turn inspiration into a shoppable setup</h2>
              <p>Upload a desk, room, outfit, or product photo. AgentPay finds similar products and real retailer offers you can compare.</p>
            </div>
          </div>
          <div className="photo-ai-badge"><Sparkles size={14} /> Channel3 visual discovery</div>
        </div>

        <div className="photo-studio-grid">
          <div className="photo-upload-pane">
            <div className="photo-pane-label"><span>01</span> Your inspiration</div>
            <label
              className={`photo-dropzone ${photoDragging ? 'is-dragging' : ''} ${photoDataUrl ? 'has-photo' : ''}`}
              htmlFor="agentpay-photo"
              onDragEnter={(event) => { event.preventDefault(); setPhotoDragging(true) }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setPhotoDragging(false)}
              onDrop={handlePhotoDrop}
            >
              <input className="photo-file-input" id="agentpay-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={handlePhotoFile} />
              {photoDataUrl ? (
                <>
                  <img src={photoDataUrl} alt="Selected shopping reference" className="photo-dropzone-image" />
                  <div className="photo-image-overlay">
                    <span className="photo-ready-pill"><CheckCircle2 size={14} /> Photo ready</span>
                    <span className="photo-replace-hint">Click to replace image</span>
                  </div>
                </>
              ) : (
                <div className="photo-upload-empty">
                  <div className="photo-upload-icon"><Upload size={24} /></div>
                  <strong>Drop your inspiration here</strong>
                  <span>or <b>browse files</b> from your device</span>
                  <div className="photo-filetypes"><span>JPG</span><span>PNG</span><span>WEBP</span><small>Up to 8 MB</small></div>
                </div>
              )}
            </label>
            <div className="photo-file-meta">
              {photoDataUrl ? (
                <>
                  <span className="photo-file-name"><FileImage size={14} /> <span title={photoFilename}>{photoFilename || 'Selected photo'}</span></span>
                  <button type="button" className="photo-remove-btn" onClick={() => { setPhotoDataUrl(''); setPhotoFilename(''); const input = document.getElementById('agentpay-photo') as HTMLInputElement | null; if (input) input.value = '' }}><X size={13} /> Remove</button>
                </>
              ) : <span className="photo-hint"><ShieldCheck size={14} /> Use a clear photo with products visible. Avoid sensitive or personal images.</span>}
            </div>
          </div>

          <div className="photo-options-pane">
            <div className="photo-pane-label"><span>02</span> Shopping goal</div>
            <h3>What should AgentPay find?</h3>
            <p className="photo-options-copy">Tell the agent how to recreate the look, what to prioritize, and how much to spend.</p>
            <label className="photo-prompt-label" htmlFor="photo-prompt">Describe your ideal result</label>
            <textarea id="photo-prompt" rows={4} value={photoPrompt} onChange={event => setPhotoPrompt(event.target.value)} placeholder="e.g. Recreate this home-office setup under $200. Prioritize compact, reliable products." />
            <div className="photo-suggestion-label">QUICK START</div>
            <div className="photo-suggestion-chips">
              <button type="button" onClick={() => setPhotoPrompt('Recreate this setup under $200. Find similar products and prioritize best value.')}>Recreate the setup</button>
              <button type="button" onClick={() => setPhotoPrompt('Find products that look as close as possible to the items in this photo. Show in-stock offers.')}>Find similar items</button>
              <button type="button" onClick={() => setPhotoPrompt('Shop the look in this photo with a budget under $150. Prioritize matching style and value.')}>Shop the look</button>
            </div>
            <div className="photo-budget-note"><Sparkles size={15} /><span>Live retailer offers where available. You stay in control of the basket and payment.</span></div>
            <button className="primary-btn photo-submit-btn" onClick={() => void searchFromPhoto()} disabled={busy || !photoDataUrl || photoPrompt.trim().length < 3}>
              {photoBusy ? <><RefreshCw className="photo-spin" size={16} /> Finding visual matches…</> : <><WandSparkles size={16} /> Find matching products <ArrowRight size={16} /></>}
            </button>
          </div>
        </div>
        <div className="photo-studio-footer"><span><CheckCircle2 size={14} /> Image processed for product discovery</span><span>JPEG · PNG · WEBP <i /> Max 8 MB</span></div>
      </section>

      <div className="content-grid">
        <section className="catalog-section">
          <div className="section-heading"><div><span className="eyebrow">CURATED FOR YOUR NEEDS</span><h2>Product matches</h2></div><span className={`count-pill ${catalogSource === 'channel3' ? 'live-badge' : ''}`}>{catalogSource === 'channel3' ? 'CHANNEL3 LIVE' : 'DEMO CATALOG'} · {products.length}</span></div>
          <div className="product-grid">
            {products.map((p, index) => <article className="product-card" key={p.id}>
              <div className={`product-art art-${index % 4}`}><div className="product-symbol">{p.category.toLowerCase().includes('headphone') || p.category.toLowerCase().includes('audio') ? '◖' : p.category.toLowerCase().includes('keyboard') ? '▤' : p.category.toLowerCase().includes('mouse') ? '◒' : '◇'}</div>{p.image_url && <img className="channel3-image" src={p.image_url} alt={p.name} loading="lazy" onError={event => { event.currentTarget.style.display = 'none' }} />}<span className="match-tag">{catalogSource === 'channel3' ? (index === 0 ? 'CHANNEL3 PICK' : 'LIVE RESULT') : (index === 0 ? 'TOP MATCH' : `${Math.max(78, 94 - index * 7)}% MATCH`)}</span></div>
              <div className="product-info"><span className="category">{p.brand || p.category}</span><h3>{p.name}</h3>{typeof p.rating === 'number' ? <div className="rating">★ <strong>{p.rating.toFixed(1)}</strong> {typeof p.review_count === 'number' && <span>({p.review_count} reviews)</span>}</div> : <div className="rating live-offer">● <strong>{p.availability || 'Catalog offer'}</strong>{p.merchant && <span> · {p.merchant}</span>}</div>}<div className="product-features">{(p.features || []).slice(0, 2).join(' · ') || p.description || (p.merchant ? `Offer from ${p.merchant}` : 'Demo product catalog')}</div>{p.offer_url && <a className="offer-link" href={p.offer_url} target="_blank" rel="noreferrer">View {p.merchant || 'retailer'} offer ↗</a>}<div className="product-bottom"><strong>{money(p.price)}</strong><button className="add-btn" onClick={() => addToCart(p)}>Add <span>+</span></button></div></div>
            </article>)}
            {!products.length && <div className="empty-state">No products found yet. Try another request.</div>}
          </div>

          <section className="grid-card" id="offers-table">
            <div className="grid-card-heading"><div><span className="eyebrow">POWERED BY AG GRID COMMUNITY</span><h2>Retailer offer intelligence</h2><p>Sort and filter offers, compare in-stock prices, then add the exact merchant offer to your basket.</p></div><span className="count-pill">{offerRows.length} offers</span></div>
            <div className="ag-grid-wrap">
              <AgGridProvider modules={AG_GRID_MODULES}>
                <AgGridReact<OfferRow>
                  rowData={offerRows}
                  columnDefs={columnDefs}
                  defaultColDef={{ sortable: true, filter: true, resizable: true }}
                  theme={themeQuartz}
                  getRowId={params => params.data.rowId}
                  pagination
                  paginationPageSize={5}
                  animateRows
                  suppressCellFocus={false}
                />
              </AgGridProvider>
            </div>
            <div className="grid-note">Retailer prices are discovered via Channel3 and can change. PayPal Sandbox checkout is a payment-flow demo, not a retailer order.</div>
          </section>

          <section className="conversation-card">
            <div className="grid-card-heading"><div><span className="eyebrow">CHANNEL3 CONVERSATIONAL AGENT</span><h2>Refine your shopping plan</h2><p>Ask for alternatives, a different color, or a cheaper option. Follow-ups reuse the conversation when Channel3 returns a conversation ID.</p></div><MessageCircle size={22} /></div>
            <div className="follow-up-row"><input value={followUp} onChange={e => setFollowUp(e.target.value)} aria-label="Follow-up shopping request" onKeyDown={event => { if (event.key === 'Enter') void sendFollowUp() }} placeholder="e.g. Show me a cheaper option" /><button className="primary-btn" onClick={() => void sendFollowUp()} disabled={busy || !followUp.trim()}>{busy ? 'Thinking…' : 'Refine results'} <ArrowRight size={16} /></button></div>
            {chatReply && <div className="chat-reply"><Bot size={16} /><p>{chatReply}</p></div>}
            {conversationId && <div className="conversation-meta">Conversation active · {conversationId}</div>}
          </section>

          <section className="mcp-card" id="paypal-mcp">
            <div className="grid-card-heading"><div><span className="eyebrow">PAYPAL AGENT TOOLKIT / MCP</span><h2>PayPal tool explorer</h2><p>Connect to the official Sandbox MCP server to discover and run read-only PayPal tools. Payment mutations stay behind AgentPay's explicit approval workflows.</p></div><Wrench size={21} /></div>
            <div className="mcp-status-line"><span className={`status-dot ${mcpState?.configured ? 'status-dot-ready' : ''}`} />{mcpState?.message || 'Checking MCP configuration…'}</div>
            <div className="mcp-actions"><button className="secondary-btn" onClick={() => void discoverPayPalMcpTools()} disabled={mcpBusy || !mcpState?.configured || !adminToken.trim()}>{mcpBusy ? 'Connecting…' : 'Discover MCP tools'}</button></div>
            {mcpTools.length > 0 && <div className="mcp-tool-form"><label htmlFor="mcp-tool-select">Read-only tool</label><select id="mcp-tool-select" value={mcpSelectedTool} onChange={event => { setMcpSelectedTool(event.target.value); setMcpResult('') }}>{mcpTools.map(tool => <option key={tool.name} value={tool.name}>{tool.name}</option>)}</select><p className="mcp-tool-description">{mcpTools.find(tool => tool.name === mcpSelectedTool)?.description || 'No description supplied by MCP server.'}</p><label htmlFor="mcp-arguments">Tool arguments (JSON object)</label><textarea id="mcp-arguments" rows={3} value={mcpArguments} onChange={event => setMcpArguments(event.target.value)} /><button className="primary-btn" onClick={() => void runPayPalMcpTool()} disabled={mcpBusy || !adminToken.trim()}>{mcpBusy ? 'Running…' : 'Run read-only tool'} <ArrowRight size={16} /></button></div>}
            {mcpResult && <pre className="mcp-result">{mcpResult}</pre>}
            <p className="mcp-safety-note">Requires <code>PAYPAL_MCP_ENABLED=true</code>, Node.js 18+, Sandbox credentials, and the operator token entered in Payment Lifecycle. Mutating MCP tool names are blocked; refunds and captures use dedicated approval endpoints.</p>
          </section>
        </section>

        <aside className="right-rail">
          <section className="basket-card" id="basket">
            <div className="rail-heading"><div><ShoppingBag size={18} /><h2>Your basket</h2></div><span className="count-pill">{cart.reduce((s, i) => s + i.quantity, 0)}</span></div>
            {cart.length ? <div className="basket-items">{cart.map(item => <div className="basket-row" key={item.product.id}><div className="mini-art"><ShoppingBag size={17} /></div><div className="basket-copy"><strong>{item.product.name}</strong><span>Qty {item.quantity}{item.product.merchant ? ` · ${item.product.merchant}` : ''}</span></div><div className="basket-price">{money(item.product.price * item.quantity)}<button onClick={() => removeFromCart(item.product.id)}>Remove</button></div></div>)}</div> : <div className="basket-empty"><ShoppingBag size={24} /><strong>Your basket is waiting</strong><span>Add products or retailer offers to start building your setup.</span></div>}
            <div className="total-row"><span>Estimated total</span><strong>{money(total)}</strong></div>
            <button className="checkout-btn" disabled={!cart.length || busy || Boolean(orderResult)} onClick={() => void validateBasket()}>{busy ? 'Working…' : basketValidated ? 'Revalidate basket' : 'Validate basket'} <ArrowRight size={16} /></button>
            {basketValidated && cart.length > 0 && !orderResult && <div className="paypal-panel">
              <div className="paypal-panel-title"><ShieldCheck size={16} /> Approve payment securely with PayPal</div>
              {paypalClientId ? <PayPalProvider
                key={`paypal-v6-${paypalClientId}`}
                clientId={paypalClientId}
                environment="sandbox"
                components={['paypal-payments']}
                pageType="checkout"
              >
                <PayPalCheckoutControls
                  disabled={busy}
                  createOrder={async () => {
                    try {
                      setBusy(true)
                      setMessage('Creating a PayPal Sandbox order…')
                      return await createPayPalOrder()
                    } catch (error) {
                      const detail = getPayPalErrorMessage(error, 'Could not create PayPal order')
                      setMessage(detail)
                      throw error
                    } finally {
                      setBusy(false)
                    }
                  }}
                  onApprove={async orderId => {
                    try {
                      setBusy(true)
                      setMessage('Buyer approved. Verifying capture with PayPal…')
                      await capturePayPalOrder(orderId)
                    } catch (error) {
                      setMessage(getPayPalErrorMessage(error, 'Capture could not be verified'))
                    } finally {
                      setBusy(false)
                    }
                  }}
                  onCancel={() => {
                    setMessage('Checkout cancelled. No completed payment was recorded.')
                    setEvents(old => [...old, 'Buyer cancelled PayPal checkout'])
                  }}
                  onError={detail => {
                    setMessage(`PayPal Checkout error: ${detail}`)
                    setEvents(old => [...old, 'PayPal Checkout reported an error'])
                  }}
                />
              </PayPalProvider> : <div className="credential-help"><strong>Sandbox Client ID unavailable</strong><span>AgentPay checks the public Client ID from FastAPI first, then <code>VITE_PAYPAL_CLIENT_ID</code> in <code>frontend/.env</code>. Verify <code>PAYPAL_CLIENT_ID</code> in <code>backend/.env</code>, then restart FastAPI. Never put the secret in frontend configuration.</span></div>}
              <p className="sandbox-warning">Sandbox demo payment only: this does not place or fulfill an order with the retailer. Use the retailer offer link to visit the store. Use a Sandbox buyer account, never real payment credentials.</p>
            </div>}
            {orderResult && <div className="order-success"><CheckCircle2 size={22} /><div><strong>Sandbox payment completed</strong><span>Order: {orderResult.orderID}</span><span>Capture: {orderResult.captureID || 'Verified by PayPal'}</span><span>{money(orderResult.total)} · {orderResult.status}</span></div></div>}
            <div className="trust-note"><ShieldCheck size={15} /> Server-validated · Buyer approval required</div>
          </section>

          <section className="lifecycle-card" id="payment-lifecycle">
            <div className="rail-heading"><div><CreditCard size={17} /><h2>Payment lifecycle & refunds</h2></div><button className="icon-button" onClick={() => void refreshTelemetry('')} title="Refresh payment history"><RotateCcw size={14} /></button></div>
            <p className="lifecycle-description">Captured Sandbox payments are stored locally for this prototype. Full and partial refunds require explicit confirmation and use PayPal's capture refund API.</p>
            <label className="refund-note-label" htmlFor="agentpay-admin-token">Sandbox operator token (required for refunds, MCP, and retries)</label><input id="agentpay-admin-token" type="password" autoComplete="off" value={adminToken} onChange={event => setAdminToken(event.target.value)} onBlur={() => void refreshTelemetry('')} placeholder="Enter AGENTPAY_ADMIN_TOKEN; kept only in this page session" />
            <p className="mcp-safety-note">Configure <code>AGENTPAY_ADMIN_TOKEN</code> in <code>backend/.env</code>. The token is not saved to browser storage or returned by the API.</p>
            <label className="refund-note-label" htmlFor="refund-note">Refund note</label><input id="refund-note" value={refundNote} onChange={event => setRefundNote(event.target.value)} maxLength={200} />
            {recentOrders.length ? <div className="payment-history-list">{recentOrders.slice(0, 10).map(order => { const remaining = Math.max(0, Number(order.total) - Number(order.refunded_total || '0')); const canRefund = Boolean(order.capture_id) && remaining > 0 && ['COMPLETED', 'PARTIALLY_REFUNDED'].includes(order.status); return <div className="payment-history-row" key={order.order_id}><div className="payment-history-top"><strong>{money(order.total)} {order.currency}</strong><span className={`state-pill ${order.status === 'REFUNDED' ? 'state-pill-muted' : ''}`}>{order.status}</span></div><span className="payment-history-id">Order {order.order_id}</span><span className="payment-history-sub">Capture {order.capture_id || 'not captured'} · Refunded {money(order.refunded_total || '0.00')}</span>{canRefund && <><input className="refund-amount-input" type="number" min="0.01" max={remaining.toFixed(2)} step="0.01" value={refundAmounts[order.order_id] || ''} onChange={event => setRefundAmounts(old => ({ ...old, [order.order_id]: event.target.value }))} placeholder={`Partial amount (max ${money(remaining)})`} aria-label={`Partial refund amount for order ${order.order_id}`} /><div className="refund-actions"><button className="secondary-btn" onClick={() => void refundPayment(order)} disabled={refundBusyOrder === order.order_id || busy || !adminToken.trim()}>{refundBusyOrder === order.order_id ? 'Processing…' : 'Refund remaining'}</button><button className="primary-btn" onClick={() => void refundPayment(order, Number(refundAmounts[order.order_id]))} disabled={refundBusyOrder === order.order_id || busy || !refundAmounts[order.order_id] || !adminToken.trim()}>{refundBusyOrder === order.order_id ? 'Processing…' : 'Partial refund'}</button></div></>}</div> })}</div> : <div className="elastic-empty">No captured Sandbox payments have been recorded yet.</div>}
            {refundMessage && <div className="refund-feedback" role="status">{refundMessage}</div>}
          </section>

          <section className="automation-card" id="post-purchase-automation">
            <div className="rail-heading"><div><Workflow size={17} /><h2>Post-purchase automation</h2></div><span className={`elastic-pill ${automationState?.configured ? 'is-connected' : ''}`}>{automationState?.configured ? 'CONFIGURED' : 'PREVIEW ONLY'}</span></div>
            <p className="elastic-description">{automationState?.message || 'Post-purchase status is loading…'}</p>
            {automationState?.runs?.length ? <div className="automation-runs">{automationState.runs.slice(0, 4).map(run => <div className="automation-run" key={run.order_id}><strong>{run.status.replace('_', ' ').toUpperCase()}</strong><span>Order {run.order_id}</span><p>{run.message}</p>{automationState?.configured && ['failed', 'preview_only'].includes(run.status) && <button className="secondary-btn" disabled={!adminToken.trim()} onClick={() => void retryAutomation(run.order_id)}>Retry delivery</button>}</div>)}</div> : <div className="elastic-empty">Complete a Sandbox payment to create a post-purchase receipt event.</div>}
            <p className="mcp-safety-note">To send the event to Zapier, set <code>ZAPIER_WEBHOOK_URL</code> to a Zapier Catch Hook URL and <code>AGENTPAY_ADMIN_TOKEN</code> in <code>backend/.env</code>, then restart FastAPI. Configure downstream actions deliberately; this event describes an AgentPay Sandbox payment, not a retailer order.</p>
            <button className="elastic-reconnect-btn" onClick={() => void refreshTelemetry('')}><RefreshCw size={13} /> Refresh workflow status</button>
          </section>

          <section className="activity-card"><div className="rail-heading"><div><SlidersHorizontal size={17} /><h2>Agent activity</h2></div><span className="live-dot">LIVE</span></div><div className="timeline">{events.slice(-7).reverse().map((event, i) => <div className="timeline-event" key={`${event}-${i}`}><span className={i === 0 ? 'timeline-dot current' : 'timeline-dot'} /><p>{event}</p></div>)}</div></section>

          <section className="observability-card" id="observability">
            <div className="rail-heading"><div><Activity size={17} /><h2>Elastic trace explorer</h2></div><span className={`elastic-pill ${elasticStatus?.connected ? 'is-connected' : ''}`}>{elasticStatus?.connected ? 'CONNECTED' : elasticStatus?.configured ? 'OFFLINE' : 'LOCAL FALLBACK'}</span></div>
            <p className="elastic-description">{elasticStatus?.message || 'Checking optional Elastic telemetry…'}</p>
            <div className="trace-search"><input value={traceQuery} onChange={event => setTraceQuery(event.target.value)} placeholder="Search events" aria-label="Search Elastic events" onKeyDown={event => { if (event.key === 'Enter') void refreshTelemetry(traceQuery) }} /><button onClick={() => void refreshTelemetry(traceQuery)} title="Search events"><Search size={15} /></button><button onClick={() => void refreshTelemetry(traceQuery)} title="Refresh"><RefreshCw size={14} /></button></div>
            <div className="trace-source">Showing {telemetrySource === 'elasticsearch' ? 'Elastic indexed events' : 'local fallback events'}</div>
            {elasticEvents.length ? <div className="elastic-events">{elasticEvents.slice(0, 8).map((event, index) => <div className="elastic-event" key={event.event_id || `${event.event_type}-${index}`}><span className="event-time">{gridDate(event.timestamp)}</span><strong>{event.event_type || 'event'}</strong><p>{event.message || ''}</p></div>)}</div> : <div className="elastic-empty">No events yet. Search or validate a basket to create an audit event.</div>}
            {!elasticStatus?.connected && <><p className="elastic-config-note">{elasticStatus?.configured ? 'Elastic settings are present, but the connection check failed. Use the status message above, verify the Elasticsearch endpoint (not Kibana URL) and API key, then reconnect.' : 'Set ELASTICSEARCH_URL and ELASTIC_API_KEY in backend/.env, then restart FastAPI to enable Elasticsearch indexing.'}</p><button className="elastic-reconnect-btn" onClick={async () => { try { const response = await fetch(`${API}/api/observability/reconnect`, { method: 'POST' }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Elastic reconnect failed'); setElasticStatus(data); await refreshTelemetry(traceQuery) } catch (error) { setMessage(error instanceof Error ? error.message : 'Elastic reconnect failed') } }}><RefreshCw size={13} /> Retry Elastic connection</button></>}
          </section>
        </aside>
      </div>
      <footer>AgentPay · Hackathon prototype <span>{catalogSource === 'channel3' ? 'Channel3 visual + conversational shopping · AG Grid · PayPal Sandbox refunds · MCP tools · Elastic' : 'Demo catalog · photo search requires Channel3 · PayPal Sandbox'}</span></footer>
    </main>
  </div>
}
