import io
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    MovieCache,
    MovieDataResponse,
    MovieProcessingReport,
    MovieStorage,
    MovieUploadInfo,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Processing API", version="1.0.0")

# Register middleware
app.middleware("http")(log_requests)

storage = MovieStorage()
cache = MovieCache()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a CSV upload and replace the stored movie collection."""
    ext = Path(file.filename or "").suffix.lower()
    if ext != ".csv":
        logger.warning(f"Unsupported file format: {ext}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}. Only .csv files are allowed.",
        )

    contents = await file.read()

    try:
        df = pd.read_csv(io.BytesIO(contents))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to parse CSV file: {e}")
        raise HTTPException(status_code=400, detail="Invalid CSV file format or contents.")

    if len(df.columns) != len(MOVIE_COLUMNS) or set(df.columns) != set(MOVIE_COLUMNS):
        logger.warning(f"Invalid columns: {list(df.columns)}")
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain exactly these columns: {MOVIE_COLUMNS}",
        )
    if df.empty:
        logger.warning("Uploaded CSV has no data rows")
        raise HTTPException(status_code=400, detail="CSV must contain at least one data row.")

    df = df[MOVIE_COLUMNS]

    storage.save(df)
    cache.invalidate()

    logger.info(f"Uploaded movies: filename={file.filename}, rows={len(df)}")
    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
    }


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return up to limit stored movies and the total count (cached)."""
    cached = cache.get(limit)
    if cached is not None:
        logger.info(f"Cache hit for movies: limit={limit}")
        return cached

    data = storage.select_columns(MOVIE_COLUMNS, limit)
    total_rows = storage.count_movies()
    response = {"data": data, "total_rows": total_rows}

    cache.set(limit, response)
    logger.info(f"Retrieved movies: returned_rows={len(data)}")
    return response


@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1),
):
    """Return selected fields of movies at or above min_rating (not cached)."""
    try:
        rows = storage.query_movies(columns, min_rating, limit)
    except ValueError as e:
        logger.warning(f"Invalid search request: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        f"Queried movies: columns={columns}, min_rating={min_rating}, "
        f"returned_rows={len(rows)}"
    )
    return rows


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate and process the stored movies, then save the result."""
    df = storage.get()
    if df.empty:
        logger.warning("No movies stored to process")
        raise HTTPException(status_code=400, detail="No movies stored. Upload a CSV first.")

    config_dict = config.model_dump()

    for col in config.validation.numeric_columns:
        if col not in df.columns:
            logger.warning(f"Configured numeric column not found: {col}")
            raise HTTPException(
                status_code=400,
                detail=f"Numeric column '{col}' not found in dataset.",
            )

    try:
        initial_rows = len(df)
        validated_df = validate_dataframe(df, config_dict["validation"])
        validation_rows_removed = initial_rows - len(validated_df)

        processed_df = process_data(validated_df.copy(), config_dict)
        cleaning_report = create_cleaning_report(validated_df, processed_df)

        storage.save(processed_df)
        cache.invalidate()

        logger.info(
            f"Processed movies: validation_removed={validation_rows_removed}, "
            f"rows_before={cleaning_report['rows_before']}, "
            f"rows_after={cleaning_report['rows_after']}"
        )
        return {
            "validation_rows_removed": validation_rows_removed,
            "cleaning_report": cleaning_report,
        }

    except ValueError as e:
        logger.warning(f"Processing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))