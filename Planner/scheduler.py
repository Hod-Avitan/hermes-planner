# scheduler.py


from Planner.rules import (
    is_vip,
    is_escalation,
    is_new_client,
    priority_score,
    normalize_task,
    is_valid_assignment
)



MAX_CAPACITY = 8

# Weekly capacity (days per week per employee)
WEEK_CAPACITY = {
    "Yael": 5,
    "Omer": 3,
    "Marc": 2
}

# Week calendar mapping (anchor for real timeline scheduling)
WEEK_MAP = {
    "18": ("2026-05-25", "2026-05-29")
}


# Rejected tasks tracking (optimizer output)
REJECTED_TASKS = []

def explain_rejection(task, task_size, max_week_capacity):
    return (
        f"Task exceeds weekly capacity constraint. "
        f"Estimated size={task_size}, max allowed={max_week_capacity}. "
        f"Cannot fit within single-week worker capacity."
    )


def expand_task(task):
    phases = []

    flow = task.get("flow")
    complexity = str(task.get("complexity", "")).lower()

    dev_days = float(task.get("est_days", 1))

    vip = is_vip(task)
    escalation = is_escalation(task)
    new_client = is_new_client(task)

    if flow == "A":
        if complexity == "simple 2d":
            asset_days = 0.5
        elif complexity == "medium 2d":
            asset_days = 1
        elif complexity in ["medium 3d", "complex 3d"]:
            asset_days = 2
        else:
            asset_days = 1

        review_days = 0.5

        qa_days = 1 if (complexity in ["medium 3d", "complex 3d"] or vip) else 0.5

        buffer_days = 0.5 if (vip or escalation or new_client) else 0

        phases.append({"task_id": task.get("task_id") or task.get("request_id"), "phase": "Asset", "duration": asset_days})
        phases.append({"task_id": task.get("task_id") or task.get("request_id"), "phase": "Dev", "duration": dev_days})
        phases.append({"task_id": task.get("task_id") or task.get("request_id"), "phase": "Review", "duration": review_days})
        phases.append({"task_id": task.get("task_id") or task.get("request_id"), "phase": "QA", "duration": qa_days})
        phases.append({"task_id": task.get("task_id") or task.get("request_id"), "phase": "Buffer", "duration": buffer_days})

    else:
        audit_days = dev_days
        qa_days = 1 if (complexity == "complex variation" or vip) else 0.5
        buffer_days = 0.5 if (vip or escalation or new_client) else 0

        phases.append({"task_id": task.get("task_id") or task.get("request_id"), "phase": "Audit", "duration": audit_days})
        phases.append({"task_id": task.get("task_id") or task.get("request_id"), "phase": "QA", "duration": qa_days})
        phases.append({"task_id": task.get("task_id") or task.get("request_id"), "phase": "Buffer", "duration": buffer_days})

    return phases


def generate_schedule(tasks_df):
    schedule = []
    global REJECTED_TASKS
    REJECTED_TASKS = []

    tasks_sorted = tasks_df.copy()
    tasks_sorted["__score"] = tasks_sorted.apply(priority_score, axis=1)
    tasks_sorted = tasks_sorted.sort_values("__score", ascending=False)

    max_week_capacity = max(WEEK_CAPACITY.values())

    # initialize employee load (unified capacity tracking)
    employee_load = {name: 0 for name in WEEK_CAPACITY.keys()}

    for _, task in tasks_sorted.iterrows():

        raw_task = task.to_dict()

        # unified data model normalization
        norm_task = normalize_task(raw_task)
        task = {**raw_task, **norm_task}

        phases = expand_task(task)
        task_size = sum(float(p["duration"]) for p in phases)

        # choose best employee by available capacity (greedy fit)
        best_employee = None
        best_score = -999

        for name in WEEK_CAPACITY.keys():
            used = employee_load.get(name, 0)
            limit = WEEK_CAPACITY[name]

            # capacity constraint
            if used + task_size > limit:
                continue

            # flow + role constraint (self-healing filter from rules layer)
            if not is_valid_assignment(task, name):
                continue

            score = limit - (used + task_size)
            if score > best_score:
                best_score = score
                best_employee = name

        if best_employee is None:
            REJECTED_TASKS.append(
                {
                    "task_id": task.get("task_id") or task.get("request_id"),
                    "reason": "no capacity across employees",
                    "size": task_size,
                    "max_capacity": max_week_capacity,
                    "explanation": explain_rejection(task, task_size, max_week_capacity),
                }
            )
            continue

        # allocate capacity
        employee_load[best_employee] += task_size

        # build unified schedule with owner
        for phase in phases:
            schedule.append(
                {
                    "task_id": phase["task_id"],
                    "phase": phase["phase"],
                    "duration": phase["duration"],
                    "deadline": task.get("request_due"),
                    "lead_owner": best_employee,
                }
            )

    return schedule


