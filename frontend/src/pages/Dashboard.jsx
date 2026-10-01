import { useCallback, useEffect, useMemo, useState } from 'react'
import { CalendarCheck, CalendarDays, Clock3, Heart, IndianRupee, Moon, RefreshCw, Scale, TriangleAlert, Users } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, EmptyState, LoadingState, MetricCard, PageHeader } from '../components/UI'
import { getApiErrorMessage, getEmployees, getSchedules, getShifts, schedulesApi } from '../services/api'

const dateLabel = (value) => value ? new Date(`${String(value).slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : 'Dates unavailable'
const currency = (value) => `₹${Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

export default function Dashboard() {
  const [employees, setEmployees] = useState([]), [shifts, setShifts] = useState([]), [schedules, setSchedules] = useState([]), [assignments, setAssignments] = useState([]), [conflicts, setConflicts] = useState([])
  const [optimizerContext, setOptimizerContext] = useState(null)
  const [loading, setLoading] = useState(true), [error, setError] = useState('')
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [employeeResult, shiftResult, scheduleResult] = await Promise.all([getEmployees({ limit: 500 }), getShifts({ limit: 500 }), getSchedules({ limit: 500 })])
      const employeeRows = Array.isArray(employeeResult.data) ? employeeResult.data : [], shiftRows = Array.isArray(shiftResult.data) ? shiftResult.data : [], scheduleRows = Array.isArray(scheduleResult.data) ? scheduleResult.data : []
      setEmployees(employeeRows); setShifts(shiftRows); setSchedules(scheduleRows)
      const latest = [...scheduleRows].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
      if (latest) {
        const [assignmentResult, conflictResult, explanationResult] = await Promise.all([schedulesApi.getAssignments(latest.id), schedulesApi.getConflicts(latest.id), schedulesApi.getExplanations(latest.id)])
        setAssignments(Array.isArray(assignmentResult.data) ? assignmentResult.data : [])
        setConflicts(Array.isArray(conflictResult.data) ? conflictResult.data : [])
        try { setOptimizerContext(JSON.parse(explanationResult.data?.[0]?.details || 'null')) } catch { setOptimizerContext(null) }
      } else { setAssignments([]); setConflicts([]); setOptimizerContext(null) }
    } catch (e) { setError(getApiErrorMessage(e)) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  const latest = useMemo(() => [...schedules].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0], [schedules])
  const required = latest ? shifts.filter((shift) => String(shift.date) >= String(latest.start_date || '') && String(shift.date) <= String(latest.end_date || '')).reduce((sum, shift) => sum + Number(shift.required_staff || 0), 0) : 0
  const coverage = latest && required ? Math.round(assignments.length / required * 100) : null
  const scheduledEmployees = new Set(assignments.map((item) => item.employee_id)).size
  const preferencePercentage = optimizerContext?.preference_metrics?.total_weight > 0 ? optimizerContext.preference_metrics.satisfaction_percentage : null
  const fairness = optimizerContext?.fairness_metrics
  const projectRequirements = (optimizerContext?.project_metrics || []).flatMap((project) => project.requirements || [])
  const projectCoverage = projectRequirements.length ? Math.round(100 * projectRequirements.filter((item) => item.satisfied).length / projectRequirements.length) : null
  const metrics = [
    { label: 'Employees', value: String(employees.length), note: `${employees.filter((item) => item.active).length} active in workforce`, icon: Users, tone: 'teal' },
    { label: 'Shifts', value: String(shifts.length), note: 'Dated shift records', icon: CalendarCheck, tone: 'blue' },
    { label: 'Coverage', value: coverage == null ? '—' : `${coverage}%`, note: latest ? `${assignments.length} assignments / ${required} required` : 'Generate a schedule to measure', icon: CalendarDays, tone: 'green' },
    { label: 'Labor cost', value: latest ? currency(latest.total_cost) : '—', note: latest ? 'Latest saved schedule' : 'No saved schedule', icon: IndianRupee, tone: 'violet' },
    { label: 'Overtime', value: latest ? `${Number(latest.overtime_hours || 0)} hrs` : '—', note: latest ? 'Latest saved schedule' : 'No saved schedule', icon: Clock3, tone: 'amber' },
    { label: 'Conflicts', value: latest ? String(conflicts.length) : '—', note: latest ? 'Latest saved schedule' : 'No saved schedule', icon: TriangleAlert, tone: 'rose' },
  ]
  if (preferencePercentage != null) metrics.push({ label: 'Preference satisfaction', value: `${Math.round(Number(preferencePercentage))}%`, note: 'Recorded with this schedule', icon: Heart, tone: 'green' })
  if (fairness?.hour_balance_score != null) metrics.push({ label: 'Hour balance', value: `${Math.round(Number(fairness.hour_balance_score) * 100)}%`, note: 'Optimizer fairness score', icon: Scale, tone: 'blue' })
  if (fairness?.night_shift_balance_score != null) metrics.push({ label: 'Night balance', value: `${Math.round(Number(fairness.night_shift_balance_score) * 100)}%`, note: 'Optimizer fairness score', icon: Moon, tone: 'violet' })
  if (fairness?.weekend_balance_score != null) metrics.push({ label: 'Weekend balance', value: `${Math.round(Number(fairness.weekend_balance_score) * 100)}%`, note: 'Optimizer fairness score', icon: CalendarDays, tone: 'amber' })
  if (projectCoverage != null) metrics.push({ label: 'Project requirements', value: `${projectCoverage}%`, note: 'Satisfied requirements', icon: CalendarCheck, tone: 'teal' })
  const coverageRows = latest ? shifts.filter((shift) => String(shift.date) >= String(latest.start_date || '') && String(shift.date) <= String(latest.end_date || '')).map((shift) => { const assigned = assignments.filter((item) => item.shift_id === shift.id).length; return { shift, assigned, required: Number(shift.required_staff || 0) } }) : []
  const coverageByDepartment = Object.values(coverageRows.reduce((groups, row) => {
    const name = row.shift.department?.name || 'Unassigned'
    groups[name] ||= { department: name, assigned: 0, required: 0 }
    groups[name].assigned += row.assigned
    groups[name].required += row.required
    return groups
  }, {}))
  return <>
    <PageHeader eyebrow="Workforce overview · Live API" title="Workforce overview" description="Current workforce records and the latest saved schedule, measured from backend data." action={<div className="flex gap-2"><Button variant="outline" icon={RefreshCw} onClick={load}>Refresh</Button><Link to="/schedule" className="inline-flex items-center gap-2 rounded-lg bg-brand px-3.5 py-2.5 text-sm font-semibold text-white">Open schedule planning</Link></div>}/>
    {loading ? <Card><LoadingState label="Loading workforce and latest schedule…"/></Card> : error ? <Card className="p-5"><p role="alert" className="text-sm text-rose-700">{error}</p><Button className="mt-3" variant="outline" onClick={load}>Try again</Button></Card> : <>
      <div className="mb-5 flex flex-wrap items-center gap-2">{latest ? <><Badge tone={latest.status?.toLowerCase() === 'generated' ? 'green' : 'blue'} dot>{latest.status}</Badge><span className="text-xs text-muted">Latest schedule · {dateLabel(latest.start_date)} – {dateLabel(latest.end_date)} · {scheduledEmployees} employees assigned</span></> : <><Badge tone="gray">No schedule yet</Badge><span className="text-xs text-muted">Schedule metrics will appear after a successful generation.</span></>}</div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">{metrics.map((item) => <MetricCard key={item.label} {...item}/>)}</div>
      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-5"><Card className="xl:col-span-3"><div className="p-5"><h2 className="text-sm font-semibold text-ink">Staffing coverage</h2><p className="mt-1 text-xs text-muted">Assignment counts compared with shift requirements for the latest saved period.</p></div>{coverageByDepartment.length > 0 && <div className="h-56 px-3 pb-3"><ResponsiveContainer width="100%" height="100%"><BarChart data={coverageByDepartment} margin={{ top: 8, right: 12, left: -18, bottom: 4 }}><CartesianGrid vertical={false} stroke="#edf0f2"/><XAxis dataKey="department" axisLine={false} tickLine={false} tick={{ fill: '#687884', fontSize: 11 }}/><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: '#96a2aa', fontSize: 10 }}/><Tooltip/><Bar dataKey="assigned" name="Assigned" fill="#168078" radius={[5, 5, 0, 0]}/><Bar dataKey="required" name="Required" fill="#dbe7e4" radius={[5, 5, 0, 0]}/></BarChart></ResponsiveContainer></div>}{coverageRows.length ? <div className="divide-y divide-line border-t border-line">{coverageRows.map(({ shift, assigned, required: needed }) => <div key={shift.id} className="flex flex-wrap items-center gap-3 px-5 py-3"><div className="min-w-0 flex-1"><p className="text-sm font-medium text-ink">{shift.template?.name || `Shift #${shift.id}`}</p><p className="text-xs text-muted">{dateLabel(shift.date)} · {shift.department?.name || 'No department'}</p></div><span className={`text-sm font-semibold ${assigned < needed ? 'text-rose-700' : 'text-emerald-700'}`}>{assigned} / {needed}</span><Badge tone={assigned >= needed ? 'green' : 'rose'}>{assigned >= needed ? 'Covered' : 'Gap'}</Badge></div>)}</div> : <EmptyState title="No coverage data" description="Generate or load a schedule to compare assigned people with required staffing."/>}</Card><Card><div className="p-5"><h2 className="text-sm font-semibold text-ink">Latest schedule</h2>{latest ? <><p className="mt-3 text-lg font-semibold text-ink">{latest.name || `Schedule #${latest.id}`}</p><p className="mt-1 text-xs text-muted">{dateLabel(latest.start_date)} – {dateLabel(latest.end_date)}</p><dl className="mt-4 space-y-3 border-t border-line pt-4 text-sm"><div className="flex justify-between gap-3"><dt className="text-muted">Assignments</dt><dd className="font-semibold">{assignments.length}</dd></div><div className="flex justify-between gap-3"><dt className="text-muted">Scheduled employees</dt><dd className="font-semibold">{scheduledEmployees}</dd></div><div className="flex justify-between gap-3"><dt className="text-muted">Cost</dt><dd className="font-semibold">{currency(latest.total_cost)}</dd></div></dl><Link className="mt-5 inline-block text-sm font-semibold text-brand hover:underline" to="/schedule">Review schedule →</Link></> : <EmptyState title="No saved schedule" description="Create a schedule to see coverage and cost here."/>}</div></Card></div>
      {!optimizerContext && latest && <p className="mt-4 text-xs text-muted">This saved schedule predates stored optimizer explanation metrics, so preference, fairness, and project completion scores are unavailable.</p>}
    </>}
  </>
}
