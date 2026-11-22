import calendar
from datetime import date
from collections import defaultdict
from database import get_connection


def is_operating_day(d: date, calendar_type: str, holidays: set) -> bool:
    """Determine if a (brand, process) requires coverage on date d."""
    date_str = d.isoformat()
    is_sunday = d.weekday() == 6
    is_holiday = date_str in holidays

    if calendar_type == "365_DAYS":
        return True
    elif calendar_type == "DAILY_EXCEPT_HOLIDAYS":
        return not is_holiday
    elif calendar_type == "NO_SUNDAYS_OR_HOLIDAYS":
        return not (is_sunday or is_holiday)
    return True


def get_month_dates(year: int, month: int):
    num_days = calendar.monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, num_days + 1)]


def generate_monthly_roster(year: int, month: int):
    """
    Generates a monthly roster for all active employees, saves it to roster_entries,
    and returns the validation report.
    """
    conn = get_connection()
    cur = conn.cursor()

    dates = get_month_dates(year, month)
    start_str, end_str = dates[0].isoformat(), dates[-1].isoformat()

    # Load reference data
    employees = [dict(r) for r in cur.execute("SELECT * FROM employees WHERE is_active = 1")]
    holidays = {r["date"] for r in cur.execute("SELECT date FROM public_holidays")}
    
    # Leaves map: (emp_id, date_str) -> leave_type
    leaves = {
        (r["employee_id"], r["date"]): r["leave_type"]
        for r in cur.execute(
            "SELECT employee_id, date, leave_type FROM leaves WHERE status = 'APPROVED' AND date BETWEEN ? AND ?",
            (start_str, end_str)
        )
    }

    # Rules map: (brand_id, process_id) -> {calendar_type, min_staff}
    rules = {
        (r["brand_id"], r["process_id"]): dict(r)
        for r in cur.execute("SELECT * FROM brand_process_rules")
    }

    # Assignments maps
    emp_assignments = defaultdict(list)       # emp_id -> [(brand_id, process_id)]
    bp_employees = defaultdict(list)          # (brand_id, process_id) -> [emp_id]
    for r in cur.execute("SELECT employee_id, brand_id, process_id FROM assignments"):
        emp_assignments[r["employee_id"]].append((r["brand_id"], r["process_id"]))
        bp_employees[(r["brand_id"], r["process_id"])].append(r["employee_id"])

    # Group dates by ISO week so every employee gets 1 weekly off per week
    weeks = defaultdict(list)
    for d in dates:
        weeks[d.isocalendar()[:2]].append(d)

    # Track tentative schedule: schedule[emp_id][date_str] = status
    schedule = {e["id"]: {} for e in employees}

    # Step 1: Assign hard pre-existing statuses (Leaves, Comp-Offs, Public Holidays)
    for emp in employees:
        eid = emp["id"]
        assigned_bps = emp_assignments[eid]
        # Check if any of the employee's brands require 365-day coverage
        works_on_holidays = any(
            rules.get(bp, {}).get("calendar_type") == "365_DAYS" for bp in assigned_bps
        )

        for d in dates:
            d_str = d.isoformat()
            if (eid, d_str) in leaves:
                schedule[eid][d_str] = leaves[(eid, d_str)]
            elif d_str in holidays and not works_on_holidays:
                schedule[eid][d_str] = "PUBLIC_HOLIDAY"
            else:
                schedule[eid][d_str] = "WORKING"

    # Step 2: Assign 1 Weekly Off per week per employee (with smart staggering for multi-resource brands)
    for week_key, week_dates in weeks.items():
        if len(week_dates) < 5:
            # Skip partial edge weeks unless Sunday falls in it
            if not any(d.weekday() == 6 for d in week_dates):
                continue
            
        for emp in employees:
            eid = emp["id"]
            pref_day = emp["preferred_weekly_off"]
            assigned_bps = emp_assignments[eid]

            # Order candidate days: preferred day first, then Sunday, then others
            candidates = sorted(
                week_dates,
                key=lambda d: (0 if d.weekday() == pref_day else (1 if d.weekday() == 6 else 2), d.weekday())
            )

            chosen_day = None
            for cand in candidates:
                c_str = cand.isoformat()
                if schedule[eid][c_str] != "WORKING":
                    continue  # Already on leave or holiday

                # Check if taking this day off breaks min_staff on any multi-resource brand
                breaks_coverage = False
                for bp in assigned_bps:
                    rule = rules.get(bp)
                    if not rule or not is_operating_day(cand, rule["calendar_type"], holidays):
                        continue
                    
                    team = bp_employees[bp]
                    # Only try to stagger if multiple employees cover this process
                    team = bp_employees[bp]
                    working_others = sum(
                        1 for other_id in team
                        if other_id != eid and schedule[other_id][c_str] == "WORKING"
                    )
                    if working_others < rule["min_staff"]:
                        breaks_coverage = True
                        break
                if not breaks_coverage:
                    chosen_day = c_str
                    break

            # Fallback: if every day breaks coverage (e.g., single-resource 365-day brand),
            # assign preferred day if available so the employee isn't overworked, and let Validator flag it.
            if not chosen_day:
                for cand in candidates:
                    if schedule[eid][cand.isoformat()] == "WORKING":
                        chosen_day = cand.isoformat()
                        break

            if chosen_day:
                schedule[eid][chosen_day] = "WEEKLY_OFF"

    # Step 3: Save to DB (overwriting existing roster for that month)
    cur.execute("DELETE FROM roster_entries WHERE date BETWEEN ? AND ?", (start_str, end_str))
    rows_to_insert = []
    for eid, day_map in schedule.items():
        for d_str, status in day_map.items():
            rows_to_insert.append((eid, d_str, status, 0, ""))

    cur.executemany(
        "INSERT INTO roster_entries (employee_id, date, status, is_manual_override, notes) VALUES (?, ?, ?, ?, ?)",
        rows_to_insert
    )
    conn.commit()
    conn.close()

    return validate_roster(year, month)


