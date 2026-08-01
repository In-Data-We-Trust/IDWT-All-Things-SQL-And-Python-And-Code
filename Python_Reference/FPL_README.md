# Fantasy Premier League (FPL) Team Selector

This document provides an overview and documentation for the FPL team selection workflow in the `Python_Reference` folder.

## Quick Start

1. Open and run the `FPL_Team_Selector_Consolidated.ipynb` notebook
2. Follow the cells from top to bottom
3. Adjust parameters in the "Customization" section if desired
4. Review your optimal team selection
5. During the season, run `FPL_Team_Monitor.ipynb` once a week to track your squad (see "Team Monitoring" below)

## Features

The FPL Team Selector provides the following capabilities:

- **Data Extraction**: Fetches the latest data from the official FPL API
- **Last-Season Scoring (Preseason Mode)**: Recommends a new-season squad from last season's final numbers, since current-season stats are all zero before Gameweek 1
- **Team Optimization**: Uses linear programming to find the optimal team within FPL constraints
- **Customizable Parameters**:
  - Budget adjustment
  - Player selection criteria (points, form, minutes played - current or last season)
  - Team preferences
  - Must-include or must-exclude players
- **Team Monitoring**: A separate weekly notebook that tracks transfer momentum, price changes and injuries for your squad
- **Data Storage**: Optional saving to Azure SQL Database for historical analysis
- **Team Validation**: Ensures all FPL rules are satisfied
- **Player Statistics**: Look up detailed stats for specific players

## How It Works

The team selection process follows these steps:

1. **Data Fetching**: Gets the latest player, team, and position data from the FPL API
2. **Data Preparation**: Transforms the raw API data into a format suitable for analysis
3. **Last-Season History** (preseason): Fetches each player's past-season totals and merges last season's numbers in as the scoring basis
4. **Filtering**: Applies filters for minutes played, injury status, etc.
5. **Optimization**: Uses linear programming to find the optimal team
6. **Validation**: Ensures the selected team meets all FPL rules
7. **Display**: Shows the selected starting 11, ordered bench, captain, and team statistics

## Last-Season Data Source (Preseason Mode)

The main `bootstrap-static` endpoint only covers the **current** season, so before Gameweek 1 every player's `total_points`, `form` and `minutes` are 0. To recommend a squad before the season starts, the notebook pulls each player's season-by-season history (`history_past`) from the `element-summary/{id}/` endpoint via the shared `fpl_data.py` module:

- One API call per player (~700 total), run concurrently on a small thread pool with retries and a per-request delay to stay rate-limit friendly
- Results are cached to `data/element_summaries_cache.json`, so only the first run is slow - repeat runs load from disk
- The most recent completed season found in the history is used as the scoring basis (`scoring_method = 'last_season_points'` or `'last_season_per_90'`)
- Players with **no** last-season history (promoted-team players, new signings from abroad) are flagged `no_history=True` and defaulted to 0 points; they are excluded from the pool by default but always listed, so you can add ones you rate to `must_include_players` or set `include_no_history_players = True`
- If the season is already underway, current-season scoring methods work as before, and the history fetch can be skipped with `fetch_last_season_history = False`

## Team Monitoring (`FPL_Team_Monitor.ipynb`)

Once your team is picked, run `FPL_Team_Monitor.ipynb` weekly (same day each week for like-for-like comparisons). Each run:

1. Fetches the latest player data and saves a snapshot to a local SQLite file (`data/fpl_snapshots.sqlite` - no database server required)
2. Diffs against the previous week's snapshot to compute **week-over-week % change in transfer activity** (`transfers_in_event` / `transfers_out_event`) - the ownership-momentum signal that anticipates bandwagons and price moves
3. Reports, for your squad and watchlist:
   - Injury/suspension/availability changes and price falls (squad alerts)
   - Transfer momentum per squad player (in/out volume, WoW %, net)
   - Market movers trending in across the game
   - Likely price rises/falls (a heuristic based on net transfer volume - FPL's real price algorithm is unpublished)
   - A suggested captain and vice-captain for the upcoming gameweek, from fixture difficulty x form (with sensible preseason fallbacks)

The FPL API's transfer counters accumulate within the current gameweek and reset at each deadline, so snapshotting weekly compares this week's flow with last week's. The first run just saves a baseline; percentages appear from the second run.

## Linear Programming Model

The team selection uses the PuLP library to solve a linear programming problem with:

- **Objective**: Maximize total points/score of the starting 11
- **Constraints**:
  - Total cost ≤ £100 million
  - Squad size = 15 players
  - Starting 11 size = 11 players
  - Goalkeeper: 1-1 (starting), 2 (squad)
  - Defenders: 3-5 (starting), 5 (squad)
  - Midfielders: 2-5 (starting), 5 (squad)
  - Forwards: 1-3 (starting), 3 (squad)
  - Maximum 3 players from any team

## Database Storage (Optional)

If you have an Azure SQL Database, you can store:
- Player data
- Team data
- Position data
- Selected team history

To enable this feature:
1. Create a `.env` file with your database credentials
2. Set the following variables:
   ```
   server_name=your_server_name
   database_name=your_database_name   username_db=your_username
   password=your_password
   ```

## File Organization

- `FPL_Team_Selector_Consolidated.ipynb`: Main notebook with complete workflow
- `FPL_Team_Monitor.ipynb`: Weekly squad monitoring notebook (transfer momentum, prices, injuries, captain pick)
- `fpl_data.py`: Shared data layer - FPL API fetching, retries, concurrent history download and disk caching
- `fpl_monitor.py`: Monitoring logic - snapshot storage, week-over-week diffs, report and captain suggestion
- `data/`: Local cache and snapshots (created on first run; not committed to git)
- `FPL_README.md`: This documentation file
- `archive/`: Folder containing legacy FPL files that have been consolidated

## Legacy Files (Reference Only)

The following files have been moved to the `archive/` folder and have been consolidated into `FPL_Team_Selector_Consolidated.ipynb`:

- `archive/FPL_Prototype.ipynb`: Original prototype for data extraction and database storage
- `archive/fpl_first_prototype_pick_team.ipynb`: Initial team optimization logic
- `archive/FPL_Team_Selector.ipynb`: Previous version with Git operations

## Troubleshooting

- **API Access Issues**: The FPL API occasionally changes. If you encounter errors, check if the API endpoints have been updated. Fetch helpers in `fpl_data.py` retry transient failures and raise a readable `FplApiError` when the API is down or its format has changed.
- **Optimization Failures**: If no valid team is found, try relaxing your filtering criteria or increasing your budget.
- **Empty player pool in preseason**: Current-season scoring methods score everyone 0 before Gameweek 1 - use `scoring_method = 'last_season_points'` (the notebook falls back to it automatically).
- **Stale history cache**: Delete `data/element_summaries_cache.json` (or pass `force_refresh=True`) to refetch player histories, e.g. after the summer transfer window closes.
- **Database Connection Errors**: Verify your database credentials and ensure your IP address has access to the database.

---

*Last updated: August 2026*
