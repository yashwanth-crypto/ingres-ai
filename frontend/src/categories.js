/**
 * CGWB assessment categories, worst to best.
 *
 * Shared rather than declared per component: the map and the bar chart often
 * appear in the same answer, and a district shown red on one and orange on the
 * other would read as two different findings.
 */
export const CATEGORY_COLOR = {
  "over-exploited": "#b91c1c",
  critical: "#ea580c",
  "semi-critical": "#d97706",
  safe: "#15803d",
};

// Districts CGWB assessed but the monitoring network does not reach.
export const NO_CATEGORY = "#78716c";

export const CATEGORY_ORDER = [
  "over-exploited",
  "critical",
  "semi-critical",
  "safe",
];

export function categoryColor(category) {
  return CATEGORY_COLOR[category] ?? NO_CATEGORY;
}
