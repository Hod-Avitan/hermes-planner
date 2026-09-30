import streamlit as st
import pandas as pd
import plotly.express as px
from Planner.scheduler import generate_schedule, build_timeline, REJECTED_TASKS

st.title("Hermes Planner")

employees_file = st.file_uploader(
    "Employees",
    type=["xlsx"]
)

clients_file = st.file_uploader(
    "Clients",
    type=["xlsx"]
)

tasks_file = st.file_uploader(
    "Tasks",
    type=["xlsx"]
)

#if st.button("Generate Plan"):
#    st.success("Files loaded")
if st.button("Generate Plan"):

    if employees_file is None or clients_file is None or tasks_file is None:
        st.error("Please upload Employees, Clients, and Tasks files before generating plan.")
        st.stop()

    employees = pd.read_excel(employees_file)
    clients = pd.read_excel(clients_file)
    tasks = pd.read_excel(tasks_file)

    st.subheader("Employees")
    st.write(f"Rows: {len(employees)}")
    st.dataframe(employees)

    st.subheader("Clients")
    st.write(f"Rows: {len(clients)}")
    st.dataframe(clients)

    st.subheader("Tasks")
    st.write(f"Rows: {len(tasks)}")
    st.dataframe(tasks)

    # Generate planning outputs
    schedule = generate_schedule(tasks)
    timeline = build_timeline(schedule)

    st.subheader("Schedule")
    st.dataframe(schedule)

    st.subheader("Timeline")
    st.dataframe(timeline)

    # Rejected tasks
    st.subheader("Rejected Tasks")

    if REJECTED_TASKS and len(REJECTED_TASKS) > 0:
        rejected_df = pd.DataFrame(REJECTED_TASKS)
        st.dataframe(rejected_df)
    else:
        st.write("No rejected tasks 🎉")

    # Build Gantt chart
    timeline_df = pd.DataFrame(timeline)

    # single source of truth: lead_owner already exists in schedule/timeline
    merged = timeline_df.copy()

    if "lead_owner" not in merged.columns:
        merged["lead_owner"] = "Unassigned"

    merged = merged.sort_values(["lead_owner", "start_dt"])

    fig = px.timeline(
        merged,
        x_start="start_dt",
        x_end="end_dt",
        y="task_id",
        color="lead_owner",
        text="phase"
    )

    fig.update_yaxes(autorange="reversed")

    st.subheader("Gantt Chart")
    st.plotly_chart(fig, width="stretch")