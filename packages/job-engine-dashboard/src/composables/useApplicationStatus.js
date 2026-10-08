/**
 * Application status transitions and operations.
 * Status names match the backend: applied, interview, offer, accepted, rejected, withdrawn
 */
const VALID_TRANSITIONS = {
  applied: ['interview', 'offer', 'accepted', 'rejected', 'withdrawn'],
  interview: ['offer', 'rejected', 'withdrawn'],
  offer: ['accepted', 'rejected', 'withdrawn'],
  accepted: ['withdrawn'],
  rejected: [],
  withdrawn: [],
}

/** Statuses where the search for this job is over — matches backend APPLICATION_TERMINAL_STATUSES. */
const TERMINAL_STATUSES = new Set(['accepted', 'rejected', 'withdrawn'])

/** Direct export for component imports (not wrapped in composable) */
export function getValidTransitions(currentStatus) {
  return VALID_TRANSITIONS[currentStatus] || []
}

/** Whether a status is closed for display purposes (dimmed rows, active counts, archive gating). */
export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.has(status)
}

export function useApplicationStatus() {
  async function transitionApp(appId, newStatus) {
    const res = await fetch(`/api/applications/${appId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    })
    if (!res.ok) throw new Error(`Transition failed: ${res.status}`)
    return res.json()
  }

  async function createApplication(jobId, status = 'applied') {
    const res = await fetch(`/api/applications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, status }),
    })
    if (!res.ok) throw new Error(`Create failed: ${res.status}`)
    return res.json()
  }

  async function deleteApp(appId) {
    const res = await fetch(`/api/applications/${appId}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`Delete failed: ${res.status}`)
    return true
  }

  async function reopenApp(appId) {
    const res = await fetch(`/api/applications/${appId}/reopen`, { method: 'POST' })
    if (!res.ok) throw new Error(`Reopen failed: ${res.status}`)
    return res.json()
  }


  async function updateApplication(appId, data) {
    const res = await fetch(`/api/applications/${appId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error(`Update failed: ${res.status}`)
    return res.json()
  }

  return { transitionApp, createApplication, deleteApp, reopenApp, getValidTransitions, isTerminalStatus, updateApplication }
}