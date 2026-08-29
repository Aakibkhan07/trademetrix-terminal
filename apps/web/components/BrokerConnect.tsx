"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import {
  getAvailableBrokers,
  getConnections,
  startConnect,
  disconnectBroker,
  connectWithCredentials,
  type BrokerKey,
  type BrokerConnection,
  type BrokerInfo,
} from "../lib/brokerApi";
import { Dialog } from "@/components/ui/dialog";
import "./BrokerConnect.css";

const LABELS: Record<BrokerKey, string> = {
  kotak: "Kotak",
  fyers: "Fyers",
  dhan: "Dhan",
  zerodha: "Zerodha",
  upstox: "Upstox",
  angelone: "Angel One",
  lemonn: "Lemonn",
  kotakneo: "Kotak Neo",
};

function fmtExpiry(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "short",
  });
}

type CardState = "off" | "live" | "reconnect";

export default function BrokerConnect() {
  const [brokers, setBrokers] = useState<BrokerInfo[]>([]);
  const [conns, setConns] = useState<BrokerConnection[]>([]);
  const [busy, setBusy] = useState<BrokerKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Credential-login dialog state (Kotak Neo: consumer_key + TOTP + MPIN).
  const [cred, setCred] = useState<{
    broker: BrokerKey | null;
    consumer_key: string;
    mobile_number: string;
    ucc: string;
    totp: string;
    mpin: string;
    busy: boolean;
    err: string | null;
  }>({
    broker: null,
    consumer_key: "",
    mobile_number: "",
    ucc: "",
    totp: "",
    mpin: "",
    busy: false,
    err: null,
  });

  const openCred = (broker: BrokerKey) =>
    setCred((c) => ({ ...c, broker, err: null }));
  const closeCred = () =>
    setCred((c) => ({ ...c, broker: null, busy: false }));

  const submitCred = async () => {
    if (!cred.broker) return;
    setCred((c) => ({ ...c, busy: true, err: null }));
    try {
      await connectWithCredentials(cred.broker, {
        consumer_key: cred.consumer_key,
        mobile_number: cred.mobile_number,
        ucc: cred.ucc,
        totp: cred.totp,
        mpin: cred.mpin,
      });
      setCred((c) => ({ ...c, broker: null, busy: false }));
      await load();
    } catch (e) {
      setCred((c) => ({
        ...c,
        busy: false,
        err: e instanceof Error ? e.message : "Connect failed.",
      }));
    }
  };

  const load = useCallback(async () => {
    try {
      const [{ brokers }, { connections }] = await Promise.all([
        getAvailableBrokers(),
        getConnections(),
      ]);
      setBrokers(brokers);
      setConns(connections);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load brokers.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Surface the ?broker=..&status=.. that our /callback bounces back with.
    const p = new URLSearchParams(window.location.search);
    const status = p.get("status");
    const broker = p.get("broker");
    if (status === "error") {
      setError(`Could not connect ${broker ?? "broker"}. Please try again.`);
    }
    if (status || broker) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [load]);

  const byBroker = useMemo(() => {
    const m = new Map<BrokerKey, BrokerConnection>();
    conns.forEach((c) => m.set(c.broker, c));
    return m;
  }, [conns]);

  const liveCount = conns.filter((c) => c.is_live).length;

  const handleConnect = async (broker: BrokerKey) => {
    setError(null);
    setBusy(broker);
    try {
      await startConnect(broker); // full-page redirect to broker login
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connect failed.");
      setBusy(null);
    }
  };

  const handleDisconnect = async (broker: BrokerKey) => {
    setBusy(broker);
    try {
      await disconnectBroker(broker);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Disconnect failed.");
    } finally {
      setBusy(null);
    }
  };

  const stateOf = (broker: BrokerKey): CardState => {
    const c = byBroker.get(broker);
    if (!c || c.status === "revoked") return "off";
    return c.is_live ? "live" : "reconnect";
  };

  return (
    <div className="tm-bc">
      <div className="tm-bc__head">
        <h2 className="tm-bc__title">Connect your broker</h2>
        <p className="tm-bc__sub">
          You log in on your broker&apos;s own secure page — we never see your
          password or PIN. We receive a revocable access token so strategies can
          execute in your own demat account.
        </p>
      </div>

      {liveCount > 0 && (
        <div className="tm-bc__connected">
          <span className="tm-bc__dot" style={{ background: "#22d3ee", boxShadow: "0 0 8px #22d3ee" }} />
          <span className="tm-bc__connected-txt">
            <b>{liveCount}</b> broker{liveCount > 1 ? "s" : ""} live and ready for
            automated execution.
          </span>
        </div>
      )}

      {error && <p className="tm-bc__err">{error}</p>}

      <div className="tm-bc__grid">
        {brokers.map((info) => {
          const broker = info.key;
          const c = byBroker.get(broker);
          const st = stateOf(broker);
          const isBusy = busy === broker;

          // Scaffold brokers not yet wired to a real OAuth flow.
          if (info.coming_soon) {
            return (
              <div className="tm-bc__card tm-bc__card--soon" key={broker}>
                <div className="tm-bc__card-top">
                  <span className="tm-bc__broker">{LABELS[broker]}</span>
                  <span className="tm-bc__pill tm-bc__pill--soon">
                    <span className="tm-bc__dot" />
                    Coming soon
                  </span>
                </div>
                <p className="tm-bc__meta">Linking opens soon — not available yet.</p>
                <button className="tm-bc__btn tm-bc__btn--ghost" disabled>
                  Connect {LABELS[broker]}
                </button>
              </div>
            );
          }

          // Already linked (live or token expired -> reconnect).
          if (st !== "off") {
            return (
              <div className="tm-bc__card" key={broker}>
                <div className="tm-bc__card-top">
                  <span className="tm-bc__broker">{LABELS[broker]}</span>
                  <span
                    className={
                      "tm-bc__pill " +
                      (st === "live"
                        ? "tm-bc__pill--live"
                        : "tm-bc__pill--reconnect")
                    }
                  >
                    <span className="tm-bc__dot" />
                    {st === "live" ? "Connected" : "Reconnect"}
                  </span>
                </div>
                <p className="tm-bc__meta">
                  {st === "live" && c ? (
                    <>
                      {c.broker_user_id ? (
                        <>
                          ID <b>{c.broker_user_id}</b> ·{" "}
                        </>
                      ) : null}
                      valid till <b>{fmtExpiry(c.token_expires_at)}</b>
                    </>
                  ) : (
                    "Daily token expired — tap to log in again for today."
                  )}
                </p>
                <button
                  className="tm-bc__btn tm-bc__btn--primary"
                  disabled={isBusy}
                  onClick={() => handleConnect(broker)}
                >
                  {isBusy ? "Redirecting…" : "Re-authenticate"}
                </button>
                <button
                  className="tm-bc__btn tm-bc__btn--ghost"
                  disabled={isBusy}
                  onClick={() => handleDisconnect(broker)}
                >
                  Disconnect
                </button>
              </div>
            );
          }

          // Not linked yet.
          if (info.credential_login) {
            return (
              <div className="tm-bc__card" key={broker}>
                <div className="tm-bc__card-top">
                  <span className="tm-bc__broker">{LABELS[broker]}</span>
                  <span className="tm-bc__pill tm-bc__pill--off">
                    <span className="tm-bc__dot" />
                    Not linked
                  </span>
                </div>
                <p className="tm-bc__meta">
                  Log in with your app credentials (consumer key, TOTP &amp; MPIN)
                  — no redirect needed.
                </p>
                <button
                  className="tm-bc__btn tm-bc__btn--primary"
                  onClick={() => openCred(broker)}
                >
                  Connect {LABELS[broker]}
                </button>
              </div>
            );
          }

          if (info.configured) {
            return (
              <div className="tm-bc__card" key={broker}>
                <div className="tm-bc__card-top">
                  <span className="tm-bc__broker">{LABELS[broker]}</span>
                  <span className="tm-bc__pill tm-bc__pill--off">
                    <span className="tm-bc__dot" />
                    Not linked
                  </span>
                </div>
                <p className="tm-bc__meta">Link once, trade hands-free.</p>
                <button
                  className="tm-bc__btn tm-bc__btn--primary"
                  disabled={isBusy}
                  onClick={() => handleConnect(broker)}
                >
                  {isBusy ? "Redirecting…" : `Connect ${LABELS[broker]}`}
                </button>
              </div>
            );
          }

          // Registered but operator hasn't set this broker's app credentials yet.
          return (
            <div className="tm-bc__card" key={broker}>
              <div className="tm-bc__card-top">
                <span className="tm-bc__broker">{LABELS[broker]}</span>
                <span className="tm-bc__pill tm-bc__pill--soon">
                  <span className="tm-bc__dot" />
                  Needs credentials
                </span>
              </div>
              <p className="tm-bc__meta">
                Add this broker&apos;s app credentials to the server env, then
                restart to enable linking.
              </p>
              <button className="tm-bc__btn tm-bc__btn--ghost" disabled>
                Connect {LABELS[broker]}
              </button>
            </div>
          );
        })}

        {!loading && brokers.length === 0 && (
          <p className="tm-bc__sub">No brokers are enabled yet.</p>
        )}
      </div>

      <p className="tm-bc__note">
        Broker access tokens reset every day (SEBI 2FA requirement). We&apos;ll
        remind you each morning to reconnect in one tap — it takes a few seconds
        and keeps your automated strategies running.
      </p>

      {cred.broker && (
        <Dialog onClose={closeCred} title={`Connect your ${LABELS[cred.broker]} account`}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 4 }}>
            <p style={{ margin: 0, fontSize: 13, opacity: 0.8 }}>
              Enter the API credentials from your {LABELS[cred.broker]} Trade API
              app. We store only the resulting daily access token.
            </p>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
              Consumer Key
              <input
                type="text"
                value={cred.consumer_key}
                autoComplete="off"
                onChange={(e) => setCred((c) => ({ ...c, consumer_key: e.target.value }))}
                style={inputStyle}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
              Mobile Number
              <input
                type="text"
                value={cred.mobile_number}
                autoComplete="off"
                onChange={(e) => setCred((c) => ({ ...c, mobile_number: e.target.value }))}
                style={inputStyle}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
              Client Code (UCC)
              <input
                type="text"
                value={cred.ucc}
                autoComplete="off"
                onChange={(e) => setCred((c) => ({ ...c, ucc: e.target.value }))}
                style={inputStyle}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
              TOTP
              <input
                type="text"
                value={cred.totp}
                autoComplete="off"
                onChange={(e) => setCred((c) => ({ ...c, totp: e.target.value }))}
                style={inputStyle}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
              MPIN
              <input
                type="password"
                value={cred.mpin}
                autoComplete="off"
                onChange={(e) => setCred((c) => ({ ...c, mpin: e.target.value }))}
                style={inputStyle}
              />
            </label>
            {cred.err && (
              <p style={{ margin: 0, color: "var(--text-red, #ef4444)", fontSize: 13 }}>
                {cred.err}
              </p>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
              <button className="tm-bc__btn tm-bc__btn--ghost" onClick={closeCred}>
                Cancel
              </button>
              <button
                className="tm-bc__btn tm-bc__btn--primary"
                onClick={submitCred}
                disabled={cred.busy}
              >
                {cred.busy ? "Connecting…" : "Connect"}
              </button>
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
}

const inputStyle: CSSProperties = {
  background: "var(--surface-2, #11131a)",
  border: "1px solid var(--border, #2a2d3a)",
  borderRadius: 8,
  padding: "8px 10px",
  color: "inherit",
  fontSize: 14,
};
