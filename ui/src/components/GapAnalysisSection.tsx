import { Chip, Grid, Paper, Stack, Typography } from "@mui/material";
import type { GapAnalysis } from "../types/api";

interface Props {
  gapAnalysis: GapAnalysis;
}

/** Strengths vs. potential gaps, drawn from the GapAnalysis payload. */
export default function GapAnalysisSection({ gapAnalysis }: Props) {
  const gaps = [
    ...gapAnalysis.missing_experiences,
    ...gapAnalysis.missing_keywords,
    ...gapAnalysis.missing_certifications,
    ...gapAnalysis.missing_leadership_signals,
  ];

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Gap Analysis
      </Typography>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Typography variant="subtitle2" gutterBottom>
            Strengths
          </Typography>
          <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1 }}>
            {gapAnalysis.strengths.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                None identified.
              </Typography>
            )}
            {gapAnalysis.strengths.map((s) => (
              <Chip key={s} label={s} color="success" variant="outlined" />
            ))}
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Typography variant="subtitle2" gutterBottom>
            Potential Gaps
          </Typography>
          <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1 }}>
            {gaps.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                None identified.
              </Typography>
            )}
            {gaps.map((g) => (
              <Chip key={g} label={g} color="warning" variant="outlined" />
            ))}
          </Stack>
        </Grid>
        {gapAnalysis.risks.length > 0 && (
          <Grid size={{ xs: 12 }}>
            <Typography variant="subtitle2" gutterBottom>
              Risks
            </Typography>
            <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1 }}>
              {gapAnalysis.risks.map((r) => (
                <Chip key={r} label={r} color="error" variant="outlined" />
              ))}
            </Stack>
          </Grid>
        )}
      </Grid>
    </Paper>
  );
}

