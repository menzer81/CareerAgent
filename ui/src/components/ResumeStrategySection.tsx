import { Chip, Grid, Paper, Stack, Typography } from "@mui/material";
import type { ResumeStrategy } from "../types/api";

interface Props {
  strategy: ResumeStrategy;
}

/** Selected persona plus emphasize / deemphasize / omit guidance. */
export default function ResumeStrategySection({ strategy }: Props) {
  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Resume Strategy
      </Typography>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 2 }}>
        <Typography variant="body1">Selected Persona:</Typography>
        <Chip label={strategy.persona} color="primary" />
      </Stack>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="subtitle2" color="success.main" gutterBottom>
            Emphasize
          </Typography>
          <Stack spacing={0.5}>
            {strategy.emphasize.map((item) => (
              <Typography key={item} variant="body2">
                • {item}
              </Typography>
            ))}
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="subtitle2" color="warning.main" gutterBottom>
            Deemphasize
          </Typography>
          <Stack spacing={0.5}>
            {strategy.deemphasize.map((item) => (
              <Typography key={item} variant="body2">
                • {item}
              </Typography>
            ))}
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            Omit
          </Typography>
          <Stack spacing={0.5}>
            {strategy.omit.map((item) => (
              <Typography key={item} variant="body2">
                • {item}
              </Typography>
            ))}
          </Stack>
        </Grid>
      </Grid>
    </Paper>
  );
}
