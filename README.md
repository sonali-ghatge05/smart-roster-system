## System Design & Architecture Decisions

### 1. How did you model employees, brands, processes, pods, and their relationships?
The system uses a normalized relational schema in SQLite (`roster.db`) as a single source of truth:
* **Organizational Hierarchy:** `pods` group both `employees` (with role and preferred weekly off) and `brands`.
* **Decoupled Operating Rules:** Instead of tying schedules to a brand globally, `brand_process_rules` maps each `(brand, process)` pair to its own operating calendar (`365_DAYS`, `DAILY_EXCEPT_HOLIDAYS`, or `NO_SUNDAYS_OR_HOLIDAYS`) and `min_staff` requirement. This natively supports mixed calendars within the same brand (e.g., `CS` running 365 days while `NDR` skips Sundays and holidays).
* **Flexible Staffing:** An `assignments` junction table models a many-to-many relationship between `employees`, `brands`, and `processes`, supporting single-resource brands, multi-resource brands (split or overlapping processes), and multi-brand employees without schema changes.
* **Operational State:** `leaves`, `public_holidays`, and `roster_entries` reference `employees` and dates to track daily availability and overrides.

### 2. How does your system generate a roster and determine whether it satisfies the required constraints?
* **Generation (`scheduler.py`):** For the selected month, the engine loads all operating rules, public holidays, and approved leaves/comp-offs. It groups the month into calendar weeks and assigns each employee one weekly off per full week—honoring their preferred day when possible, or shifting it (for example, to Sunday on `NO_SUNDAYS_OR_HOLIDAYS` brands) to avoid creating avoidable coverage gaps.
* **Validation (`validate_roster()`):** After generation (and after any live edit), the engine evaluates every active `(brand, process)` on every required operating day against `min_staff`. It separates findings into **Hard Conflicts** (actual working staff < `min_staff`) and **Soft Warnings** (an employee was scheduled on their preferred weekly off to preserve coverage).

### 3. How did you handle the difference between single-resource brands and brands with multiple employees?
Rather than hardcoding a static flag, the system derives staffing structure dynamically from the `assignments` table:
* **Multi-resource brands (20%):** When multiple employees share a process, the scheduler staggers their weekly offs across different days so `min_staff` remains satisfied.
* **Single-resource brands (80%):** When only one employee is assigned to a brand-process, any weekly off or leave on a required operating day immediately drops coverage to zero. The validator flags these gaps as `single_resource = True` with `CRITICAL` severity so managers can prioritize them first.

### 4. What happens when an employee manages all processes for a brand but is unavailable on a required working day?
The validator checks every process independently, so an unavailable single-resource employee triggers a **Hard Conflict** for *each* active process on that brand for that date (e.g., both `CS` and `ACC`), tagged with the exact cause (`WEEKLY_OFF` or `PLANNED_LEAVE`). In the **Conflict Center**, the manager can filter by Pod or Cause and use one-click **Backup Assignment** to assign an available teammate from the same pod to cover the gap.

### 5. How does your system handle conflicting requirements or insufficient staffing?
The engine never fails silently or drops a rule. It follows a strict constraint hierarchy:
1. **Hard Constraints** (brand coverage, approved leaves, public holidays) always take precedence over **Soft Constraints** (preferred weekly-off days).
2. When staffing is mathematically insufficient—such as a single employee assigned to a `365_DAYS` brand—the system produces the best-effort schedule, surfaces every unresolvable gap in the Conflict Center with root cause and severity, and switches the dashboard status to **Action Required** for human resolution.

### 6. Which parts of the process did you automate, and which did you leave under human control? Why?
* **Automated:** Monthly baseline roster generation, weekly-off staggering, calendar/holiday rule evaluation, real-time conflict detection, and available backup filtering. These are repetitive, rule-heavy calculations where manual spreadsheets are error-prone.
* **Human-Controlled:** Final backup selection, manual roster overrides/simulations, approving or canceling leaves, editing brand operating rules, and modifying employee assignments. Operations managers hold context that a database does not—such as client sensitivity, employee fatigue, and cross-training readiness.

### 7. If the company doubled its team and brand count, what would you change about your solution?
* **Database:** Migrate from local SQLite to a managed **PostgreSQL** database to support concurrent multi-manager edits and durable cloud persistence.
* **Optimization Engine:** Replace the heuristic weekly-off scheduler with a constraint programming solver (such as **Google OR-Tools CP-SAT**) to globally optimize staggering and cross-pod backup allocation across 60+ employees and 40+ brands.
* **Access & Scale:** Introduce Role-Based Access Control (Pod Leads vs. Ops Admins), server-side pagination/caching for larger roster matrices, and a persistent audit log of all manual overrides.

### 8. If you had one additional week to work on this, what would you improve first?
1. **Skill & Cross-Training Matrix:** Track secondary brand familiarity so backup recommendations are ranked by domain readiness rather than pod availability alone.
2. **Multi-Shift & Fatigue Rules:** Support multiple shifts per day (morning/evening/night), variable weekday vs. weekend `min_staff`, and consecutive working-day limits (e.g., max 6 consecutive days).
3. **Audit Trail & Notifications:** Add a change-history log with one-click undo and automated Slack/email alerts when a new leave creates a `CRITICAL` coverage gap.
