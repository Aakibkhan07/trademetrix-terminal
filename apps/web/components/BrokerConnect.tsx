"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { api, friendlyApiError, type BrokerMeta, type BrokerCred, type BrokerFieldMeta } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import "./BrokerConnect.css";

const LABELS: Record<string, string> = {
  fyers: "Fyers",
  dhan: "Dhan",
  zerodha: "Zerodha",
  upstox: "Upstox",
  angelone: "Angel One",
  lemonn: "Lemonn",
  kotakneo: "Kotak Neo",
};

const PLACEHOLDER_BROKERS = new Set([
  "hdfc", "iifl", "motilal", "geojit", "reliance", "axis",
  "binance", "bybit", "okx", "oanda", "interactive_brokers", "alpaca",
  "icici", "aliceblue", "fivepaisa", "finvasia", "flattrade", "groww",
]);

function isPlaceholderBroker(broker: string): boolean {
  return PLACEHOLDER_BROKERS.has(broker);
}


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
  const [brokers, setBrokers] = useState<BrokerMeta[]>([]);
  const [creds, setCreds] = useState<BrokerCred[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [form, setForm] = useState<{
    broker: string | null;
    api_key: string;
    secret_key: string;
    client_id: string;
    client_code: string;
    totp_secret: string;
    busy: boolean;
    err: string | null;
  }>({
    broker: null,
    api_key: "",
    secret_key: "",
    client_id: "",
    client_code: "",
    totp_secret: "",
    busy: false,
    err: null,
  });

  const openForm = (broker: string) =>
    setForm((f) => ({
      ...f,
      broker,
      api_key: "",
      secret_key: "",
      client_id: "",
      client_code: "",
      totp_secret: "",
      busy: false,
      err: null,
    }));

  const closeForm = () =>
    setForm((f) => ({ ...f, broker: null, busy: false }));

  const submitForm = async () => {
    if (!form.broker) return;
    setForm((f) => ({ ...f, busy: true, err: null }));
    try {
      const additional_params: Record<string, string> = {};
      if (form.totp_secret) additional_params.totp_secret = form.totp_secret;

      const payload: Parameters<typeof api.brokers.saveCredentials>[0] = {
        broker: form.broker,
        api_key: form.api_key || form.client_id,
        secret_key: form.secret_key,
        client_id: form.client_id || undefined,
        client_code: form.client_code || undefined,
        additional_params: Object.keys(additional_params).length ? additional_params : undefined,
      };
      await api.brokers.saveCredentials(payload);

      const meta = brokers.find(b => b.broker === form.broker);
      if (meta?.oauth_available) {
        const { auth_url } = await api.brokers.authUrl(form.broker) as { auth_url: string };
        if (auth_url) {
          window.open(auth_url, "_blank");
          setSuccess(`${LABELS[form.broker] ?? form.broker} saved! OAuth link opened.`);
        } else {
          setSuccess(`${LABELS[form.broker] ?? form.broker} connected successfully.`);
        }
      } else {
        setSuccess(`${LABELS[form.broker] ?? form.broker} credentials saved!`);
      }
      setTimeout(() => setSuccess(null), 4000);
      setForm((f) => ({ ...f, broker: null, busy: false }));
      await load();
    } catch (e) {
      setForm((f) => ({
        ...f,
        busy: false,
        err: e instanceof Error ? e.message : "Connect failed. Check your details.",
      }));
    }
  };

  const load = useCallback(async () => {
    try {
      const [{ credentials }] = await Promise.all([api.brokers.credentials()]);
      setCreds(credentials || []);
      const metaData = await api.brokers.metadata();
      setBrokers((metaData as { brokers: BrokerMeta[] }).brokers || []);
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
      setSuccess(`${broker ? LABELS[broker as keyof typeof LABELS] ?? broker : "Broker"} connected — ready for trading.`);
      setTimeout(() => setSuccess(null), 4000);
    }
    if (status === "error") {
      setError(`Could not connect ${broker ?? "broker"}. Please check your credentials and try again.`);
    }
    if (status || broker) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [load]);

  const byBroker = useMemo(() => {
    const m = new Map<string, BrokerCred>();
    creds.forEach((c) => m.set(c.broker, c));
    return m;
  }, [creds]);

  const liveCount = creds.filter((c) => c.is_active && c.token_expires_at).length;

  const handleReAuth = async (broker: string) => {
    setBusy(broker);
    try {
      const { auth_url } = await api.brokers.reAuth(broker) as { auth_url?: string };
      if (auth_url) {
        window.open(auth_url, "_blank");
        setSuccess(`${LABELS[broker] ?? broker} re-auth link opened.`);
        setTimeout(() => setSuccess(null), 4000);
      } else {
        setSuccess(`Re-auth initiated for ${LABELS[broker] ?? broker}.`);
        setTimeout(() => setSuccess(null), 4000);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Re-auth failed.");
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async (broker: string) => {
    setBusy(broker);
    try {
      await api.brokers.deleteCredentials(broker);
      setSuccess(`${LABELS[broker] ?? broker} disconnected.`);
      setTimeout(() => setSuccess(null), 3000);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Disconnect failed.");
    } finally {
      setBusy(null);
    }
  };

  const stateOf = (broker: string): CardState => {
    const c = byBroker.get(broker);
    if (!c || !c.is_active) return "off";
    return c.token_expires_at ? "live" : "reconnect";
  };

  const availableBrokers = brokers.filter(
    (b) => !creds.some((c) => c.broker === b.broker) && !PLACEHOLDER_BROKERS.has(b.broker)
  );
  const placeholderBrokers = brokers.filter(
    (b) => !creds.some((c) => c.broker === b.broker) && PLACEHOLDER_BROKERS.has(b.broker)
  );

  return (
    <div className="tm-bc">
      <div className="tm-bc__head">
        <h2 className="tm-bc__title">Connect your Trading Account</h2>
        <p className="tm-bc__sub">
          Enter your broker API details below, or use{" "}
          <b style={{ color: "#e7e9ee" }}>OAuth</b> for one-tap login where available.
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

      {success && <p className="tm-bc__msg tm-bc__msg--success">{success}</p>}
      {error && <p className="tm-bc__msg tm-bc__msg--error">{error}</p>}

      <div className="tm-bc__grid">
        {brokers.map((info) => {
          const broker = info.broker;
          const c = byBroker.get(broker);
          const st = stateOf(broker);
          const isBusy = busy === broker;
          const isConnected = !!c && c.is_active;
          const isOAuth = info.oauth_available;
          const isPlaceholder = isPlaceholderBroker(broker);

          if (isPlaceholder) {
            return (
              <div className="tm-bc__card tm-bc__card--soon" key={broker}>
                <div className="tm-bc__card-top">
                  <span className="tm-bc__broker">{info.display_name}</span>
                  <span className="tm-bc__pill tm-bc__pill--soon">
                    <span className="tm-bc__dot" />
                    Coming soon
                  </span>
                </div>
                <p className="tm-bc__meta">
                  {info.description || "Not yet available for live trading."}
                </p>
                <button className="tm-bc__btn tm-bc__btn--ghost" disabled>
                  Connect {info.display_name}
                </button>
              </div>
            );
          }

          if (isConnected) {
            return (
              <div className="tm-bc__card" key={broker}>
                <div className="tm-bc__card-top">
                  <span className="tm-bc__broker">{info.display_name}</span>
                  <span
                    className={`tm-bc__pill ${st === "live" ? "tm-bc__pill--live" : "tm-bc__pill--reconnect"}`}
                  >
                    <span className="tm-bc__dot" />
                    {st === "live" ? "Connected" : "Reconnect"}
                  </span>
                </div>
                <p className="tm-bc__meta">
                  {st === "live" && c ? (
                    <>
                      {c.token_expires_at ? (
                        <>Token valid till <b>{fmtExpiry(c.token_expires_at)}</b></>
                      ) : (
                        "Credentials saved"
                      )}
                    </>
                  ) : (
                    "Token expired — reconnect for today."
                  )}
                </p>
                <button
                  className="tm-bc__btn tm-bc__btn--primary"
                  disabled={isBusy}
                  onClick={() => openForm(broker)}
                >
                  Update Details
                </button>
                {isOAuth && (
                  <button
                    className="tm-bc__btn tm-bc__btn--ghost"
                    disabled={isBusy}
                    onClick={() => handleReAuth(broker)}
                  >
                    {isBusy ? "…" : `Login via ${info.display_name} (OAuth)`}
                  </button>
                )}
                <button
                  className="tm-bc__btn tm-bc__btn--ghost"
                  disabled={isBusy}
                  onClick={() => handleDelete(broker)}
                  style={{ opacity: 0.7 }}
                >
                  Disconnect
                </button>
              </div>
            );
          }

          return (
            <div className="tm-bc__card" key={broker}>
              <div className="tm-bc__card-top">
                <span className="tm-bc__broker">{info.display_name}</span>
                <span className="tm-bc__pill tm-bc__pill--off">
                  <span className="tm-bc__dot" />
                  Not linked
                </span>
              </div>
              <p className="tm-bc__meta">
                {info.description?.split("\n")[0] || "Fill your API details to connect."}
              </p>
              <button
                className="tm-bc__btn tm-bc__btn--primary"
                onClick={() => openForm(broker)}
              >
                Connect {info.display_name}
              </button>
              {isOAuth && (
                <button
                  className="tm-bc__btn tm-bc__btn--ghost"
                  disabled={isBusy}
                  onClick={() => {
                    api.brokers.authUrl(broker).then((data: unknown) => {
                      const { auth_url } = data as { auth_url: string };
                      if (auth_url) window.open(auth_url, "_blank");
                    }).catch(() => {
                      openForm(broker);
                    });
                  }}
                >
                  {isBusy ? "…" : `Login via ${info.display_name} (OAuth)`}
                </button>
              )}
            </div>
          );
        })}

        {!loading && brokers.length === 0 && (
          <p className="tm-bc__sub">No brokers are enabled yet.</p>
        )}
      </div>

      {placeholderBrokers.length > 0 && (
        <div style={{ marginTop: 12, padding: 10, background: "rgba(255,255,255,0.02)", border: "1px dashed var(--border)", borderRadius: 8 }}>
          <p className="t-faint" style={{ fontSize: 11, margin: 0 }}>
            {placeholderBrokers.length} more brokers registered but not yet available:{" "}
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>
              {placeholderBrokers.map(b => b.display_name).join(", ")}.
            </span>
          </p>
        </div>
      )}

      <p className="tm-bc__note">
        <b style={{ color: "#e7e9ee" }}>API keys:</b> Enter your trading API details and click{" "}
        <b>Connect</b> — we encrypt and store only the daily access token.<br />
        <b style={{ color: "#e7e9ee" }}>OAuth:</b> Or tap <b>Login via Broker</b> to authenticate on your broker&apos;s secure page.<br />
        Broker tokens reset daily (SEBI 2FA). We&apos;ll remind you each morning to reconnect in one tap.
      </p>

      {form.broker && (() => {
        const info = brokers.find((b) => b.broker === form.broker);
        const fields = info?.fields ?? [];
        return (
          <Dialog onClose={closeForm} title={`Connect ${info?.display_name ?? form.broker}`}>
            <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 4 }}>
              <p style={{ margin: 0, fontSize: 13, opacity: 0.85, lineHeight: 1.5 }}>
                Fill your <b>{info?.display_name ?? form.broker}</b> API details and click{" "}
                <b>Connect</b>. We encrypt the credentials and keep only the daily access token.
              </p>

              {fields.map((f: BrokerFieldMeta) => (
                <label
                  key={f.key}
                  style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}
                >
                  <span>{f.label}{f.required ? " *" : ""}</span>
                  <input
                    type={f.type === "password" ? "password" : "text"}
                    value={
                      f.key === "client_code" ? form.client_code
                        : f.key === "client_id" ? form.client_id
                        : f.key === "secret_key" ? form.secret_key
                        : f.key === "api_key" ? form.api_key
                        : ""
                    }
                    placeholder={f.placeholder ?? ""}
                    autoComplete="off"
                    onChange={(e) => {
                      const val = e.target.value;
                      if (f.key === "client_code") setForm((f) => ({ ...f, client_code: val }));
                      else if (f.key === "client_id") setForm((f) => ({ ...f, client_id: val }));
                      else if (f.key === "secret_key") setForm((f) => ({ ...f, secret_key: val }));
                      else if (f.key === "api_key") setForm((f) => ({ ...f, api_key: val }));
                    }}
                    style={inputStyle}
                  />
                </label>
              ))}

              {(info?.has_additional_params ?? false) && (
                <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                  <span>TOTP Secret <span style={{ opacity: 0.5 }}>(optional)</span></span>
                  <input
                    type="text"
                    value={form.totp_secret}
                    autoComplete="off"
                    placeholder="Base32 TOTP secret (leave blank if using manual TOTP)"
                    onChange={(e) => setForm((f) => ({ ...f, totp_secret: e.target.value }))}
                    style={inputStyle}
                  />
                </label>
              )}

              {info?.instructions && (
                <p style={{ margin: 0, fontSize: 12, opacity: 0.65, whiteSpace: "pre-wrap", background: "rgba(255,255,255,0.03)", padding: "8px 10px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)" }}>
                  {info.instructions}
                </p>
              )}

              {form.err && (
                <p style={{ margin: 0, color: "var(--text-red, #ef4444)", fontSize: 13, background: "rgba(239,68,68,0.08)", padding: "8px 10px", borderRadius: 8 }}>
                  {form.err}
                </p>
              )}

              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
                <button className="tm-bc__btn tm-bc__btn--ghost" onClick={closeForm} style={{ width: "auto", marginTop: 0 }}>
                  Cancel
                </button>
                <button
                  className="tm-bc__btn tm-bc__btn--primary"
                  onClick={submitForm}
                  disabled={form.busy}
                  style={{ width: "auto", marginTop: 0, minWidth: 120 }}
                >
                  {form.busy ? "Connecting…" : "Connect"}
                </button>
              </div>

              <p style={{ margin: 0, fontSize: 11, opacity: 0.5, textAlign: "center" }}>
                🔒 Encrypted · Revocable token · SEBI 2FA daily refresh
              </p>
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
