"use client";

import { useEffect, useState } from "react";
import { api, connectionsFromCredentials, type BrokerCred } from "../lib/api";

interface Props {
  /** where the full "Connect broker" page lives, e.g. "/brokers" */
  href?: string;
  /** poll interval ms (0 = no polling) */
  pollMs?: number;
}

type Health = "live" | "reconnect" | "off";

export default function BrokerStatusWidget({ href = "/brokers", pollMs = 60000 }: Props) {
  const [creds, setCreds] = useState<BrokerCred[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.brokers.credentials()
        .then(({ credentials }) => alive && setCreds(credentials || []))
        .catch(() => {});
    load().finally(() => setLoading(false));
    if (pollMs > 0) {
      const t = setInterval(load, pollMs);
      return () => { alive = false; clearInterval(t); };
    }
    return () => { alive = false; };
  }, [pollMs]);

  const linked = creds.filter(c => c.is_active);
  const live = linked.filter(c => c.token_expires_at);
  const health: Health =
    live.length > 0 ? "live" : linked.length > 0 ? "reconnect" : "off";

  const color =
    health === "live" ? "#22d3ee" : health === "reconnect" ? "#f5a524" : "#8b90a0";
  const label =
    health === "live"
      ? `${live.length} broker${live.length > 1 ? "s" : ""} live`
      : health === "reconnect"
      ? "Reconnect broker"
      : "Link broker";

  return (
    <a
      href={href}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 12px",
        borderRadius: 999,
        fontFamily: '"DM Sans", sans-serif',
        fontStyle: "normal",
        fontSize: 12.5,
        fontWeight: 500,
        textDecoration: "none",
        color: color,
        background: "rgba(255,255,255,0.03)",
        border: `1px solid ${color}44`,
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: color,
          boxShadow: `0 0 8px ${color}`,
        }}
      />
      {label}
    </a>
  );
}
