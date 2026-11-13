import logging
import sqlite3
import pandas as pd
from src.database import get_connection, initialize_database

logger = logging.getLogger(__name__)

MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]

class MovieStorage:
    def __init__(self, db_path="data/movies.db"):
        self.db_path = db_path
        initialize_database(self.db_path)

    def save(self, df):
        """Replace all movie rows in one transaction."""
        # Convert missing values to Python None for SQL NULL
        df_clean = df.where(pd.notnull(df), None)
        
        connection = get_connection(self.db_path)
        try:
            with connection:
                connection.execute("DELETE FROM movies")
                # Insert rows matching MOVIE_COLUMNS order
                rows_to_insert = df_clean[MOVIE_COLUMNS].to_records(index=False).tolist()
                connection.executemany(
                    "INSERT INTO movies (title, release_year, rating, genre) VALUES (?, ?, ?, ?)",
                    rows_to_insert
                )
            logger.debug(f"Stored movies in SQLite: rows={len(df_clean)}")
        except sqlite3.Error as e:
            logger.error(f"Database error during save: {e}")
            raise
        finally:
            connection.close()

    def get(self):
        """Return the four movie columns as a DataFrame, ordered by id."""
        connection = get_connection(self.db_path)
        try:
            query = "SELECT title, release_year, rating, genre FROM movies ORDER BY id"
            df = pd.read_sql_query(query, connection)
            if df.empty:
                return pd.DataFrame(columns=MOVIE_COLUMNS)
            return df[MOVIE_COLUMNS]
        finally:
            connection.close()

    def select_columns(self, columns, limit=5):
        """Return id plus requested movie columns, ordered by id."""
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
            query = f"SELECT {selected_columns} FROM movies ORDER BY id LIMIT ?"
            cursor = connection.execute(query, (limit,))
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
            count = cursor.fetchone()[0]
            return count
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
            query = f"""
                SELECT {selected_columns} 
                FROM movies 
                WHERE rating >= ? 
                ORDER BY rating DESC, id ASC 
                LIMIT ?
            """
            cursor = connection.execute(query, (min_rating, limit))
            rows = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Queried movies: columns={columns}, min_rating={min_rating}, returned_rows={len(rows)}")
            return rows
        finally:
            connection.close()