def employee_score(employee, task):
    score = 0

    specialties = [
        str(employee.get("specialty", "")).lower(),
        str(employee.get("specialty 2", "")).lower(),
        str(employee.get("specialty 3", "")).lower(),
    ]

    required = str(task.get("specialty_required", "")).lower()

    if required in specialties:
        score += 50

    score += priority_score(task)

    if "top performer" in specialties:
        score += 20

    seniority = str(employee.get("seniority", "")).lower()

    if seniority == "senior":
        score += 15
    elif seniority == "mid":
        score += 5

    return score


def assign_resources(task, employees_df, employee_load):
    flow = str(task["flow"]).upper()

    if flow == "A":
        candidates = employees_df[employees_df["role"].isin(["HTML5 Dev", "HTML5 Dev Team Lead"])]
    else:
        candidates = employees_df[employees_df["role"] == "Auditor"]

    # fallback: if no role-based candidates, use full pool
    if candidates is None or len(candidates) == 0:
        candidates = employees_df

    best_employee = None
    best_score = -999

    task_size = float(task.get("est_days", 1))

    # first pass: try only feasible employees
    feasible_found = False

    for _, employee in candidates.iterrows():
        name = employee["name"]

        used = employee_load.get(name, 0)
        limit = WEEK_CAPACITY.get(name, MAX_CAPACITY)

        # enforce strict cumulative capacity constraint
        if used + task_size <= limit:
            feasible_found = True
            score = employee_score(employee, task) - used * 2
            if score > best_score:
                best_score = score
                best_employee = employee

    # STRICT MODE: do NOT allow overflow assignment
    if best_employee is None:
        return {
            "task_id": task.get("task_id") or task.get("request_id"),
            "lead_owner": None,
            "support_owner": None,
            "reviewer": "Marc",
            "qa_owner": None,
            "status": "rejected_due_to_capacity"
        }

    lead_owner = best_employee["name"] if best_employee is not None else None

    if best_employee is not None:
        employee_load[lead_owner] = employee_load.get(lead_owner, 0) + task_size
    else:
        # do not update load for rejected assignments
        pass

    qa_candidates = employees_df[employees_df["role"] == "QA"]
    qa_owner = qa_candidates.iloc[0]["name"] if len(qa_candidates) > 0 else None
    # ensure QA fallback if empty pool edge case
    if qa_owner is None and len(employees_df) > 0:
        qa_owner = employees_df.iloc[0]["name"]

    reviewer = "Marc"

    return {
        "task_id": task.get("task_id") or task.get("request_id"),
        "lead_owner": lead_owner,
        "support_owner": None,
        "reviewer": reviewer,
        "qa_owner": qa_owner,
    }


def generate_assignments(tasks_df, employees_df):
    """
    Unified mode: assignments are derived from schedule.
    """
    schedule = generate_schedule(tasks_df)

    assignments_map = {}

    for item in schedule:
        task_id = item.get("task_id")
        if task_id not in assignments_map:
            assignments_map[task_id] = {
                "task_id": task_id,
                "lead_owner": item.get("lead_owner"),
                "qa_owner": "Marc",
                "reviewer": "Marc",
                "support_owner": None,
            }

    return list(assignments_map.values())


def build_timeline(schedule):
    from collections import defaultdict
    import pandas as pd

    tasks = defaultdict(list)

    # normalize schedule input (can be list[dict] or nested/invalid structures)
    if isinstance(schedule, tuple):
        # safety: if something still returns tuple, extract first element if list-like
        schedule = schedule[0] if len(schedule) > 0 else []

    for item in schedule:
        if isinstance(item, dict):
            task_id = item.get("task_id")
        elif isinstance(item, (list, tuple)) and len(item) > 0:
            # fallback: assume first element is task_id if structure is broken
            task_id = item[0]
            # try to coerce into dict-like minimal structure
            item = {"task_id": task_id}
        else:
            continue

        if task_id is None:
            continue

        tasks[task_id].append(item)

    timeline = []
    week_start_str, week_end_str = WEEK_MAP["18"]
    week_start = pd.to_datetime(week_start_str)

    for task_id, items in tasks.items():
        items = sorted(items, key=lambda x: x.get("phase", ""))

        deadline_raw = items[0].get("deadline")
        deadline = pd.to_datetime(deadline_raw) if deadline_raw else None

        temp = []
        current_end = week_start

        # build naive schedule first
        for item in items:
            duration = float(item["duration"])

            start = current_end
            end = start + pd.Timedelta(days=duration)

            temp.append({
                "task_id": task_id,
                "phase": item.get("phase"),
                "start_dt": start,
                "end_dt": end,
                "duration": duration,
                "lead_owner": item.get("lead_owner")
            })

            current_end = end

        # HARD deadline enforcement (shift entire task if needed)
        if deadline is not None:
            last_end = temp[-1]["end_dt"]
            if last_end > deadline:
                shift = last_end - deadline
                temp = [
                    {
                        **t,
                        "start_dt": t["start_dt"] - shift,
                        "end_dt": t["end_dt"] - shift,
                    }
                    for t in temp
                ]

        timeline.extend(temp)

    return timeline