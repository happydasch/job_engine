/**
 * Shared enum display-name mappings for job fields.
 *
 * The enum identifier (lowercase key) is what's stored in the DB/API.
 * The display name is what users see in the dashboard.
 */

export const EXPERIENCE_LEVELS = {
  junior: 'Junior',
  jr: 'Junior',
  entry: 'Junior',
  mid: 'Mid',
  regular: 'Mid',
  intermediate: 'Mid',
  senior: 'Senior',
  sr: 'Senior',
  staff: 'Senior',
  lead: 'Lead',
  principal: 'Lead',
  head: 'Lead',
  intern: 'Intern',
  manager: 'Manager',
  executive: 'Executive',
  director: 'Executive',
  'c-level': 'Executive',
  cfo: 'Executive',
  cto: 'Executive',
  trainee: 'Trainee',
  expert: 'Expert',
  c_level: 'C-Level',
}

export const CONTRACT_TYPES = {
  b2b: 'B2B',
  permanent: 'Permanent',
  uop: 'Permanent (UoP)',
  uz: 'Contract (UZ)',
  ud: 'Specific Task (UD)',
  full_time: 'Full-time',
  part_time: 'Part-time',
  contract: 'Contract',
  freelance: 'Freelance',
  internship: 'Internship',
  other: 'Other',
}

export function getExperienceLabel(value) {
  return EXPERIENCE_LEVELS[(value || '').toLowerCase()] || value || ''
}

export function getContractLabel(value) {
  return CONTRACT_TYPES[(value || '').toLowerCase()] || value || ''
}