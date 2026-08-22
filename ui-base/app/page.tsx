"use client";

import { useState } from "react";

// Seeded dev personas mirror the local IdentityPort (hex_service_kit). The picker sets the
// X-Dev-Persona header so a demo can exercise per-user authorization with no IdP.
const PERSONAS = ["analyst", "approver", "auditor", "other-tenant"] as const;

export default function Home() {
  const [persona, setPersona] = useState<string>(PERSONAS[0]);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 640 }}>
      <h1>GRC Agent (demo)</h1>
      <p>Local profile: pick a seeded persona to exercise per-user authorization (no IdP).</p>
      <label>
        Persona:{" "}
        <select value={persona} onChange={(e) => setPersona(e.target.value)}>
          {PERSONAS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
      <p style={{ marginTop: "1rem", color: "#666" }}>
        Requests carry <code>X-Dev-Persona: {persona}</code>. Wire this to your repo's API.
      </p>
    </main>
  );
}
