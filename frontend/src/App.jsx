import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import Dashboard from './pages/Dashboard'
import Employees from './pages/Employees'
import Shifts from './pages/Shifts'
import Projects from './pages/Projects'
import Constraints from './pages/Constraints'
import Schedule from './pages/Schedule'
import Conflicts from './pages/Conflicts'
import Reschedule from './pages/Reschedule'

export default function App() { return <Routes><Route element={<AppLayout />}><Route index element={<Dashboard />} /><Route path="employees" element={<Employees />} /><Route path="shifts" element={<Shifts />} /><Route path="projects" element={<Projects />} /><Route path="constraints" element={<Constraints />} /><Route path="schedule" element={<Schedule />} /><Route path="conflicts" element={<Conflicts />} /><Route path="reschedule" element={<Reschedule />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes> }
