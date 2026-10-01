import { useCallback, useEffect, useMemo, useState } from 'react'
import { RefreshCw, WandSparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, EmptyState, LoadingState, PageHeader, Select } from '../components/UI'
import { applyReschedule, getApiErrorMessage, getSchedules, previewReschedule, schedulesApi } from '../services/api'

const dateLabel = (value) => value ? new Date(`${String(value).slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

export default function Reschedule() {
  const [schedules, setSchedules] = useState([])
  const [scheduleId, setScheduleId] = useState('')
  const [assignments, setAssignments] = useState([])
  const [assignmentId, setAssignmentId] = useState('')
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const loadSchedules = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getSchedules({ limit: 500 })
      setSchedules(Array.isArray(response.data) ? response.data : [])
    } catch (e) { setError(getApiErrorMessage(e)) } finally { setLoading(false) }
  }, [])
  useEffect(() => { loadSchedules() }, [loadSchedules])

  const selectedAssignment = assignments.find((item) => String(item.id) === assignmentId)
  const originalByShift = useMemo(() => new Map(assignments.map((item) => [item.shift_id, item])), [assignments])
  const candidateByShift = useMemo(() => new Map((preview?.assignments || []).map((item) => [item.shift_id, item])), [preview])
  const changed = useMemo(() => {
    if (!preview || preview.status !== 'FEASIBLE') return []
    const shiftIds = new Set([...originalByShift.keys(), ...candidateByShift.keys()])
    return [...shiftIds]
      .filter((id) => originalByShift.get(id)?.employee_id !== candidateByShift.get(id)?.employee_id)
      .map((id) => ({ shiftId: id, before: originalByShift.get(id), after: candidateByShift.get(id) }))
  }, [preview, originalByShift, candidateByShift])
  const affectedEmployees = new Set(changed.flatMap((item) => [item.before?.employee_id, item.after?.employee_id].filter(Boolean))).size

  const loadAssignments = async (id) => {
    setScheduleId(id); setAssignmentId(''); setAssignments([]); setPreview(null); setError('')
    if (!id) return
    setBusy(true)
    try {
      const response = await schedulesApi.getAssignments(id)
      setAssignments(Array.isArray(response.data) ? response.data : [])
    } catch (e) { setError(getApiErrorMessage(e)) } finally { setBusy(false) }
  }
  const runPreview = async () => {
    if (!selectedAssignment) return
    setBusy(true); setError(''); setPreview(null)
    try { setPreview((await previewReschedule({ schedule_id: Number(scheduleId), assignment_id: selectedAssignment.id })).data) }
    catch (e) { setError(getApiErrorMessage(e)) } finally { setBusy(false) }
  }
  const applyPreview = async () => {
    if (!preview || preview.status !== 'FEASIBLE' || !selectedAssignment) return
    if (!window.confirm('Apply this optimizer-verified replacement to the saved schedule? This replaces its assignments atomically.')) return
    setBusy(true); setError(''); setSuccess('')
    try {
      await applyReschedule({ schedule_id: Number(scheduleId), assignment_id: selectedAssignment.id, confirmed: true })
      setSuccess('The validated schedule replacement was applied.')
      const response = await schedulesApi.getAssignments(scheduleId)
      setAssignments(Array.isArray(response.data) ? response.data : [])
      await loadSchedules()
    } catch (e) { setError(getApiErrorMessage(e)) } finally { setBusy(false) }
  }

  return <>
    <PageHeader eyebrow="Schedule changes · Live optimizer" title="Reschedule preview" description="Test a full-day absence against a saved schedule and compare a feasible optimizer result without changing stored data." action={<Button variant="outline" icon={RefreshCw} onClick={loadSchedules}>Refresh schedules</Button>}/>
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-5">
      <Card className="xl:col-span-2"><div className="space-y-4 p-5">
        <h2 className="text-sm font-semibold text-ink">Select the absence scenario</h2>
        {loading ? <LoadingState label="Loading saved schedules…"/> : <>
          <label className="block text-xs font-medium text-ink">Saved schedule<Select aria-label="Saved schedule" className="mt-1.5 w-full" value={scheduleId} onChange={(e) => loadAssignments(e.target.value)}><option value="">Select a schedule</option>{schedules.map((item) => <option key={item.id} value={item.id}>{item.name || `Schedule #${item.id}`} · {dateLabel(item.start_date)}</option>)}</Select></label>
          <label className="block text-xs font-medium text-ink">Affected assignment<Select aria-label="Affected assignment" className="mt-1.5 w-full" value={assignmentId} onChange={(e) => { setAssignmentId(e.target.value); setPreview(null) }} disabled={!assignments.length}><option value="">Select an assignment</option>{assignments.map((item) => <option key={item.id} value={item.id}>{item.employee_name} · {item.shift_name} · {dateLabel(item.shift_date)}</option>)}</Select></label>
          {selectedAssignment && <div className="rounded-lg border border-dashed border-line bg-slate-50 p-3"><p className="text-xs font-semibold text-ink">Previewed absence</p><p className="mt-1 text-sm text-slate-700">{selectedAssignment.employee_name} unavailable all day on {dateLabel(selectedAssignment.shift_date)}</p><p className="mt-1 text-xs text-muted">The scenario applies temporary approved leave for this preview only.</p></div>}
          <Button className="w-full" disabled={!selectedAssignment || busy} onClick={runPreview} icon={WandSparkles}>{busy ? 'Testing with optimizer…' : 'Preview re-optimization'}</Button>
          <p className="text-center text-[11px] text-muted">The source schedule remains unchanged. Preview results are not persisted.</p>
        </>}
      </div></Card>
      <div className="space-y-4 xl:col-span-3">
        {error && <Card className="p-4"><p role="alert" className="text-sm text-rose-700">{error}</p></Card>}{success && <Card className="p-4"><p role="status" className="text-sm text-emerald-700">{success}</p></Card>}
        {busy && scheduleId && <Card><LoadingState label="Running the existing schedule optimizer…"/></Card>}
        {preview && <>
          <Card><div className="p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-semibold text-ink">Reschedule comparison</h2><p className="mt-1 text-xs text-muted">Original schedule #{preview.source_schedule_id} · {dateLabel(preview.absence_date)}</p></div><Badge tone={preview.status === 'FEASIBLE' ? 'green' : 'rose'} dot>{preview.status}</Badge></div>
            {preview.status === 'FEASIBLE' ? <><div className="mt-4 grid grid-cols-3 gap-2">{[['Changed shifts', changed.length], ['Affected employees', affectedEmployees], ['Candidate assignments', preview.assignments.length]].map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 p-3"><p className="text-lg font-semibold text-ink">{value}</p><p className="mt-1 text-xs text-muted">{label}</p></div>)}</div><p className="mt-3 text-xs text-muted">Changed counts are direct comparisons by shift ID. This preview does not optimize a dedicated minimal-change objective.</p></> : <div className="mt-4 rounded-lg border border-rose-100 bg-rose-50 p-4"><p className="text-sm font-semibold text-rose-900">No feasible revised schedule was returned.</p><p className="mt-1 text-sm text-rose-800">The saved schedule remains intact. See the returned optimizer diagnostics below.</p>{preview.conflicts?.map((item, index) => <p key={item.conflict_id || index} className="mt-2 text-xs text-rose-800">{item.type}: {item.message}</p>)}<Link to="/conflicts" className="mt-3 inline-block text-sm font-semibold text-brand">Open conflict analysis →</Link></div>}
          </div></Card>
          {preview.status === 'FEASIBLE' && <>
            <Card><div className="border-b border-line p-5"><h2 className="text-sm font-semibold text-ink">Assignment differences</h2><p className="mt-1 text-xs text-muted">All returned differences are computed against the stored assignments.</p></div>
              {changed.length ? <div className="divide-y divide-line">{changed.map(({ shiftId, before, after }) => <div key={shiftId} className="flex flex-wrap items-center gap-3 p-4"><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">{after?.shift_name || before?.shift_name || `Shift #${shiftId}`}</p><p className="text-xs text-muted">{dateLabel(after?.shift_date || before?.shift_date)}</p></div><div className="text-right text-xs"><p className="text-muted">{before?.employee_name || 'Unassigned'} <span aria-hidden="true">→</span></p><p className="font-semibold text-ink">{after?.employee_name || 'Unassigned'}</p></div><Badge tone="blue">Changed</Badge></div>)}</div> : <div className="p-5"><EmptyState title="No assignment changes" description="The feasible candidate has the same employee assignments as the saved schedule."/></div>}
            </Card>
            <Card className="p-4"><p className="text-sm font-semibold text-ink">Apply reviewed schedule</p><p className="mt-1 text-xs text-muted">The server reruns the optimizer candidate and atomically replaces assignments only when it remains feasible.</p><div className="mt-3 flex gap-2"><Button variant="outline" disabled={busy} onClick={() => { setPreview(null); setSuccess('') }}>Cancel review</Button><Button disabled={busy} onClick={applyPreview}>{busy ? 'Validating and applying…' : 'Confirm and apply'}</Button></div></Card>
          </>}
        </>}
        {!preview && !loading && !busy && !error && <Card><EmptyState title="No preview yet" description="Select a saved schedule and an assignment, then run the optimizer-backed absence preview."/></Card>}
      </div>
    </div>
  </>
}
