from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.io as pio
from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    PageBreak,
)


def _safe_name(name: str) -> str:
    return (
        name.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace(".csv", "")
    )


def verify_plotly_export_environment() -> None:
    """
    Ensure Chrome is available for Kaleido and verify static image export works.
    This allows `python main.py` to run end-to-end without manually running
    plotly_get_chrome first.
    """
    print("[DEBUG] Verifying Plotly/Kaleido export environment...")

    try:
        chrome_path = pio.get_chrome()
        print(f"[DEBUG] Chrome available for Kaleido at: {chrome_path}")
    except Exception as e:
        raise RuntimeError(
            "Chrome is not available for Kaleido and automatic installation failed."
        ) from e

    test_dir = Path("reports")
    test_dir.mkdir(parents=True, exist_ok=True)
    test_path = test_dir / "plotly_healthcheck.png"

    try:
        df = px.data.tips()
        fig = px.bar(df, x="day", y="total_bill", title="Health Check")
        fig.write_image(str(test_path), width=800, height=500, scale=1)
    except Exception as e:
        raise RuntimeError(
            "Plotly static image export failed even though Chrome was found."
        ) from e

    if not test_path.exists():
        raise RuntimeError("Plotly health check did not create the expected PNG file.")

    print(f"[DEBUG] Plotly export health check passed: {test_path}")


def _save_plot(fig, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[DEBUG] About to write image: {output_path}")
    fig.write_image(str(output_path), width=1200, height=700, scale=2)
    print(f"[DEBUG] Finished writing image: {output_path}")


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


def _render_chart_from_spec(
    df: pd.DataFrame,
    dataset_name: str,
    spec: dict,
    output_dir: Path,
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

    output_path = output_dir / f"{_safe_name(dataset_name)}_{idx}_{chart_type}.png"
    _save_plot(fig, output_path)

    return {
        "dataset": dataset_name,
        "title": title,
        "path": str(output_path),
    }


def generate_chart_images_from_plan(
    dfs: Dict[str, pd.DataFrame],
    chart_plan: dict,
    charts_dir: str = "reports/charts",
) -> List[dict]:
    output_dir = Path(charts_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    chart_entries: List[dict] = []

    print(f"[DEBUG] Generating charts from AI plan into: {output_dir}")

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
                chart_entry = _render_chart_from_spec(
                    df=df,
                    dataset_name=dataset_name,
                    spec=spec,
                    output_dir=output_dir,
                    idx=idx,
                )
                if chart_entry:
                    chart_entries.append(chart_entry)
                else:
                    print(f"[WARN] Skipped invalid/unrenderable chart spec: {spec}")
            except Exception as e:
                print(f"[ERROR] Failed to render chart for {dataset_name}: {e}")

    print(f"[DEBUG] Total charts generated from AI plan: {len(chart_entries)}")
    return chart_entries


def build_visualization_pdf(
    dfs: Dict[str, pd.DataFrame],
    insights_text: Optional[str],
    chart_plan: dict,
    output_pdf_path: str = "reports/project_tracking_report.pdf",
) -> str:
    output_pdf = Path(output_pdf_path)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    print(f"[DEBUG] Building PDF at: {output_pdf}")

    chart_entries = generate_chart_images_from_plan(
        dfs=dfs,
        chart_plan=chart_plan,
        charts_dir=str(output_pdf.parent / "charts"),
    )
    print(f"[DEBUG] Chart entries: {chart_entries}")

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    body_style = styles["BodyText"]

    small_gray = ParagraphStyle(
        "SmallGray",
        parent=styles["BodyText"],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=8,
    )

    story = []

    story.append(Paragraph("AI-Powered Project Tracking Report", title_style))
    story.append(Spacer(1, 0.15 * inch))
    story.append(
        Paragraph(
            "Automatically generated visual summary of project tracking datasets.",
            small_gray,
        )
    )
    story.append(Spacer(1, 0.2 * inch))

    # if insights_text:
    #     story.append(Paragraph("AI Summary", heading_style))
    #     for block in insights_text.split("\n\n"):
    #         clean_block = block.strip().replace("\n", "<br/>")
    #         if clean_block:
    #             story.append(Paragraph(clean_block, body_style))
    #             story.append(Spacer(1, 0.12 * inch))
    #     story.append(PageBreak())

    if not chart_entries:
        story.append(
            Paragraph(
                "No charts could be generated from the AI chart plan.",
                body_style,
            )
        )
    else:
        current_dataset = None

        for entry in chart_entries:
            dataset = entry["dataset"]
            title = entry["title"]
            image_path = entry["path"]

            if current_dataset != dataset:
                if current_dataset is not None:
                    story.append(PageBreak())
                current_dataset = dataset
                story.append(Paragraph(f"Dataset: {dataset}", heading_style))
                story.append(Spacer(1, 0.12 * inch))

            story.append(Paragraph(title, body_style))
            story.append(Spacer(1, 0.08 * inch))

            img = PILImage.open(image_path)
            img_width, img_height = img.size
            aspect = img_height / img_width

            display_width = 6.8 * inch
            display_height = display_width * aspect

            if display_height > 8.0 * inch:
                display_height = 8.0 * inch
                display_width = display_height / aspect

            story.append(Image(image_path, width=display_width, height=display_height))
            story.append(Spacer(1, 0.2 * inch))

    print("[DEBUG] Finalizing PDF build...")
    doc.build(story)
    print("[DEBUG] PDF build complete.")

    return str(output_pdf)