import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { CalendarClock, CalendarDays, FolderKanban, LayoutDashboard, Menu, SlidersHorizontal, TriangleAlert, Users, WandSparkles, X } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '../components/UI'

const items = [
  { label: 'Dashboard', to: '/', icon: LayoutDashboard },
  { label: 'Employees', to: '/employees', icon: Users },
  { label: 'Shifts', to: '/shifts', icon: CalendarClock },
  { label: 'Projects', to: '/projects', icon: FolderKanban },
  { label: 'Constraints', to: '/constraints', icon: SlidersHorizontal },
  { label: 'Schedule', to: '/schedule', icon: CalendarDays },
  { label: 'Conflicts', to: '/conflicts', icon: TriangleAlert },
  { label: 'Reschedule', to: '/reschedule', icon: WandSparkles },
]
const titles = Object.fromEntries(items.map((item) => [item.to, item.label]))
const descriptions = {
  '/': 'Workforce counts and latest saved schedule metrics from the backend',
  '/employees': 'Employee, department, and skill records from the backend',
  '/shifts': 'Dated staffing requirements from the backend',
  '/projects': 'Projects and optimizer requirements from the backend',
  '/constraints': 'Live source record counts and optimizer rule reference',
  '/schedule': 'Schedules and optimization connected to the workforce backend',
  '/conflicts': 'Persisted conflicts and non-persistent optimizer diagnostics',
  '/reschedule': 'Non-persistent reschedule preview using the optimizer',
}

export default function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { pathname } = useLocation()
  const title = titles[pathname] || 'Dashboard'
  return <div className="min-h-screen bg-canvas md:flex">
    {mobileOpen && <button aria-label="Close navigation" onClick={() => setMobileOpen(false)} className="fixed inset-0 z-30 bg-slate-900/30 md:hidden" />}
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-[248px] flex-col border-r border-line bg-white transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
      <div className="flex h-[68px] items-center justify-between border-b border-line px-5"><div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-white"><CalendarDays size={18}/></div><div><div className="text-sm font-semibold tracking-tight text-ink">Workforce</div><div className="text-[11px] text-muted">Scheduler</div></div></div><button aria-label="Close navigation" onClick={() => setMobileOpen(false)} className="rounded p-1 text-muted md:hidden"><X size={18}/></button></div>
      <div className="mx-4 mt-5 rounded-lg border border-line bg-slate-50 px-3 py-3"><p className="text-xs font-semibold text-ink">Workforce workspace</p><p className="mt-1 text-[10px] text-muted">Connected application data</p></div>
      <nav className="flex-1 px-3 pt-7"><p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[.15em] text-slate-400">Workspace</p><div className="space-y-1">{items.map(({ label, to, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} onClick={() => setMobileOpen(false)} className={({ isActive }) => `group flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] font-medium transition-colors ${isActive ? 'bg-[#eaf4f2] text-[#126f68]' : 'text-slate-600 hover:bg-slate-50 hover:text-ink'}`}><Icon size={17} strokeWidth={1.8}/><span>{label}</span></NavLink>)}</div></nav>
      <NavLink to="/schedule" className="m-3 rounded-xl border border-[#e3eeec] bg-[#f6faf9] p-3.5 hover:bg-[#eef7f5]"><div className="text-xs font-semibold text-ink">Schedule planning</div><p className="mt-1 text-[11px] text-muted">Generate a roster from configured workforce data.</p></NavLink>
    </aside>
    <div className="min-w-0 flex-1"><header className="sticky top-0 z-20 flex h-[68px] items-center justify-between border-b border-line bg-white/95 px-4 backdrop-blur sm:px-6 lg:px-9"><div className="flex items-center gap-3"><button aria-label="Open navigation" onClick={() => setMobileOpen(true)} className="rounded-lg p-2 text-muted hover:bg-slate-100 md:hidden"><Menu size={19}/></button><div><p className="text-sm font-semibold text-ink">{title}</p><p className="hidden text-[11px] text-muted sm:block">Workforce <span className="mx-1.5 text-slate-300">/</span>{title}</p></div></div><Badge tone="green" dot>LIVE API</Badge></header><main className="mx-auto max-w-[1500px] px-4 py-6 sm:px-6 sm:py-8 lg:px-9"><div className="mb-5 flex flex-wrap items-center gap-2"><span className="text-xs text-muted">{descriptions[pathname] || descriptions['/']}</span></div><Outlet/></main></div>
  </div>
}
