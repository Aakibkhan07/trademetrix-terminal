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
import { api } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import "./BrokerConnect.css";

const LABELS: Record<BrokerKey, string> = {
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
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [cred, setCred] = useState<{
    broker: BrokerKey | null;
    consumer_key: string;
    fields: Record<string, string>;
    busy: boolean;
    err: string | null;
  }>({
    broker: null,
    consumer_key: "",
    fields: {},
    busy: false,
    err: null,
  });

  const openCred = (broker: BrokerKey) =>
    setCred((c) => ({ ...c, broker, fields: {}, err: null }));
  const closeCred = () =>
    setCred((c) => ({ ...c, broker: null, busy: false }));

  const submitCred = async () => {
    if (!cred.broker) return;
    setCred((c) => ({ ...c, busy: true, err: null }));
    try {
      const broker = cred.broker as string;
      const isKotakNeo = broker === "kotakneo";
      if (isKotakNeo) {
        await connectWithCredentials(cred.broker, cred.consumer_key, cred.fields);
      } else {
        const fields = cred.fields as Record<string, string>;
        const get = (k: string) => fields[k] || "";
        type CredPayload = Parameters<typeof api.brokers.saveCredentials>[0];
        let payload: CredPayload = { broker };
        if (broker === "angelone") {
          const additional_params: Record<string, string> = {};
          if (get("totp_secret")) additional_params.totp_secret = get("totp_secret");
          payload = { broker, client_code: get("client_code"), secret_key: get("secret_key"), api_key: get("api_key"), ...(Object.keys(additional_params).length ? { additional_params } : {}) };
        } else if (broker === "fyers" || broker === "zerodha" || broker === "dhan" || broker === "upstox") {
          const additional_params: Record<string, string> = {};
          if (get("totp_secret")) additional_params.totp_secret = get("totp_secret");
          payload = { broker, client_id: get("client_id") || cred.consumer_key, api_key: get("api_key") || get("client_id") || cred.consumer_key, secret_key: get("secret_key"), ...(Object.keys(additional_params).length ? { additional_params } : {}) };
        } else if (broker === "lemonn") {
          payload = { broker, client_code: get("client_code"), secret_key: get("secret_key") };
        } else {
          payload = { broker, client_code: get("client_code") || get("client_id"), secret_key: get("secret_key"), api_key: get("api_key") || cred.consumer_key, additional_params: fields };
        }
        await api.brokers.saveCredentials(payload);
      }
      setSuccess(`${LABELS[cred.broker]} demat connected successfully — token active.`);
      setTimeout(() => setSuccess(null), 4000);
      setCred((c) => ({ ...c, broker: null, busy: false }));
      await load();
    } catch (e) {
      setCred((c) => ({
        ...c,
        busy: false,
        err: e instanceof Error ? e.message : "Connect failed. Check your demat details.",
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
    const p = new URLSearchParams(window.location.search);
    const status = p.get("status");
    const broker = p.get("broker");
    if (status === "connected") {
      setSuccess(`${broker ? LABELS[broker as BrokerKey] ?? broker : "Broker"} connected — demat ready for trading.`);
      setTimeout(() => setSuccess(null), 4000);
    }
    if (status === "error") {
      setError(`Could not connect ${broker ?? "broker"}. Please check your demat credentials and try again.`);
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
    setSuccess(null);
    setBusy(broker);
    try {
      await startConnect(broker);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connect failed.");
      setBusy(null);
    }
  };

  const handleDisconnect = async (broker: BrokerKey) => {
    setBusy(broker);
    try {
      await disconnectBroker(broker);
      setSuccess(`${LABELS[broker]} disconnected.`);
      setTimeout(() => setSuccess(null), 3000);
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
        <h2 className="tm-bc__title">Connect your Demat Account</h2>
        <p className="tm-bc__sub">
          Fill your broker details below to log in with your demat account, or use <b style={{ color: "#e7e9ee" }}>Login via Broker</b> for one-tap OAuth.
          We store only a revocable access token — never your password or PIN.
        </p>
      </div>

      {liveCount > 0 && (
        <div className="tm-bc__connected">
          <span className="tm-bc__dot" style={{ background: "#22d3ee", boxShadow: "0 0 8px #22d3ee" }} />
          <span className="tm-bc__connected-txt">
            <b>{liveCount}</b> broker{liveCount > 1 ? "s" : ""} live and ready for automated execution.
          </span>
        </div>
      )}

      {success && <p className="tm-bc__err" style={{ color: "#22d3ee", background: "rgba(34,211,238,0.08)", border: "1px solid rgba(34,211,238,0.25)", padding: "10px 12px", borderRadius: 10 }}>{success}</p>}
      {error && <p className="tm-bc__err">{error}</p>}

      <div className="tm-bc__grid">
        {brokers.map((info) => {
          const broker = info.key;
          const c = byBroker.get(broker);
          const st = stateOf(broker);
          const isBusy = busy === broker;

          if (info.coming_soon) {
            const isLemonn = broker === "lemonn";
            return (
              <div className={`tm-bc__card ${isLemonn ? "" : "tm-bc__card--soon"}`} key={broker}>
                <div className="tm-bc__card-top">
                  <span className="tm-bc__broker">{LABELS[broker]}</span>
                  <span className={`tm-bc__pill ${isLemonn ? "tm-bc__pill--off" : "tm-bc__pill--soon"}`}>
                    <span className="tm-bc__dot" />
                    {isLemonn ? "Pre-connect" : "Coming soon"}
                  </span>
                </div>
                <p className="tm-bc__meta">{isLemonn ? "Save your demat details now — auto-activates when API launches." : "Linking opens soon — not available yet."}</p>
                {isLemonn ? (
                  <button className="tm-bc__btn tm-bc__btn--primary" onClick={() => openCred(broker)}>
                    Fill Demat Details — Connect {LABELS[broker]}
                  </button>
                ) : (
                  <button className="tm-bc__btn tm-bc__btn--ghost" disabled>
                    Connect {LABELS[broker]}
                  </button>
                )}
              </div>
            );
          }

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
                    "Daily token expired — fill demat details or tap re-login for today."
                  )}
                </p>
                <button
                  className="tm-bc__btn tm-bc__btn--primary"
                  disabled={isBusy}
                  onClick={() => openCred(broker)}
                >
                  Update Demat Details
                </button>
                <button
                  className="tm-bc__btn tm-bc__btn--ghost"
                  disabled={isBusy}
                  onClick={() => handleConnect(broker)}
                >
                  {isBusy ? "Redirecting…" : "Login via Broker"}
                </button>
                <button
                  className="tm-bc__btn tm-bc__btn--ghost"
                  disabled={isBusy}
                  onClick={() => handleDisconnect(broker)}
                  style={{ opacity: 0.7 }}
                >
                  Disconnect
                </button>
              </div>
            );
          }

          const canOAuth = !!info.configured && !info.coming_soon;
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
                {info.instructions
                  ? info.instructions.split("\n")[0]
                  : "Fill your demat credentials to login instantly."}
              </p>
              <button
                className="tm-bc__btn tm-bc__btn--primary"
                onClick={() => openCred(broker)}
              >
                Fill Demat Details — Login
              </button>
              {canOAuth ? (
                <button
                  className="tm-bc__btn tm-bc__btn--ghost"
                  disabled={isBusy}
                  onClick={() => handleConnect(broker)}
                >
                  {isBusy ? "Redirecting…" : `Login via ${LABELS[broker]} (OAuth)`}
                </button>
              ) : null}
            </div>
          );
        })}

        {!loading && brokers.length === 0 && (
          <p className="tm-bc__sub">No brokers are enabled yet.</p>
        )}
      </div>

      <p className="tm-bc__note">
        <b style={{ color: "#e7e9ee" }}>Demat login:</b> Enter your trading API details (Client Code / API Key / Password / TOTP) and click <b>Connect</b> — we encrypt and store only the daily access token.<br />
        <b style={{ color: "#e7e9ee" }}>OAuth:</b> Or tap <b>Login via Broker</b> to authenticate on your broker&apos;s secure page.<br />
        Broker tokens reset daily (SEBI 2FA). We&apos;ll remind you each morning to reconnect in one tap.
      </p>

      {cred.broker && (() => {
        const credInfo = brokers.find((b) => b.key === cred.broker);
        let fields = credInfo?.credential_fields ?? [];
        if (fields.length === 0) {
          const fallbacks: Record<string, typeof fields> = {
            fyers: [{ key: "client_id", label: "Client ID / App ID", placeholder: "Fyers App ID", required: true }, { key: "secret_key", label: "App Secret", type: "password", placeholder: "Fyers App Secret", required: true }],
            zerodha: [{ key: "client_id", label: "API Key", placeholder: "Kite API Key", required: true }, { key: "secret_key", label: "API Secret", type: "password", placeholder: "Kite API Secret", required: true }],
            dhan: [{ key: "client_id", label: "Client ID", placeholder: "Dhan Client ID", required: true }, { key: "secret_key", label: "Client Secret", type: "password", placeholder: "Dhan Client Secret", required: true }],
            upstox: [{ key: "client_id", label: "API Key", placeholder: "Upstox API Key", required: true }, { key: "secret_key", label: "API Secret", type: "password", placeholder: "Upstox API Secret", required: true }],
            angelone: [{ key: "client_code", label: "Client Code", placeholder: "Angel Client Code", required: true }, { key: "secret_key", label: "Password", type: "password", placeholder: "Trading Password", required: true }, { key: "api_key", label: "App Key", placeholder: "Angel App API Key", required: true }, { key: "totp_secret", label: "TOTP Secret", placeholder: "Base32 (leave blank if using manual TOTP)", required: false }],
            lemonn: [{ key: "client_code", label: "Client ID / Mobile", placeholder: "Lemonn Client ID", required: true }, { key: "secret_key", label: "Password / PIN", type: "password", placeholder: "Lemonn Password", required: true }],
            kotakneo: [{ key: "consumer_key", label: "Consumer Key", placeholder: "Neo app → More → Trade API → Generate", required: true }, { key: "mobile_number", label: "Registered Mobile", placeholder: "+919999999999", required: true }, { key: "ucc", label: "UCC (Client Code)", placeholder: "e.g. AB1234", required: true }, { key: "totp", label: "TOTP (6-digit)", placeholder: "From authenticator app", required: true }, { key: "mpin", label: "MPIN", type: "password", placeholder: "6-digit MPIN", required: true }],
          };
          fields = fallbacks[cred.broker] ?? [];
        }
        const showConsumerKey = cred.broker === "kotakneo" && !fields.some((f) => f.key === "consumer_key");
        return (
        <Dialog onClose={closeCred} title={`Login with ${LABELS[cred.broker]} Demat Account`}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 4 }}>
            <p style={{ margin: 0, fontSize: 13, opacity: 0.85, lineHeight: 1.5 }}>
              Fill your <b>{LABELS[cred.broker]}</b> demat / trading API details and click <b>Connect</b>. We encrypt the credentials and keep only the daily access token — your strategies can then trade directly in your demat.
            </p>
            {credInfo?.instructions && (
              <p style={{ margin: 0, fontSize: 12, opacity: 0.65, whiteSpace: "pre-wrap", background: "rgba(255,255,255,0.03)", padding: "8px 10px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)" }}>
                {credInfo.instructions}
              </p>
            )}
            {showConsumerKey && (
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
              Consumer Key *
              <input
                type="text"
                value={cred.consumer_key}
                autoComplete="off"
                placeholder="Consumer Key"
                onChange={(e) => setCred((c) => ({ ...c, consumer_key: e.target.value }))}
                style={inputStyle}
              />
            </label>
            )}
            {fields.map((f) => (
              <label
                key={f.key}
                style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}
              >
                <span>{f.label}{f.required ? " *" : ""}</span>
                <input
                  type={f.type === "password" ? "password" : "text"}
                  value={f.key === "consumer_key" ? cred.consumer_key : cred.fields[f.key] ?? ""}
                  placeholder={f.placeholder ?? ""}
                  autoComplete="off"
                  onChange={(e) => {
                    if (f.key === "consumer_key") {
                      setCred((c) => ({ ...c, consumer_key: e.target.value }));
                    } else {
                      setCred((c) => ({
                        ...c,
                        fields: { ...c.fields, [f.key]: e.target.value },
                      }));
                    }
                  }}
                  style={inputStyle}
                />
              </label>
            ))}
            {cred.err && (
              <p style={{ margin: 0, color: "var(--text-red, #ef4444)", fontSize: 13, background: "rgba(239,68,68,0.08)", padding: "8px 10px", borderRadius: 8 }}>
                {cred.err}
              </p>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
              <button className="tm-bc__btn tm-bc__btn--ghost" onClick={closeCred} style={{ width: "auto", marginTop: 0 }}>
                Cancel
              </button>
              <button
                className="tm-bc__btn tm-bc__btn--primary"
                onClick={submitCred}
                disabled={cred.busy}
                style={{ width: "auto", marginTop: 0, minWidth: 120 }}
              >
                {cred.busy ? "Connecting…" : "Connect Demat"}
              </button>
            </div>
            <p style={{ margin: 0, fontSize: 11, opacity: 0.5, textAlign: "center" }}>🔒 Encrypted · Revocable token · SEBI 2FA daily refresh</p>
          </div>
        </Dialog>
        );
      })()}
    </div>
  );
}

const inputStyle: CSSProperties = {
  background: "var(--surface-2, #11131a)",
  border: "1px solid var(--border, #2a2d3a)",
  borderRadius: 8,
  padding: "10px 12px",
  color: "inherit",
  fontSize: 14,
};
