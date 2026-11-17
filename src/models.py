class MovieUploadInfo(BaseModel):
    filename: str
    rows: int
    columns: int
    column_names: list[str]

class MovieDataResponse(BaseModel):
    data: list[dict]
    total_rows: int

class MovieProcessingReport(BaseModel):
    validation_rows_removed: int
    cleaning_report: dict