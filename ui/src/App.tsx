import { useState } from "react";
import {
  AppBar,
  Box,
  Button,
  CircularProgress,
  Container,
  Grid,
  Stack,
  Toolbar,
  Typography,
} from "@mui/material";
import PersonIcon from "@mui/icons-material/Person";
import JobInputPanel from "./components/JobInputPanel";
import AnalysisResults from "./components/AnalysisResults";
import GapAnalysisSection from "./components/GapAnalysisSection";
import ResumeStrategySection from "./components/ResumeStrategySection";
import AccomplishmentsSection from "./components/AccomplishmentsSection";
import ResumeGenerationSection from "./components/ResumeGenerationSection";
import ProfileDialog from "./components/ProfileDialog";
import { runAnalysis } from "./api/client";
import type { JobPostingResponse, ResumePlan, ScoringResultResponse } from "./types/api";

function App() {
  const [job, setJob] = useState<JobPostingResponse | null>(null);
  const [scoring, setScoring] = useState<ScoringResultResponse | null>(null);
  const [resumePlan, setResumePlan] = useState<ResumePlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleJobReady(newJob: JobPostingResponse) {
    setJob(newJob);
    setScoring(null);
    setResumePlan(null);
    setError(null);
    setAnalyzing(true);
    try {
      const result = await runAnalysis(newJob.id);
      setScoring(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="static" color="primary" enableColorOnDark>
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            CareerAgent Dashboard
          </Typography>
          <Button
            color="inherit"
            startIcon={<PersonIcon />}
            onClick={() => setProfileOpen(true)}
          >
            Profile
          </Button>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, md: 4 }}>
            <JobInputPanel onJobReady={handleJobReady} busy={busy} setBusy={setBusy} />
          </Grid>

          <Grid size={{ xs: 12, md: 8 }}>
            <Stack spacing={3}>
              {analyzing && (
                <Stack sx={{ alignItems: "center", py: 6 }}>
                  <CircularProgress />
                  <Typography variant="body2" sx={{ mt: 2 }} color="text.secondary">
                    Analyzing job posting…
                  </Typography>
                </Stack>
              )}

              {error && (
                <Typography color="error" variant="body2">
                  {error}
                </Typography>
              )}

              {!analyzing && !job && !error && (
                <Stack sx={{ alignItems: "center", py: 8 }}>
                  <Typography variant="body1" color="text.secondary">
                    Paste or upload a job posting on the left, then click "Analyze Job"
                    to see match scores, gap analysis, and a tailored resume strategy.
                  </Typography>
                </Stack>
              )}

              {scoring && (
                <>
                  <AnalysisResults scoring={scoring.scoring_data.scoring} />
                  <GapAnalysisSection gapAnalysis={scoring.scoring_data.gap_analysis} />
                </>
              )}

              {resumePlan && (
                <>
                  <ResumeStrategySection strategy={resumePlan.strategy} />
                  <AccomplishmentsSection selection={resumePlan.selection} />
                </>
              )}

              {job && scoring && (
                <ResumeGenerationSection
                  jobId={job.id}
                  plan={resumePlan}
                  onPlanReady={setResumePlan}
                />
              )}
            </Stack>
          </Grid>
        </Grid>
      </Container>

      <ProfileDialog open={profileOpen} onClose={() => setProfileOpen(false)} />
    </Box>
  );
}

export default App;
