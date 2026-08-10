import { Box, Chip, List, ListItem, ListItemText, Paper, Tooltip, Typography } from "@mui/material";
import type { AchievementSelectionResult } from "../types/api";

interface Props {
  selection: AchievementSelectionResult;
}

/** Top accomplishments chosen by the Achievement Selection Engine. */
export default function AccomplishmentsSection({ selection }: Props) {
  const rankingById = new Map(selection.rankings.map((r) => [r.id, r]));

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Top Accomplishments
      </Typography>
      <List dense>
        {selection.selected_accomplishment_ids.map((id, idx) => {
          const ranking = rankingById.get(id);
          return (
            <ListItem key={id} divider>
              <ListItemText
                primary={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Typography component="span" sx={{ fontWeight: 600 }}>
                      {idx + 1}. {id}
                    </Typography>
                    {ranking?.boosted && (
                      <Chip label="Boosted" size="small" color="secondary" />
                    )}
                    {ranking && (
                      <Typography component="span" variant="body2" color="text.secondary">
                        score {Math.round(ranking.ranking_score)}
                      </Typography>
                    )}
                  </Box>
                }
                secondary={
                  ranking?.ranking_reason.length ? (
                    <Tooltip title={ranking.ranking_reason.join(" · ")}>
                      <Typography
                        component="span"
                        variant="body2"
                        color="text.secondary"
                        noWrap
                        sx={{ display: "block" }}
                      >
                        {ranking.ranking_reason.join(" · ")}
                      </Typography>
                    </Tooltip>
                  ) : undefined
                }
              />
            </ListItem>
          );
        })}
        {selection.selected_accomplishment_ids.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No accomplishments selected yet.
          </Typography>
        )}
      </List>
    </Paper>
  );
}
