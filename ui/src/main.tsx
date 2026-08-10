import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import "./index.css";
import App from "./App.tsx";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#1e5f74" },
    secondary: { main: "#0b6e4f" },
    background: { default: "#f4f6f8" },
  },
  shape: { borderRadius: 10 },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </StrictMode>
);
