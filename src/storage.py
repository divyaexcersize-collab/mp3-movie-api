import logging
import sqlite3

import pandas as pd

from .database import get_connection, initialize_database

logger = logging.getLogger(__name__)

MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]


class MovieStorage:
    def __init__(self, db_path="data/movies.db"):
        self.db_path = db_path
        initialize_database(self.db_path)

    def save(self, df):
        """Replace all movie rows in one transaction."""
        # Convert every value to a plain Python type, and missing values to None (SQL NULL).
        rows_to_insert = []
        for row in df[MOVIE_COLUMNS].itertuples(index=False, name=None):
            clean_row = []
            for value in row:
                if pd.isna(value):
                    clean_row.append(None)
                elif hasattr(value, "item"):
                    clean_row.append(value.item())  # numpy scalar -> Python
                else:
                    clean_row.append(value)
            rows_to_insert.append(tuple(clean_row))

        connection = get_connection(self.db_path)
        try:
            with connection:
                connection.execute("DELETE FROM movies")
                connection.executemany(
                    "INSERT INTO movies (title, release_year, rating, genre) "
                    "VALUES (?, ?, ?, ?)",
                    rows_to_insert,
                )
            logger.debug(f"Stored movies in SQLite: rows={len(rows_to_insert)}")
        except sqlite3.Error as e:
            logger.error(f"Database error during save: {e}")
            raise
        finally:
            connection.close()

    def get(self):
        """Return the four movie columns as a DataFrame, ordered by id."""
        connection = get_connection(self.db_path)
        try:
            cursor = connection.execute(
                "SELECT title, release_year, rating, genre FROM movies ORDER BY id"
            )
            rows = [tuple(row) for row in cursor.fetchall()]
            return pd.DataFrame(rows, columns=MOVIE_COLUMNS)
        finally:
            connection.close()

    def select_columns(self, columns, limit=5):
        """Return id plus the requested movie columns, ordered by id."""
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")
        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error(f"Unsupported column: {column}")
                raise ValueError(f"Unsupported column: {column}")

        selected_columns = ", ".join(["id"] + columns)
        connection = get_connection(self.db_path)
        try:
            cursor = connection.execute(
                f"SELECT {selected_columns} FROM movies ORDER BY id LIMIT ?",
                (limit,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Selected columns {columns}, fetched {len(rows)} rows")
            return rows
        finally:
            connection.close()

    def count_movies(self):
        """Return the number of stored movies using SQL COUNT(*)."""
        connection = get_connection(self.db_path)
        try:
            cursor = connection.execute("SELECT COUNT(*) FROM movies")
            return cursor.fetchone()[0]
        finally:
            connection.close()

    def query_movies(self, columns, min_rating, limit):
        """Return selected fields from matching movies using SQL."""
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")
        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error(f"Unsupported column: {column}")
                raise ValueError(f"Unsupported column: {column}")

        selected_columns = ", ".join(["id"] + columns)
        connection = get_connection(self.db_path)
        try:
            cursor = connection.execute(
                f"SELECT {selected_columns} FROM movies "
                "WHERE rating >= ? ORDER BY rating DESC, id ASC LIMIT ?",
                (min_rating, limit),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            logger.debug(
                f"Queried movies: columns={columns}, min_rating={min_rating}, "
                f"returned_rows={len(rows)}"
            )
            return rows
        finally:
            connection.close()