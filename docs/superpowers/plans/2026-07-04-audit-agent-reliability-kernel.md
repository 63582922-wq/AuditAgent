# Audit Agent Reliability Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first reliability slice for the meeting audit Agent: evidence-led fact extraction, SMS regression fixes, and delivery gating when automatic evaluation fails.

**Architecture:** Keep this as a backend kernel change. Add tests that encode the observed SMS failures, then update classification, field extraction, and harness status handling so failed quality checks do not look deliverable.

**Tech Stack:** Python, SQLAlchemy, pytest, openpyxl, existing FXPG compliance services.

---

### Task 1: SMS Evidence Regression Tests

**Files:**
- Modify: `backend/tests/test_compliance_classifier_samples.py`
- Modify: `backend/tests/test_compliance_case_facts.py`
- Modify: `backend/tests/test_compliance_harness.py`

- [ ] Add a classifier test proving OCR text from `确认单 (3).jpg` must remain `observation_confirmation`, not `a1_meeting_export`.
- [ ] Add a fact extraction test proving presentation topic should prefer PPT/confirmation evidence over lower-priority agenda subtopics.
- [ ] Add an attendance test proving Zoom peak count, watch record count, and composite attendance expression are separate facts.
- [ ] Add a harness test proving failed critical evaluation gates the deliverable to `needs_review`.

### Task 2: Classification and Fact Extraction Fixes

**Files:**
- Modify: `backend/app/services/domain/compliance/classifier.py`
- Modify: `backend/app/services/domain/compliance/template_field_engine.py`
- Modify: `backend/app/services/domain/compliance/cross_checker.py` if facts are flattened there.

- [ ] Update OCR reclassification so confirmation/checklist text and confirmation filenames cannot be stolen by A1 export classification.
- [ ] Preserve `zoom_peak_count`, `watch_record_count`, and `total_attendance_expression` separately.
- [ ] Prefer high-priority sources for `presentation_topic`: confirmation/PPT cover before agenda subtopic and process screenshots.

### Task 3: Evaluation Gate

**Files:**
- Modify: `backend/app/services/agent/harness/compliance_harness.py`
- Modify: tests in `backend/tests/test_compliance_harness.py`

- [ ] When automatic evaluation has critical failures, set deliverable status to `needs_review`.
- [ ] Store a clear gate reason and failed check IDs in `deliverable_json`.
- [ ] Do not block unknown/unbaselined cases; only gate concrete failed evaluation reports.

### Task 4: Verification

**Commands:**
- `PYTHONPATH=backend python3 -m pytest backend/tests/test_compliance_classifier_samples.py backend/tests/test_compliance_case_facts.py backend/tests/test_compliance_harness.py -q`
- `PYTHONPATH=backend python3 -m pytest backend/tests -q`
- `PATH=/tmp/fxpg-node20/node-v20.20.2-darwin-arm64/bin:$PATH ./frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit`
- `PATH=/tmp/fxpg-node20/node-v20.20.2-darwin-arm64/bin:$PATH npm --prefix frontend run build`
