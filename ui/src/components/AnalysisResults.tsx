import { Box, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import type { ScoringBreakdown } from "../types/api";

interface Props {
  scoring: ScoringBreakdown;
}

const RECOMMENDATION_COLOR: Record<string, "success" | "info" | "warning" | "error"> = {
  "Strong Apply": "success",
  Apply: "info",
  "Stretch Opportunity": "warning",
  "Low Priority": "error",
};

const DIMENSIONS: Array<{ key: keyof ScoringBreakdown; label: string }> = [
  { key: "leadership_match", label: "Leadership" },
  { key: "technical_match", label: "Technical" },
  { key: "cloud_match", label: "Cloud" },
  { key: "ai_match", label: "AI" },
  { key: "management_scope_match", label: "Scope" },
  { key: "industry_match", label: "Industry" },
];

/** Center panel: overall fit score, recommendation, and per-dimension breakdown. */
export default function AnalysisResults({ scoring }: Props) {
  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Job Analysis Results
      </Typography>

      <Stack direction="row" spacing={2} sx={{ mb: 1, alignItems: "baseline" }}>
        <Typography variant="h3">{Math.round(scoring.overall_score)}</Typography>
        <Typography variant="body2" color="text.secondary">
          Overall Match Score
        </Typography>
        <Chip
          label={scoring.recommendation}
          color={RECOMMENDATION_COLOR[scoring.recommendation] ?? "default"}
        />
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {scoring.recommendation_reasoning}
      </Typography>

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Score Breakdown
      </Typography>
      <Stack spacing={1.5}>
        {DIMENSIONS.map(({ key, label }) => {
          const dim = scoring[key];
          if (typeof dim === "string" || typeof dim === "number") return null;
          return (
            <Box key={key}>
              <Stack direction="row" sx={{ justifyContent: "space-between" }}>
                <Typography variant="body2">{label}</Typography>
                <Typography variant="body2">{Math.round(dim.score)}</Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={dim.score}
                sx={{ height: 8, borderRadius: 4 }}
              />
            </Box>
          );
        })}
      </Stack>
    </Paper>
  );
}
