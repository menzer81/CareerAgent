import { useRef, useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import { getProfile, refreshProfileFromCanonicalFile, uploadProfile } from "../api/client";
import type { CandidateProfileResponse } from "../types/api";

interface Props {
  open: boolean;
  onClose: () => void;
}

/** Dialog for viewing/uploading the candidate profile JSON. */
export default function ProfileDialog({ open, onClose }: Props) {
  const [profile, setProfile] = useState<CandidateProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleLoad() {
    setError(null);
    setLoading(true);
    try {
      const data = await getProfile();
      setProfile(data);
    } catch {
      setError("No candidate profile found. Upload one below.");
    } finally {
      setLoading(false);
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setLoading(true);
    try {
      const data = await uploadProfile(file);
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload profile.");
    } finally {
      setLoading(false);
      e.target.value = "";
    }
  }

  async function handleRefresh() {
    setError(null);
    setLoading(true);
    try {
      const data = await refreshProfileFromCanonicalFile();
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh profile.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Candidate Profile</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Button variant="outlined" onClick={handleLoad} disabled={loading}>
            Load Current Profile
          </Button>
          <Button variant="outlined" onClick={handleRefresh} disabled={loading}>
            Refresh From JSON
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            hidden
            onChange={handleFileChange}
          />
          <Button
            variant="outlined"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
          >
            Upload Profile JSON
          </Button>

          {error && <Alert severity="warning">{error}</Alert>}

          {profile && (
            <Stack spacing={0.5}>
              <Typography variant="subtitle1">{profile.full_name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {profile.profile_data.current_title ?? ""}
              </Typography>
            </Stack>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
