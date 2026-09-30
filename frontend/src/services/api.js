import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api', headers: { 'Content-Type': 'application/json' } })
export const getEmployees = (params) => api.get('/employees', { params })
export const getShifts = (params) => api.get('/shifts', { params })
export const getProjects = (params) => api.get('/projects', { params })
export const getDepartments = () => api.get('/departments')
export const getSkills = () => api.get('/skills')
export const getSchedules = (params) => api.get('/schedules', { params })
export const getConflicts = () => api.get('/conflicts')
export const getExplanations = (params) => api.get('/explanations', { params })
export default api
