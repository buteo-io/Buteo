# Buteo Roadmap

## Active

### Phase: Overnight Detection v2

**Branch:** `feat/improve-overnight-detection`

**Goal:** Stable overnight spot detection with full-window rescans, correct night counts, automatic updates, and safe date-change invalidation.

#### Problem
- Count always=1 even for multi-night stays (incremental scan sees partial stop windows)
- Opening a trip with new data doesn't update spots (detection not triggered automatically)
- Editing trip dates leaves spots stale (marker never reset, no reconciliation)

#### Design Decisions

**Backend — `overnight_service.py`**
- Drop incremental `scan_from = marker` logic; always scan full window `started_at → effective_end`
- Reconcile detected spots against existing DB rows:
  - Match by proximity ≤80m → update `nights_count` + `last_stay_at`
  - New location → create row
  - Existing spot with `last_stay_at` outside new trip window → delete (media loss accepted; user warned in UI before date narrowing)
- `PATCH /trips/{id}` resets `overnights_last_checked_position_time = NULL` when `started_at` or `ended_at` changes → forces rescan on next detect call
- Cooldown (4h) kept for **ongoing trips only**; removed for closed trips (window is fixed, rescan is idempotent)

**Frontend — `App.tsx`**
- Keep explicit `detectTripOvernightSpots` POST on `onOpen` — detection fires server-side via full rescan
- Add warning dialog before saving a trip edit that shortens the window if affected spots have media attached

**Stability fix:** Full rescan means `_count_nights` always sees complete stop windows → count=1 bug eliminated.

#### Constraints
- Never delete `OvernightSpot` rows that have media, unless the spot is outside the trip window (user warned)
- Cooldown protects ongoing trips from expensive rescans on every page open
