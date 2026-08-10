import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  FormControl,
  Grid,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { buildResumePlan, resumeDocxDownloadUrl, resumePdfDownloadUrl } from "../api/client";
import type { ExportPreferences, ResumePlan } from "../types/api";

interface Props {
  jobId: number;
  plan: ResumePlan | null;
  onPlanReady: (plan: ResumePlan) => void;
}

const TEMPLATE_OPTIONS = [
  "azurill",
  "bronzor",
  "chikorita",
  "ditgar",
  "ditto",
  "gengar",
  "glalie",
  "kakuna",
  "lapras",
  "leafish",
  "meowth",
  "onyx",
  "pikachu",
  "rhyhorn",
  "scizor",
] as const;

const PAGE_FORMAT_OPTIONS = ["letter", "a4"] as const;

/** Generate Resume button, quality/coverage summary, markdown preview, exports. */
export default function ResumeGenerationSection({ jobId, plan, onPlanReady }: Props) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportPreferences, setExportPreferences] = useState<ExportPreferences>({
    reactive_resume_template: "onyx",
    reactive_resume_page_format: "letter",
  });

  useEffect(() => {
    if (plan?.export_preferences) {
      setExportPreferences(plan.export_preferences);
    }
  }, [plan]);

  async function handleGenerate() {
    setError(null);
    setGenerating(true);
    try {
      const newPlan = await buildResumePlan(jobId, {
        export_preferences: exportPreferences,
      });
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
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, sm: 6 }}>
          <FormControl fullWidth size="small">
            <InputLabel id="resume-template-label">Resume Template</InputLabel>
            <Select
              labelId="resume-template-label"
              label="Resume Template"
              value={exportPreferences.reactive_resume_template}
              onChange={(event) =>
                setExportPreferences((current) => ({
                  ...current,
                  reactive_resume_template: event.target.value,
                }))
              }
            >
              {TEMPLATE_OPTIONS.map((template) => (
                <MenuItem key={template} value={template}>
                  {template}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <FormControl fullWidth size="small">
            <InputLabel id="resume-page-format-label">Page Format</InputLabel>
            <Select
              labelId="resume-page-format-label"
              label="Page Format"
              value={exportPreferences.reactive_resume_page_format}
              onChange={(event) =>
                setExportPreferences((current) => ({
                  ...current,
                  reactive_resume_page_format: event.target.value,
                }))
              }
            >
              {PAGE_FORMAT_OPTIONS.map((format) => (
                <MenuItem key={format} value={format}>
                  {format.toUpperCase()}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
      </Grid>
      {generating && <LinearProgress sx={{ mb: 2 }} />}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Alert severity="info" sx={{ mb: 2 }}>
        PDF export: {plan?.export_capabilities.pdf_renderer === "reactive-resume" ? "Reactive Resume" : "Local fallback"}
        {" | "}
        Template: {exportPreferences.reactive_resume_template}
        {" | "}
        Page format: {exportPreferences.reactive_resume_page_format.toUpperCase()}
        {" | "}
        DOCX export: {plan?.export_capabilities.docx_renderer ?? "local"}
      </Alert>

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
              href={resumePdfDownloadUrl(jobId, exportPreferences)}
            >
              Download PDF
            </Button>
          </Stack>
        </>
      )}
    </Paper>
  );
}
