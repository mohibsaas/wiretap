/** Client-side PDF of the metrics shown on a report detail page. */

import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import {
  REPORT_CATEGORIES,
  categoryLabel,
  type ReportView,
} from "@/lib/reports";

const GREEN: [number, number, number] = [10, 149, 81];
const DANGER: [number, number, number] = [192, 57, 43];
const INK: [number, number, number] = [41, 41, 39];
const MUTED: [number, number, number] = [138, 137, 132];
const LINE: [number, number, number] = [216, 214, 209];
const WASH: [number, number, number] = [249, 248, 246];
const MID: [number, number, number] = [5, 105, 56];

const PAGE_W = 612;
const MARGIN = 44;

export function downloadReportPdf(report: ReportView): void {
  const doc = new jsPDF({ unit: "pt", format: "letter" });
  const maxX = PAGE_W - MARGIN;
  let y = 48;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...GREEN);
  doc.text("WIRETAP", MARGIN, y);

  doc.setFont("helvetica", "normal");
  doc.setTextColor(...MUTED);
  doc.text("Evaluation report", maxX, y, { align: "right" });
  y += 22;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(20);
  doc.setTextColor(...INK);
  const title = pdfText(report.name || "Report");
  const titleLines = doc.splitTextToSize(title, maxX - MARGIN);
  doc.text(titleLines, MARGIN, y);
  y += titleLines.length * 24 + 4;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(...MUTED);
  doc.text(
    pdfText(
      `${report.suiteId}  ·  ${report.agent}  ·  v-${report.hash}  ·  Issued ${report.issued}`,
    ),
    MARGIN,
    y,
  );
  y += 28;

  y = sectionLabel(doc, "Overall score", y);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(36);
  doc.setTextColor(...INK);
  doc.text(report.overall == null ? "—" : String(report.overall), MARGIN, y + 28);
  const scoreWidth = doc.getTextWidth(
    report.overall == null ? "—" : String(report.overall),
  );
  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  doc.setTextColor(...MUTED);
  doc.text("/ 100", MARGIN + scoreWidth + 8, y + 28);

  const clean = report.status === "Clean";
  drawPill(
    doc,
    MARGIN + scoreWidth + 56,
    y + 12,
    report.status,
    clean ? GREEN : DANGER,
  );
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text("90 or above ships", MARGIN + scoreWidth + 56, y + 36);
  y += 52;

  const summary: [string, string][] = [
    ["Categories covered", `${report.covered.length} of ${REPORT_CATEGORIES.length}`],
    ["Simulations played", String(report.simCount)],
    ["Checks passed", `${report.passedCount} / ${report.simCount}`],
    ["Agent", report.agent],
    ["Period", report.period],
    ["Valid to", report.expires],
  ];
  autoTable(doc, {
    startY: y,
    margin: { left: MARGIN, right: MARGIN },
    body: summary.map(([k, v]) => [pdfText(k), pdfText(v)]),
    theme: "plain",
    styles: {
      font: "helvetica",
      fontSize: 9,
      cellPadding: { top: 5, bottom: 5, left: 0, right: 0 },
      textColor: INK,
      overflow: "linebreak",
    },
    columnStyles: {
      0: { textColor: MUTED, cellWidth: 180 },
      1: { fontStyle: "bold", halign: "right" },
    },
    didDrawCell: (data) => {
      if (data.section === "body") {
        doc.setDrawColor(...LINE);
        doc.setLineWidth(0.5);
        doc.line(
          data.cell.x,
          data.cell.y + data.cell.height,
          data.cell.x + data.cell.width,
          data.cell.y + data.cell.height,
        );
      }
    },
  });
  y = tableEnd(doc) + 22;

  y = ensureSpace(doc, y, 80);
  y = sectionLabel(doc, "Score by category", y);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text(
    `Only the categories this run was pointed at. ${report.covered.length} of ${REPORT_CATEGORIES.length} covered.`,
    MARGIN,
    y,
  );
  y += 14;

  const catRows = REPORT_CATEGORIES.map((c) => {
    const v = report.scores[c.id];
    return [c.label, v == null ? "—" : String(v), v];
  });
  autoTable(doc, {
    startY: y,
    margin: { left: MARGIN, right: MARGIN },
    body: catRows.map(([label, score]) => [
      pdfText(String(label)),
      "",
      String(score),
    ]),
    theme: "plain",
    styles: {
      font: "helvetica",
      fontSize: 9,
      cellPadding: { top: 6, bottom: 6, left: 0, right: 0 },
      textColor: INK,
    },
    columnStyles: {
      0: { cellWidth: 120 },
      1: { cellWidth: 360 },
      2: { cellWidth: 36, fontStyle: "bold", halign: "right" },
    },
    didDrawCell: (data) => {
      if (data.section !== "body" || data.column.index !== 1) return;
      const raw = catRows[data.row.index]?.[2];
      const value = typeof raw === "number" ? raw : null;
      const barW = Math.max(40, data.cell.width - 12);
      const barX = data.cell.x;
      const barY = data.cell.y + data.cell.height / 2 - 3;
      doc.setFillColor(...WASH);
      doc.roundedRect(barX, barY, barW, 6, 3, 3, "F");
      if (value != null) {
        const fill = value >= 85 ? GREEN : value >= 70 ? MID : DANGER;
        doc.setFillColor(...fill);
        doc.roundedRect(barX, barY, Math.max(4, (barW * value) / 100), 6, 3, 3, "F");
      }
    },
  });
  y = tableEnd(doc) + 10;

  if (!report.full) {
    y = ensureSpace(doc, y, 36);
    doc.setFillColor(...WASH);
    doc.roundedRect(MARGIN, y, maxX - MARGIN, 32, 6, 6, "F");
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(...MUTED);
    const note = pdfText(
      `Not covered by this run: ${report.missing.map(categoryLabel).join(", ")}. Overall averages only the ${report.covered.length} ${report.covered.length === 1 ? "category" : "categories"} that ran.`,
    );
    doc.text(doc.splitTextToSize(note, maxX - MARGIN - 16), MARGIN + 8, y + 12);
    y += 44;
  } else {
    y += 8;
  }

  y = ensureSpace(doc, y, 80);
  const earned = report.badges.filter((b) => b.met).length;
  y = sectionLabel(doc, "Badges", y);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  const badgeIntro = report.full
    ? earned
      ? `${earned} of 4 badges earned. Full coverage, so every badge was assessed.`
      : "No badges earned from this run."
    : `Badges locked. A badge needs one run across all ${REPORT_CATEGORIES.length} categories. This run covered ${report.covered.length}.`;
  doc.text(pdfText(badgeIntro), MARGIN, y);
  y += 12;

  autoTable(doc, {
    startY: y,
    margin: { left: MARGIN, right: MARGIN },
    head: [["Badge", "Status", "Score", "Rule"]],
    body: report.badges.map((b) => [
      pdfText(b.name),
      b.locked ? "Locked" : b.met ? "Earned" : "Not attained",
      b.locked || b.value == null ? "—" : String(b.value),
      pdfText(
        b.locked
          ? `Needs all ${REPORT_CATEGORIES.length} categories`
          : b.met
            ? `Valid to ${report.expires}`
            : `Needs ${b.min}, scored ${b.value}`,
      ),
    ]),
    theme: "plain",
    headStyles: {
      font: "helvetica",
      fontStyle: "bold",
      fontSize: 8,
      textColor: MUTED,
      fillColor: WASH,
      cellPadding: 6,
    },
    styles: {
      font: "helvetica",
      fontSize: 8,
      textColor: INK,
      cellPadding: 6,
      overflow: "linebreak",
      lineColor: LINE,
      lineWidth: 0.4,
    },
    columnStyles: {
      0: { cellWidth: 150, fontStyle: "bold" },
      1: { cellWidth: 80 },
      2: { cellWidth: 48, halign: "right" },
      3: { cellWidth: "auto" },
    },
    didParseCell: (data) => {
      if (data.section !== "body" || data.column.index !== 1) return;
      const text = String(data.cell.raw || "");
      if (text === "Earned") data.cell.styles.textColor = GREEN;
      if (text === "Not attained") data.cell.styles.textColor = DANGER;
    },
  });
  y = tableEnd(doc) + 22;

  y = ensureSpace(doc, y, 80);
  y = sectionLabel(doc, "Simulations", y);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text(
    pdfText(
      `Every simulation in this run · ${report.simCount}. One row per scenario the simulator played.`,
    ),
    MARGIN,
    y,
  );
  y += 10;

  autoTable(doc, {
    startY: y,
    margin: { left: MARGIN, right: MARGIN },
    head: [["Test", "Expected outcome", "Result", "Suggested fix"]],
    body: report.rows.map((row) => {
      const sim = row.simulation;
      const name = pdfText(sim.scenario_name || sim.scenario_id);
      const cat = pdfText(row.categoryLabel);
      return [
        `${name}\n${cat}`,
        pdfText(row.expected || "—"),
        row.score == null ? "—" : String(row.score),
        pdfText(row.fix || "—"),
      ];
    }),
    theme: "plain",
    headStyles: {
      font: "helvetica",
      fontStyle: "bold",
      fontSize: 8,
      textColor: MUTED,
      fillColor: WASH,
      cellPadding: 6,
    },
    styles: {
      font: "helvetica",
      fontSize: 8,
      textColor: INK,
      cellPadding: 6,
      overflow: "linebreak",
      valign: "top",
      lineColor: LINE,
      lineWidth: 0.4,
    },
    columnStyles: {
      0: { cellWidth: 130 },
      1: { cellWidth: 150 },
      2: { cellWidth: 44, fontStyle: "bold", halign: "right" },
      3: { cellWidth: "auto" },
    },
    didParseCell: (data) => {
      if (data.section !== "body" || data.column.index !== 2) return;
      const row = report.rows[data.row.index];
      if (!row) return;
      data.cell.styles.textColor = row.flagged ? DANGER : GREEN;
    },
  });

  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i += 1) {
    doc.setPage(i);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(...MUTED);
    doc.text(
      pdfText(`Wiretap  ·  v-${report.hash}  ·  scores and findings only`),
      MARGIN,
      770,
    );
    doc.text(`${i} / ${pages}`, maxX, 770, { align: "right" });
  }

  doc.save(`wiretap-report-${report.hash}.pdf`);
}

