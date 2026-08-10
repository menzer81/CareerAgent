import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Grid,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { buildResumePlan, resumeDocxDownloadUrl, resumePdfDownloadUrl } from "../api/client";
import type { ResumePlan } from "../types/api";

interface Props {
  jobId: number;
  plan: ResumePlan | null;
  onPlanReady: (plan: ResumePlan) => void;
}

/** Generate Resume button, quality/coverage summary, markdown preview, exports. */
export default function ResumeGenerationSection({ jobId, plan, onPlanReady }: Props) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setError(null);
    setGenerating(true);
    try {
      const newPlan = await buildResumePlan(jobId);
      onPlanReady(newPlan);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate resume.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Resume Generation
      </Typography>

      <Button variant="contained" onClick={handleGenerate} disabled={generating} sx={{ mb: 2 }}>
        {generating ? "Generating…" : "Generate Resume"}
      </Button>
      {generating && <LinearProgress sx={{ mb: 2 }} />}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {plan && (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 6, sm: 3 }}>
              <Typography variant="body2" color="text.secondary">
                Resume Quality Score
              </Typography>
              <Typography variant="h5">
                {Math.round(plan.quality_score.overall_resume_quality)}
              </Typography>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <Typography variant="body2" color="text.secondary">
                Keyword Coverage
              </Typography>
              <Typography variant="h5">
                {Math.round(plan.keyword_coverage.coverage_percent)}%
              </Typography>
            </Grid>
          </Grid>

          <Typography variant="subtitle2" gutterBottom>
            Resume Preview
          </Typography>
          <Box
            sx={{
              maxHeight: 480,
              overflowY: "auto",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              p: 2,
              mb: 2,
              bgcolor: "background.default",
            }}
          >
            {plan.markdown ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{plan.markdown}</ReactMarkdown>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No markdown generated.
              </Typography>
            )}
          </Box>

          <Stack direction="row" spacing={2}>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              component="a"
              href={resumeDocxDownloadUrl(jobId)}
            >
              Download DOCX
            </Button>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              component="a"
              href={resumePdfDownloadUrl(jobId)}
            >
              Download PDF
            </Button>
          </Stack>
        </>
      )}
    </Paper>
  );
}
