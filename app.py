import os
from database import get_connection, init_db
init_db()
from seed import seed_data
if not os.path.exists("roster.db"):
    seed_data()

import calendar
import pandas as pd
import streamlit as st
from database import get_connection
from scheduler import generate_monthly_roster, validate_roster, suggest_backups

st.set_page_config(page_title="Smart Roster Management System", layout="wide")
st.title("Smart Roster Management System")
st.caption("Operations scheduling tool for 32 employees across 4 pods and 20 D2C brands (80% single-resource, 20% multi-resource).")
if "flash_msg" in st.session_state:
    st.success(st.session_state.pop("flash_msg"))


with st.expander("How to use this app (Quick Guide)"):
    st.markdown("""
    1. **Generate Roster:** Pick a month in the left sidebar and click **Generate Monthly Roster**.
    2. **Inspect Schedules:** Use **Tab 2** to switch between Company, Pod, Brand, Process, and Employee views.
    3. **Resolve Conflicts:** Open **Tab 1** to see coverage gaps (Hard Conflicts) vs. preference overrides (Soft Warnings) and suggested backups.
    4. **Test Live Changes:** Use **Tab 3** to put any employee on leave and watch the conflict counter update automatically.
    """)

# --- Sidebar Controls ---
st.sidebar.header("Roster Controls")
year = st.sidebar.number_input("Year", min_value=2025, max_value=2030, value=2026)
month = st.sidebar.selectbox(
    "Month",
    options=list(range(1, 13)),
    index=11,  # Default: December
    format_func=lambda m: calendar.month_name[m]
)

if st.sidebar.button("Generate / Regenerate Monthly Roster", type="primary", use_container_width=True):
    generate_monthly_roster(year, month)
    st.sidebar.success(f"Generated roster for {calendar.month_name[month]} {year}!")

# Always validate current DB state for the selected month
report = validate_roster(year, month)
hard_conflicts = report["hard_conflicts"]
soft_warnings = report["soft_warnings"]

# --- Top Metrics ---
c1, c2, c3 = st.columns(3)
c1.metric(
    "Hard Conflicts (Coverage Gaps)", 
    len(hard_conflicts),
    help="Days where a brand/process is below minimum required staff (e.g., a single-resource 365-day brand when its only employee takes a weekly off or leave)."
)
c2.metric(
    "Soft Warnings (Preference Overrides)", 
    len(soft_warnings),
    help="Days where an employee's preferred weekly off was moved to protect client coverage."
)
c3.metric(
    "Roster Status", 
    "Action Required" if hard_conflicts else "Ready to Publish",
    help="Ready to Publish only when all Hard Conflicts are resolved."
)

# --- Helper to Load Roster Data ---
def load_roster_df(y, m):
    conn = get_connection()
    start_str = f"{y}-{m:02d}-01"
    end_str = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
    query = """
        SELECT r.date, e.id AS emp_id, e.name AS employee, e.role, p.name AS pod, r.status, r.is_manual_override
        FROM roster_entries r
        JOIN employees e ON r.employee_id = e.id
        JOIN pods p ON e.pod_id = p.id
        WHERE r.date BETWEEN ? AND ?
        ORDER BY p.id, e.id, r.date
    """
    df = pd.read_sql_query(query, conn, params=(start_str, end_str))
    conn.close()
    return df

roster_df = load_roster_df(year, month)

# --- Main Tabs ---
tab1, tab2, tab3, tab4 = st.tabs([
    "1. Conflict Center & Backups",
    "2. Roster Views (5 Perspectives)",
    "3. Edit Roster & Simulate Change",
    "4. Manage Assignments & Leaves"
])