def validate_roster(year: int, month: int):
    """
    Validates the saved roster for a given month (including temporary backup covers).
    Returns a dict with 'hard_conflicts' and 'soft_warnings'.
    """
    conn = get_connection()
    cur = conn.cursor()

    dates = get_month_dates(year, month)
    start_str, end_str = dates[0].isoformat(), dates[-1].isoformat()

    holidays = {r["date"] for r in cur.execute("SELECT date FROM public_holidays")}
    pods = {r["id"]: r["name"] for r in cur.execute("SELECT id, name FROM pods")}
    brands = {r["id"]: dict(r) for r in cur.execute("SELECT * FROM brands")}
    processes = {r["id"]: dict(r) for r in cur.execute("SELECT * FROM processes")}
    employees = {r["id"]: dict(r) for r in cur.execute("SELECT * FROM employees")}

    rules = [dict(r) for r in cur.execute("SELECT * FROM brand_process_rules")]
    bp_employees = defaultdict(list)
    for r in cur.execute("SELECT employee_id, brand_id, process_id FROM assignments"):
        bp_employees[(r["brand_id"], r["process_id"])].append(r["employee_id"])

    roster = defaultdict(dict)
    for r in cur.execute(
        "SELECT employee_id, date, status FROM roster_entries WHERE date BETWEEN ? AND ?",
        (start_str, end_str)
    ):
        roster[r["employee_id"]][r["date"]] = r["status"]

    # Load temporary backup covers for this month
    covers = defaultdict(list)
    for r in cur.execute(
        "SELECT date, brand_id, process_id, backup_employee_id FROM temporary_covers WHERE date BETWEEN ? AND ?",
        (start_str, end_str)
    ):
        covers[(r["date"], r["brand_id"], r["process_id"])].append(r["backup_employee_id"])

    hard_conflicts = []
    soft_warnings = []

    # 1. Check Hard Constraints: Brand & Process Coverage Gaps
    for d in dates:
        d_str = d.isoformat()
        for rule in rules:
            b_id, p_id = rule["brand_id"], rule["process_id"]
            if not is_operating_day(d, rule["calendar_type"], holidays):
                continue

            assigned = bp_employees[(b_id, p_id)]
            working_regular = [eid for eid in assigned if roster[eid].get(d_str) == "WORKING"]
            working_backups = [
                bid for bid in covers[(d_str, b_id, p_id)]
                if roster[bid].get(d_str) == "WORKING" and bid not in working_regular
            ]
            total_working = len(working_regular) + len(working_backups)

            if total_working < rule["min_staff"]:
                off_reasons = [
                    f"{employees[eid]['name']} ({roster[eid].get(d_str, 'UNSCHEDULED')})"
                    for eid in assigned if eid not in working_regular
                ]
                severity = "CRITICAL" if total_working == 0 else "HIGH"
                hard_conflicts.append({
                    "date": d_str,
                    "pod": pods[brands[b_id]["pod_id"]],
                    "severity": severity,
                    "brand_id": b_id,
                    "brand": brands[b_id]["name"],
                    "process_id": p_id,
                    "process": processes[p_id]["code"],
                    "required": rule["min_staff"],
                    "actual": total_working,
                    "single_resource": len(assigned) == 1,
                    "reason": ", ".join(off_reasons) if off_reasons else "No employee assigned"
                })

    # 2. Check Soft Constraints: Preferred Weekly Off Violations
    for eid, emp in employees.items():
        pref_day = emp["preferred_weekly_off"]
        pref_name = calendar.day_name[pref_day]
        for d in dates:
            if d.weekday() == pref_day and roster[eid].get(d.isoformat()) == "WORKING":
                soft_warnings.append({
                    "date": d.isoformat(),
                    "employee": emp["name"],
                    "type": "PREFERENCE_VIOLATED",
                    "detail": f"Working on preferred weekly off ({pref_name}) to maintain coverage."
                })

    conn.close()
    return {"hard_conflicts": hard_conflicts, "soft_warnings": soft_warnings}

