import logging
import io
import pandas as pd
from azure.storage.blob import BlobServiceClient

class NoDataInputError(RuntimeError):
    """Custom error to indicate no data was provided for insights generation."""
    pass

def download_csv(storage_connection_str: str, storage_container_name: str) -> dict[str, pd.DataFrame]:
    logger = logging.getLogger("hitachi_pipeline")
    logger.info(
        "Downloading CSV files from Blob Storage: container=%s",
        storage_container_name,
    )

    client = BlobServiceClient.from_connection_string(storage_connection_str)
    container = client.get_container_client(container=storage_container_name)

    dataframes = {}

    for blob in container.list_blobs():
        if blob.name.lower().endswith(".csv"):
            logger.info("Downloading %s from %s...", blob.name, storage_container_name)
            blob_client = container.get_blob_client(blob.name)
            data = blob_client.download_blob().readall()
            df = pd.read_csv(io.BytesIO(data))
            dataframes[blob.name] = df

    return dataframes

def build_dataset_metadata(dfs: dict[str, pd.DataFrame]) -> str:
    lines = []

    for dataset_name, df in dfs.items():
        cols = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            cols.append(f"{col} ({dtype})")

        lines.append(f"Dataset: {dataset_name}")
        lines.append(f"Rows: {len(df)}, Columns: {len(df.columns)}")
        lines.append("Columns:")
        for c in cols:
            lines.append(f"  - {c}")
        lines.append("")

    return "\n".join(lines)