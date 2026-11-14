import React from "react";
export default function Overview() {
  return (
    <div style={{ padding: 0, margin: 0, position: "relative", width: "100%", height: "calc(100vh - 64px)", overflow: "hidden" }}>
      <iframe src="/overview/index.html" title="Banni Overview" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", border: 0, display: "block" }} />
    </div>
  );
}
