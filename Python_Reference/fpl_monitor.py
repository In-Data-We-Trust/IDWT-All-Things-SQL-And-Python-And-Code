"""
FPL team monitoring utilities used by FPL_Team_Monitor.ipynb.

Each run snapshots the current bootstrap-static player data into a local
SQLite file, diffs it against the previous snapshot, and surfaces:

- week-over-week % change in transfers_in_event / transfers_out_event
  (ownership momentum for your squad and watchlist)
- price changes (cost_change_event / cost_change_start) and a simple
  price-move heuristic
- form trend, status (injured/suspended/doubtful) and
  chance_of_playing_next_round changes
- a captain suggestion for the upcoming gameweek based on fixture
  difficulty and form

No database server is required: everything persists to one .sqlite file.

A note on the transfer counters: transfers_in_event / transfers_out_event
accumulate within the current gameweek and reset at each deadline. If you
snapshot once a week (ideally the same day each week), the % change here
compares this week's transfer flow against last week's - which is the
signal you want for spotting momentum and likely price moves.
"""

import os
import sqlite3
from datetime import date

import pandas as pd

DEFAULT_DB_PATH = os.path.join("data", "fpl_snapshots.sqlite")

SNAPSHOT_COLUMNS = [
    "player_id", "web_name", "full_name", "team_id", "team_name", "position",
    "now_cost", "cost_change_event", "cost_change_start",
    "total_points", "points_per_game", "form", "selected_by_percent",
    "transfers_in_event", "transfers_out_event",
    "status", "chance_of_playing_next_round", "news",
]

STATUS_LABELS = {
    "a": "available",
    "d": "doubtful",
    "i": "injured",
    "s": "suspended",
    "u": "unavailable",
    "n": "not in squad",
}


def bootstrap_to_snapshot_df(bootstrap):
    """Flatten bootstrap-static into one row per player for snapshotting."""
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}

    rows = []
    for el in bootstrap["elements"]:
        rows.append({
            "player_id": el["id"],
            "web_name": el["web_name"],
            "full_name": f"{el['first_name']} {el['second_name']}",
            "team_id": el["team"],
            "team_name": teams.get(el["team"], f"team {el['team']}"),
            "position": positions.get(el["element_type"], str(el["element_type"])),
            "now_cost": el["now_cost"] / 10.0,
            "cost_change_event": el["cost_change_event"] / 10.0,
            "cost_change_start": el["cost_change_start"] / 10.0,
            "total_points": el["total_points"],
            "points_per_game": float(el["points_per_game"] or 0),
            "form": float(el["form"] or 0),
            "selected_by_percent": float(el["selected_by_percent"] or 0),
            "transfers_in_event": el["transfers_in_event"],
            "transfers_out_event": el["transfers_out_event"],
            "status": el["status"],
            "chance_of_playing_next_round": el["chance_of_playing_next_round"],
            "news": el.get("news") or "",
        })
    return pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)


def get_upcoming_event(bootstrap):
    """Return the next (or current, if mid-gameweek) event dict, or None."""
    events = bootstrap.get("events", [])
    for ev in events:
        if ev.get("is_next"):
            return ev
    for ev in events:
        if ev.get("is_current") and not ev.get("finished"):
            return ev
    return events[0] if events else None


