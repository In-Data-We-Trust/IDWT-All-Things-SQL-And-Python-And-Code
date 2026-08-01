"""
Shared FPL data utilities used by the team selector and team monitor notebooks.

Provides:
- fetch_bootstrap_static(): current-season snapshot of players/teams/positions
- fetch_fixtures(): fixture list (with difficulty ratings)
- fetch_element_summaries(): per-player season-by-season history (history_past),
  fetched concurrently and cached to disk so repeat runs don't refetch ~700 players
- latest_completed_season() / get_last_season_stats(): extract last season's
  numbers as a scoring basis for preseason squad recommendations

The FPL API is unofficial and occasionally changes; all fetch helpers raise
FplApiError with a readable message instead of surfacing raw stack traces.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE_FPL_URL = "https://fantasy.premierleague.com/api/"

# The FPL API sometimes rejects requests without a browser-like user agent.
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (FPL team selector notebook)"}

DEFAULT_CACHE_PATH = os.path.join("data", "element_summaries_cache.json")


class FplApiError(Exception):
    """Raised when the FPL API is unreachable or returns unexpected data."""


def _get_json(url, timeout=30, retries=3, backoff=2.0):
    """GET a URL and return parsed JSON, retrying transient failures."""
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
            if response.status_code == 429:
                # Rate limited: back off and retry
                time.sleep(backoff * (attempt + 1))
                last_error = FplApiError(f"Rate limited (429) at {url}")
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise FplApiError(
        f"Could not fetch {url} after {retries} attempts: {last_error}. "
        "The FPL API may be down, or its endpoints may have changed - "
        "check https://fantasy.premierleague.com is reachable."
    )


def fetch_bootstrap_static(timeout=30):
    """
    Fetch the bootstrap-static payload (players, teams, positions, events).

    Note: this reflects the CURRENT season only. Before the first gameweek,
    per-player fields like total_points, form and minutes are reset to 0.
    """
    data = _get_json(BASE_FPL_URL + "bootstrap-static/", timeout=timeout)
    missing = [key for key in ("elements", "teams", "element_types", "events") if key not in data]
    if missing:
        raise FplApiError(
            f"bootstrap-static response is missing expected keys {missing} - "
            "the FPL API format may have changed."
        )
    return data


def fetch_fixtures(event_id=None, future_only=False, timeout=30):
    """
    Fetch fixtures. Optionally restrict to one gameweek (event_id) or to
    future fixtures only. Each fixture includes team_h/team_a and the
    FPL difficulty ratings team_h_difficulty/team_a_difficulty (1=easy, 5=hard).
    """
    url = BASE_FPL_URL + "fixtures/"
    if event_id is not None:
        url += f"?event={event_id}"
    elif future_only:
        url += "?future=1"
    fixtures = _get_json(url, timeout=timeout)
    if not isinstance(fixtures, list):
        raise FplApiError("fixtures response was not a list - the FPL API format may have changed.")
    return fixtures


def _load_cache(cache_path):
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r") as f:
            cached = json.load(f)
        return cached.get("players", {})
    except (ValueError, OSError):
        print(f"Warning: could not read cache at {cache_path}; refetching from the API.")
        return {}


def _save_cache(cache_path, players):
    directory = os.path.dirname(cache_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump({"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"), "players": players}, f)


def fetch_element_summaries(player_ids, cache_path=DEFAULT_CACHE_PATH,
                            max_workers=6, request_delay=0.05,
                            force_refresh=False, progress=True):
    """
    Fetch element-summary/{id}/ for each player and return
    {player_id: {"history_past": [...]}}.

    history_past holds one row per past season (season_name, total_points,
    minutes, goals_scored, assists, start_cost, end_cost, ...), which is the
    only place last season's numbers live once bootstrap-static resets.

    This is one API call per player (~700), so calls run on a small thread
    pool with a per-request delay to stay rate-limit friendly, and results
    are cached to cache_path so repeat runs only fetch players not yet cached.
    Players whose fetch fails are reported and skipped rather than aborting
    the whole run.
    """
    player_ids = [int(pid) for pid in player_ids]
    cached = {} if force_refresh else _load_cache(cache_path)
    results = {int(pid): cached[str(pid)] for pid in player_ids if str(pid) in cached}
    to_fetch = [pid for pid in player_ids if pid not in results]

    if progress:
        print(f"Element summaries: {len(results)} loaded from cache, {len(to_fetch)} to fetch.")

    if to_fetch:
        failed = []

        def fetch_one(pid):
            time.sleep(request_delay)
            summary = _get_json(BASE_FPL_URL + f"element-summary/{pid}/")
            return pid, {"history_past": summary.get("history_past", [])}

        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(fetch_one, pid): pid for pid in to_fetch}
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    pid, entry = future.result()
                    results[pid] = entry
                except FplApiError:
                    failed.append(pid)
                completed += 1
                if progress and completed % 100 == 0:
                    print(f"  ...fetched {completed}/{len(to_fetch)}")

        # Persist everything we have so far (existing cache + new fetches)
        merged = dict(cached)
        merged.update({str(pid): entry for pid, entry in results.items()})
        _save_cache(cache_path, merged)

        if failed:
            print(f"Warning: failed to fetch history for {len(failed)} players "
                  f"(ids: {failed[:10]}{'...' if len(failed) > 10 else ''}). "
                  "They will be treated as having no history.")

    return results


def latest_completed_season(element_summaries):
    """
    Return the most recent season_name (e.g. '2025/26') present in any
    player's history_past, or None if no history exists at all.
    """
    seasons = {
        row["season_name"]
        for entry in element_summaries.values()
        for row in entry.get("history_past", [])
        if row.get("season_name")
    }
    return max(seasons) if seasons else None


def get_last_season_stats(element_summaries, season_name=None):
    """
    Extract per-player stats for one past season as
    {player_id: {"season_name", "total_points", "minutes", "points_per_90",
                 "start_cost", "end_cost"}}.

    Players without a row for that season (new signings from abroad,
    promoted-team players, academy debutants) are simply absent from the
    result - callers decide how to default them.
    """
    if season_name is None:
        season_name = latest_completed_season(element_summaries)
        if season_name is None:
            return {}

    stats = {}
    for pid, entry in element_summaries.items():
        for row in entry.get("history_past", []):
            if row.get("season_name") == season_name:
                minutes = row.get("minutes", 0) or 0
                total_points = row.get("total_points", 0) or 0
                stats[int(pid)] = {
                    "season_name": season_name,
                    "total_points": total_points,
                    "minutes": minutes,
                    "points_per_90": round(total_points / (minutes / 90.0), 2) if minutes else 0.0,
                    "start_cost": row.get("start_cost"),
                    "end_cost": row.get("end_cost"),
                }
                break
    return stats
