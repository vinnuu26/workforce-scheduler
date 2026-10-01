import { useCallback, useEffect, useMemo, useState } from 'react'
import { CalendarDays, CheckCircle2, CircleAlert, Clock3, Search, Sparkles, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Avatar, Badge, Button, Card, EmptyState, Input, LoadingState, PageHeader, Select } from '../components/UI'
import { generateAlternatives, generateSchedule, getApiErrorMessage, getSchedules, schedulesApi } from '../services/api'

const localDate = (date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
const today = new Date()
const initialEnd = new Date(today)
initialEnd.setDate(today.getDate() + 6)
const dateLabel = (value) => value ? new Date(`${String(value).slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) : 'Date unavailable'
const timeLabel = (value) => value ? String(value).split('T').at(-1).slice(0, 5) : '—'
const money = (value) => Number.isFinite(Number(value)) ? `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'
const listData = (response) => Array.isArray(response?.data) ? response.data : []

function normalizeAssignment(item, index = 0) {
  return {
    ...item,
    id: item.id ?? `${item.employee_id}-${item.shift_id}-${item.shift_date}-${index}`,
    employee: item.employee_name || `Employee #${item.employee_id}`,
    shift: item.shift_name || 'Shift',
    date: item.shift_date || item.date,
    department: item.department || 'Department not specified',
    hours: Number(item.hours ?? item.regular_hours ?? 0) + Number(item.overtime_hours || 0),
  }
}

function metricRows(schedule) {
  const result = schedule?.result || {}
  const rows = []
  if (result.total_required != null || result.total_assigned != null) {
    rows.push({ label: 'Coverage', value: `${result.total_assigned ?? '—'} / ${result.total_required ?? '—'}`, note: result.total_excess ? `${result.total_excess} excess assignments` : 'Assigned / required', icon: Users })
  }
  if (result.total_cost != null) rows.push({ label: 'Labor cost', value: money(result.total_cost), note: 'Optimizer result', icon: Clock3 })
  const preference = result.preference?.total_weight > 0 ? Number(result.preference.satisfaction_percentage) / 100 : null
  if (preference != null) rows.push({ label: 'Preference match', value: `${Math.round(preference * 100)}%`, note: 'Preference satisfaction', icon: CheckCircle2 })
  const fairness = result.fairness || {}
  for (const [key, label] of [['hour_balance_score', 'Hour balance'], ['night_balance_score', 'Night balance'], ['weekend_balance_score', 'Weekend balance']]) {
    if (fairness[key] != null) rows.push({ label, value: `${Math.round(Number(fairness[key]) * 100)}%`, note: 'Fairness score', icon: CheckCircle2 })
  }
  const projectRequirements = (result.projects || []).flatMap((project) => project.requirements || [])
  if (projectRequirements.length) rows.push({ label: 'Project requirements', value: `${Math.round(100 * projectRequirements.filter((item) => item.satisfied).length / projectRequirements.length)}%`, note: 'Satisfied requirements', icon: CheckCircle2 })
  if (!rows.some((row) => row.label === 'Labor cost') && schedule?.total_cost != null) rows.push({ label: 'Labor cost', value: money(schedule.total_cost), note: 'Saved schedule', icon: Clock3 })
  if (schedule?.overtime_hours != null) rows.push({ label: 'Overtime', value: `${Number(schedule.overtime_hours)} hrs`, note: 'Saved schedule', icon: Clock3 })
  return rows
}

export default function Schedule() {
  const [startDate, setStartDate] = useState(localDate(today))
  const [endDate, setEndDate] = useState(localDate(initialEnd))
  const [schedules, setSchedules] = useState([])
  const [scheduleLoading, setScheduleLoading] = useState(true)
  const [scheduleError, setScheduleError] = useState('')
  const [active, setActive] = useState(null)
  const [conflicts, setConflicts] = useState([])
  const [explanations, setExplanations] = useState([])
  const [infeasible, setInfeasible] = useState(null)
  const [alternatives, setAlternatives] = useState([])
  const [selectedAlternative, setSelectedAlternative] = useState(0)
  const [alternativeCount, setAlternativeCount] = useState('3')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [department, setDepartment] = useState('All departments')
  const [view, setView] = useState('Employee')
  const [selected, setSelected] = useState(null)

  const loadSchedules = useCallback(async () => {
    setScheduleLoading(true)
    setScheduleError('')
    try {
      setSchedules(listData(await getSchedules({ limit: 500 })))
    } catch (requestError) {
      setScheduleError(getApiErrorMessage(requestError))
    } finally {
      setScheduleLoading(false)
    }
  }, [])

  useEffect(() => { loadSchedules() }, [loadSchedules])

  const resetDisplay = () => {
    setActive(null)
    setConflicts([])
    setExplanations([])
    setInfeasible(null)
    setAlternatives([])
    setSelected(null)
    setError('')
  }

  const handleGenerate = async () => {
    resetDisplay()
    setBusy('generate')
    try {
      const result = (await generateSchedule({ start_date: startDate, end_date: endDate })).data
      if (result.status === 'INFEASIBLE') {
        setInfeasible(result)
      } else if (result.status === 'FEASIBLE' && result.schedule_id != null) {
        const assignments = (result.assignments || []).map(normalizeAssignment)
        setActive({ id: result.schedule_id, name: `Generated · ${dateLabel(result.start_date)} – ${dateLabel(result.end_date)}`, source: 'generated', result, assignments })
        const [conflictResponse, explanationResponse] = await Promise.allSettled([
          schedulesApi.getConflicts(result.schedule_id), schedulesApi.getExplanations(result.schedule_id),
        ])
        if (conflictResponse.status === 'fulfilled') setConflicts(listData(conflictResponse.value))
        if (explanationResponse.status === 'fulfilled') setExplanations(listData(explanationResponse.value))
        await loadSchedules()
      } else {
        setError(result.message || 'The optimizer did not return a usable schedule.')
      }
    } catch (requestError) {
      setError(getApiErrorMessage(requestError))
    } finally {
      setBusy('')
    }
  }

  const handleAlternatives = async () => {
    resetDisplay()
    setBusy('alternatives')
    try {
      const result = (await generateAlternatives({ start_date: startDate, end_date: endDate, count: Number(alternativeCount) })).data
      const found = result.alternatives || []
      setAlternatives(found)
      setSelectedAlternative(0)
      if (!found.length) setError(result.message || 'No alternative schedules were available for this date range.')
      else {
        const first = found[0]
        setActive({ id: first.alternative_id, name: `Alternative 1 · ${dateLabel(startDate)} – ${dateLabel(endDate)}`, source: 'alternative', result: first, assignments: (first.assignments || []).map(normalizeAssignment) })
      }
    } catch (requestError) {
      setError(getApiErrorMessage(requestError))
    } finally {
      setBusy('')
    }
  }

  const chooseAlternative = (index) => {
    const alternative = alternatives[index]
    if (!alternative) return
    setSelectedAlternative(index)
    setActive({ id: alternative.alternative_id, name: `Alternative ${index + 1} · ${dateLabel(startDate)} – ${dateLabel(endDate)}`, source: 'alternative', result: alternative, assignments: (alternative.assignments || []).map(normalizeAssignment) })
    setConflicts([])
    setExplanations([])
  }

  const chooseSavedSchedule = async (scheduleId) => {
    if (!scheduleId) { resetDisplay(); return }
    const schedule = schedules.find((item) => String(item.id) === String(scheduleId))
    resetDisplay()
    setBusy('saved')
    try {
      const [assignmentResponse, conflictResponse, explanationResponse] = await Promise.all([
        schedulesApi.getAssignments(scheduleId), schedulesApi.getConflicts(scheduleId), schedulesApi.getExplanations(scheduleId),
      ])
      setActive({ ...schedule, id: scheduleId, name: schedule?.name || `Schedule #${scheduleId}`, source: 'saved', assignments: listData(assignmentResponse).map(normalizeAssignment) })
      setConflicts(listData(conflictResponse))
      setExplanations(listData(explanationResponse))
      if (schedule?.start_date) setStartDate(String(schedule.start_date).slice(0, 10))
      if (schedule?.end_date) setEndDate(String(schedule.end_date).slice(0, 10))
    } catch (requestError) {
      setError(getApiErrorMessage(requestError))
    } finally {
      setBusy('')
    }
  }

  const allAssignments = active?.assignments || []
  const departments = useMemo(() => [...new Set(allAssignments.map((item) => item.department).filter((name) => name && name !== 'Department not specified'))].sort(), [allAssignments])
  const assignments = useMemo(() => allAssignments.filter((item) => `${item.employee} ${item.shift} ${item.department}`.toLowerCase().includes(query.toLowerCase()) && (department === 'All departments' || item.department === department)), [allAssignments, query, department])
  const days = useMemo(() => [...new Set(assignments.map((item) => String(item.date || '').slice(0, 10)).filter(Boolean))].sort(), [assignments])
  const groups = useMemo(() => {
    const keyFor = (item) => view === 'Department' ? item.department : view === 'Shift' ? item.shift : item.employee
    return [...new Set(assignments.map(keyFor))].sort().map((name) => ({ name, rows: assignments.filter((item) => keyFor(item) === name) }))
  }, [assignments, view])
  const metrics = metricRows(active)
  const selectedExplanation = selected ? explanations.filter((item) => {
    if (!item.details) return false
    try {
      const detail = JSON.parse(item.details)
      return (detail.employee_id != null && String(detail.employee_id) === String(selected.employee_id)) || (detail.shift_id != null && String(detail.shift_id) === String(selected.shift_id))
    } catch { return false }
  }) : []

  return <>
    <PageHeader eyebrow="Schedule planning" title="Schedule" description="Generate a roster, compare optimizer alternatives, or review a saved schedule." />

    <Card className="mb-5 p-4 sm:p-5">
      <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-medium text-muted">Start date<Input className="mt-1.5" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
          <label className="text-xs font-medium text-muted">End date<Input className="mt-1.5" type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button icon={CalendarDays} disabled={Boolean(busy) || !startDate || !endDate || endDate < startDate} onClick={handleGenerate}>{busy === 'generate' ? 'Generating…' : 'Generate schedule'}</Button>
          <Select aria-label="Number of alternatives" value={alternativeCount} onChange={(event) => setAlternativeCount(event.target.value)} disabled={Boolean(busy)}><option value="1">1 alternative</option><option value="2">2 alternatives</option><option value="3">3 alternatives</option><option value="5">5 alternatives</option></Select>
          <Button variant="outline" icon={Sparkles} disabled={Boolean(busy) || !startDate || !endDate || endDate < startDate} onClick={handleAlternatives}>{busy === 'alternatives' ? 'Comparing…' : 'Generate alternatives'}</Button>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4">
        <label className="text-xs font-medium text-muted" htmlFor="saved-schedule">Saved schedule</label>
        <Select id="saved-schedule" aria-label="Load saved schedule" className="min-w-56" value="" disabled={Boolean(busy) || scheduleLoading} onChange={(event) => chooseSavedSchedule(event.target.value)}>
          <option value="">{scheduleLoading ? 'Loading schedules…' : 'Choose a saved schedule'}</option>
          {schedules.map((item) => <option key={item.id} value={item.id}>{item.name || `Schedule #${item.id}`} · {dateLabel(item.start_date)}</option>)}
        </Select>
        <span className="text-xs text-muted">{scheduleLoading ? 'Loading saved schedules…' : `${schedules.length} saved ${schedules.length === 1 ? 'schedule' : 'schedules'}`}</span>
        {scheduleError && <span role="alert" className="text-xs text-rose-700">Could not load saved schedules: {scheduleError}</span>}
      </div>
    </Card>

    {error && <div role="alert" className="mb-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><p className="font-semibold">Schedule request failed</p><p className="mt-1">{error}</p></div>}
    {busy && <Card className="mb-5"><LoadingState label={busy === 'saved' ? 'Loading saved schedule…' : busy === 'alternatives' ? 'Generating alternatives…' : 'Generating schedule…'} /></Card>}

    {infeasible && <Card className="mb-5 border-rose-200 p-5" aria-live="polite"><div className="flex items-start gap-3"><CircleAlert className="mt-0.5 shrink-0 text-rose-700"/><div><h2 className="font-semibold text-rose-900">No feasible schedule for this date range</h2><p className="mt-1 text-sm text-rose-800">{infeasible.message || 'The optimizer could not satisfy the current staffing requirements.'}</p><p className="mt-2 text-xs text-rose-700">No assignments were saved. Review staffing conflicts and constraints before trying again.</p></div></div>{(infeasible.conflicts || []).length > 0 && <div className="mt-4 space-y-2">{infeasible.conflicts.map((item, index) => <div key={item.id || index} className="rounded-lg border border-rose-100 bg-white p-3"><p className="text-sm font-medium text-ink">{item.message || item.type || 'Scheduling conflict'}</p>{item.details && <p className="mt-1 text-xs text-muted">{typeof item.details === 'string' ? item.details : JSON.stringify(item.details)}</p>}{(item.required != null || item.available != null || item.gap != null) && <p className="mt-1 text-xs text-muted">Required {item.required ?? '—'} · Available {item.available ?? '—'} · Gap {item.gap ?? '—'}</p>}</div>)}</div>}<Link className="mt-4 inline-flex text-sm font-semibold text-brand hover:underline" to="/conflicts">Review conflicts</Link></Card>}

    {alternatives.length > 0 && <Card className="mb-5 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-semibold text-ink">Optimizer alternatives</h2><p className="mt-1 text-xs text-muted">These candidates are not saved until a schedule is generated.</p></div><div className="flex flex-wrap gap-2">{alternatives.map((item, index) => <button key={item.alternative_id} aria-pressed={selectedAlternative === index} onClick={() => chooseAlternative(index)} className={`rounded-lg border px-3 py-2 text-xs font-semibold ${selectedAlternative === index ? 'border-brand bg-[#eaf4f2] text-brand' : 'border-line text-slate-600 hover:bg-slate-50'}`}>Option {index + 1} · {money(item.total_cost)}</button>)}</div></div></Card>}

    {active && <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><h2 className="text-sm font-semibold text-ink">{active.name}</h2><Badge tone={active.source === 'alternative' ? 'violet' : 'green'} dot>{active.source === 'alternative' ? 'Not saved' : active.source === 'saved' ? 'Saved schedule' : 'Generated'}</Badge></div><span className="text-xs text-muted">{assignments.length} assignments shown</span></div>
      {metrics.length > 0 && <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{metrics.map(({ label, value, note, icon: Icon }) => <Card key={label} className="p-4"><div className="flex items-start justify-between"><div className="text-xs font-medium text-muted">{label}</div><span className="rounded-lg bg-teal-50 p-2 text-teal-700"><Icon size={16}/></span></div><p className="mt-3 text-2xl font-semibold tracking-tight text-ink">{value}</p><p className="mt-1 text-xs text-muted">{note}</p></Card>)}</div>}
      {conflicts.length > 0 && <Card className="mb-5 border-amber-200 p-4"><div className="flex items-center gap-2 text-sm font-semibold text-amber-900"><CircleAlert size={17}/> {conflicts.length} saved schedule {conflicts.length === 1 ? 'conflict' : 'conflicts'}</div><div className="mt-3 space-y-2">{conflicts.map((item, index) => <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900" key={item.id || index}>{item.message || 'Conflict details unavailable'}{item.details && <span className="mt-1 block text-xs text-amber-800">{item.details}</span>}</p>)}</div></Card>}
      {busy ? null : assignments.length === 0 ? <Card><EmptyState title="No assignments in this schedule" description="This schedule has no assignment records to display." /></Card> : <>
        <div className="mb-4 flex flex-wrap items-center gap-2"><div className="relative min-w-[210px] flex-1 sm:max-w-xs"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><Input aria-label="Search schedule assignments" className="pl-9" placeholder="Search employee or shift" value={query} onChange={(event) => setQuery(event.target.value)}/></div><Select aria-label="Filter assignments by department" value={department} onChange={(event) => setDepartment(event.target.value)}><option>All departments</option>{departments.map((name) => <option key={name}>{name}</option>)}</Select><div className="ml-auto flex gap-1">{['Employee', 'Department', 'Shift'].map((item) => <button key={item} onClick={() => setView(item)} aria-pressed={view === item} className={`rounded-lg px-3 py-2 text-xs font-semibold ${view === item ? 'bg-brand text-white' : 'border border-line bg-white text-muted hover:bg-slate-50'}`}>{item} view</button>)}</div></div>
        {assignments.length === 0 ? <Card><EmptyState title="No assignments match" description="Try clearing the search or department filter."/></Card> : <Card className="overflow-hidden"><div className="overflow-x-auto"><div className="min-w-[850px]"><div className="grid border-b border-line bg-slate-50/70" style={{ gridTemplateColumns: `210px repeat(${Math.max(days.length, 1)}, minmax(130px, 1fr))` }}><div className="p-3 text-[10px] font-semibold uppercase tracking-wider text-muted">{view}</div>{days.map((day) => <div className="border-l border-line p-3 text-center text-xs font-semibold text-ink" key={day}>{dateLabel(day)}<p className="mt-1 text-[10px] font-normal text-muted">{assignments.filter((item) => String(item.date).slice(0, 10) === day).length} assignments</p></div>)}</div>{groups.map((group) => <div key={group.name} className="grid min-h-[96px] border-b border-line last:border-0" style={{ gridTemplateColumns: `210px repeat(${Math.max(days.length, 1)}, minmax(130px, 1fr))` }}><div className="flex items-center gap-2.5 p-3">{view === 'Employee' && <Avatar name={group.name} size="sm"/>}<div><p className="text-xs font-semibold text-ink">{group.name}</p><p className="mt-0.5 text-[10px] text-muted">{group.rows.length} assignments</p></div></div>{days.map((day) => <div className="space-y-1.5 border-l border-line p-2" key={day}>{group.rows.filter((item) => String(item.date).slice(0, 10) === day).map((item) => <button key={item.id} onClick={() => setSelected(item)} className="w-full rounded-r-lg border-l-[3px] border-l-teal-600 bg-teal-50/70 p-2.5 text-left hover:brightness-[.98]"><p className="text-[11px] font-semibold text-ink">{item.shift}</p><p className="mt-1 text-[10px] text-slate-600">{timeLabel(item.start_time)}–{timeLabel(item.end_time)}</p><p className="mt-1 text-[10px] text-slate-500">{item.employee} · {item.hours} hrs</p></button>)}</div>)}</div>)}</div></div><div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3 text-[11px] text-muted"><span>Assignments returned by the workforce API</span><span className="ml-auto">Click an assignment for details</span></div></Card>}
      </>}
    </>}

    {!active && !busy && !infeasible && !error && <Card className="p-1"><EmptyState title="No schedule selected" description="Choose a saved schedule or generate a schedule for the selected dates to review real assignments."/></Card>}

    {selected && <div role="presentation" onClick={() => setSelected(null)} className="fixed inset-0 z-50 flex justify-end bg-slate-900/25"><section role="dialog" aria-modal="true" aria-label="Assignment details" onClick={(event) => event.stopPropagation()} className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl"><button aria-label="Close assignment details" onClick={() => setSelected(null)} className="float-right rounded-lg px-2 py-1 text-muted hover:bg-slate-100">×</button><p className="text-xs font-semibold uppercase tracking-wider text-brand">Assignment details · {active?.source === 'alternative' ? 'Unsaved alternative' : 'Live schedule data'}</p><h2 className="mt-5 text-xl font-semibold text-ink">{selected.employee}</h2><p className="mt-1 text-sm text-muted">{selected.shift} · {dateLabel(selected.date)}</p><div className="mt-6 grid grid-cols-2 gap-3">{[['Department', selected.department], ['Time', `${timeLabel(selected.start_time)}–${timeLabel(selected.end_time)}`], ['Hours', `${selected.hours} hrs`], ['Cost', selected.cost == null ? '—' : money(selected.cost)], ['Project', selected.project_id == null ? 'Not specified' : `#${selected.project_id}`], ['Preference match', selected.preference_match == null ? 'Not returned' : selected.preference_match ? 'Matched' : 'No match']].map(([label, value]) => <div className="rounded-lg border border-line p-3" key={label}><p className="text-xs text-muted">{label}</p><p className="mt-1 text-sm font-semibold text-ink">{value}</p></div>)}</div><h3 className="mb-2 mt-6 text-sm font-semibold">Why this assignment?</h3>{selected.explanation?.message && <p className="mb-3 text-sm leading-relaxed text-slate-700">{selected.explanation.message}</p>}{selected.preference_reasons?.length > 0 && <div className="mb-3 rounded-lg bg-teal-50 p-3"><p className="text-xs font-semibold text-teal-900">Preference reasons returned by optimizer</p><ul className="mt-2 list-inside list-disc space-y-1 text-sm text-teal-900">{selected.preference_reasons.map((reason, index) => <li key={index}>{typeof reason === 'string' ? reason : JSON.stringify(reason)}</li>)}</ul></div>}{selected.explanation?.details?.required_skills_matched?.length > 0 && <div className="mb-3"><p className="text-xs font-semibold text-muted">Required skills satisfied</p><p className="mt-1 text-sm text-slate-700">{selected.explanation.details.required_skills_matched.join(', ')}</p></div>}{selected.explanation?.details?.eligibility_checks && <div className="mb-3 rounded-lg border border-line p-3"><p className="text-xs font-semibold text-muted">Optimizer eligibility checks</p><ul className="mt-2 space-y-1 text-xs text-slate-700">{Object.entries(selected.explanation.details.eligibility_checks).map(([key, passed]) => <li key={key} className="flex items-center justify-between gap-2"><span>{({ employee_active: 'Active employee', department_match: 'Department match', available_for_complete_shift: 'Available for complete shift', approved_leave_applied: 'Approved leave conflict' })[key] || key}</span><Badge tone={(key === 'approved_leave_applied' ? !passed : passed) ? 'green' : 'rose'}>{(key === 'approved_leave_applied' ? !passed : passed) ? 'Passed' : 'Failed'}</Badge></li>)}</ul></div>}{selectedExplanation.length > 0 && selectedExplanation.map((item) => <div key={item.id} className="mb-3 rounded-lg border border-line p-3"><p className="text-sm text-slate-700">{item.message}</p></div>)}{active?.source === 'alternative' && <p className="text-sm text-muted">This unsaved alternative has no persisted explanation record; only optimizer-returned assignment fields are available.</p>}{active?.source !== 'alternative' && !selected.explanation?.message && !selected.preference_reasons?.length && !selectedExplanation.length && <p className="text-sm text-muted">No assignment-specific explanation data is available from the backend.</p>}</section></div>}
  </>
}
