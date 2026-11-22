# PhishCoach AI — User Manual

Welcome to **PhishCoach AI**, an interactive security-awareness platform that generates role-aware phishing simulations, delivers instant personalized coaching, and provides privacy-preserving risk analytics.

---

## 1. Roles & Demo Accounts

PhishCoach AI supports three distinct roles:

| Role | Purpose | Demo Email | Password |
|---|---|---|---|
| **Security Admin** | Create/approve/deploy campaigns, monitor live risk, manage remediation & config | `ravi.admin@example.com` | `DemoPass123!` |
| **Employee (Treatment Arm)** | Receive simulated emails, receive AI coaching, practice in Attacker Chat, track progress | `asha.treatment@example.com` | `DemoPass123!` |
| **Employee (Control Arm)** | Receive simulated emails and standard static guidance (for pilot comparison) | `dev.control@example.com` | `DemoPass123!` |
| **HR Viewer** | View department-level aggregate readiness (minimum cohort size enforced) | `meera.hr@example.com` | `DemoPass123!` |

> **Privacy & Ethics Notice:** All employee records are referenced by anonymized IDs (`emp_...`). No real credentials are ever captured, and all simulated sender/link domains use reserved training domains (`.invalid`, `.test`, `example.com`).

---

## 2. Getting Started (Signing In)

1. Open the web app (default: `http://localhost:5173`).
2. Enter your email and password and click **Sign In**.
3. You are automatically routed to the workspace matching your role (`security_admin`, `employee`, or `hr_viewer`).
4. Use **Sign Out** in the top-right header to switch accounts.

---

## 3. Employee Workspace

### 3.1 Simulated Inbox
- A **Transparency Notice** at the top confirms that the mailbox contains training exercises and that feedback is supportive, not punitive.
- Select any email from the left-hand list to read it (opening an email logs an `opened` event).
- **Report Phishing (Recommended):** Click the green **Report Phishing** button if you suspect an email is a scam. Reporting lowers your risk score and triggers reinforcing coaching.
- **Clicking Links:** Clicking the email's action button opens a **Simulated Verification Page (Training Exercise)** modal. It explicitly warns that it is a training exercise and **never stores any typed text**; clicking **Simulate Submit** records only the `submitted` event for training metrics.

### 3.2 Instant Coaching
- After clicking, submitting, or reporting an email:
  - **Treatment-arm employees** receive live-streamed, personalized AI coaching referencing the email's planted red flags and playbook guidance in real time.
  - **Control-arm employees** receive standard static guidance configured in `app_config`.
- Real-time generation: No canned or fallback templates are displayed; all coaching is generated live or reported with transparent service availability notifications.

### 3.3 Practice Chat (Treatment Arm Only)
1. Open the **Practice Chat** tab.
2. Click **Start Practice Chat** to begin a role-tailored conversation with a sandboxed attacker persona.
3. Reply naturally or call out the scam (e.g., *"This looks like phishing — I'm going to report it"*).
4. When you spot the scam or reach the configured turn cap, the session concludes with a concise **Debrief**.

### 3.4 My Progress
- View your current **Personal Risk Band** (`Low`, `Medium`, `High`) and numeric **Score**.
- Track **Simulations Received**, **Next Difficulty Tier** (adaptive 1–3), **Phishing Reported**, **Clicked**, **Submitted**, and **Coaching Sessions** completed.

---

## 4. Security Admin Workspace

### 4.1 Live Dashboard
- Displays real-time metrics computed from stored events:
  - **Delivered** & enrolled user count
  - **Click Rate** & **Submit Rate**
  - **Report Rate** & **Median Time-to-Report (TTR)**
  - **Repeat-Failure Rate** & **High Risk** user count
  - **Coaching Engagement** (coaching views & chat completions)
- **Department Interaction Breakdown:** Interactive bar chart comparing `Delivered`, `Clicked`, and `Reported` by department.
- **Toggles:**
  - **Include synthetic:** Off by default so synthetic load-test personas never inflate real effectiveness metrics.
  - **Show SQL:** Displays the underlying SQL queries for transparency during audits/demos.

### 4.2 Campaigns (Create, Approve, Deploy)
1. Enter a **Campaign Brief** (theme, target department or `all`, difficulty tier 1–3, and wave number) and click **Generate Draft**.
2. The LangGraph pipeline generates a JSON email, verifies all declared `planted_flags`, and runs rule + LLM safety guardrails.
3. Review the draft (check its `source` badge and `planted_flags`). Click **Approve** (or **Reject**).
4. Click **Deploy** to deliver the approved simulation to matching employees. *(Unapproved campaigns cannot be deployed.)*

### 4.3 Remediation Queue
- Users who enter the **High** risk band or fail across multiple campaigns appear automatically in **Remediation** (once per pending user).
- Click **Approve & Launch Follow-up** to create a targeted remediation campaign for that user.

### 4.4 Pilot View
- Compares **Control** vs **Treatment** arms across **Wave 1** and **Wave 2** with **95% Wilson confidence intervals** and **Difference-in-Differences (DiD)** on click rate, plus an honest small-sample interpretation note.

### 4.5 Config & Budget
- **Sync HR Employees:** Pulls employees from the HR adapter, anonymizes IDs, and assigns balanced control/treatment arms.
- **CSV / PDF Export:** Downloads department readiness reports in CSV or PDF format.
- **Live Config Editor:** Edit `risk_weights`, `decay_half_life_days`, `role_multipliers`, `band_thresholds`, `difficulty_map`, `chat_turn_cap`, `min_cohort_size`, and `control_static_feedback` without redeploying.
- **LLM Budget Telemetry:** Displays recent token usage and per-model rate-limit headroom.

---

## 5. HR Viewer Workspace

- Displays department-level aggregate metrics (`Users`, `Delivered`, `Click Rate`, `Submit Rate`, `Report Rate`, `Avg Risk`).
- **Privacy Enforcement:** Individual employees are never shown, and departments with fewer users than `min_cohort_size` (default: `5`) are automatically suppressed.

---

## 6. Troubleshooting

- **Login fails with 401/403:** Ensure `python tools/create_demo_users.py` has been run and the backend (`port 8000`) is running.
- **Empty Inbox:** Ensure a Security Admin has approved and deployed a campaign targeting your department (or `all`).
- **Real-Time Updates:** Live event streams (`/realtime/stream`) instantly push activity and metric changes to the Admin, HR, and Employee dashboards without periodic polling.
