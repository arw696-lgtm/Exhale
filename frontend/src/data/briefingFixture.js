/**
 * Sample Weekly COO Briefing payload — matches the shape produced by the
 * backend's `exhale.briefing.build_weekly_briefing` (see backend/examples).
 * Mirrors the mockup in Blueprint §9.1.
 */
export const briefingFixture = {
  product: "Exhale",
  view: "weekly_coo_briefing",
  week_of: "Week of July 19, 2026",
  summary: {
    critical_count: 2,
    dependency_watch_count: 1,
    advisory_count: 1,
    total_gaps: 4,
  },
  critical_threats: [
    {
      obligation_id: "permission_slip",
      title: "West High Field Trip Permission Slip",
      person: "Olivia",
      anchor_event: "School Resumes",
      deadline: "2026-07-20",
      hours_until_deadline: 20.0,
      risk_score: 0.765,
      threat_level: "CRITICAL",
      source_document_name: "West High Weekly Newsletter",
      primary_action: "Review & Sign Draft",
      secondary_action: "View Source Email",
    },
    {
      obligation_id: "immunization",
      title: "Missing State Immunization Record for Soccer League",
      person: "Leo",
      anchor_event: "Soccer League Start",
      deadline: "2026-07-24",
      hours_until_deadline: 30.0,
      risk_score: 0.72,
      threat_level: "CRITICAL",
      source_document_name: "Soccer League Onboarding Packet",
      primary_action: "Text Doctor for Record",
      secondary_action: "View Attached Form",
    },
  ],
  dependency_watch: [
    {
      obligation_id: "supply_list",
      title: "3rd Grade Classroom Supply List",
      person: "Olivia",
      anchor_event: "School Resumes",
      deadline: "2026-08-08",
      hours_until_deadline: 480.0,
      risk_score: 0.42,
      threat_level: "IMPORTANT",
      status: "UNRESOLVED",
      detail: "Found 12 items on Amazon Cart. Would you like to buy?",
    },
  ],
  completed: [
    { title: "Medical Physical Forms", detail: "COMPLETED (Uploaded July 14)" },
    { title: "Bus Route Confirmation", detail: "COMPLETED (Sourced from School Portal)" },
  ],
  calendar_conflicts: [
    {
      window: "Thursday, July 23 @ 4:00 PM",
      detail: "Olivia's Dentist Appointment overlaps with Leo's Soccer Carpool.",
      action: "Auto-draft text to Grandma to cover Leo",
    },
  ],
  advisories: [],
  care_watch: {
    view: "care_watch",
    recipient: "Leo",
    summary: { total_gaps: 2, critical: 0, important: 1, advisory: 1, assumption_dependent: 1 },
    gaps: [
      {
        recipient: "Leo",
        date: "2026-07-24",
        start: "2026-07-24T19:00:00",
        end: "2026-07-24T21:30:00",
        duration_hours: 2.5,
        threat_level: "IMPORTANT",
        indicator: "🟡",
        reason: "Both parents at Gary Clark Jr. concert (The Fitzgerald Theater)",
        depends_on_inference: false,
        suggested_action: "Book a sitter",
      },
      {
        recipient: "Leo",
        date: "2026-10-15",
        start: "2026-10-15T09:00:00",
        end: "2026-10-15T12:00:00",
        duration_hours: 3.0,
        threat_level: "ADVISORY",
        indicator: "🔵",
        reason: "school closed (MEA break); one parent working; other in a meeting",
        depends_on_inference: true,
        suggested_action: "Book a sitter",
      },
    ],
  },
};