def save_snapshot(snapshot_df, db_path=DEFAULT_DB_PATH, snapshot_date=None, event_id=None):
    """
    Persist a snapshot. Re-running on the same date replaces that date's
    snapshot, so a rerun never diffs against itself.
    """
    snapshot_date = snapshot_date or date.today().isoformat()
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    df = snapshot_df.copy()
    df.insert(0, "snapshot_date", snapshot_date)
    df.insert(1, "event_id", event_id)

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_date TEXT, event_id INTEGER,
                {} )
        """.format(", ".join(f"{c} TEXT" if c in ("web_name", "full_name", "team_name",
                                                  "position", "status", "news")
                             else f"{c} REAL" for c in SNAPSHOT_COLUMNS)))
        conn.execute("DELETE FROM snapshots WHERE snapshot_date = ?", (snapshot_date,))
        df.to_sql("snapshots", conn, if_exists="append", index=False)
    return snapshot_date


def load_previous_snapshot(db_path=DEFAULT_DB_PATH, exclude_date=None):
    """
    Load the most recent stored snapshot, skipping exclude_date (normally
    today, so reruns on the same day still diff against last week's run).
    Returns (DataFrame or None, snapshot_date or None).
    """
    if not os.path.exists(db_path):
        return None, None
    with sqlite3.connect(db_path) as conn:
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT snapshot_date FROM snapshots ORDER BY snapshot_date DESC")]
        dates = [d for d in dates if d != exclude_date]
        if not dates:
            return None, None
        prev_date = dates[0]
        df = pd.read_sql_query(
            "SELECT * FROM snapshots WHERE snapshot_date = ?", conn, params=(prev_date,))
    return df, prev_date


def _pct_change(current, previous):
    """% change; None when there is no previous baseline to compare against."""
    if previous is None or pd.isna(previous) or previous == 0:
        return None
    return round((current - previous) / previous * 100.0, 1)


def compute_changes(current_df, previous_df):
    """
    Merge the current snapshot with the previous one and compute
    week-over-week deltas. Columns added:

    - transfers_in_wow_pct / transfers_out_wow_pct: % change in this
      gameweek's transfer flow vs last snapshot's (None = no baseline)
    - net_transfers_event: transfers_in_event - transfers_out_event (current)
    - cost_delta: price change since previous snapshot (in £m)
    - form_delta, status_prev, status_changed, chance_delta
    - is_new_player: player appeared since the previous snapshot

    previous_df may be None or empty (first ever run): every player is then
    treated as new, with no week-over-week baseline.
    """
    if previous_df is None or previous_df.empty:
        previous_df = current_df.iloc[0:0]
    prev = previous_df[[
        "player_id", "now_cost", "form", "status",
        "chance_of_playing_next_round", "transfers_in_event", "transfers_out_event",
    ]].rename(columns=lambda c: c if c == "player_id" else f"{c}_prev")

    merged = current_df.merge(prev, on="player_id", how="left")
    merged["is_new_player"] = merged["now_cost_prev"].isna()

    merged["transfers_in_wow_pct"] = merged.apply(
        lambda r: _pct_change(r["transfers_in_event"], r["transfers_in_event_prev"]), axis=1)
    merged["transfers_out_wow_pct"] = merged.apply(
        lambda r: _pct_change(r["transfers_out_event"], r["transfers_out_event_prev"]), axis=1)
    merged["net_transfers_event"] = merged["transfers_in_event"] - merged["transfers_out_event"]
    merged["cost_delta"] = (merged["now_cost"] - merged["now_cost_prev"]).round(1)
    merged["form_delta"] = (merged["form"] - merged["form_prev"]).round(1)
    merged["status_changed"] = (~merged["is_new_player"]) & (merged["status"] != merged["status_prev"])
    merged["chance_delta"] = merged["chance_of_playing_next_round"].fillna(100) \
        - merged["chance_of_playing_next_round_prev"].fillna(100)
    return merged


def resolve_player_ids(snapshot_df, names):
    """
    Resolve a list of player names (web_name like 'M.Salah' or full name like
    'Mohamed Salah', case-insensitive) to player ids. Prints any names that
    could not be matched, and any that matched more than one player.
    """
    ids = []
    for name in names:
        target = name.strip().lower()
        matches = snapshot_df[
            (snapshot_df["web_name"].str.lower() == target)
            | (snapshot_df["full_name"].str.lower() == target)
        ]
        if len(matches) == 1:
            ids.append(int(matches.iloc[0]["player_id"]))
        elif len(matches) == 0:
            print(f"  ! No player matched '{name}' - check spelling "
                  "(try the short web name shown on fantasy.premierleague.com).")
        else:
            options = ", ".join(
                f"{r.full_name} ({r.team_name}, £{r.now_cost}m)" for r in matches.itertuples())
            print(f"  ! '{name}' is ambiguous between: {options}. "
                  "Use the full name to disambiguate.")
    return ids


def team_fixture_ease(fixtures, event_id):
    """
    For one gameweek, return {team_id: {"ease": float, "opponents": [str]}}.
    Ease per fixture = (5 - difficulty) / 4, so 1.0 = easiest, 0.0 = hardest;
    a double gameweek sums both fixtures, a blank gameweek gives 0.
    """
    ease = {}
    for fx in fixtures:
        if fx.get("event") != event_id:
            continue
        home, away = fx["team_h"], fx["team_a"]
        ease.setdefault(home, {"ease": 0.0, "opponents": []})
        ease.setdefault(away, {"ease": 0.0, "opponents": []})
        ease[home]["ease"] += (5 - fx["team_h_difficulty"]) / 4.0
        ease[away]["ease"] += (5 - fx["team_a_difficulty"]) / 4.0
        ease[home]["opponents"].append((away, "H"))
        ease[away]["opponents"].append((home, "A"))
    return ease


def suggest_captain(current_df, squad_ids, fixtures, event_id, team_names=None):
    """
    Rank the squad for the upcoming gameweek: base score x fixture ease.

    Base score is `form` once the season is underway; before any matches are
    played (form all zero) it falls back to points_per_game, then to
    selected_by_percent / 10 as a crowd-wisdom proxy. Players with no fixture
    (blank gameweek) or a non-available status score 0 and are flagged.
    """
    squad = current_df[current_df["player_id"].isin(squad_ids)].copy()
    if squad.empty:
        return squad

    if squad["form"].abs().max() > 0:
        base, base_label = squad["form"], "form"
    elif squad["points_per_game"].abs().max() > 0:
        base, base_label = squad["points_per_game"], "points_per_game"
    else:
        base, base_label = squad["selected_by_percent"] / 10.0, "selected_by_percent/10"

    ease = team_fixture_ease(fixtures, event_id)
    team_names = team_names or {}

    def describe_fixture(team_id):
        info = ease.get(team_id)
        if not info or not info["opponents"]:
            return 0.0, "BLANK - no fixture"
        parts = [
            f"vs {team_names.get(opp_id, f'team {opp_id}')} ({venue})"
            for opp_id, venue in info["opponents"]
        ]
        return info["ease"], "; ".join(parts)

    fixture_ease, fixture_desc = zip(*(describe_fixture(t) for t in squad["team_id"]))
    squad["base_score"] = base.round(2)
    squad["base_metric"] = base_label
    squad["fixture_ease"] = [round(e, 2) for e in fixture_ease]
    squad["fixture"] = list(fixture_desc)
    available = (squad["status"] == "a") | (
        squad["chance_of_playing_next_round"].fillna(100) >= 75)
    squad["captain_score"] = (squad["base_score"] * squad["fixture_ease"]).where(available, 0.0).round(2)
    squad.loc[~available, "fixture"] = squad.loc[~available, "fixture"] + \
        " [flagged: " + squad.loc[~available, "status"].map(STATUS_LABELS).fillna("unknown") + "]"

    return squad.sort_values("captain_score", ascending=False)[[
        "web_name", "team_name", "position", "base_score", "base_metric",
        "fixture_ease", "fixture", "captain_score",
    ]]


def build_report(changes_df, squad_ids, watchlist_ids=None,
                 swing_threshold_pct=50.0, min_transfer_volume=5000,
                 price_rise_net=40000, price_fall_net=-40000, top_movers=10):
    """
    Print an actionable summary from the diffed snapshot.

    swing_threshold_pct: WoW % change in transfer flow considered "large".
    min_transfer_volume: ignore movers below this many transfers this GW (noise).
    price_rise_net / price_fall_net: net transfers-in thresholds for the
    price-move heuristic. The real FPL price algorithm is secret; treat these
    flags as "worth checking tonight", not certainties.
    """
    watchlist_ids = watchlist_ids or []
    squad = changes_df[changes_df["player_id"].isin(squad_ids)]
    watch = changes_df[changes_df["player_id"].isin(watchlist_ids)]
    has_baseline = changes_df["transfers_in_wow_pct"].notna().any()

    def fmt_pct(v):
        return "n/a" if v is None or pd.isna(v) else f"{v:+.0f}%"

    print("=" * 70)
    print("SQUAD ALERTS")
    print("=" * 70)
    alerts = []
    for r in squad.itertuples():
        if r.status_changed and r.status != "a":
            label = STATUS_LABELS.get(r.status, r.status)
            news = f" - {r.news}" if r.news else ""
            alerts.append(f"  {r.web_name} ({r.team_name}): now {label.upper()}{news}")
        elif r.chance_delta < 0:
            alerts.append(f"  {r.web_name} ({r.team_name}): chance of playing dropped "
                          f"to {r.chance_of_playing_next_round:.0f}%")
        if r.cost_delta and r.cost_delta < 0:
            alerts.append(f"  {r.web_name} ({r.team_name}): price fell £{-r.cost_delta:.1f}m "
                          f"to £{r.now_cost:.1f}m")
        out_pct = r.transfers_out_wow_pct
        if (out_pct is not None and not pd.isna(out_pct) and out_pct >= swing_threshold_pct
                and r.net_transfers_event < 0
                and r.transfers_out_event >= min_transfer_volume):
            alerts.append(f"  {r.web_name} ({r.team_name}): heavy selling - transfers out "
                          f"{fmt_pct(out_pct)} WoW, net {r.net_transfers_event:+,.0f} this GW")
    print("\n".join(alerts) if alerts else "  No alerts - squad looks stable this week.")

    print()
    print("=" * 70)
    print("SQUAD MOMENTUM (week-over-week transfer flow)")
    print("=" * 70)
    if squad.empty:
        print("  No squad players resolved - fill in MY_SQUAD.")
    else:
        header = f"  {'Player':<18}{'£m':>6}{'Δ£ wk':>7}{'In (GW)':>10}{'WoW in':>9}{'Out (GW)':>10}{'WoW out':>9}{'Net':>10}"
        print(header)
        for r in squad.sort_values("net_transfers_event", ascending=False).itertuples():
            print(f"  {r.web_name:<18}{r.now_cost:>6.1f}"
                  f"{(r.cost_delta if not pd.isna(r.cost_delta) else 0):>+7.1f}"
                  f"{r.transfers_in_event:>10,.0f}{fmt_pct(r.transfers_in_wow_pct):>9}"
                  f"{r.transfers_out_event:>10,.0f}{fmt_pct(r.transfers_out_wow_pct):>9}"
                  f"{r.net_transfers_event:>+10,.0f}")
    if not has_baseline:
        print("\n  (First snapshot - WoW %s will appear from next week's run.)")

    print()
    print("=" * 70)
    print("MARKET MOVERS - trending in (watchlist + biggest WoW risers)")
    print("=" * 70)
    movers = changes_df[
        (changes_df["transfers_in_event"] >= min_transfer_volume)
        & (~changes_df["player_id"].isin(squad_ids))
    ].copy()
    if has_baseline:
        movers = movers[movers["transfers_in_wow_pct"].notna()]
        movers = movers.sort_values("transfers_in_wow_pct", ascending=False)
    else:
        movers = movers.sort_values("net_transfers_event", ascending=False)
    shown = pd.concat([watch, movers.head(top_movers)]).drop_duplicates("player_id")
    if shown.empty:
        print("  No significant movers this week.")
    else:
        for r in shown.itertuples():
            tag = " [watchlist]" if r.player_id in watchlist_ids else ""
            print(f"  {r.web_name:<18} ({r.team_name}, £{r.now_cost:.1f}m){tag}: "
                  f"in {r.transfers_in_event:,.0f} ({fmt_pct(r.transfers_in_wow_pct)} WoW), "
                  f"net {r.net_transfers_event:+,.0f}, form {r.form}")

    print()
    print("=" * 70)
    print("LIKELY PRICE MOVES (heuristic - check tonight before the change window)")
    print("=" * 70)
    risers = changes_df[changes_df["net_transfers_event"] >= price_rise_net] \
        .sort_values("net_transfers_event", ascending=False).head(top_movers)
    fallers = changes_df[changes_df["net_transfers_event"] <= price_fall_net] \
        .sort_values("net_transfers_event").head(top_movers)
    if risers.empty and fallers.empty:
        print("  No players near the heuristic thresholds.")
    for r in risers.itertuples():
        mine = " [IN YOUR SQUAD]" if r.player_id in squad_ids else ""
        print(f"  ↑ {r.web_name} ({r.team_name}, £{r.now_cost:.1f}m){mine}: "
              f"net {r.net_transfers_event:+,.0f} this GW")
    for r in fallers.itertuples():
        mine = " [IN YOUR SQUAD]" if r.player_id in squad_ids else ""
        print(f"  ↓ {r.web_name} ({r.team_name}, £{r.now_cost:.1f}m){mine}: "
              f"net {r.net_transfers_event:+,.0f} this GW")
    print("\n  Note: FPL's real price algorithm is unpublished; these flags mean")
    print("  'transfer volume is high enough to watch', not a guaranteed move.")
