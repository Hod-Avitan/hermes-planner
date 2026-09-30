# rules.py

WEEK_CAPACITY = {
    "Yael": 5,
    "Omer": 5,
    "Marc": 5
}

EMPLOYEE_FLOWS = {
    "Yael": ["A"],
    "Marc": ["A", "B"],
    "Omer": ["ALL"]
}

REJECTED_TASKS = []

# -----------------------------
# Normalization Layer
# -----------------------------
def normalize_task(task):
    return {
        "task_id": task.get("task_id") or task.get("request_id"),
        "flow": task.get("flow"),
        "phase": task.get("phase") or task.get("type") or task.get("task_type"),
        "size": float(task.get("size") or task.get("duration") or 1),
        "request_due": task.get("request_due") or task.get("due_date"),
        "priority": task.get("priority", 0),
        "complexity": task.get("complexity"),
        "est_days": task.get("est_days", 1),
    }

def _norm(task):
    return normalize_task(task)

# -----------------------------
# Role constraints
# -----------------------------
ROLE_CONSTRAINTS = {
    "Audit": {
        "forbidden_owners": ["Yael"]
    }
}

def is_valid_assignment(task, employee_name):
    t = normalize_task(task)

    # role constraint check (e.g. Audit cannot be assigned to Yael)
    phase = str(t.get("phase") or "").strip()
    constraints = ROLE_CONSTRAINTS.get(phase, {})
    forbidden = constraints.get("forbidden_owners", [])
    if employee_name in forbidden:
        return False

    # flow constraint check (A / B / ALL)
    task_flow = str(t.get("flow") or "").upper()
    allowed_flows = EMPLOYEE_FLOWS.get(employee_name, ["ALL"])

    if "ALL" in allowed_flows:
        return True

    # if task has no flow defined, allow assignment
    if not task_flow:
        return True

    return task_flow in allowed_flows

# -----------------------------
# Business rules
# -----------------------------
def is_vip(task):
    t = normalize_task(task)
    return "vip" in str(t.get("priority", "")).lower()

def is_escalation(task):
    t = normalize_task(task)
    return "escalation" in str(t.get("flow", "")).lower()

def is_new_client(task):
    t = normalize_task(task)
    return "new client" in str(t.get("priority", "")).lower()

# -----------------------------
# Scoring
# -----------------------------
def priority_score(task):
    t = normalize_task(task)
    score = 0

    priority = str(t.get("priority", "")).lower()

    if "vip" in priority:
        score += 30

    if "escalation" in str(t.get("flow", "")).lower():
        score += 30

    if "new client" in priority:
        score += 10

    return score