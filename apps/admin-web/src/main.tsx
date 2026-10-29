import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "sonner";

import { App } from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
    <Toaster
      className="console-toaster"
      position="top-center"
      richColors
      closeButton
    />
  </React.StrictMode>,
);