def suggest_backups(date_str: str, brand_id: int):
    """
    Suggests available employees from the same pod who are WORKING on date_str
    and not already assigned to this brand.
    """
    conn = get_connection()
    cur = conn.cursor()

    brand = cur.execute("SELECT pod_id FROM brands WHERE id = ?", (brand_id,)).fetchone()
    if not brand:
        conn.close()
        return []

    pod_id = brand["pod_id"]
    query = """
        SELECT e.id, e.name, e.role, r.status,
               (SELECT COUNT(DISTINCT a.brand_id) FROM assignments a WHERE a.employee_id = e.id) AS brand_load
        FROM employees e
        JOIN roster_entries r ON e.id = r.employee_id AND r.date = ?
        WHERE e.pod_id = ?
          AND e.is_active = 1
          AND r.status = 'WORKING'
          AND e.id NOT IN (SELECT employee_id FROM assignments WHERE brand_id = ?)
        ORDER BY CASE WHEN e.role = 'Pod Lead' THEN 0 ELSE 1 END, brand_load ASC
        LIMIT 3
    """
    backups = [dict(r) for r in cur.execute(query, (date_str, pod_id, brand_id))]
    conn.close()
    return backups


if __name__ == "__main__":
    # Quick CLI test for December 2026
    report = generate_monthly_roster(2026, 12)
    print(f"Generated Dec 2026 roster!")
    print(f"Hard Conflicts Found: {len(report['hard_conflicts'])}")
    print(f"Soft Warnings Found:  {len(report['soft_warnings'])}")
    if report["hard_conflicts"]:
        sample = report["hard_conflicts"][0]
        print("\nSample Conflict:", sample)
        print("Suggested Backups:", suggest_backups(sample["date"], sample["brand_id"]))