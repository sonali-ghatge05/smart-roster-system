import os
from database import DB_PATH, get_connection, init_db

def seed_data():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()

    conn = get_connection()
    cur = conn.cursor()

    # 1. Pods
    pods = ["Pod Alpha (Beauty & Personal Care)", "Pod Beta (Apparel & Fashion)", 
            "Pod Gamma (Health & Wellness)", "Pod Delta (Home & Electronics)"]
    cur.executemany("INSERT INTO pods (name) VALUES (?)", [(p,) for p in pods])

    # 2. Processes
    processes = [
        ("CS", "Customer Support"),
        ("ACC", "Abandoned Cart Conversions"),
        ("NDR", "Non-Delivery Report Management"),
        ("RET", "Customer Retention")
    ]
    cur.executemany("INSERT INTO processes (code, name) VALUES (?, ?)", processes)
    proc_map = {row["code"]: row["id"] for row in cur.execute("SELECT id, code FROM processes")}

    # 3. Employees (32 total: 4 Pod Leads + 28 Specialists)
    # preferred_weekly_off: 0=Mon ... 6=Sun
    employees_data = [
        # Pod 1 (8 people)
        ("Aarav Mehta", "Pod Lead", 1, 6),
        ("Priya Sharma", "Specialist", 1, 6),
        ("Rohan Verma", "Specialist", 1, 0),
        ("Sneha Iyer", "Specialist", 1, 1),
        ("Kabir Nair", "Specialist", 1, 2),
        ("Ananya Joshi", "Specialist", 1, 6),
        ("Vikram Patel", "Specialist", 1, 3),
        ("Meera Kulkarni", "Specialist", 1, 6),
        # Pod 2 (8 people)
        ("Neha Deshmukh", "Pod Lead", 2, 6),
        ("Arjun Rao", "Specialist", 2, 6),
        ("Divya Menon", "Specialist", 2, 4),
        ("Siddharth Gupta", "Specialist", 2, 6),
        ("Pooja Reddy", "Specialist", 2, 0),
        ("Karan Malhotra", "Specialist", 2, 2),
        ("Ishita Banerjee", "Specialist", 2, 6),
        ("Rahul Tiwari", "Specialist", 2, 1),
        # Pod 3 (8 people)
        ("Ritu Chawla", "Pod Lead", 3, 6),
        ("Aditya Singh", "Specialist", 3, 6),
        ("Nisha Kapoor", "Specialist", 3, 3),
        ("Varun Shetty", "Specialist", 3, 6),
        ("Tanvi Agarwal", "Specialist", 3, 5),
        ("Manish Jain", "Specialist", 3, 6),
        ("Shreya Bose", "Specialist", 3, 0),
        ("Deepak Pillai", "Specialist", 3, 4),
        # Pod 4 (8 people)
        ("Sandeep Khanna", "Pod Lead", 4, 6),
        ("Kavita Mishra", "Specialist", 4, 6),
        ("Nikhil Sawant", "Specialist", 4, 1),
        ("Swati Dubey", "Specialist", 4, 6),
        ("Gaurav Saxena", "Specialist", 4, 2),
        ("Roshni Thakur", "Specialist", 4, 6),
        ("Harshvardhan Rao", "Specialist", 4, 3),
        ("Simran Kaur", "Specialist", 4, 5),
    ]
    cur.executemany(
        "INSERT INTO employees (name, role, pod_id, preferred_weekly_off) VALUES (?, ?, ?, ?)",
        employees_data
    )

    # 4. Brands (20 total: 16 Single-Resource [80%], 4 Multi-Resource [20%])
    brands_data = [
        # Pod 1: 4 Single + 1 Multi (GlowCraft)
        ("AuraSkin", 1), ("Botaniq", 1), ("LumaCare", 1), ("VelvetRoots", 1), ("GlowCraft", 1),
        # Pod 2: 4 Single + 1 Multi (UrbanThread)
        ("Loom & Co", 2), ("Draped", 2), ("SoleVibe", 2), ("KnitHouse", 2), ("UrbanThread", 2),
        # Pod 3: 4 Single + 1 Multi (VitaPulse)
        ("PureFuel", 3), ("ZenGummies", 3), ("HerbaLifeX", 3), ("NutriCore", 3), ("VitaPulse", 3),
        # Pod 4: 4 Single + 1 Multi (VoltNest)
        ("CasaMinimal", 4), ("BrewCraft", 4), ("LumenHome", 4), ("DeskPro", 4), ("VoltNest", 4),
    ]
    cur.executemany("INSERT INTO brands (name, pod_id) VALUES (?, ?)", brands_data)
    brand_map = {row["name"]: row["id"] for row in cur.execute("SELECT id, name FROM brands")}

    # 5. Brand-Process Operating Rules & Assignments
    rules = []
    assignments = []

    # 16 Single-Resource Brands (1 dedicated specialist handles CS + NDR or CS + ACC)
    single_brands = [
        ("AuraSkin", 2, [("CS", "365_DAYS", 1), ("NDR", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("Botaniq", 3, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("ACC", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("LumaCare", 4, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("RET", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("VelvetRoots", 5, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("ACC", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),

        ("Loom & Co", 10, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("NDR", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("Draped", 11, [("CS", "365_DAYS", 1), ("ACC", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("SoleVibe", 12, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("NDR", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("KnitHouse", 13, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("RET", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),

        ("PureFuel", 18, [("CS", "365_DAYS", 1), ("NDR", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("ZenGummies", 19, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("ACC", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("HerbaLifeX", 20, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("RET", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("NutriCore", 21, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("NDR", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),

        ("CasaMinimal", 26, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("ACC", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("BrewCraft", 27, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("NDR", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("LumenHome", 28, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("NDR", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
        ("DeskPro", 29, [("CS", "NO_SUNDAYS_OR_HOLIDAYS", 1), ("RET", "NO_SUNDAYS_OR_HOLIDAYS", 1)]),
    ]
    
    for b_name, emp_id, proc_configs in single_brands:
        b_id = brand_map[b_name]
        for p_code, cal_type, min_s in proc_configs:
            p_id = proc_map[p_code]
            rules.append((b_id, p_id, cal_type, min_s))
            assignments.append((emp_id, b_id, p_id))

    # 4 Multi-Resource Brands (Split processes + Overlapping processes)
    # GlowCraft (Pod 1): Emp 6 & 7 overlap on CS (min 1/day, 365 days); Emp 8 handles ACC & NDR
    b_id = brand_map["GlowCraft"]
    rules += [(b_id, proc_map["CS"], "365_DAYS", 1), (b_id, proc_map["ACC"], "DAILY_EXCEPT_HOLIDAYS", 1), (b_id, proc_map["NDR"], "NO_SUNDAYS_OR_HOLIDAYS", 1)]
    assignments += [(6, b_id, proc_map["CS"]), (7, b_id, proc_map["CS"]), (8, b_id, proc_map["ACC"]), (8, b_id, proc_map["NDR"])]

    # UrbanThread (Pod 2): Emp 14 & 15 overlap on CS (min 2 on peak or 1 baseline -> set min 1, 365 days); Emp 16 handles NDR
    b_id = brand_map["UrbanThread"]
    rules += [(b_id, proc_map["CS"], "365_DAYS", 1), (b_id, proc_map["NDR"], "DAILY_EXCEPT_HOLIDAYS", 1)]
    assignments += [(14, b_id, proc_map["CS"]), (15, b_id, proc_map["CS"]), (16, b_id, proc_map["NDR"])]

    # VitaPulse (Pod 3): Emp 22 (CS), Emp 23 (ACC), Emp 24 (NDR + CS backup overlap)
    b_id = brand_map["VitaPulse"]
    rules += [(b_id, proc_map["CS"], "365_DAYS", 1), (b_id, proc_map["ACC"], "DAILY_EXCEPT_HOLIDAYS", 1), (b_id, proc_map["NDR"], "NO_SUNDAYS_OR_HOLIDAYS", 1)]
    assignments += [(22, b_id, proc_map["CS"]), (24, b_id, proc_map["CS"]), (23, b_id, proc_map["ACC"]), (24, b_id, proc_map["NDR"])]

    # VoltNest (Pod 4): Emp 30, 31, 32 all overlap on CS (min_staff=2, 365 days) + Emp 32 handles RET
    b_id = brand_map["VoltNest"]
    rules += [(b_id, proc_map["CS"], "365_DAYS", 2), (b_id, proc_map["RET"], "NO_SUNDAYS_OR_HOLIDAYS", 1)]
    assignments += [(30, b_id, proc_map["CS"]), (31, b_id, proc_map["CS"]), (32, b_id, proc_map["CS"]), (32, b_id, proc_map["RET"])]

    # Multi-brand assignments (1 employee working across 2 brands)
    rules.append((brand_map["Botaniq"], proc_map["RET"], "NO_SUNDAYS_OR_HOLIDAYS", 1))
    assignments.append((2, brand_map["Botaniq"], proc_map["RET"]))   # Priya Sharma -> AuraSkin + Botaniq
    rules.append((brand_map["SoleVibe"], proc_map["ACC"], "DAILY_EXCEPT_HOLIDAYS", 1))
    assignments.append((10, brand_map["SoleVibe"], proc_map["ACC"])) # Arjun Rao -> Loom & Co + SoleVibe

    cur.executemany(
        "INSERT INTO brand_process_rules (brand_id, process_id, calendar_type, min_staff) VALUES (?, ?, ?, ?)",
        rules
    )
    cur.executemany(
        "INSERT INTO assignments (employee_id, brand_id, process_id) VALUES (?, ?, ?)",
        assignments
    )

    # 6. Public Holidays (Sample for Dec 2026)
    holidays = [
        ("2026-12-25", "Christmas Day"),
    ]
    cur.executemany("INSERT INTO public_holidays (date, name) VALUES (?, ?)", holidays)

    # 7. Sample Planned Leaves & Comp-Offs (Dec 2026)
    leaves = [
        (2, "2026-12-10", "PLANNED_LEAVE", "APPROVED"),  # Priya (AuraSkin single-resource -> will trigger conflict!)
        (2, "2026-12-11", "PLANNED_LEAVE", "APPROVED"),
        (6, "2026-12-15", "COMP_OFF", "APPROVED"),       # Ananya (GlowCraft multi-resource -> Emp 7 covers!)
        (30, "2026-12-18", "PLANNED_LEAVE", "APPROVED"), # Roshni (VoltNest min_staff=2 -> Emp 31 & 32 cover!)
    ]
    cur.executemany(
        "INSERT INTO leaves (employee_id, date, leave_type, status) VALUES (?, ?, ?, ?)",
        leaves
    )

    conn.commit()
    conn.close()
    print("Seeded 4 pods, 32 employees, 20 brands, operating rules, holidays, and leaves.")

if __name__ == "__main__":
    seed_data()