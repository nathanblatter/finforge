import io

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# FinForge palette
_SKY_BLUE = HexColor("#0ea5e9")
_DARK_TEXT = HexColor("#334155")
_ALT_ROW = HexColor("#f8fafc")
_WHITE = colors.white


class FinForgePDFBuilder:
    """Reportlab-based PDF document builder for FinForge financial reports."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        self._buffer = io.BytesIO()
        self._elements: list = []

        self._doc = SimpleDocTemplate(
            self._buffer,
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        self._page_width = letter[0] - 1.5 * inch  # usable width

        # ── base styles ──────────────────────────────────────────────
        self._styles = getSampleStyleSheet()

        self._styles.add(
            ParagraphStyle(
                "FF_Title",
                parent=self._styles["Title"],
                fontSize=26,
                leading=32,
                textColor=_DARK_TEXT,
                alignment=TA_CENTER,
                spaceAfter=4,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "FF_Subtitle",
                parent=self._styles["Normal"],
                fontSize=13,
                leading=18,
                textColor=_SKY_BLUE,
                alignment=TA_CENTER,
                spaceAfter=20,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "FF_Heading",
                parent=self._styles["Heading2"],
                fontSize=16,
                leading=22,
                textColor=_SKY_BLUE,
                fontName="Helvetica-Bold",
                spaceAfter=8,
                spaceBefore=14,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "FF_Body",
                parent=self._styles["Normal"],
                fontSize=10,
                leading=14,
                textColor=_DARK_TEXT,
                alignment=TA_LEFT,
                spaceAfter=6,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "FF_Cell",
                parent=self._styles["Normal"],
                fontSize=9,
                leading=12,
                textColor=_DARK_TEXT,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "FF_CellWhite",
                parent=self._styles["Normal"],
                fontSize=9,
                leading=12,
                textColor=_WHITE,
            )
        )

        # ── title page header ────────────────────────────────────────
        self._elements.append(Paragraph(title, self._styles["FF_Title"]))
        if subtitle:
            self._elements.append(Paragraph(subtitle, self._styles["FF_Subtitle"]))

        # thin sky-blue rule under the header
        rule = Table(
            [[""]],
            colWidths=[self._page_width],
            rowHeights=[2],
        )
        rule.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _SKY_BLUE),
                    ("LINEBELOW", (0, 0), (-1, -1), 0, _SKY_BLUE),
                ]
            )
        )
        self._elements.append(rule)
        self._elements.append(Spacer(1, 0.25 * inch))

    # ── public API ───────────────────────────────────────────────────

    def add_heading(self, text: str) -> None:
        """Section heading in sky-blue, bold."""
        self._elements.append(Paragraph(text, self._styles["FF_Heading"]))

    def add_text(self, text: str) -> None:
        """Regular body paragraph."""
        self._elements.append(Paragraph(text, self._styles["FF_Body"]))

    def add_summary_table(self, rows: list[tuple[str, str]]) -> None:
        """Two-column key/value summary table (e.g. 'Net Worth' | '$5,000')."""
        cell = self._styles["FF_Cell"]
        data = [[Paragraph(k, cell), Paragraph(v, cell)] for k, v in rows]

        col_w = self._page_width / 2
        table = Table(data, colWidths=[col_w, col_w])

        style_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ]
        # alternating row backgrounds
        for i in range(len(data)):
            bg = _ALT_ROW if i % 2 == 0 else _WHITE
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))

        table.setStyle(TableStyle(style_cmds))
        self._elements.append(table)
        self._elements.append(Spacer(1, 0.15 * inch))

    def add_data_table(self, headers: list[str], rows: list[list[str]]) -> None:
        """Full data table with sky-blue header and alternating row shading."""
        hdr_style = self._styles["FF_CellWhite"]
        cell_style = self._styles["FF_Cell"]

        header_row = [Paragraph(h, hdr_style) for h in headers]
        data = [header_row] + [
            [Paragraph(str(c), cell_style) for c in row] for row in rows
        ]

        n_cols = len(headers)
        col_w = self._page_width / n_cols
        table = Table(data, colWidths=[col_w] * n_cols)

        style_cmds = [
            # header row
            ("BACKGROUND", (0, 0), (-1, 0), _SKY_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            # global
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#e2e8f0")),
        ]
        # alternating body rows (index 1+)
        for i in range(1, len(data)):
            bg = _ALT_ROW if i % 2 == 1 else _WHITE
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))

        table.setStyle(TableStyle(style_cmds))
        self._elements.append(table)
        self._elements.append(Spacer(1, 0.15 * inch))

    def add_chart(self, fig) -> None:
        """Embed a matplotlib Figure as a PNG image, preserving aspect ratio."""
        import matplotlib.pyplot as plt

        img_buf = io.BytesIO()
        fig.savefig(img_buf, format="png", dpi=150, bbox_inches="tight")
        img_buf.seek(0)

        # Get actual figure dimensions to compute proper aspect ratio
        fig_w, fig_h = fig.get_size_inches()
        target_width = min(6.0, self._page_width / inch)
        scale = target_width / fig_w
        target_height = fig_h * scale

        img = Image(img_buf, width=target_width * inch, height=target_height * inch)
        img.hAlign = "CENTER"
        self._elements.append(img)
        self._elements.append(Spacer(1, 0.15 * inch))
        plt.close(fig)

    def add_spacer(self, height: float = 0.3) -> None:
        """Add vertical whitespace (height in inches)."""
        self._elements.append(Spacer(1, height * inch))

    def build(self) -> io.BytesIO:
        """Finalize the PDF and return the BytesIO buffer (rewound to 0)."""
        self._doc.build(self._elements)
        self._buffer.seek(0)
        return self._buffer
