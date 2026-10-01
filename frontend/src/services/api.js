import axios from 'axios'

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? '' : 'http://localhost:8000')

export const apiClient = axios.create({
  baseURL: `${configuredBaseUrl.replace(/\/+$/, '')}/api`,
  headers: { 'Content-Type': 'application/json' },
})

const get = (path, params) => apiClient.get(path, { params })
const createResourceMethods = (path) => ({
  create: (payload) => apiClient.post(path, payload),
  getById: (id) => apiClient.get(`${path}/${id}`),
  update: (id, payload) => apiClient.put(`${path}/${id}`, payload),
  remove: (id) => apiClient.delete(`${path}/${id}`),
})

export const getDepartments = (params) => get('/departments', params)
export const departmentsApi = createResourceMethods('/departments')

export const getSkills = (params) => get('/skills', params)
export const skillsApi = createResourceMethods('/skills')

export const getEmployees = (params) => get('/employees', params)
export const employeesApi = {
  ...createResourceMethods('/employees'),
  addSkill: (employeeId, skillId, proficiency = 1) => apiClient.post(`/employees/${employeeId}/skills`, { skill_id: skillId, proficiency }),
  updateSkill: (employeeId, skillId, proficiency) => apiClient.put(`/employees/${employeeId}/skills/${skillId}`, { proficiency }),
  removeSkill: (employeeId, skillId) => apiClient.delete(`/employees/${employeeId}/skills/${skillId}`),
}

export const getShifts = (params) => get('/shifts', params)
export const shiftsApi = createResourceMethods('/shifts')
export const getShiftTemplates = (params) => get('/shift-templates', params)
export const shiftTemplatesApi = createResourceMethods('/shift-templates')
export const getAvailability = (params) => get('/availability', params)
export const availabilityApi = createResourceMethods('/availability')
export const getLeave = (params) => get('/leave', params)
export const leaveApi = createResourceMethods('/leave')
export const getEmployeePreferences = (params) => get('/preferences', params)
export const employeePreferencesApi = createResourceMethods('/preferences')

export const getProjects = (params) => get('/projects', params)
export const projectsApi = {
  ...createResourceMethods('/projects'),
  addRequirement: (projectId, payload) => apiClient.post(`/projects/${projectId}/requirements`, payload),
  removeRequirement: (projectId, requirementId) => apiClient.delete(`/projects/${projectId}/requirements/${requirementId}`),
}

export const getSchedules = (params) => get('/schedules', params)
export const schedulesApi = {
  ...createResourceMethods('/schedules'),
  getAssignments: (scheduleId) => apiClient.get(`/schedules/${scheduleId}/assignments`),
  addAssignment: (scheduleId, payload) => apiClient.post(`/schedules/${scheduleId}/assignments`, payload),
  removeAssignment: (scheduleId, assignmentId) => apiClient.delete(`/schedules/${scheduleId}/assignments/${assignmentId}`),
  getConflicts: (scheduleId) => apiClient.get(`/schedules/${scheduleId}/conflicts`),
  getExplanations: (scheduleId) => apiClient.get(`/schedules/${scheduleId}/explanations`),
}

export const generateSchedule = (payload) => apiClient.post('/optimization/generate', payload)
export const generateAlternatives = (payload) => apiClient.post('/optimization/alternatives', payload)
export const resolveConflict = (payload) => apiClient.post('/optimization/resolve-conflict', payload)
export const previewReschedule = (payload) => apiClient.post('/optimization/reschedule-preview', payload)
export const applyReschedule = (payload) => apiClient.post('/optimization/apply-reschedule', payload)

const isDisplayableMessage = (value) => typeof value === 'string'
  && value.trim().length > 0
  && !/(Traceback \(most recent call last\)|^\s*File ".+", line \d+|^\s*at .+\(.+\))/m.test(value)

export function getApiErrorMessage(error, fallback = 'The request could not be completed. Please try again.') {
  const responseData = axios.isAxiosError(error) ? error.response?.data : null
  const detail = responseData?.detail
  if (isDisplayableMessage(detail)) return detail
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter(isDisplayableMessage)
    if (messages.length) return messages.join(' ')
  }
  if (isDisplayableMessage(responseData?.message)) return responseData.message
  if (axios.isAxiosError(error) && error.request && !error.response) {
    return 'Unable to reach the workforce server. Check that the backend is running and try again.'
  }
  return fallback
}

export default apiClient