# ==========================================
# TAB 1: CONFLICT CENTER & BACKUPS
# ==========================================
with tab1:
    st.subheader("Hard Constraints: Coverage Gaps")
    if not hard_conflicts:
        st.success("No hard conflicts detected for this month!")
    else:
        hc_df = pd.DataFrame(hard_conflicts)

        # Quick Filters
        f1, f2 = st.columns(2)
        pod_filter = f1.selectbox("Filter by Pod", ["All Pods"] + sorted(hc_df["pod"].unique().tolist()))
        cause_filter = f2.selectbox("Filter by Cause", ["All Causes", "Leaves / Comp-Offs Only", "Weekly Offs Only"])

        filtered_df = hc_df.copy()
        if pod_filter != "All Pods":
            filtered_df = filtered_df[filtered_df["pod"] == pod_filter]
        if cause_filter == "Leaves / Comp-Offs Only":
            filtered_df = filtered_df[filtered_df["reason"].str.contains("PLANNED_LEAVE|COMP_OFF", regex=True)]
        elif cause_filter == "Weekly Offs Only":
            filtered_df = filtered_df[filtered_df["reason"].str.contains("WEEKLY_OFF")]

        st.dataframe(
            filtered_df[["date", "pod", "severity", "brand", "process", "required", "actual", "single_resource", "reason"]],
            use_container_width=True
        )

        st.markdown("### Resolve a Gap: One-Click Backup Assignment")
        if not filtered_df.empty:
            filtered_list = filtered_df.to_dict("records")
            conflict_idx = st.selectbox(
                "Select a conflict to resolve:",
                options=range(len(filtered_list)),
                format_func=lambda i: f"{filtered_list[i]['date']} | {filtered_list[i]['brand']} ({filtered_list[i]['process']}) - {filtered_list[i]['reason']}"
            )
            selected = filtered_list[conflict_idx]
            backups = suggest_backups(selected["date"], selected["brand_id"])

            if backups:
                st.dataframe(pd.DataFrame(backups), use_container_width=True)
                backup_map = {f"{b['name']} ({b['role']} | {b['brand_load']} brands)": b["id"] for b in backups}
                chosen_label = st.selectbox("Choose backup employee to assign:", list(backup_map.keys()))

                if st.button("Assign Selected Backup & Resolve Conflict", type="primary"):
                    conn = get_connection()
                    conn.execute(
                        """INSERT OR IGNORE INTO temporary_covers (date, brand_id, process_id, backup_employee_id)
                           VALUES (?, ?, ?, ?)""",
                        (selected["date"], selected["brand_id"], selected["process_id"], backup_map[chosen_label])
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Assigned {chosen_label} to cover {selected['brand']} ({selected['process']}) on {selected['date']}!")
                    st.rerun()
            else:
                st.warning("No available backups found in this pod on that date.")

    st.divider()
    st.subheader("Soft Constraints: Preference Warnings")
    if not soft_warnings:
        st.info("No preference warnings.")
    else:
        st.dataframe(pd.DataFrame(soft_warnings), use_container_width=True)


# ==========================================
# TAB 2: 5 STAKEHOLDER VIEWS
# ==========================================
with tab2:
    if roster_df.empty:
        st.warning("No roster generated for this month yet. Click 'Generate Monthly Roster' in the sidebar.")
    else:
        view_type = st.radio(
            "Select View:",
            ["Company-Wide", "Pod-Wise", "Brand-Wise", "Process-Wise", "Employee-Wise"],
            horizontal=True
        )

        # Short codes for compact matrix display
        code_map = {
            "WORKING": "W", "WEEKLY_OFF": "WO", "PUBLIC_HOLIDAY": "PH",
            "PLANNED_LEAVE": "PL", "COMP_OFF": "CO"
        }
        roster_df["code"] = roster_df["status"].map(code_map)
        roster_df["day"] = pd.to_datetime(roster_df["date"]).dt.strftime("%d (%a)")

        conn = get_connection()

        st.markdown("**Legend:** 🟩 `W` = Working | ⬜ `WO` = Weekly Off | 🟦 `PH` = Public Holiday | 🟥 `PL` = Planned Leave | 🟨 `CO` = Comp-Off")

        def color_cells(val):
            colors = {
                "W": "background-color: #d4edda; color: #155724;",
                "WO": "background-color: #e2e3e5; color: #383d41;",
                "PH": "background-color: #cce5ff; color: #004085;",
                "PL": "background-color: #f8d7da; color: #721c24;",
                "CO": "background-color: #fff3cd; color: #856404;",
            }
            return colors.get(val, "")

        if view_type == "Company-Wide":
            pivot = roster_df.pivot(index=["pod", "employee", "role"], columns="day", values="code")
            st.dataframe(pivot.style.map(color_cells), use_container_width=True)

        elif view_type == "Pod-Wise":
            pod_choice = st.selectbox("Select Pod:", roster_df["pod"].unique())
            sub = roster_df[roster_df["pod"] == pod_choice]
            pivot = sub.pivot(index=["employee", "role"], columns="day", values="code")
            st.dataframe(pivot.style.map(color_cells), use_container_width=True)

        elif view_type == "Brand-Wise":
            brands = pd.read_sql_query("SELECT id, name FROM brands ORDER BY name", conn)
            brand_choice = st.selectbox("Select Brand:", brands["name"])
            b_id = int(brands[brands["name"] == brand_choice]["id"].iloc[0])
            emp_ids = [r[0] for r in conn.execute("SELECT DISTINCT employee_id FROM assignments WHERE brand_id = ?", (b_id,))]
            b_rules = pd.read_sql_query("""
                SELECT p.code, r.calendar_type, r.min_staff
                FROM brand_process_rules r
                JOIN processes p ON r.process_id = p.id
                WHERE r.brand_id = ?
            """, conn, params=(b_id,))
            rule_text = " | ".join(
                f"**{row['code']}**: `{row['calendar_type']}` (Min Staff: {row['min_staff']})"
                for _, row in b_rules.iterrows()
            )
            st.info(f"**Operating Rules for {brand_choice}:** {rule_text}")
            sub = roster_df[roster_df["emp_id"].isin(emp_ids)]
            if sub.empty:
                st.info("No employees assigned to this brand.")
            else:
                pivot = sub.pivot(index=["employee", "role"], columns="day", values="code")
                st.dataframe(pivot.style.map(color_cells), use_container_width=True)

        elif view_type == "Process-Wise":
            procs = pd.read_sql_query("SELECT id, code, name FROM processes", conn)
            proc_choice = st.selectbox("Select Process:", procs["code"])
            p_id = int(procs[procs["code"] == proc_choice]["id"].iloc[0])
            emp_ids = [r[0] for r in conn.execute("SELECT DISTINCT employee_id FROM assignments WHERE process_id = ?", (p_id,))]
            sub = roster_df[roster_df["emp_id"].isin(emp_ids)]
            pivot = sub.pivot(index=["pod", "employee"], columns="day", values="code")
            st.dataframe(pivot.style.map(color_cells), use_container_width=True)

        elif view_type == "Employee-Wise":
            emp_choice = st.selectbox("Select Employee:", roster_df["employee"].unique())
            sub = roster_df[roster_df["employee"] == emp_choice][["date", "status", "is_manual_override"]]

            # 1. Quick Monthly Summary
            m1, m2, m3 = st.columns(3)
            m1.metric("Working Days", int((sub["status"] == "WORKING").sum()))
            m2.metric("Weekly Offs / Holidays", int(sub["status"].isin(["WEEKLY_OFF", "PUBLIC_HOLIDAY"]).sum()))
            m3.metric("Leaves / Comp-Offs", int(sub["status"].isin(["PLANNED_LEAVE", "COMP_OFF"]).sum()))

            # 2. Instant Single-Date Check
            check_date = st.selectbox("Check status on a specific date:", sub["date"].tolist())
            day_status = sub[sub["date"] == check_date]["status"].iloc[0]
            if day_status == "WORKING":
                st.success(f"**{emp_choice}** is **WORKING** on {check_date}.")
            else:
                st.warning(f"**{emp_choice}** is **NOT WORKING** ({day_status}) on {check_date}.")

            # 3. Full Monthly Table
            st.dataframe(sub, use_container_width=True)

        conn.close()

        csv = roster_df.to_csv(index=False).encode("utf-8")
        st.download_button("Export Roster to CSV", csv, f"roster_{year}_{month:02d}.csv", "text/csv")

# ==========================================
# TAB 3: MANUAL EDIT & SIMULATE CHANGE
# ==========================================
with tab3:
    st.subheader("Modify Employee Availability & Re-Validate Live")
    if roster_df.empty:
        st.warning("Generate a roster first to test manual overrides.")
    else:
        col1, col2, col3 = st.columns(3)
        emp_map = dict(zip(roster_df["employee"], roster_df["emp_id"]))
        sel_emp = col1.selectbox("Employee", list(emp_map.keys()))
        sel_date = col2.selectbox("Date", sorted(roster_df["date"].unique()))
        new_status = col3.selectbox(
            "New Status",
            ["PLANNED_LEAVE", "COMP_OFF", "WEEKLY_OFF", "WORKING", "PUBLIC_HOLIDAY"]
        )

        if st.button("Apply Change & Validate Impact", type="primary"):
            conn = get_connection()
            conn.execute(
                "UPDATE roster_entries SET status = ?, is_manual_override = 1 WHERE employee_id = ? AND date = ?",
                (new_status, emp_map[sel_emp], sel_date)
            )
            conn.commit()
            conn.close()
            st.success(f"Updated {sel_emp} on {sel_date} to {new_status}. Re-validating...")
            st.rerun()

# ==========================================
# TAB 4: MANAGE ASSIGNMENTS (NO CODE CHANGES)
# ==========================================
with tab4:
    st.subheader("Add Employee-Brand-Process Assignment")
    conn = get_connection()
    emps = pd.read_sql_query("SELECT id, name FROM employees ORDER BY name", conn)
    brands = pd.read_sql_query("SELECT id, name FROM brands ORDER BY name", conn)
    procs = pd.read_sql_query("SELECT id, code FROM processes", conn)

    c1, c2, c3 = st.columns(3)
    a_emp = c1.selectbox("Employee", emps["name"], key="a_emp")
    a_brand = c2.selectbox("Brand", brands["name"], key="a_brand")
    a_proc = c3.selectbox("Process", procs["code"], key="a_proc")

    if st.button("Add Assignment"):
        e_id = int(emps[emps["name"] == a_emp]["id"].iloc[0])
        b_id = int(brands[brands["name"] == a_brand]["id"].iloc[0])
        p_id = int(procs[procs["code"] == a_proc]["id"].iloc[0])
        try:
            conn.execute(
                "INSERT INTO assignments (employee_id, brand_id, process_id) VALUES (?, ?, ?)",
                (e_id, b_id, p_id)
            )
            conn.commit()
            st.success(f"Assigned {a_emp} to {a_brand} ({a_proc})!")
        except Exception as e:
            st.error(f"Could not add assignment (may already exist): {e}")

        st.divider()
    st.subheader("Log Planned Leave or Comp-Off")
    l1, l2, l3 = st.columns(3)
    l_emp = l1.selectbox("Employee", emps["name"], key="l_emp")
    l_date = l2.date_input("Leave Date", value=pd.to_datetime(f"{year}-{month:02d}-10"))
    l_type = l3.selectbox("Leave Type", ["PLANNED_LEAVE", "COMP_OFF"], key="l_type")

    st.markdown("#### Remove an Assignment")
    rem_df = pd.read_sql_query("""
        SELECT a.id, e.name AS employee, b.name AS brand, p.code AS process
        FROM assignments a
        JOIN employees e ON a.employee_id = e.id
        JOIN brands b ON a.brand_id = b.id
        JOIN processes p ON a.process_id = p.id
        ORDER BY b.name, e.name
    """, conn)
    if not rem_df.empty:
        rem_map = {
            f"{r['brand']} ({r['process']}) — {r['employee']}": int(r["id"])
            for _, r in rem_df.iterrows()
        }
        sel_rem = st.selectbox("Select assignment to remove:", list(rem_map.keys()))
        if st.button("Remove Selected Assignment"):
            conn.execute("DELETE FROM assignments WHERE id = ?", (rem_map[sel_rem],))
            conn.commit()
            st.session_state["flash_msg"] = f"Removed assignment: {sel_rem}"
            st.rerun()

    if st.button("Approve Leave & Update Roster"):
        e_id = int(emps[emps["name"] == l_emp]["id"].iloc[0])
        d_str = l_date.isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO leaves (employee_id, date, leave_type, status) VALUES (?, ?, ?, 'APPROVED')",
            (e_id, d_str, l_type)
        )
        conn.execute(
            "UPDATE roster_entries SET status = ?, is_manual_override = 1 WHERE employee_id = ? AND date = ?",
            (l_type, e_id, d_str)
        )
        conn.commit()
        st.session_state["flash_msg"] = f"Logged {l_type} for {l_emp} on {d_str} and re-validated roster!"
        st.rerun()

    st.markdown("### Current Assignments")
    assign_df = pd.read_sql_query("""
        SELECT e.name AS employee, b.name AS brand, p.code AS process, r.calendar_type, r.min_staff
        FROM assignments a
        JOIN employees e ON a.employee_id = e.id
        JOIN brands b ON a.brand_id = b.id
        JOIN processes p ON a.process_id = p.id
        LEFT JOIN brand_process_rules r ON a.brand_id = r.brand_id AND a.process_id = r.process_id
        ORDER BY b.name, p.code
    """, conn)
    st.divider()
    with st.expander("Configure Brand Operating Rules & Public Holidays"):
        st.markdown("#### Update Brand-Process Operating Rule")
        r1, r2, r3, r4 = st.columns(4)
        rb_brand = r1.selectbox("Brand", brands["name"], key="rb_brand")
        rb_proc = r2.selectbox("Process", procs["code"], key="rb_proc")
        rb_cal = r3.selectbox(
            "Operating Calendar",
            ["365_DAYS", "DAILY_EXCEPT_HOLIDAYS", "NO_SUNDAYS_OR_HOLIDAYS"],
            key="rb_cal"
        )
        rb_min = r4.number_input("Min Staff", min_value=1, max_value=5, value=1, key="rb_min")

        if st.button("Save Operating Rule"):
            b_id = int(brands[brands["name"] == rb_brand]["id"].iloc[0])
            p_id = int(procs[procs["code"] == rb_proc]["id"].iloc[0])
            conn.execute(
                """INSERT INTO brand_process_rules (brand_id, process_id, calendar_type, min_staff)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(brand_id, process_id) DO UPDATE SET
                   calendar_type = excluded.calendar_type, min_staff = excluded.min_staff""",
                (b_id, p_id, rb_cal, int(rb_min))
            )
            conn.commit()
            st.session_state["flash_msg"] = f"Updated rule for {rb_brand} ({rb_proc}): {rb_cal}, Min Staff={rb_min}"
            st.rerun()

        st.markdown("#### Add a Public Holiday")
        h1, h2 = st.columns(2)
        h_date = h1.date_input("Holiday Date", value=pd.to_datetime(f"{year}-{month:02d}-26"), key="h_date")
        h_name = h2.text_input("Holiday Name", value="Boxing Day / Company Holiday", key="h_name")
        if st.button("Add Public Holiday"):
            conn.execute(
                "INSERT OR REPLACE INTO public_holidays (date, name) VALUES (?, ?)",
                (h_date.isoformat(), h_name)
            )
            conn.commit()
            st.session_state["flash_msg"] = f"Added public holiday: {h_name} ({h_date.isoformat()}). Regenerate roster to apply."
            st.rerun()

    st.markdown("#### Cancel / Delete an Existing Leave")
    leaves_df = pd.read_sql_query("""
        SELECT l.id, e.id AS emp_id, e.name AS employee, l.date, l.leave_type
        FROM leaves l
        JOIN employees e ON l.employee_id = e.id
        ORDER BY l.date, e.name
    """, conn)

    if leaves_df.empty:
        st.info("No leaves currently logged.")
    else:
        leave_options = {
            f"{row['date']} | {row['employee']} ({row['leave_type']})": (int(row["id"]), int(row["emp_id"]), row["date"], row["employee"])
            for _, row in leaves_df.iterrows()
        }
        selected_leave = st.selectbox("Select a leave to cancel:", list(leave_options.keys()))

        if st.button("Cancel Selected Leave"):
            l_id, e_id, d_str, emp_name = leave_options[selected_leave]
            conn.execute("DELETE FROM leaves WHERE id = ?", (l_id,))
            conn.execute(
                "UPDATE roster_entries SET status = 'WORKING', is_manual_override = 1 WHERE employee_id = ? AND date = ?",
                (e_id, d_str)
            )
            conn.commit()
            st.session_state["flash_msg"] = f"Cancelled leave for {emp_name} on {d_str} and set status back to WORKING."
            st.rerun()

    st.dataframe(assign_df,width="stretch")
    conn.close()