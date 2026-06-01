import streamlit as st
import pandas as pd
import pdfplumber
import re
from fpdf import FPDF

st.set_page_config(
    page_title="SUPs Job Made Easy",
    page_icon="✈️",
    layout="wide"
)

st.markdown(
    """
    <div style="text-align:center; padding: 20px;">
        <h1>✈️ SUPs Job Made Easy</h1>
        <p style="font-size:18px;">Smart tools for airport supervisors</p>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------------------
# MAIN FEATURE CARDS
# ---------------------------
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        """
        <div style="padding:20px; border-radius:15px; border:1px solid #ddd; background-color:#f8f9fa;">
            <h3>🧾 Duty Sheet Extractor</h3>
            <p>Extract CX staffing, check SLA, and generate reports.</p>
            <b>Status: Available ✅</b>
        </div>
        """,
        unsafe_allow_html=True
    )

with col2:
    st.markdown(
        """
        <div style="padding:20px; border-radius:15px; border:1px solid #ddd; background-color:#f8f9fa;">
            <h3>✈️ Flight Briefing Sheet</h3>
            <p>Prepare flight briefing data automatically.</p>
            <b>Status: Coming Soon ⏳</b>
        </div>
        """,
        unsafe_allow_html=True
    )

with col3:
    st.markdown(
        """
        <div style="padding:20px; border-radius:15px; border:1px solid #ddd; background-color:#f8f9fa;">
            <h3>👥 Staff Allocator</h3>
            <p>Allocate staff automatically based on flights and shifts.</p>
            <b>Status: Coming Soon ⏳</b>
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()

st.header("🧾 Duty Sheet Extractor")

TARGET_ROLES = [
    "CSA CX",
    "CSA CX LATE",
    "CX Supervisor",
    "CX Superviosr Late",
    "CX Supervisor Late",
    "CX Flight Control",
    "CX Flight Control Late"
]

SLA_REQUIREMENTS = {
    "Early Supervisor": 1,
    "Early Flight Controller": 1,
    "Early CSA": 7,
    "Late Supervisor": 3,
    "Late Flight Controller": 2,
    "Late CSA": 14
}

DISPLAY_COLUMNS = {
    "Early Supervisor": "Early Sup",
    "Early Flight Controller": "Early FC",
    "Early CSA": "Early CSA",
    "Late Supervisor": "Late Sup",
    "Late Flight Controller": "Late FC",
    "Late CSA": "Late CSA"
}

def time_to_minutes(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m

def compact_to_time(raw):
    return f"{raw[:2]}:{raw[2:]}"

def extract_time_from_shift_text(text):
    match = re.search(r"(\d{4})-(\d{4})", text)
    if match:
        return compact_to_time(match.group(1)), compact_to_time(match.group(2))
    return None, None

def extract_required_staff_from_pdf(pdf_file):
    rows = []
    current_role = None
    current_date = "Unknown Date"

    date_pattern = re.compile(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{2}/\d{2}/\d{4}"
    )

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")

            for line in lines:
                line = line.strip()

                if date_pattern.match(line):
                    current_date = line
                    current_role = None
                    continue

                if "Planned Cover" in line:
                    matched_role = None
                    for role in TARGET_ROLES:
                        if role.lower() in line.lower():
                            matched_role = role
                            break
                    current_role = matched_role
                    continue

                if current_role:
                    match = re.match(
                        r"^(.+?)\s+(\d{3,8})\s+(.+?)\s+(\d{2}:\d{2})\s+(\d{2}:\d{2})(.*)$",
                        line
                    )

                    if match:
                        staff_name = match.group(1).strip()
                        staff_id = match.group(2).strip()
                        shift_text = match.group(3).strip()
                        shift_start = match.group(4).strip()
                        shift_end = match.group(5).strip()
                        comments = match.group(6).strip()

                        if shift_start == "00:00" and shift_end == "00:00":
                            real_start, real_end = extract_time_from_shift_text(shift_text)
                            if real_start and real_end:
                                shift_start = real_start
                                shift_end = real_end

                        rows.append({
                            "Date": current_date,
                            "Role": current_role,
                            "Staff Name": staff_name,
                            "Staff ID": staff_id,
                            "Shift Text": shift_text,
                            "Shift Start": shift_start,
                            "Shift End": shift_end,
                            "Absence Start": "",
                            "Absence End": "",
                            "Absence Description": "",
                            "Comments": comments
                        })

    return pd.DataFrame(rows)

def categorise_staff(df):
    categories = {
        "Early Supervisor": [],
        "Early Flight Controller": [],
        "Early CSA": [],
        "Late Supervisor": [],
        "Late Flight Controller": [],
        "Late CSA": []
    }

    for _, row in df.iterrows():
        start = time_to_minutes(row["Shift Start"])
        role = row["Role"].lower()

        is_supervisor = "supervisor" in role or "superviosr" in role
        is_flight_control = "flight control" in role
        is_csa = "csa" in role

        if is_supervisor and row["Shift Start"] in ["04:15", "04:30"]:
            categories["Early Supervisor"].append(row)
        elif is_flight_control and time_to_minutes("04:15") <= start <= time_to_minutes("05:30"):
            categories["Early Flight Controller"].append(row)
        elif is_csa and time_to_minutes("04:15") <= start <= time_to_minutes("09:00"):
            categories["Early CSA"].append(row)
        elif is_supervisor and time_to_minutes("12:45") <= start <= time_to_minutes("14:30"):
            categories["Late Supervisor"].append(row)
        elif is_flight_control and time_to_minutes("12:45") <= start <= time_to_minutes("14:30"):
            categories["Late Flight Controller"].append(row)
        elif is_csa and time_to_minutes("12:45") <= start <= time_to_minutes("14:30"):
            categories["Late CSA"].append(row)

    return categories

def make_sla_table(grouped):
    sla_row = {}
    actual_row = {}

    for category, display_name in DISPLAY_COLUMNS.items():
        sla_row[display_name] = SLA_REQUIREMENTS[category]
        actual_row[display_name] = len(grouped[category])

    return pd.DataFrame([sla_row, actual_row], index=["SLA", "Actual"])

def colour_actual_row(dataframe):
    styles = pd.DataFrame("", index=dataframe.index, columns=dataframe.columns)

    for category, display_name in DISPLAY_COLUMNS.items():
        actual = dataframe.loc["Actual", display_name]
        sla = dataframe.loc["SLA", display_name]

        if actual == sla:
            colour = "background-color: #92d050; color: black; font-weight: bold"
        elif actual < sla:
            colour = "background-color: #ff0000; color: black; font-weight: bold"
        else:
            colour = "background-color: #ffff00; color: black; font-weight: bold"

        styles.loc["Actual", display_name] = colour

    return styles

def make_numbered_df(rows):
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df = df.reset_index(drop=True)
    df.insert(0, "No", range(1, len(df) + 1))

    return df[
        [
            "No",
            "Staff Name",
            "Staff ID",
            "Role",
            "Shift Text",
            "Shift Start",
            "Shift End",
            "Absence Start",
            "Absence End",
            "Absence Description",
            "Comments"
        ]
    ]

def draw_pdf_sla_table(pdf, grouped):
    sla_table = make_sla_table(grouped)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, "SLA Summary", ln=True)

    row_label_width = 25
    col_width = 28

    pdf.set_font("Arial", "B", 8)

    pdf.cell(row_label_width, 7, "", border=1, align="C")
    for col in sla_table.columns:
        pdf.cell(col_width, 7, col, border=1, align="C")
    pdf.ln()

    pdf.cell(row_label_width, 8, "SLA", border=1, align="C")
    pdf.set_font("Arial", "", 9)

    for col in sla_table.columns:
        pdf.set_fill_color(255, 255, 255)
        pdf.cell(col_width, 8, str(sla_table.loc["SLA", col]), border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Arial", "B", 9)
    pdf.cell(row_label_width, 8, "Actual", border=1, align="C")

    for category, display_name in DISPLAY_COLUMNS.items():
        actual = sla_table.loc["Actual", display_name]
        sla = sla_table.loc["SLA", display_name]

        if actual == sla:
            pdf.set_fill_color(146, 208, 80)
        elif actual < sla:
            pdf.set_fill_color(255, 0, 0)
        else:
            pdf.set_fill_color(255, 255, 0)

        pdf.cell(col_width, 8, str(actual), border=1, align="C", fill=True)

    pdf.ln(10)

def create_pdf(date_grouped_data):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)

    for date, grouped in date_grouped_data.items():
        pdf.add_page()

        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "CX Staff Duty Report", ln=True, align="C")

        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, f"Date: {date}", ln=True)

        draw_pdf_sla_table(pdf, grouped)

        sections = [
            "Early Supervisor",
            "Early Flight Controller",
            "Early CSA",
            "Late Supervisor",
            "Late Flight Controller",
            "Late CSA"
        ]

        for section in sections:
            pdf.ln(4)
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 7, section, ln=True)

            df = make_numbered_df(grouped[section])

            if df.empty:
                pdf.set_font("Arial", "", 9)
                pdf.cell(0, 6, "No staff found", ln=True)
                continue

            headers = ["No", "Name", "ID", "Role", "Shift", "Start", "End", "Abs Start", "Abs End", "Abs Desc", "Comments"]
            widths = [10, 42, 16, 35, 42, 16, 16, 20, 20, 35, 45]

            pdf.set_font("Arial", "B", 7)
            for h, w in zip(headers, widths):
                pdf.cell(w, 7, h, border=1)
            pdf.ln()

            pdf.set_font("Arial", "", 6.5)
            for _, row in df.iterrows():
                values = [
                    str(row["No"]),
                    str(row["Staff Name"])[:26],
                    str(row["Staff ID"]),
                    str(row["Role"])[:22],
                    str(row["Shift Text"])[:28],
                    str(row["Shift Start"]),
                    str(row["Shift End"]),
                    str(row["Absence Start"]),
                    str(row["Absence End"]),
                    str(row["Absence Description"])[:22],
                    str(row["Comments"])[:35]
                ]

                for value, w in zip(values, widths):
                    pdf.cell(w, 6, value, border=1)
                pdf.ln()

    pdf_path = "cx_staff_date_wise_report.pdf"
    pdf.output(pdf_path)
    return pdf_path

