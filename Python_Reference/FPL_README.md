# Python Reference: FPL Team Selection and Utilities

This document provides an overview and documentation for the Python scripts and notebooks in the `Python_Reference` folder, with a focus on Fantasy Premier League (FPL) team selection and related utilities.

## Contents
- [FPL_Prototype.ipynb](#fpl_prototypeipynb)
- [fpl_first_prototype_pick_team.ipynb](#fpl_first_prototype_pick_teamipynb)
- [Reference_Python_Notebook.ipynb](#reference_python_notebookipynb)
- [database_connections_git_copy.py](#database_connections_git_copypy)
- [Azure_SQL_DB_connection.ipynb](#azure_sql_db_connectionipynb)

---

## FPL_Prototype.ipynb
A comprehensive notebook for:
- Downloading and processing FPL data from the official API
- Data wrangling and transformation using pandas
- Storing and loading data to/from Azure SQL DB
- Functions for extracting player and team statistics
- Useful for data exploration and building custom FPL analytics

**Key Features:**
- Uses `requests` to fetch FPL data
- Data normalization and DataFrame creation
- SQL database integration (requires environment variables for credentials)
- Example: Extracting player gameweek history

---

## fpl_first_prototype_pick_team.ipynb
A focused notebook for:
- Building an optimal FPL team using linear programming (PuLP)
- Fetches latest player data from the FPL API
- Defines constraints for budget, squad size, and team/position limits
- Outputs a suggested starting 11, bench, and captain

**Key Features:**
- Uses `requests` and `pulp` libraries
- Easy to run for up-to-date team suggestions
- Can be merged into the main FPL notebook for a single workflow

---

## Reference_Python_Notebook.ipynb
A general-purpose notebook for:
- Storing frequently used Python syntax and data analysis patterns
- Quick reference for pandas operations (filtering, adding/removing columns, etc.)

---

## database_connections_git_copy.py
A Python script template for:
- Storing database connection credentials (should be renamed to `database_connections_local.py` and updated with your own credentials)

---

## Azure_SQL_DB_connection.ipynb
A notebook for:
- Demonstrating how to connect to an Azure SQL Database using `pyodbc` and `pandas`
- Example query and DataFrame loading

---

## Recommended Workflow
- Use `FPL_Prototype.ipynb` for data extraction, exploration, and database loading.
- Use or merge `fpl_first_prototype_pick_team.ipynb` for optimal team selection each week.
- Store your database credentials securely and do not commit them to version control.
- Refer to `Reference_Python_Notebook.ipynb` for quick code snippets.

## One-Click Team Selection
For a single, easy-to-run workflow, merge the team selection logic from `fpl_first_prototype_pick_team.ipynb` into `FPL_Prototype.ipynb` or create a new notebook/script that:
- Fetches latest FPL data
- Runs the optimization model
- Outputs the recommended team

---

*Last updated: May 2025*
