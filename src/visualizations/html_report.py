from __future__ import annotations

import base64
import io
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # non-interactive backend - no display or Chrome required
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, ContentSettings, generate_blob_sas


def _safe_name(name: str) -> str:
    return (
        name.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace(".csv", "")
    )


def _normalize_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def _validate_column(df: pd.DataFrame, col: Optional[str]) -> bool:
    return col is not None and col in df.columns


def _aggregate_for_chart(
    df: pd.DataFrame,
    x: str,
    y: Optional[str],
    aggregation: str,
    chart_type: str,
) -> Optional[pd.DataFrame]:
    temp = df.copy()

    if not _validate_column(temp, x):
        return None

    if chart_type == "line":
        temp[x] = _normalize_datetime(temp[x])
        temp = temp.dropna(subset=[x])
        if temp.empty:
            return None

    if aggregation == "count":
        grouped = temp.groupby(x).size().reset_index(name="value")
        return grouped.sort_values(x) if chart_type == "line" else grouped

    if y is None or not _validate_column(temp, y):
        return None

    # Skip obviously meaningless numeric ID aggregations
    if y.lower().endswith("_id") or y.lower() == "id":
        return None

    if aggregation == "sum":
        grouped = temp.groupby(x, as_index=False)[y].sum(numeric_only=False)
        grouped = grouped.rename(columns={y: "value"})
    elif aggregation == "mean":
        grouped = temp.groupby(x, as_index=False)[y].mean(numeric_only=True)
        grouped = grouped.rename(columns={y: "value"})
    else:
        return None

    return grouped.sort_values(x) if chart_type == "line" else grouped


def _render_chart_html(
    df: pd.DataFrame,
    dataset_name: str,
    spec: dict,
    tmp_dir: Path,
    idx: int,
) -> Optional[dict]:
    chart_type = spec.get("chart_type")
    x = spec.get("x")
    y = spec.get("y")
    aggregation = spec.get("aggregation")
    title = spec.get("title", f"{dataset_name} chart")

    if chart_type not in {"bar", "line"}:
        return None
    if aggregation not in {"count", "sum", "mean"}:
        return None
    if not isinstance(x, str):
        return None

    grouped = _aggregate_for_chart(
        df=df,
        x=x,
        y=y,
        aggregation=aggregation,
        chart_type=chart_type,
    )
    if grouped is None or grouped.empty:
        return None

    if chart_type == "bar":
        fig = px.bar(grouped, x=x, y="value", title=title, text="value")
    else:
        fig = px.line(grouped, x=x, y="value", title=title, markers=True)

    fig.update_layout(
        xaxis_title=x,
        yaxis_title=f"{aggregation}({y})" if y else "count",
    )

    # Write a standalone interactive HTML file for blob storage upload
    filename = f"{_safe_name(dataset_name)}_{idx}_{chart_type}.html"
    local_path = tmp_dir / filename
    fig.write_html(str(local_path), include_plotlyjs="cdn")

    # Generate a static PNG for email embedding using matplotlib (no Chrome/Kaleido needed)
    fig_mpl, ax = plt.subplots(figsize=(7, 4))
    x_labels = grouped[x].astype(str)
    if chart_type == "bar":
        ax.bar(x_labels, grouped["value"])
    else:
        ax.plot(x_labels, grouped["value"], marker="o")
    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel(f"{aggregation}({y})" if y else "count")
    if len(x_labels) > 6:
        plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    buf = io.BytesIO()
    fig_mpl.savefig(buf, format="png", dpi=150)
    plt.close(fig_mpl)
    buf.seek(0)
    image_b64 = base64.b64encode(buf.read()).decode("utf-8")

    return {
        "dataset": dataset_name,
        "title": title,
        "local_path": str(local_path),
        "blob_name": filename,
        "image_b64": image_b64,
    }


def build_and_upload_chart_htmls(
    dfs: Dict[str, pd.DataFrame],
    chart_plan: dict,
    connection_string: str,
    container_name: str,
    blob_prefix: str = "charts/",
) -> Tuple[List[str], List[dict]]:
    """
    Generates interactive HTML charts from the AI chart plan, uploads them to
    Blob Storage, and returns local temp file paths and per-chart dicts containing
    a base64 PNG (for email inline embedding) and a 7-day SAS URL (for interactive viewing).

    Files are written to a temp directory that persists for the lifetime of the
    process. The Container App Job exits after send, so no explicit cleanup is
    needed.

    Args:
        dfs: Mapping of dataset name to DataFrame.
        chart_plan: AI-generated chart plan dict.
        connection_string: Azure Storage connection string.
        container_name: Blob container to upload charts into (e.g. 'bi-reports').
        blob_prefix: Prefix applied to every blob name inside the container.

    Returns:
        Tuple of (local HTML paths, list of {title, image_b64, sas_url} dicts for email).
    """
    blob_service = BlobServiceClient.from_connection_string(connection_string)
    container = blob_service.get_container_client(container_name)

    tmp_dir = Path(tempfile.mkdtemp(prefix="hitachi_charts_"))
    local_paths: List[str] = []
    chart_images: List[dict] = []

    # SAS tokens expire after 7 days (enough time for the recipient to act)
    sas_expiry = datetime.now(timezone.utc) + timedelta(days=7)

    datasets = chart_plan.get("datasets", [])
    for dataset_entry in datasets:
        dataset_name = dataset_entry.get("dataset_name")
        chart_specs = dataset_entry.get("charts", [])

        if dataset_name not in dfs:
            print(f"[WARN] Dataset from chart plan not found: {dataset_name}")
            continue

        df = dfs[dataset_name]
        print(f"[DEBUG] Processing planned charts for: {dataset_name}")

        for idx, spec in enumerate(chart_specs):
            try:
                entry = _render_chart_html(
                    df=df,
                    dataset_name=dataset_name,
                    spec=spec,
                    tmp_dir=tmp_dir,
                    idx=idx,
                )
                if entry is None:
                    print(f"[WARN] Skipped invalid/unrenderable chart spec: {spec}")
                    continue

                blob_name = f"{blob_prefix}{entry['blob_name']}"
                with open(entry["local_path"], "rb") as f:
                    container.get_blob_client(blob_name).upload_blob(
                        f, overwrite=True, content_settings=ContentSettings(content_type="text/html")
                    )

                # Build a time-limited SAS URL so email recipients can open the
                # interactive chart in their browser without any Azure login
                sas_token = generate_blob_sas(
                    account_name=blob_service.account_name,
                    container_name=container_name,
                    blob_name=blob_name,
                    account_key=blob_service.credential.account_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=sas_expiry,
                )
                sas_url = (
                    f"https://{blob_service.account_name}.blob.core.windows.net"
                    f"/{container_name}/{blob_name}?{sas_token}"
                )

                print(f"[DEBUG] Uploaded chart to blob: {container_name}/{blob_name}")
                local_paths.append(entry["local_path"])
                chart_images.append({
                    "title": entry["title"],
                    "image_b64": entry["image_b64"],
                    "sas_url": sas_url,
                })

            except Exception as e:
                print(f"[ERROR] Failed to render chart for {dataset_name}: {e}")

    print(f"[DEBUG] Total HTML charts generated and uploaded: {len(local_paths)}")
    return local_paths, chart_images
