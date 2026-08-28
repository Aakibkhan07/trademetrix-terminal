"use client";

// Compact, always-visible connection status for the portal header/topbar.
// Green = at least one broker live. Amber = linked but token expired (reconnect).
// Grey = nothing linked. Clicking routes to the full connect page.

import { useEffect, useState } from "react";
import { getConnections, type BrokerConnection } from "../lib/brokerApi";

interface Props {
  /** where the full "Connect broker" page lives, e.g. "/portal/brokers" */
  href?: string;
  /** poll interval ms (0 = no polling) */
  pollMs?: number;
}

type Health = "live" | "reconnect" | "off";

export default function BrokerStatusWidget({ href = "/portal/brokers", pollMs = 60000 }: Props) {
  const [conns, setConns] = useState<BrokerConnection[]>([]);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getConnections()
        .then(({ connections }) => alive && setConns(connections))
        .catch(() => {});
    load();
    if (pollMs > 0) {
      const t = setInterval(load, pollMs);
      return () => {
        alive = false;
        clearInterval(t);
      };
    }
    return () => {
      alive = false;
    };
  }, [pollMs]);

  const linked = conns.filter((c) => c.status !== "revoked");
  const live = linked.filter((c) => c.is_live);
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
