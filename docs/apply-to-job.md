# Apply to Job Workflow

> **Purpose:** Track the full application lifecycle — from creating a new application through to offer, rejection, or withdrawal. Status transitions are enforced with strict validation.

## Layer Overview

```mermaid
flowchart LR
    JOB[/jobs/{id}] --> APPLY[Mark as Applied]
    APPLY -->|POST /api/applications| API[routes/applications.py]
    API --> DB[(job_engine.db)]
    DB --> APP[/applications page]
    APP -->|PATCH /api/applications/{id}/status| API
    APP -->|PATCH /api/applications/{id}| API
```

## Step-by-Step

### 1. Create an Application

**From the job detail page** (`/jobs/{id}`), click "Apply" → sends:

```
POST /api/applications
{
  "job_id": "justjoin_<guid>",
  "status": "applied",
  "cover_letter": "optional cover letter text"
}
```

Or start at a later stage:
```
POST /api/applications
{
  "job_id": "linkedin_<guid>",
  "status": "interview",    // skip directly to interview
  "outcome": "notes..."
}
```

The endpoint:
1. Validates `job_id` exists in the `jobs` table
2. Checks for duplicate applications (returns existing if found)
3. Creates an `Application` record with `applied_at` timestamp
4. Updates the job's `status` to match

### 2. Status State Machine

Defined in `packages/job-engine-dashboard/src/dashboard/routes/applications.py`:

```text
        ┌──────────┐
        │  applied  │
        └────┬─────┘
             │
      ┌──────┴──────┐
      │  interview   │
      └──────┬──────┘
             │
      ┌──────┴──────┐
      │    offer     │
      └──────┬──────┘
             │
    ┌────────┴────────┐
    │    accepted     │
    └────────┬────────┘
             │
    ┌────────┴────────┐
    │   withdrawn     │  (terminal)
    └─────────────────┘
             │
    ┌────────┴────────┐
    │   rejected      │  (terminal)
    └─────────────────┘
```

**Valid transitions:**

| From | → Allowed |
|------|-----------|
| `applied` | interview, offer, accepted, rejected, withdrawn |
| `interview` | offer, rejected, withdrawn |
| `offer` | accepted, rejected, withdrawn |
| `accepted` | withdrawn |
| `rejected` | *(terminal — no transitions)* |
| `withdrawn` | *(terminal — no transitions)* |

### 3. Update Application Status

```
PATCH /api/applications/{id}/status
{
  "status": "interview",
  "outcome_reason": "First round passed"
}
```

The endpoint validates the transition against the state machine. Invalid transitions (e.g., `rejected` → `interview`) return a 400 error.

### 4. Update Application Metadata

```
PATCH /api/applications/{id}
{
  "outcome": "Notes about the process",
  "outcome_reason": "hired",
  "cover_letter": "Updated cover letter",
  "archived_materials_path": "data/applications/company_name/"
}
```

Only allowed for non-closed statuses (rejected/withdrawn are locked).

### 5. Reopen a Closed Application

```
POST /api/applications/{id}/reopen
```

Reopens a closed/finished application back to `applied` status, clearing `interview_at`, `offer_at`, `outcome`, and `outcome_reason`.

### 6. Delete an Application

```
DELETE /api/applications/{id}
```

Permanently removes the application record and resets the job's status to `"new"`.

### 7. Dashboard: Applications Page

Navigate to **`http://localhost:8000/applications`**:

| Feature | Description |
|---------|-------------|
| **List** | All applications with job title, company, status badge, dates |
| **Status Badge** | Color-coded `StatusBadge.vue` — applied=blue, interview=purple, offer=green, rejected=red |
| **Update Status** | Dropdown/modal to transition to next status |
| **Details** | Expand to see cover letter, outcome notes, timestamps |
| **Actions** | Reopen (if closed), Delete |

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/applications` | Create new application |
| `GET` | `/api/applications` | List applications (filter by status, job_id) |
| `PATCH` | `/api/applications/{id}/status` | Transition status |
| `PATCH` | `/api/applications/{id}` | Update metadata (outcome, notes, cover letter) |
| `POST` | `/api/applications/{id}/reopen` | Reopen closed application |
| `DELETE` | `/api/applications/{id}` | Delete application permanently |

### Data Model

**`Application`** (SQLAlchemy model in `packages/job-engine-core/src/job_engine/models.py`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | PK | Auto-increment |
| `job_id` | FK → jobs | The job being applied to |
| `status` | String(20) | applied → interview → offer → accepted/rejected/withdrawn |
| `applied_at` | DateTime | When application was submitted |
| `interview_at` | DateTime | When interview was scheduled/occurred |
| `offer_at` | DateTime | When offer was received |
| `outcome` | Text | Free-text notes about the outcome |
| `outcome_reason` | String(50) | Structured: hired, offer_declined, rejected, no_response, interview_only |
| `cover_letter` | Text | Cover letter content |
| `archived_materials_path` | Text | File path to saved CV/cover letter |
| `created_at` | DateTime | Record creation timestamp |
| `updated_at` | DateTime | Last update timestamp |

**Status constraint:** `CHECK(status IN ('applied','interview','offer','accepted','rejected','withdrawn'))`

### Layer Trace

| Layer | File | Key Code |
|-------|------|----------|
| **DB** | `packages/job-engine-core/src/job_engine/models.py` | `Application` model, `VALID_TRANSITIONS` |
| **API** | `packages/job-engine-dashboard/src/dashboard/routes/applications.py` | `api_create_application()`, `api_update_application_status()`, `api_reopen_application()` |
| **API Helper** | `packages/job-engine-dashboard/src/dashboard/routes/route_helpers.py` | `app_to_dict()` — serializes application for JSON |
| **Composable** | `packages/job-engine-dashboard/src/composables/useApplicationStatus.js` | Application status tracking composable |
| **Component** | `packages/job-engine-dashboard/src/views/ApplicationsView.vue` | Application list with status management |

### Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| `APPLICATION_STATUSES` | `["applied", "interview", "offer", "accepted", "rejected", "withdrawn"]` | `routes/applications.py` |
| `CLOSED_STATUSES` | `{"rejected", "withdrawn"}` | `routes/applications.py` |
| `JOB_STATUSES` | `("new", "matched", "applied", "interview", "offer", "rejected", "archived")` | `models.py` |