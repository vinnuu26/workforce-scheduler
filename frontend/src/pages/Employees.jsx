import { useCallback, useEffect, useMemo, useState } from 'react'
import { Download, MoreHorizontal, Plus, Search, SlidersHorizontal, Users } from 'lucide-react'
import { Avatar, Badge, Button, Card, Input, LoadingState, PageHeader, Select, Table } from '../components/UI'
import { getApiErrorMessage, getEmployees } from '../services/api'

function toEmployeeView(employee) {
  return {
    ...employee,
    code: employee.email || `Employee #${employee.id}`,
    departmentName: employee.department?.name || 'Unassigned',
    skillNames: (employee.skills || []).map((skill) => (typeof skill === 'string' ? skill : skill.name)).filter(Boolean),
    rate: Number(employee.hourly_rate || 0),
    maxHours: Number(employee.max_hours_per_week || 0),
  }
}

export default function Employees() {
  const [employees, setEmployees] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [department, setDepartment] = useState('All departments')
  const [status, setStatus] = useState('All status')
  const [selected, setSelected] = useState(null)

  const loadEmployees = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getEmployees({ limit: 500 })
      setEmployees((Array.isArray(response.data) ? response.data : []).map(toEmployeeView))
    } catch (requestError) {
      setError(getApiErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadEmployees()
  }, [loadEmployees])

  const departments = useMemo(
    () => [...new Set(employees.map((employee) => employee.departmentName).filter((name) => name !== 'Unassigned'))].sort(),
    [employees],
  )
  const activeCount = employees.filter((employee) => employee.active).length
  const filtered = useMemo(() => employees.filter((employee) =>
    `${employee.name} ${employee.code} ${employee.skillNames.join(' ')}`.toLowerCase().includes(query.toLowerCase())
    && (department === 'All departments' || employee.departmentName === department)
    && (status === 'All status' || (status === 'Active' ? employee.active : !employee.active))),
  [employees, query, department, status])

  const columns = [
    { key: 'name', label: 'Employee', render: (row) => <button className="flex items-center gap-3 text-left" onClick={() => setSelected(row)}><Avatar name={row.name || 'Employee'} /><span><span className="block font-semibold text-ink">{row.name}</span><span className="text-xs text-muted">{row.code}</span></span></button> },
    { key: 'departmentName', label: 'Department' },
    { key: 'skillNames', label: 'Skills', render: (row) => row.skillNames.length ? <div className="flex flex-wrap gap-1.5">{row.skillNames.map((skill) => <Badge key={skill} tone="gray">{skill}</Badge>)}</div> : <span className="text-xs text-muted">No skills listed</span> },
    { key: 'rate', label: 'Hourly rate', render: (row) => `₹${row.rate}/hr` },
    { key: 'maxHours', label: 'Max hours', render: (row) => `${row.maxHours} hrs` },
    { key: 'active', label: 'Status', render: (row) => <Badge tone={row.active ? 'green' : 'gray'} dot>{row.active ? 'Active' : 'Inactive'}</Badge> },
    { key: 'actions', label: '', render: () => <button aria-label="More options" className="rounded p-1.5 text-muted hover:bg-slate-100"><MoreHorizontal size={17} /></button> },
  ]

  return <>
    <PageHeader eyebrow="People" title="Employees" description="Manage your people, skills and availability in one place." action={<div className="flex gap-2"><Button variant="outline" icon={Download}>Export</Button><Button icon={Plus}>Add employee</Button></div>} />
    {loading ? <Card><LoadingState label="Loading employees…" /></Card> : error ? <Card className="p-5"><div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4"><p className="text-sm font-medium text-rose-800">Could not load employees</p><p className="mt-1 text-sm text-rose-700">{error}</p><Button className="mt-3" variant="outline" onClick={loadEmployees}>Try again</Button></div></Card> : <>
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="flex items-center gap-3 p-4"><span className="rounded-lg bg-teal-50 p-2.5 text-brand"><Users size={18}/></span><div><p className="text-xl font-semibold text-ink">{employees.length}</p><p className="text-xs text-muted">Total employees</p></div></Card>
        <Card className="flex items-center gap-3 p-4"><span className="rounded-lg bg-emerald-50 p-2.5 text-emerald-700"><Users size={18}/></span><div><p className="text-xl font-semibold text-ink">{activeCount}</p><p className="text-xs text-muted">Active employees</p></div></Card>
        <Card className="flex items-center gap-3 p-4"><span className="rounded-lg bg-blue-50 p-2.5 text-blue-700"><Users size={18}/></span><div><p className="text-xl font-semibold text-ink">{departments.length}</p><p className="text-xs text-muted">Departments represented</p></div></Card>
      </div>
      <Card><div className="flex flex-wrap items-center justify-between gap-3 p-4"><div className="relative min-w-[220px] flex-1 sm:max-w-xs"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><Input aria-label="Search employees" className="pl-9" placeholder="Search name, email or skill" value={query} onChange={(event) => setQuery(event.target.value)} /></div><div className="flex flex-wrap items-center gap-2"><Select aria-label="Filter by department" value={department} onChange={(event) => setDepartment(event.target.value)}><option>All departments</option>{departments.map((item) => <option key={item}>{item}</option>)}</Select><Select aria-label="Filter by status" value={status} onChange={(event) => setStatus(event.target.value)}><option>All status</option><option>Active</option><option>Inactive</option></Select><Button variant="outline" icon={SlidersHorizontal}>Filters</Button></div></div><Table columns={columns} rows={filtered} emptyMessage={employees.length ? 'No employees match those filters.' : 'No employees have been added yet.'}/><div className="flex items-center justify-between border-t border-line px-5 py-3 text-xs text-muted"><span>Showing <b className="text-ink">{filtered.length}</b> of {employees.length} employees</span><span>Live backend data</span></div></Card>
    </>}
    {selected && <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/25" onClick={() => setSelected(null)}><div role="dialog" aria-modal="true" aria-label={`${selected.name} employee profile`} onClick={(event) => event.stopPropagation()} className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl"><button aria-label="Close employee profile" onClick={() => setSelected(null)} className="float-right rounded-lg px-2 py-1 text-muted hover:bg-slate-100">×</button><p className="text-xs font-semibold uppercase tracking-wider text-brand">Employee profile · Live API</p><div className="mt-6 flex items-center gap-4"><Avatar name={selected.name || 'Employee'} /><div><h2 className="text-xl font-semibold">{selected.name}</h2><p className="mt-1 text-sm text-muted">{selected.code} · {selected.departmentName}</p></div></div><div className="mt-7 grid grid-cols-2 gap-3">{[['Hourly rate', `₹${selected.rate}`], ['Maximum hours', `${selected.maxHours} hrs`], ['Status', selected.active ? 'Active' : 'Inactive'], ['Department', selected.departmentName]].map(([label, value]) => <div className="rounded-lg border border-line p-3" key={label}><p className="text-xs text-muted">{label}</p><p className="mt-1 text-sm font-semibold">{value}</p></div>)}</div><h3 className="mb-2 mt-6 text-sm font-semibold">Skills</h3><div className="flex flex-wrap gap-2">{selected.skillNames.length ? selected.skillNames.map((skill) => <Badge key={skill} tone="teal">{skill}</Badge>) : <span className="text-sm text-muted">No skills listed</span>}</div></div></div>}
  </>
}