function sectionLabel(doc: jsPDF, label: string, y: number): number {
  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text(label.toUpperCase(), MARGIN, y);
  return y + 16;
}

function drawPill(
  doc: jsPDF,
  x: number,
  y: number,
  label: string,
  color: [number, number, number],
): void {
  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  const w = doc.getTextWidth(label) + 16;
  doc.setDrawColor(...color);
  doc.setLineWidth(0.8);
  doc.roundedRect(x, y, w, 16, 8, 8, "S");
  doc.setTextColor(...color);
  doc.text(label, x + 8, y + 11);
}

function tableEnd(doc: jsPDF): number {
  const last = (
    doc as jsPDF & { lastAutoTable?: { finalY: number } }
  ).lastAutoTable;
  return last?.finalY ?? 72;
}

function ensureSpace(doc: jsPDF, y: number, need: number): number {
  if (y + need < 740) return y;
  doc.addPage();
  return 48;
}

/** Helvetica / WinAnsi — drop characters the built-in font cannot encode. */
function pdfText(value: string): string {
  return String(value || "")
    .replace(/℣/g, "v")
    .replace(/[—–]/g, "-")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/…/g, "...")
    .replace(/·/g, "-")
    .replace(/[^\t\n\r\u0020-\u007E]/g, "");
}
