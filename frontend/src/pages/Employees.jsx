import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, Search, Users } from 'lucide-react'
import { Avatar, Badge, Button, Card, Input, LoadingState, PageHeader, Select, Table } from '../components/UI'
import { departmentsApi, employeesApi, getApiErrorMessage, getDepartments, getEmployees, getSkills, skillsApi } from '../services/api'

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
  const [departmentRows, setDepartmentRows] = useState([])
  const [skillRows, setSkillRows] = useState([])
  const [showEmployeeForm, setShowEmployeeForm] = useState(false)
  const [showReferenceForm, setShowReferenceForm] = useState(false)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [employeeForm, setEmployeeForm] = useState({ name: '', email: '', department_id: '', hourly_rate: 0, max_hours_per_week: 40 })
  const [editingEmployee, setEditingEmployee] = useState(null)
  const [referenceForm, setReferenceForm] = useState({ kind: 'skill', name: '', description: '' })
  const [editingReference, setEditingReference] = useState(null)
  const [skillToAdd, setSkillToAdd] = useState('')

  const loadEmployees = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [response, departmentResponse, skillResponse] = await Promise.all([getEmployees({ limit: 500 }), getDepartments({ limit: 500 }), getSkills({ limit: 500 })])
      setEmployees((Array.isArray(response.data) ? response.data : []).map(toEmployeeView))
      setDepartmentRows(Array.isArray(departmentResponse.data) ? departmentResponse.data : [])
      setSkillRows(Array.isArray(skillResponse.data) ? skillResponse.data : [])
    } catch (requestError) {
      setError(getApiErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  const createEmployee = async (event) => {
    event.preventDefault(); setSaving(true); setFormError('')
    try { const payload = { ...employeeForm, department_id: employeeForm.department_id ? Number(employeeForm.department_id) : null, hourly_rate: Number(employeeForm.hourly_rate), max_hours_per_week: Number(employeeForm.max_hours_per_week), active: editingEmployee ? editingEmployee.active : true }; if (editingEmployee) await employeesApi.update(editingEmployee.id, payload); else await employeesApi.create(payload); setShowEmployeeForm(false); setEditingEmployee(null); setEmployeeForm({ name: '', email: '', department_id: '', hourly_rate: 0, max_hours_per_week: 40 }); await loadEmployees() }
    catch (e) { setFormError(getApiErrorMessage(e)) } finally { setSaving(false) }
  }
  const editEmployee = (employee) => { setSelected(null); setEditingEmployee(employee); setFormError(''); setEmployeeForm({ name: employee.name || '', email: employee.email || '', department_id: employee.department_id || '', hourly_rate: employee.hourly_rate ?? 0, max_hours_per_week: employee.max_hours_per_week ?? 40 }); setShowEmployeeForm(true) }
  const deleteEmployee = async (employee) => { if (!window.confirm(`Delete employee “${employee.name}”?`)) return; try { await employeesApi.remove(employee.id); setSelected(null); await loadEmployees() } catch (e) { setError(getApiErrorMessage(e)) } }
  const createReference = async (event) => {
    event.preventDefault(); setSaving(true); setFormError('')
    try { const service = referenceForm.kind === 'skill' ? skillsApi : departmentsApi; const payload = { name: referenceForm.name, description: referenceForm.description || null }; if (editingReference) await service.update(editingReference.id, payload); else await service.create(payload); setShowReferenceForm(false); setEditingReference(null); setReferenceForm({ ...referenceForm, name: '', description: '' }); await loadEmployees() }
    catch (e) { setFormError(getApiErrorMessage(e)) } finally { setSaving(false) }
  }
  const editReference = (item, kind) => { setEditingReference({ ...item, kind }); setReferenceForm({ kind, name: item.name, description: item.description || '' }); setFormError(''); setShowReferenceForm(true) }
  const deleteReference = async (item, kind) => { if (!window.confirm(`Delete ${kind} “${item.name}”?`)) return; try { await (kind === 'skill' ? skillsApi : departmentsApi).remove(item.id); await loadEmployees() } catch (e) { setError(getApiErrorMessage(e)) } }
  const updateEmployeeSkill = async (skillId, add) => {
    try { if (add) await employeesApi.addSkill(selected.id, Number(skillId), 1); else await employeesApi.removeSkill(selected.id, Number(skillId)); await loadEmployees(); const refreshed = await getEmployees({ limit: 500 }); const current = refreshed.data.find((item) => item.id === selected.id); if (current) setSelected(toEmployeeView(current)) }
    catch (e) { setError(getApiErrorMessage(e)) }
  }

  useEffect(() => {
    loadEmployees()
  }, [loadEmployees])

  const departments = useMemo(() => departmentRows.map((item) => item.name).sort(), [departmentRows])
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
  ]

  return <>
    <PageHeader eyebrow="People · Live API" title="Employees" description="Manage workforce records and review their configured department and skills." action={<div className="flex gap-2"><Button variant="outline" icon={Plus} onClick={() => { setEditingReference(null); setReferenceForm({ kind: 'skill', name: '', description: '' }); setFormError(''); setShowReferenceForm(true) }}>Add skill / department</Button><Button icon={Plus} onClick={() => { setEditingEmployee(null); setEmployeeForm({ name: '', email: '', department_id: '', hourly_rate: 0, max_hours_per_week: 40 }); setFormError(''); setShowEmployeeForm(true) }}>Add employee</Button></div>} />
    <Card className="mb-5 p-4"><div className="grid gap-5 md:grid-cols-2"><section><h2 className="text-sm font-semibold text-ink">Departments</h2>{departmentRows.length ? <ul className="mt-2 divide-y divide-line">{departmentRows.map((item) => <li key={item.id} className="flex items-center justify-between py-2 text-sm"><span>{item.name}</span><span className="flex gap-2"><button className="text-brand" onClick={() => editReference(item, 'department')}>Edit</button><button className="text-rose-700" onClick={() => deleteReference(item, 'department')}>Delete</button></span></li>)}</ul> : <p className="mt-2 text-xs text-muted">No departments configured.</p>}</section><section><h2 className="text-sm font-semibold text-ink">Skills</h2>{skillRows.length ? <ul className="mt-2 divide-y divide-line">{skillRows.map((item) => <li key={item.id} className="flex items-center justify-between py-2 text-sm"><span>{item.name}</span><span className="flex gap-2"><button className="text-brand" onClick={() => editReference(item, 'skill')}>Edit</button><button className="text-rose-700" onClick={() => deleteReference(item, 'skill')}>Delete</button></span></li>)}</ul> : <p className="mt-2 text-xs text-muted">No skills configured.</p>}</section></div></Card>    {loading ? <Card><LoadingState label="Loading employees…" /></Card> : error ? <Card className="p-5"><div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4"><p className="text-sm font-medium text-rose-800">Could not load employees</p><p className="mt-1 text-sm text-rose-700">{error}</p><Button className="mt-3" variant="outline" onClick={loadEmployees}>Try again</Button></div></Card> : <>
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="flex items-center gap-3 p-4"><span className="rounded-lg bg-teal-50 p-2.5 text-brand"><Users size={18}/></span><div><p className="text-xl font-semibold text-ink">{employees.length}</p><p className="text-xs text-muted">Total employees</p></div></Card>
        <Card className="flex items-center gap-3 p-4"><span className="rounded-lg bg-emerald-50 p-2.5 text-emerald-700"><Users size={18}/></span><div><p className="text-xl font-semibold text-ink">{activeCount}</p><p className="text-xs text-muted">Active employees</p></div></Card>
        <Card className="flex items-center gap-3 p-4"><span className="rounded-lg bg-blue-50 p-2.5 text-blue-700"><Users size={18}/></span><div><p className="text-xl font-semibold text-ink">{departments.length}</p><p className="text-xs text-muted">Departments represented</p></div></Card>
      </div>
      <Card><div className="flex flex-wrap items-center justify-between gap-3 p-4"><div className="relative min-w-[220px] flex-1 sm:max-w-xs"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><Input aria-label="Search employees" className="pl-9" placeholder="Search name, email or skill" value={query} onChange={(event) => setQuery(event.target.value)} /></div><div className="flex flex-wrap items-center gap-2"><Select aria-label="Filter by department" value={department} onChange={(event) => setDepartment(event.target.value)}><option>All departments</option>{departments.map((item) => <option key={item}>{item}</option>)}</Select><Select aria-label="Filter by status" value={status} onChange={(event) => setStatus(event.target.value)}><option>All status</option><option>Active</option><option>Inactive</option></Select></div></div><Table columns={columns} rows={filtered} emptyMessage={employees.length ? 'No employees match those filters.' : 'No employees have been added yet.'}/><div className="flex items-center justify-between border-t border-line px-5 py-3 text-xs text-muted"><span>Showing <b className="text-ink">{filtered.length}</b> of {employees.length} employees</span><span>Live backend data</span></div></Card>
    </>}
    {showEmployeeForm && <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/25" onClick={() => { setShowEmployeeForm(false); setEditingEmployee(null) }}><form role="dialog" aria-modal="true" aria-label={editingEmployee ? 'Edit employee' : 'Add employee'} onSubmit={createEmployee} onClick={(e) => e.stopPropagation()} className="h-full w-full max-w-md space-y-4 overflow-y-auto bg-white p-6 shadow-xl"><button type="button" aria-label="Close form" className="float-right" onClick={() => { setShowEmployeeForm(false); setEditingEmployee(null) }}>×</button><h2 className="text-lg font-semibold">{editingEmployee ? 'Edit employee' : 'Add employee'}</h2><label className="block text-xs font-medium">Full name<Input className="mt-1" required value={employeeForm.name} onChange={(e) => setEmployeeForm({ ...employeeForm, name: e.target.value })}/></label><label className="block text-xs font-medium">Email<Input className="mt-1" type="email" required value={employeeForm.email} onChange={(e) => setEmployeeForm({ ...employeeForm, email: e.target.value })}/></label><label className="block text-xs font-medium">Department<Select className="mt-1 w-full" value={employeeForm.department_id} onChange={(e) => setEmployeeForm({ ...employeeForm, department_id: e.target.value })}><option value="">Unassigned</option>{departmentRows.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></label><div className="grid grid-cols-2 gap-3"><label className="text-xs font-medium">Hourly rate<Input className="mt-1" type="number" min="0" step="0.01" value={employeeForm.hourly_rate} onChange={(e) => setEmployeeForm({ ...employeeForm, hourly_rate: e.target.value })}/></label><label className="text-xs font-medium">Weekly max hours<Input className="mt-1" type="number" min="0" step="0.5" value={employeeForm.max_hours_per_week} onChange={(e) => setEmployeeForm({ ...employeeForm, max_hours_per_week: e.target.value })}/></label></div>{formError && <p role="alert" className="text-sm text-rose-700">{formError}</p>}<div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => { setShowEmployeeForm(false); setEditingEmployee(null) }}>Cancel</Button><Button disabled={saving}>{saving ? 'Saving…' : editingEmployee ? 'Save changes' : 'Create employee'}</Button></div></form></div>}
    {showReferenceForm && <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/25" onClick={() => setShowReferenceForm(false)}><form role="dialog" aria-modal="true" aria-label="Add skill or department" onSubmit={createReference} onClick={(e) => e.stopPropagation()} className="h-full w-full max-w-md space-y-4 bg-white p-6 shadow-xl"><button type="button" aria-label="Close form" className="float-right" onClick={() => setShowReferenceForm(false)}>×</button><h2 className="text-lg font-semibold">{editingReference ? `Edit ${editingReference.kind}` : 'Add skill or department'}</h2><label className="block text-xs font-medium">Type<Select className="mt-1 w-full" value={referenceForm.kind} onChange={(e) => setReferenceForm({ ...referenceForm, kind: e.target.value })}><option value="skill">Skill</option><option value="department">Department</option></Select></label><label className="block text-xs font-medium">Name<Input className="mt-1" required value={referenceForm.name} onChange={(e) => setReferenceForm({ ...referenceForm, name: e.target.value })}/></label><label className="block text-xs font-medium">Description<Input className="mt-1" value={referenceForm.description} onChange={(e) => setReferenceForm({ ...referenceForm, description: e.target.value })}/></label><p className="text-xs text-muted">Skills can be linked to employees from the employee profile API. Department and skill creation use existing backend endpoints.</p>{formError && <p role="alert" className="text-sm text-rose-700">{formError}</p>}<Button disabled={saving}>{saving ? 'Saving…' : `Create ${referenceForm.kind}`}</Button></form></div>}
    {selected && <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/25" onClick={() => setSelected(null)}><div role="dialog" aria-modal="true" aria-label={`${selected.name} employee profile`} onClick={(event) => event.stopPropagation()} className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl"><button aria-label="Close employee profile" onClick={() => setSelected(null)} className="float-right rounded-lg px-2 py-1 text-muted hover:bg-slate-100">×</button><p className="text-xs font-semibold uppercase tracking-wider text-brand">Employee profile · Live API</p><div className="mt-4 flex gap-2"><Button variant="outline" onClick={() => editEmployee(selected)}>Edit employee</Button><Button variant="outline" onClick={() => deleteEmployee(selected)}>Delete employee</Button></div><div className="mt-6 flex items-center gap-4"><Avatar name={selected.name || 'Employee'} /><div><h2 className="text-xl font-semibold">{selected.name}</h2><p className="mt-1 text-sm text-muted">{selected.code} · {selected.departmentName}</p></div></div><div className="mt-7 grid grid-cols-2 gap-3">{[['Hourly rate', `₹${selected.rate}`], ['Maximum hours', `${selected.maxHours} hrs`], ['Status', selected.active ? 'Active' : 'Inactive'], ['Department', selected.departmentName]].map(([label, value]) => <div className="rounded-lg border border-line p-3" key={label}><p className="text-xs text-muted">{label}</p><p className="mt-1 text-sm font-semibold">{value}</p></div>)}</div><h3 className="mb-2 mt-6 text-sm font-semibold">Skills and proficiency</h3>{selected.skills?.length > 0 ? <ul className="space-y-2">{selected.skills.map((skill) => <li key={skill.id} className="flex items-center justify-between gap-2 text-sm"><span>{skill.name}</span><div className="flex items-center gap-2"><label className="text-xs text-muted" htmlFor={`skill-level-${skill.id}`}>Level</label><Select id={`skill-level-${skill.id}`} aria-label={`${skill.name} proficiency`} value={skill.proficiency || 1} onChange={async (event) => { try { await employeesApi.updateSkill(selected.id, skill.id, Number(event.target.value)); await loadEmployees(); const fresh = await getEmployees({ limit: 500 }); const current = fresh.data.find((item) => item.id === selected.id); if (current) setSelected(toEmployeeView(current)) } catch (e) { setError(getApiErrorMessage(e)) } }}><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option></Select><button className="text-xs text-rose-700" onClick={() => updateEmployeeSkill(skill.id, false)}>Remove</button></div></li>)}</ul> : <span className="text-sm text-muted">No skills listed</span>}<div className="mt-4 flex gap-2"><Select aria-label="Select skill to add" value={skillToAdd} onChange={(e) => setSkillToAdd(e.target.value)}><option value="">Add a skill</option>{skillRows.filter((skill) => !selected.skills?.some((current) => current.id === skill.id)).map((skill) => <option key={skill.id} value={skill.id}>{skill.name}</option>)}</Select><Button disabled={!skillToAdd} onClick={() => { updateEmployeeSkill(skillToAdd, true); setSkillToAdd('') }}>Add</Button></div></div></div>}
  </>
}
