"use client";

import { useState } from "react";

// Repository IDs keep icons attached to the reviewed project when names change.
const ARTCRAFT_ICONS: Partial<Record<string, string>> = {
  "1398080271": "photocraft",
  "1398097510": "vectorcraft",
  "1398091865": "filmcraft",
  "1398185212": "lightcraft",
  "1398086162": "pdfcraft",
  "1400136506": "effectcraft",
  "1400018213": "designcraft",
  "1408489772": "wordcraft",
  "1408486424": "soundcraft",
  "1408294296": "deckcraft",
  "1408289866": "cadcraft",
  "1408285582": "gridcraft",
};

export function AppIcon({ repoId, name, large = false }: { repoId: string; name: string; large?: boolean }) {
  const [failedSource, setFailedSource] = useState("");
  const icon = ARTCRAFT_ICONS[repoId];
  const source = icon ? `/app-icons/artcraft/${icon}.webp` : "";
  const showImage = source !== "" && failedSource !== source;
  const size = large ? 80 : 48;

  return <span className={`app-mark${large ? " app-mark-large" : ""}${showImage ? " app-mark-image" : ""}`} aria-hidden="true">
    {showImage ? <img
      src={source}
      alt=""
      width={size}
      height={size}
      loading={large ? "eager" : "lazy"}
      decoding="async"
      onError={() => setFailedSource(source)}
    /> : name.slice(0, 2).toUpperCase()}
  </span>;
}
