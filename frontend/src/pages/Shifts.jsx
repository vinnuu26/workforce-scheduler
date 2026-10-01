import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, RefreshCw, Search, Trash2 } from 'lucide-react'
import { Badge, Button, Card, EmptyState, Input, LoadingState, PageHeader, Select, Table } from '../components/UI'
import { getApiErrorMessage, getDepartments, getProjects, getShifts, getSkills, getShiftTemplates, shiftsApi } from '../services/api'

const dateText = (value) => value ? new Date(`${String(value).slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
const timeText = (value) => value ? String(value).slice(0, 5) : '—'

export default function Shifts() {
  const [rows, setRows] = useState([]), [departments, setDepartments] = useState([]), [templates, setTemplates] = useState([]), [skills, setSkills] = useState([]), [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [query, setQuery] = useState(''), [department, setDepartment] = useState('all')
  const [showForm, setShowForm] = useState(false), [saving, setSaving] = useState(false), [formError, setFormError] = useState('')
  const [notice, setNotice] = useState('')
  const [form, setForm] = useState({ date: '', department_id: '', template_id: '', start_time: '09:00', end_time: '17:00', required_staff: 1, project_id: '', skills: [] })

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [shiftResponse, departmentResponse, templateResponse, skillResponse, projectResponse] = await Promise.all([getShifts({ limit: 500 }), getDepartments({ limit: 500 }), getShiftTemplates({ limit: 500 }), getSkills({ limit: 500 }), getProjects({ limit: 500 })])
      setRows(Array.isArray(shiftResponse.data) ? shiftResponse.data : [])
      setDepartments(Array.isArray(departmentResponse.data) ? departmentResponse.data : [])
      setTemplates(Array.isArray(templateResponse.data) ? templateResponse.data : [])
      setSkills(Array.isArray(skillResponse.data) ? skillResponse.data : [])
      setProjects(Array.isArray(projectResponse.data) ? projectResponse.data : [])
    } catch (e) { setError(getApiErrorMessage(e)) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  const filtered = useMemo(() => rows.filter((row) => `${row.template?.name || ''} ${row.department?.name || ''} ${(row.required_skills || []).map((skill) => skill.name).join(' ')}`.toLowerCase().includes(query.toLowerCase()) && (department === 'all' || String(row.department_id) === department)), [rows, query, department])
  const toggleSkill = (id) => setForm((current) => ({ ...current, skills: current.skills.includes(id) ? current.skills.filter((item) => item !== id) : [...current.skills, id] }))
  const submit = async (event) => {
    event.preventDefault(); setSaving(true); setFormError('')
    try {
      const payload = { date: form.date, department_id: form.department_id ? Number(form.department_id) : null, template_id: form.template_id ? Number(form.template_id) : null, start_time: form.template_id ? null : form.start_time || null, end_time: form.template_id ? null : form.end_time || null, required_staff: Number(form.required_staff), project_id: form.project_id ? Number(form.project_id) : null }
      const created = (await shiftsApi.create(payload)).data
      try { await Promise.all(form.skills.map((skill_id) => shiftsApi.addSkill(created.id, skill_id))) } catch (relationError) { setNotice(`Shift was saved, but a required skill link failed: ${getApiErrorMessage(relationError)}`) }
      await load(); setShowForm(false); setForm({ date: '', department_id: '', template_id: '', start_time: '09:00', end_time: '17:00', required_staff: 1, project_id: '', skills: [] })
    } catch (e) { setFormError(getApiErrorMessage(e)) } finally { setSaving(false) }
  }
  const remove = async (row) => {
    if (!window.confirm(`Delete shift on ${dateText(row.date)}?`)) return
    try { await shiftsApi.remove(row.id); await load() } catch (e) { setError(getApiErrorMessage(e)) }
  }
  const columns = [
    { key: 'date', label: 'Date', render: (row) => dateText(row.date) },
    { key: 'template', label: 'Shift', render: (row) => <><p className="font-semibold text-ink">{row.template?.name || `Shift #${row.id}`}</p><p className="text-xs text-muted">{timeText(row.start_time || row.template?.start_time)}–{timeText(row.end_time || row.template?.end_time)}</p></> },
    { key: 'department', label: 'Department', render: (row) => row.department?.name || 'Unassigned' },
    { key: 'required_staff', label: 'Required staff', render: (row) => `${row.required_staff} people` },
    { key: 'project', label: 'Project', render: (row) => row.project?.name || (row.project_id ? `Project #${row.project_id}` : '—') },
    { key: 'skills', label: 'Required skills', render: (row) => row.required_skills?.length ? <div className="flex flex-wrap gap-1">{row.required_skills.map((skill) => <Badge key={skill.id} tone="gray">{skill.name}</Badge>)}</div> : <span className="text-xs text-muted">None</span> },
    { key: 'action', label: '', render: (row) => <button aria-label={`Delete shift ${row.id}`} title="Delete shift" onClick={() => remove(row)} className="rounded p-2 text-muted hover:bg-rose-50 hover:text-rose-700"><Trash2 size={15}/></button> },
  ]
  return <>
    <PageHeader eyebrow="Planning · Live API" title="Shifts" description="Manage dated staffing demand, shift times, department and required skills." action={<div className="flex gap-2"><Button variant="outline" icon={RefreshCw} onClick={load}>Refresh</Button><Button icon={Plus} onClick={() => { setFormError(''); setShowForm(true) }}>Add shift</Button></div>} />
    {!loading && !error && <div className="mb-5 grid gap-3 sm:grid-cols-3">{[[rows.length, 'Shifts in data'], [rows.reduce((sum, row) => sum + Number(row.required_staff || 0), 0), 'Required assignments'], [new Set(rows.map((row) => row.department_id).filter(Boolean)).size, 'Departments represented']].map(([value, label]) => <Card key={label} className="p-4"><p className="text-2xl font-semibold text-ink">{value}</p><p className="mt-1 text-xs text-muted">{label}</p></Card>)}</div>}
    {notice && <div role="status" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{notice}</div>}
    {loading ? <Card><LoadingState label="Loading shifts and related data…"/></Card> : error ? <Card className="p-5"><div role="alert" className="text-sm text-rose-800">{error}</div><Button className="mt-3" variant="outline" onClick={load}>Try again</Button></Card> : <Card><div className="flex flex-wrap gap-3 p-4"><Input aria-label="Search shifts" className="max-w-xs" placeholder="Search shift, department or skill" value={query} onChange={(e) => setQuery(e.target.value)}/><Select aria-label="Filter by department" value={department} onChange={(e) => setDepartment(e.target.value)}><option value="all">All departments</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select><span className="self-center text-xs text-muted">{filtered.length} of {rows.length} shifts · Live API</span></div><Table columns={columns} rows={filtered} emptyMessage={rows.length ? 'No shifts match those filters.' : 'No shifts exist yet. Add a dated shift to begin.'}/></Card>}
    {showForm && <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/25" onClick={() => setShowForm(false)}><form role="dialog" aria-modal="true" aria-label="Add shift" onSubmit={submit} onClick={(e) => e.stopPropagation()} className="h-full w-full max-w-lg space-y-4 overflow-y-auto bg-white p-6 shadow-xl"><button type="button" aria-label="Close form" className="float-right text-muted" onClick={() => setShowForm(false)}>×</button><h2 className="text-lg font-semibold">Add dated shift</h2><label className="block text-xs font-medium">Date<Input required type="date" className="mt-1" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })}/></label><label className="block text-xs font-medium">Department<Select className="mt-1 w-full" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}><option value="">No department</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></label><label className="block text-xs font-medium">Shift template<Select className="mt-1 w-full" value={form.template_id} onChange={(e) => setForm({ ...form, template_id: e.target.value })}><option value="">Use times below</option>{templates.map((item) => <option key={item.id} value={item.id}>{item.name} ({timeText(item.start_time)}–{timeText(item.end_time)})</option>)}</Select></label><div className="grid grid-cols-2 gap-3"><label className="text-xs font-medium">Start time<Input className="mt-1" type="time" required={!form.template_id} disabled={Boolean(form.template_id)} value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })}/></label><label className="text-xs font-medium">End time<Input className="mt-1" type="time" required={!form.template_id} disabled={Boolean(form.template_id)} value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })}/></label></div><label className="block text-xs font-medium">Project (optional)<Select className="mt-1 w-full" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}><option value="">No project</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></label><label className="block text-xs font-medium">Required staff<Input className="mt-1" type="number" min="1" required value={form.required_staff} onChange={(e) => setForm({ ...form, required_staff: e.target.value })}/></label><fieldset><legend className="mb-2 text-xs font-medium">Required skills</legend><div className="flex flex-wrap gap-2">{skills.map((skill) => <label key={skill.id} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-2 text-xs"><input type="checkbox" checked={form.skills.includes(skill.id)} onChange={() => toggleSkill(skill.id)}/>{skill.name}</label>)}</div>{!skills.length && <p className="text-xs text-muted">No skills configured.</p>}</fieldset>{formError && <p role="alert" className="text-sm text-rose-700">{formError}</p>}<div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button><Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Create shift'}</Button></div></form></div>}
  </>
}
