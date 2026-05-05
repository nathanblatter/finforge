import { Link } from 'react-router-dom'

export default function SecurityPolicyPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-300">
      <div className="max-w-3xl mx-auto px-6 py-16">
        <div className="mb-8 flex items-center gap-3">
          <img src="/finforge_minimal.png" alt="FinForge" className="w-8 h-8 rounded-md" />
          <span className="text-xl font-bold text-sky-400 tracking-tight">FinForge</span>
        </div>

        <h1 className="text-3xl font-bold text-slate-100 mb-2">Information Security Policy</h1>
        <p className="text-sm text-slate-500 mb-10">Last updated: 20 April 2026</p>

        <div className="space-y-8 text-sm leading-relaxed">
          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">1. Purpose &amp; Scope</h2>
            <p>
              This policy defines the security controls, practices, and principles that govern the FinForge
              platform. It applies to all system components including the API server, web interface, cron/ETL
              services, database, and all integrations with third-party services.
            </p>
            <p className="mt-2">
              FinForge is operated by Nathan Blatter as a self-hosted personal finance platform.
              Contact:{' '}
              <a href="mailto:nathan.blatter@yahoo.com" className="text-sky-400 hover:underline">
                nathan.blatter@yahoo.com
              </a>
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">2. Infrastructure Security</h2>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">2.1 Hosting Environment</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>FinForge runs on dedicated self-hosted hardware (Mac mini M4) — not shared cloud infrastructure.</li>
              <li>All services are containerized via Docker Compose with isolated networking.</li>
              <li>The host operating system is kept up to date with security patches.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">2.2 Network Architecture</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>Public access is routed through a Cloudflare Tunnel, providing DDoS protection and TLS termination.</li>
              <li>Internal services communicate over a private Docker bridge network not exposed to the internet.</li>
              <li>The PostgreSQL database is accessible only on the internal Docker network — no external ports are published.</li>
              <li>Administrative access (SSH, pgAdmin) is restricted to the Tailscale private network.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">2.3 TLS / Encryption in Transit</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>All client-to-server traffic is encrypted via TLS (managed by Cloudflare).</li>
              <li>All outbound API calls to third parties (Plaid, Schwab, Anthropic) use HTTPS/TLS.</li>
              <li>Internal Docker network traffic is not encrypted (defense-in-depth: network is isolated and not routable).</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">3. Identity &amp; Access Management</h2>

            <p className="mb-3">
              FinForge maintains a defined access control policy built on the principle of least privilege.
              Every identity — whether a human user, an automated service, or a third-party integration — is
              granted only the minimum permissions required to perform its function.
            </p>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">3.1 Access Control Principles</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li><span className="text-slate-200 font-medium">Least privilege:</span> Every account and service credential is scoped to the narrowest set of permissions necessary. Database credentials used by the API have access only to the FinForge schema. Plaid and Schwab integrations are read-only.</li>
              <li><span className="text-slate-200 font-medium">Role-based access:</span> Access is segmented by role — platform user (authenticated via JWT), service account (API key for NateBot and cron jobs), and administrator (host-level access via Tailscale). Each role has distinct capabilities and restrictions.</li>
              <li><span className="text-slate-200 font-medium">Deny by default:</span> All API endpoints require authentication. Unauthenticated access is limited to the login page, privacy policy, and security policy.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">3.2 Roles &amp; Permissions</h3>
            <div className="overflow-x-auto mt-2">
              <table className="w-full text-left text-slate-400">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="py-2 pr-4 text-xs font-semibold text-slate-300">Role</th>
                    <th className="py-2 pr-4 text-xs font-semibold text-slate-300">Authentication</th>
                    <th className="py-2 text-xs font-semibold text-slate-300">Permissions</th>
                  </tr>
                </thead>
                <tbody className="text-xs">
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4 text-slate-200">Platform User</td>
                    <td className="py-2 pr-4">JWT + optional MFA</td>
                    <td className="py-2">Read/write own financial data, goals, watchlists, and settings. Chat with Claude AI.</td>
                  </tr>
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4 text-slate-200">Service Account</td>
                    <td className="py-2 pr-4">Static API key (<code className="bg-slate-800 px-1 py-0.5 rounded">X-API-Key</code>)</td>
                    <td className="py-2">Read-only access to summaries, goals, alerts, and health endpoints. No write access to user data.</td>
                  </tr>
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4 text-slate-200">Cron / ETL</td>
                    <td className="py-2 pr-4">Internal Docker network + API key</td>
                    <td className="py-2">Write ingested financial data to database. Read Plaid/Schwab tokens from encrypted files. No UI access.</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4 text-slate-200">Administrator</td>
                    <td className="py-2 pr-4">Tailscale + host OS login</td>
                    <td className="py-2">Full system access: SSH, pgAdmin, Docker management, secret rotation, backups.</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">3.3 Granting, Modifying &amp; Revoking Access</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li><span className="text-slate-200 font-medium">Granting:</span> New user accounts are created by the administrator. API keys for service integrations are generated manually and stored in environment variables.</li>
              <li><span className="text-slate-200 font-medium">Modifying:</span> Permission changes (e.g., enabling MFA, rotating API keys) are performed by the administrator and take effect immediately.</li>
              <li><span className="text-slate-200 font-medium">Revoking:</span> User accounts can be deactivated (setting the active flag to false), which immediately invalidates all JWT tokens on the next request. API keys are revoked by removing them from the environment and restarting the affected service. Plaid and Schwab tokens can be individually revoked by deleting them from the encrypted token store.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">3.4 Credential Lifecycle</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>JWT tokens expire after 7 days and must be re-issued via login.</li>
              <li>Schwab OAuth access tokens are refreshed automatically every 25 minutes. Refresh tokens have a 7-day lifetime and are rolled forward on each nightly sync.</li>
              <li>API keys do not auto-expire but are rotated periodically or immediately upon suspected compromise.</li>
              <li>All credential rotation events are logged for audit purposes.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">3.5 Policy Review</h3>
            <p className="text-slate-400">
              This access control policy is reviewed whenever changes are made to the platform&apos;s role model,
              authentication mechanisms, or third-party integrations, and at minimum annually.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">4. Authentication &amp; Access Control</h2>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">4.1 User Authentication</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>Authentication is handled via JSON Web Tokens (JWT) with a 7-day expiry.</li>
              <li>Passwords are hashed using <span className="text-slate-200">bcrypt</span> (adaptive cost function) before storage. Plaintext passwords are never stored, logged, or transmitted after initial receipt.</li>
              <li>Optional TOTP-based multi-factor authentication (MFA) is supported via authenticator apps.</li>
              <li>Failed authentication attempts return generic error messages to prevent username enumeration.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">4.2 API Authentication</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>All API endpoints require an <code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">X-API-Key</code> header.</li>
              <li>Service-to-service calls (e.g., NateBot) use a static API key stored in environment variables, never in source code.</li>
              <li>Authenticated user endpoints additionally require a valid JWT Bearer token.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">4.3 Session Management</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>No server-side sessions are maintained — authentication is stateless via JWT.</li>
              <li>Tokens are stored in the browser&apos;s localStorage and cleared on logout or upon receiving a 401/403 response.</li>
              <li>No HTTP cookies are used for authentication.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">5. Data Protection</h2>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">5.1 De-identification Policy</h3>
            <p className="text-slate-400 mb-2">
              All financial data undergoes a mandatory de-identification step in the ETL pipeline before being written to the database.
              The following data is <span className="text-slate-200 font-medium">never</span> stored in the database:
            </p>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>Full account numbers or card numbers</li>
              <li>Routing numbers</li>
              <li>Social Security Numbers or government-issued identity data</li>
              <li>Bank login credentials</li>
              <li>Plaid access tokens or item IDs</li>
              <li>Schwab OAuth tokens</li>
            </ul>
            <p className="text-slate-400 mt-2">
              Accounts are referenced by internal UUIDs. A human-readable alias (e.g., &ldquo;WF Checking&rdquo;) and
              optionally the last 4 digits are stored for display purposes only.
            </p>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">5.2 Secrets Management</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>Plaid access tokens and Schwab OAuth tokens are stored in encrypted files on the host filesystem (<code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">/secrets/</code>), never in the database or version control.</li>
              <li>API keys (Plaid, Schwab, Anthropic, internal) are stored in environment variables loaded via <code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">.env</code> files excluded from version control.</li>
              <li>The Claude API key is used server-side only — never exposed to the frontend.</li>
              <li>All secrets files are listed in <code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">.gitignore</code>.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">5.3 Data at Rest</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>The PostgreSQL database runs in a Docker volume on the host filesystem.</li>
              <li>Host-level disk encryption (FileVault on macOS) provides encryption at rest for all data, including database files and secret stores.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">6. Third-Party Integration Security</h2>

            <div className="space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-1">Plaid</h3>
                <ul className="list-disc list-inside space-y-1 text-slate-400">
                  <li>Bank credentials are entered directly into Plaid&apos;s Link widget — FinForge never receives or processes them.</li>
                  <li>Plaid access tokens are exchanged once and stored in encrypted files (not the database).</li>
                  <li>If Plaid reports <code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">ITEM_LOGIN_REQUIRED</code>, an alert is raised — no automatic re-authentication occurs.</li>
                  <li>Data retrieval is read-only: transactions, balances, and account metadata.</li>
                </ul>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-1">Charles Schwab</h3>
                <ul className="list-disc list-inside space-y-1 text-slate-400">
                  <li>Authentication uses OAuth 2.0 — FinForge never handles Schwab passwords.</li>
                  <li>OAuth tokens are stored in encrypted files with automatic refresh (25-minute access token, 7-day refresh token).</li>
                  <li>If the refresh token expires (7+ days of downtime), a re-authentication alert is raised.</li>
                  <li>API access is read-only: positions, balances, and order history.</li>
                </ul>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-1">Anthropic (Claude AI)</h3>
                <ul className="list-disc list-inside space-y-1 text-slate-400">
                  <li>All Claude API calls are made server-side — the API key is never exposed to the browser.</li>
                  <li>Only de-identified financial summaries are sent: balances by alias, spending categories, goal progress, and holdings by ticker symbol.</li>
                  <li>No account numbers, card numbers, credentials, or personally identifiable information beyond the financial summary is included in prompts.</li>
                  <li>Chat conversations are session-only and not persisted.</li>
                </ul>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">7. Monitoring &amp; Logging</h2>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li>All API requests are logged with a unique <code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">X-Request-ID</code> for traceability. Logs include HTTP method, path, status code, and response time.</li>
              <li>Cron job execution is recorded in a <code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">CronLog</code> audit table with job name, status, and error details.</li>
              <li>Health checks run every 15 minutes and verify service availability and last successful sync times.</li>
              <li>Sensitive data (passwords, tokens, account numbers) is never included in logs.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">8. Incident Response</h2>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">8.1 Detection</h3>
            <p className="text-slate-400">
              Anomalous access patterns, failed authentication spikes, and service health failures are surfaced
              through the built-in alert system and NateBot iMessage notifications.
            </p>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">8.2 Response Process</h3>
            <ol className="list-decimal list-inside space-y-1 text-slate-400">
              <li>Identify and contain the incident (e.g., revoke compromised tokens, rotate API keys).</li>
              <li>Assess the scope: determine what data, if any, was accessed or exfiltrated.</li>
              <li>Remediate: patch the vulnerability, update credentials, and restore from backup if necessary.</li>
              <li>Notify affected parties within 72 hours if personal data was compromised (per GDPR Article 33).</li>
              <li>Document the incident and update security controls to prevent recurrence.</li>
            </ol>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">8.3 Data Breach Notification</h3>
            <p className="text-slate-400">
              In the event of a personal data breach, the Controller will notify the relevant supervisory authority
              within 72 hours of becoming aware of the breach (GDPR Article 33). If the breach is likely to result
              in a high risk to affected individuals, those individuals will also be notified without undue delay
              (GDPR Article 34).
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">9. Backup &amp; Recovery</h2>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li>Database backups are performed via automated scripts (<code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">scripts/backup_db.sh</code>).</li>
              <li>Backup files are stored on the host filesystem with restricted permissions.</li>
              <li>Recovery procedures are tested periodically to ensure backup integrity.</li>
              <li>Secret files (Plaid tokens, Schwab tokens) are backed up separately from the database.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">10. Software Security</h2>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li>Dependencies are reviewed and updated regularly to address known vulnerabilities.</li>
              <li>The application follows the OWASP Top 10 security guidelines, including input validation, parameterized queries (via SQLAlchemy ORM), and output encoding.</li>
              <li>Docker images use minimal base images (Alpine/slim variants) to reduce attack surface.</li>
              <li>CORS is configured to restrict cross-origin requests to trusted origins only.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">11. Physical Security</h2>
            <p className="text-slate-400">
              The host hardware is located in a private residence with controlled physical access.
              macOS FileVault full-disk encryption is enabled, ensuring data is protected if hardware is
              physically compromised.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">12. Policy Review</h2>
            <p className="text-slate-400">
              This Information Security Policy is reviewed and updated at least annually, or whenever
              significant changes are made to the platform&apos;s architecture, integrations, or data processing practices.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">13. Contact</h2>
            <p>
              For security concerns or to report a vulnerability:
            </p>
            <p className="mt-2 text-slate-400">
              Nathan Blatter<br />
              <a href="mailto:nathan.blatter@yahoo.com" className="text-sky-400 hover:underline">
                nathan.blatter@yahoo.com
              </a>
            </p>
          </section>
        </div>

        <div className="mt-12 pt-6 border-t border-slate-800 flex items-center gap-4 text-sm text-slate-500">
          <Link to="/privacy" className="hover:text-sky-400 transition-colors">Privacy Policy</Link>
          <span>&middot;</span>
          <Link to="/login" className="hover:text-sky-400 transition-colors">Sign In</Link>
        </div>
      </div>
    </div>
  )
}