pdf_file = st.file_uploader("Upload Duty Report PDF", type="pdf")

if pdf_file:
    extracted_df = extract_required_staff_from_pdf(pdf_file)

    if extracted_df.empty:
        st.error("No matching CX staff found in this PDF.")
    else:
        st.success("PDF extracted successfully")

        all_dates = extracted_df["Date"].unique().tolist()

        selected_date = st.selectbox(
            "Select date to view",
            ["All Dates"] + all_dates
        )

        view_df = extracted_df if selected_date == "All Dates" else extracted_df[extracted_df["Date"] == selected_date]

        date_grouped_data = {}

        for date in view_df["Date"].unique():
            date_df = view_df[view_df["Date"] == date]
            date_grouped_data[date] = categorise_staff(date_df)

        for date, grouped in date_grouped_data.items():
            st.header(f"📅 {date}")

            st.subheader("📊 SLA Summary")

            sla_table = make_sla_table(grouped)

            styled_sla_table = sla_table.style.apply(
                colour_actual_row,
                axis=None
            )

            st.dataframe(styled_sla_table)

            st.subheader("🌅 Early Shift")

            for section in ["Early Supervisor", "Early Flight Controller", "Early CSA"]:
                st.markdown(f"### {section}")
                df_section = make_numbered_df(grouped[section])

                if df_section.empty:
                    st.info("No staff found")
                else:
                    st.dataframe(df_section, hide_index=True)

            st.subheader("🌙 Late Shift")

            for section in ["Late Supervisor", "Late Flight Controller", "Late CSA"]:
                st.markdown(f"### {section}")
                df_section = make_numbered_df(grouped[section])

                if df_section.empty:
                    st.info("No staff found")
                else:
                    st.dataframe(df_section, hide_index=True)

        pdf_path = create_pdf(date_grouped_data)

        with open(pdf_path, "rb") as f:
            st.download_button(
                label="📄 Download Professional PDF Report",
                data=f,
                file_name="cx_staff_date_wise_report.pdf",
                mime="application/pdf"
            )
