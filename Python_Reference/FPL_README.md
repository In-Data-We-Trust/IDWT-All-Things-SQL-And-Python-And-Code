# Fantasy Premier League (FPL) Team Selector

This document provides an overview and documentation for the FPL team selection workflow in the `Python_Reference` folder.

## Quick Start

1. Open and run the `FPL_Team_Selector_Consolidated.ipynb` notebook
2. Follow the cells from top to bottom
3. Adjust parameters in the "Customization" section if desired
4. Review your optimal team selection

## Features

The FPL Team Selector provides the following capabilities:

- **Data Extraction**: Fetches the latest data from the official FPL API
- **Team Optimization**: Uses linear programming to find the optimal team within FPL constraints
- **Customizable Parameters**:
  - Budget adjustment
  - Player selection criteria (points, form, minutes played)
  - Team preferences
  - Must-include or must-exclude players
- **Data Storage**: Optional saving to Azure SQL Database for historical analysis
- **Team Validation**: Ensures all FPL rules are satisfied
- **Player Statistics**: Look up detailed stats for specific players

## How It Works

The team selection process follows these steps:

1. **Data Fetching**: Gets the latest player, team, and position data from the FPL API
2. **Data Preparation**: Transforms the raw API data into a format suitable for analysis
3. **Filtering**: Applies filters for minutes played, injury status, etc.
4. **Optimization**: Uses linear programming to find the optimal team
5. **Validation**: Ensures the selected team meets all FPL rules
6. **Display**: Shows the selected starting 11, bench, captain, and team statistics

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
   database_name=your_database_name
   username_db=your_username
   password=your_password
   ```

## File Organization

- `FPL_Team_Selector_Consolidated.ipynb`: Main notebook with complete workflow
- `FPL_README.md`: This documentation file

## Legacy Files (Reference Only)

The following files have been consolidated into `FPL_Team_Selector_Consolidated.ipynb`:

- `FPL_Prototype.ipynb`: Original prototype for data extraction and database storage
- `fpl_first_prototype_pick_team.ipynb`: Initial team optimization logic
- `FPL_Team_Selector.ipynb`: Previous version with Git operations

## Troubleshooting

- **API Access Issues**: The FPL API occasionally changes. If you encounter errors, check if the API endpoints have been updated.
- **Optimization Failures**: If no valid team is found, try relaxing your filtering criteria or increasing your budget.
- **Database Connection Errors**: Verify your database credentials and ensure your IP address has access to the database.

---

*Last updated: May 2025*
