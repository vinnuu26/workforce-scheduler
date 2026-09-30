export const employees = [
  { id: 1, name: 'Rahul Sharma', code: 'EMP-1042', department: 'Operations', skills: ['Forklift', 'Inventory'], rate: 500, maxHours: 40, active: true },
  { id: 2, name: 'Priya Nair', code: 'EMP-1043', department: 'Logistics', skills: ['Dispatch', 'First aid'], rate: 620, maxHours: 36, active: true },
  { id: 3, name: 'Arjun Mehta', code: 'EMP-1044', department: 'Operations', skills: ['Forklift', 'Safety'], rate: 540, maxHours: 40, active: true },
  { id: 4, name: 'Ananya Rao', code: 'EMP-1045', department: 'Customer care', skills: ['Support', 'Training'], rate: 480, maxHours: 32, active: false },
  { id: 5, name: 'Kabir Singh', code: 'EMP-1046', department: 'Logistics', skills: ['Dispatch', 'Inventory'], rate: 580, maxHours: 40, active: true },
]
export const shifts = [
  { id: 1, date: '2026-10-06', name: 'Morning shift', time: '06:00 – 14:00', department: 'Operations', template: 'Early operations', required: 8, skills: ['Forklift', 'Safety'], status: 'Covered' },
  { id: 2, date: '2026-10-07', name: 'Night shift', time: '22:00 – 06:00', department: 'Logistics', template: 'Overnight dispatch', required: 6, skills: ['Dispatch'], status: 'Needs cover' },
  { id: 3, date: '2026-10-08', name: 'Day shift', time: '09:00 – 17:00', department: 'Customer care', template: 'Customer support', required: 5, skills: ['Support'], status: 'Covered' },
  { id: 4, date: '2026-10-09', name: 'Evening shift', time: '14:00 – 22:00', department: 'Operations', template: 'Late operations', required: 7, skills: ['Forklift'], status: 'Draft' },
]
export const projects = [
  { id: 1, name: 'Regional fulfilment', priority: 'High', deadline: '18 Oct 2026', status: 'In progress', skills: ['Forklift', 'Inventory'], staffing: '12 people' },
  { id: 2, name: 'Dispatch coverage', priority: 'Medium', deadline: '22 Oct 2026', status: 'Planning', skills: ['Dispatch', 'Safety'], staffing: '8 people' },
  { id: 3, name: 'Service desk launch', priority: 'High', deadline: '30 Oct 2026', status: 'At risk', skills: ['Support', 'Training'], staffing: '6 people' },
]
export const departments = ['Operations', 'Logistics', 'Customer care']
export const metrics = [
  { label: 'Employees', value: '48', note: '42 active this week', icon: 'Users', tone: 'teal' },
  { label: 'Coverage', value: '92%', note: '4 shifts need attention', icon: 'CalendarCheck', tone: 'blue' },
  { label: 'Total cost', value: '₹2.84L', note: '7.2% below budget', icon: 'IndianRupee', tone: 'violet' },
  { label: 'Overtime', value: '36 hrs', note: 'Across 8 employees', icon: 'Clock3', tone: 'amber' },
  { label: 'Conflicts', value: '3', note: '1 high severity', icon: 'TriangleAlert', tone: 'rose' },
  { label: 'Preference match', value: '86%', note: 'Up 4% this month', icon: 'Heart', tone: 'green' },
]
export const coverageData = [{ name: 'Operations', scheduled: 92, target: 100 }, { name: 'Logistics', scheduled: 76, target: 92 }, { name: 'Customer care', scheduled: 84, target: 90 }, { name: 'Facilities', scheduled: 68, target: 78 }]
export const costData = [{ name: 'Mon', cost: 34 }, { name: 'Tue', cost: 38 }, { name: 'Wed', cost: 32 }, { name: 'Thu', cost: 42 }, { name: 'Fri', cost: 37 }, { name: 'Sat', cost: 48 }, { name: 'Sun', cost: 40 }]
export const hoursData = [{ name: '0–20 hrs', value: 8 }, { name: '21–30 hrs', value: 13 }, { name: '31–40 hrs', value: 21 }, { name: '40+ hrs', value: 6 }]
export const mixData = [{ name: 'Weekday day', value: 54 }, { name: 'Evening', value: 26 }, { name: 'Night', value: 13 }, { name: 'Weekend', value: 7 }]
export const schedule = [
  { id: 1, employee: 'Rahul Sharma', department: 'Operations', date: '2026-10-06', shift: 'Morning', hours: 8, time: '06:00 – 14:00', color: 'teal' },
  { id: 2, employee: 'Priya Nair', department: 'Logistics', date: '2026-10-06', shift: 'Day', hours: 8, time: '09:00 – 17:00', color: 'blue' },
  { id: 3, employee: 'Arjun Mehta', department: 'Operations', date: '2026-10-06', shift: 'Evening', hours: 8, time: '14:00 – 22:00', color: 'violet' },
  { id: 4, employee: 'Kabir Singh', department: 'Logistics', date: '2026-10-07', shift: 'Night', hours: 8, time: '22:00 – 06:00', color: 'amber' },
  { id: 5, employee: 'Ananya Rao', department: 'Customer care', date: '2026-10-07', shift: 'Day', hours: 8, time: '09:00 – 17:00', color: 'blue' },
]
export const conflicts = [{ id: 1, severity: 'High', shift: 'Night shift · 7 Oct', required: 6, available: 4, issue: 'Two qualified employees are unavailable for the overnight dispatch shift.', constraints: ['Minimum staffing', 'Availability', 'Required skill'], suggestions: ['Add a qualified employee', 'Allow planned overtime', 'Review staffing requirement'] }, { id: 2, severity: 'Medium', shift: 'Evening shift · 9 Oct', required: 7, available: 6, issue: 'Coverage falls one person below the Operations target.', constraints: ['Minimum staffing', 'Rest period'], suggestions: ['Move an available employee', 'Offer an open shift'] }, { id: 3, severity: 'Low', shift: 'Weekend · 11 Oct', required: 4, available: 4, issue: 'Weekend preference balance is lower than the team average.', constraints: ['Weekend preference'], suggestions: ['Rotate weekend assignments next week'] }]
export const assignments = [{ employee: 'Rahul Sharma', shift: 'Morning', date: '6 Oct 2026', hours: 8, cost: 4000, why: ['Required skill', 'Available', 'Department match', 'Preference match', 'Within hour limit'] }]
