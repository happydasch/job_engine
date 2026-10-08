# Interview Prep Workflow

> **Purpose:** Generate LLM-powered interview questions tailored to a specific job posting, using the combined context of the job description and your profile.

## Layer Overview

```mermaid
flowchart LR
    JOB[/jobs/{id}] --> TAB[Interview Questions Tab]
    TAB -->|POST /api/tasks/llm| API[routes/tasks.py]
    API --> TM[TaskManager]
    TM --> LLM[llm_task.py → _run_llm_analysis]
    LLM --> PROFILE[data/my_profile.yaml]
    LLM --> JOB_DATA[(job_engine.db)]
    LLM --> OPENROUTER[OpenRouter API]
    OPENROUTER --> RESULT[Questions cached in DB]
    CLIENT -->|GET /api/tasks/{task_id}| POLL[Poll for result]
```

## Step-by-Step

### 1. Navigate to a Job Detail Page

Go to **`/jobs/{id}`** in the dashboard — the job detail view for any scored job.

### 2. Open the Interview Questions Tab

The job detail page has a set of tabs rendered via `AppTabs.vue`:

| Tab | Content |
|-----|---------|
| **Analysis** | Structured LLM analysis (skills, seniority, culture) |
| **Match Explanation** | Natural-language explanation of the match score |
| **Cover Letter** | Generated cover letter |
| **Interview Questions** | Practice interview questions (this workflow) |

### 3. Trigger Interview Question Generation

Clicking the "Interview Questions" tab sends:

```
POST /api/tasks/llm
{
  "job_id": "justjoin_<guid>",
  "task_type": "llm_analysis",
  "language": "english"
}
```

> **Note:** Interview questions are generated as part of the combined `llm_analysis` task (along with analysis, match explanation, cover letter, and summary). There is no standalone "interview questions only" task type.

### 4. Background Task Execution

The `POST /api/tasks/llm` endpoint:

| Step | What Happens |
|------|-------------|
| 1 | Returns `{"task_id": "<uuid>", "status": "running"}` immediately |
| 2 | `TaskManager.start()` creates a `Task` with type `llm_analysis` |
| 3 | `_run_llm_analysis()` loads the job from the database via `job_to_dict()` |
| 4 | Loads the profile from `data/my_profile.yaml` |
| 5 | Calls `analyze_all_job()` which invokes `suggest_interview_questions()` internally |
| 6 | Results are saved to the job's `llm_questions` field in the DB |
| 7 | Task status updates to `completed` with the result |

### 5. Poll for Completion

The frontend polls `GET /api/tasks/{task_id}` for status using `useTaskPoll` composable:

- **Poll interval:** ~2 seconds
- **Status:** `"running"` → `"completed"` or `"failed"`
- **Progress:** `progress_pct` field (5% → 20% → 30% → 80% → 100%)
- **On completion:** Displays questions in the Interview Questions tab

### 6. Interview Questions in the LLM Module

**`suggest_interview_questions()`** in `packages/job-engine-core/src/job_engine/llm.py`:

```
function suggest_interview_questions(
    job: dict,
    profile: dict,
    language: str = "English"
) -> list[str]
```

**What it produces:**
- A curated list of 5–10 interview practice questions
- Tailored to the specific job's requirements and technologies
- References your profile skills to suggest questions relevant to your background
- Covers: technical skills, domain knowledge, behavioral questions, problem-solving

**Prompt template:** `INTERVIEW_QUESTIONS_PROMPT_TEMPLATE` from `packages/job-engine-core/src/job_engine/_prompts/`

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/tasks/llm` | Start background LLM analysis (includes interview questions) |
| `GET` | `/api/tasks/{task_id}` | Poll task for status/result |
| `GET` | `/api/tasks/{task_id}/logs` | Get log lines for a running task |
| `GET` | `/api/jobs/{id}/analysis` | Read cached LLM analysis (read-only) |
| `DELETE` | `/api/tasks/{task_id}` | Cancel a running task |

### LLM Configuration

The LLM module uses LangChain + OpenRouter. Configuration via dashboard Settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `llm.provider` | `openrouter` | LLM provider |
| `llm.model` | `openai/gpt-4o-mini` | Model for analysis |
| `llm.api_key` | *(from env)* | OpenRouter API key |
| `language` | `English` | Output language for all LLM responses |

Check LLM readiness:
```bash
make llm-test
```

### Data Flow

```text
User clicks "Interview Questions" tab
  → POST /api/tasks/llm { job_id, task_type: "llm_analysis" }
  → 202 Accepted { task_id }
  → useTaskPoll polls GET /api/tasks/{task_id} every 2s
  → Background: _run_llm_analysis()
      → loads job dict from DB
      → loads profile from data/my_profile.yaml
      → analyze_all_job(job, profile)
          → suggest_interview_questions() → LLM API
      → saves to job.llm_questions
  → Poll returns: status=completed, result.questions=[...]
  → Frontend displays questions in tab
```

### Layer Trace

| Layer | File | Key Code |
|-------|------|----------|
| **Core** | `packages/job-engine-core/src/job_engine/llm.py` | `suggest_interview_questions()`, `analyze_all_job()`, `_prompts/` |
| **Task** | `packages/job-engine-core/src/job_engine/task_manager.py` | `TaskManager`, `Task` model |
| **API** | `packages/job-engine-dashboard/src/dashboard/routes/tasks.py` | `api_trigger_llm_task()`, `api_get_task()` |
| **API** | `packages/job-engine-dashboard/src/dashboard/routes/llm_task.py` | `_run_llm_analysis()` — runner function |
| **API Helper** | `packages/job-engine-dashboard/src/dashboard/jobs_helpers.py` | `_save_llm_fields_to_job()` |
| **Composable** | `packages/job-engine-dashboard/src/composables/useTaskPoll.js` | Poll task status periodically |
| **Component** | `packages/job-engine-dashboard/src/views/JobDetailView.vue` | Tab UI for "Interview Questions" |

### Troubleshooting

| Symptom | Likely Cause |
|---------|-------------|
| Task fails with "No LLM API key" | Set OpenRouter key in Settings or `OPENROUTER_API_KEY` in `.env` |
| Task stays "running" forever | OpenRouter API unresponsive or rate-limited. Check `GET /api/tasks/{task_id}/logs` |
| Questions are generic | Improve profile with specific skills and domain keywords for better-tailored questions |
| `make llm-test` fails | LangChain or langchain-openai not installed. Run `pip install -e packages/job-engine-core` |