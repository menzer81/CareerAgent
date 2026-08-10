import { useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  ButtonGroup,
  Paper,
  TextField,
  Typography,
} from "@mui/material";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { ingestJobText, uploadJobFile } from "../api/client";
import type { JobPostingResponse } from "../types/api";

interface Props {
  onJobReady: (job: JobPostingResponse) => void;
  busy: boolean;
  setBusy: (busy: boolean) => void;
}

/** Left panel: paste or upload a job posting, then trigger ingestion. */
export default function JobInputPanel({ onJobReady, busy, setBusy }: Props) {
  const [rawText, setRawText] = useState("");
  const [mode, setMode] = useState<"paste" | "upload">("paste");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canSubmit =
    !busy && (mode === "paste" ? rawText.trim().length >= 50 : file !== null);

  async function handleAnalyze() {
    setError(null);
    setBusy(true);
    try {
      const job =
        mode === "paste"
          ? await ingestJobText({ raw_text: rawText })
          : await uploadJobFile(file as File);
      onJobReady(job);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Paper elevation={2} sx={{ p: 2, display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="h6">Job Posting</Typography>

      <ButtonGroup size="small" fullWidth>
        <Button
          variant={mode === "paste" ? "contained" : "outlined"}
          onClick={() => setMode("paste")}
        >
          Paste Text
        </Button>
        <Button
          variant={mode === "upload" ? "contained" : "outlined"}
          onClick={() => setMode("upload")}
        >
          Upload File
        </Button>
      </ButtonGroup>

      {mode === "paste" ? (
        <TextField
          label="Job posting text"
          placeholder="Paste the full job description here…"
          multiline
          minRows={12}
          maxRows={20}
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          fullWidth
        />
      ) : (
        <Box
          sx={{
            border: "1px dashed",
            borderColor: "divider",
            borderRadius: 2,
            p: 3,
            textAlign: "center",
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md"
            hidden
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button
            variant="outlined"
            startIcon={<UploadFileIcon />}
            onClick={() => fileInputRef.current?.click()}
          >
            Choose File
          </Button>
          <Typography variant="body2" sx={{ mt: 1 }} color="text.secondary">
            {file ? file.name : "Supported: txt, md (plain text job postings)"}
          </Typography>
        </Box>
      )}

      {error && <Alert severity="error">{error}</Alert>}

      <Button
        variant="contained"
        size="large"
        disabled={!canSubmit}
        onClick={handleAnalyze}
      >
        {busy ? "Analyzing…" : "Analyze Job"}
      </Button>
    </Paper>
  );
}

function extractErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "response" in err) {
    const response = (err as { response?: { status?: number; data?: { detail?: string } } })
      .response;
    if (response?.status === 502) {
      return "Cannot reach the API server at http://localhost:8000. Start the backend (for example: uvicorn app.main:app --reload) and try again.";
    }
    if (response?.data?.detail) return response.data.detail;
  }

  if (err && typeof err === "object" && "message" in err) {
    const message = String((err as { message?: unknown }).message ?? "");
    if (/ECONNREFUSED|Network Error|Failed to fetch/i.test(message)) {
      return "Cannot connect to the API server at http://localhost:8000. Make sure the backend is running and then retry Analyze Job.";
    }
  }

  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
