import { Link } from 'react-router-dom'

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-300">
      <div className="max-w-3xl mx-auto px-6 py-16">
        <div className="mb-8 flex items-center gap-3">
          <img src="/finforge_minimal.png" alt="FinForge" className="w-8 h-8 rounded-md" />
          <span className="text-xl font-bold text-sky-400 tracking-tight">FinForge</span>
        </div>

        <h1 className="text-3xl font-bold text-slate-100 mb-2">Privacy Policy</h1>
        <p className="text-sm text-slate-500 mb-10">Last updated: 20 April 2026</p>

        <div className="space-y-8 text-sm leading-relaxed">
          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">1. Data Controller</h2>
            <p>
              FinForge is a self-hosted personal finance platform operated by Nathan Blatter
              (&ldquo;Controller&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;).
            </p>
            <p className="mt-2">
              Contact for privacy inquiries:{' '}
              <a href="mailto:nathan.blatter@yahoo.com" className="text-sky-400 hover:underline">
                nathan.blatter@yahoo.com
              </a>
            </p>
            <p className="mt-2">
              Platform URL:{' '}
              <span className="text-slate-100">finforge.nathanblatter.com</span>
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">2. What Data We Collect</h2>
            <p className="mb-3">We collect and process the following categories of personal data:</p>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">2.1 Account Data</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>Username (chosen by you at registration)</li>
              <li>Password (stored only as a bcrypt hash &mdash; we never store or can recover your plaintext password)</li>
              <li>Multi-factor authentication secret (if you enable MFA)</li>
              <li>Account creation and last-update timestamps</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">2.2 Financial Data (via Third-Party Integrations)</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>Transaction records: date, amount, merchant name, and category</li>
              <li>Account balances: current balance amounts per linked account (referenced by alias only)</li>
              <li>Investment holdings: ticker symbol, quantity, market value, and cost basis</li>
              <li>Goal definitions and progress snapshots</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">2.3 What We Never Store</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>Full account numbers or card numbers</li>
              <li>Routing numbers</li>
              <li>Social Security Numbers or government-issued ID data</li>
              <li>Bank login credentials</li>
              <li>Plaid access tokens or Schwab OAuth tokens (stored in encrypted files on the server, never in the database)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">3. Legal Basis for Processing (GDPR Article 6)</h2>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li>
                <span className="text-slate-200 font-medium">Legitimate interest (Art. 6(1)(f)):</span>{' '}
                Processing financial data to provide personal finance aggregation, goal tracking, and insights — the core purpose of the platform.
              </li>
              <li>
                <span className="text-slate-200 font-medium">Performance of a contract (Art. 6(1)(b)):</span>{' '}
                Processing necessary to provide the service you signed up for.
              </li>
              <li>
                <span className="text-slate-200 font-medium">Consent (Art. 6(1)(a)):</span>{' '}
                Where you voluntarily connect financial accounts via Plaid or Schwab integrations.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">4. Third-Party Data Processors</h2>
            <p className="mb-3">We share limited data with the following third-party services in order to operate the platform:</p>

            <div className="space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-1">Plaid Inc.</h3>
                <p className="text-slate-400">
                  Used to connect your bank and credit card accounts. Plaid receives your bank credentials directly
                  during the Link flow (FinForge never sees them). Plaid returns transaction and balance data to us.
                  See{' '}
                  <a href="https://plaid.com/legal/#end-user-privacy-policy" className="text-sky-400 hover:underline" target="_blank" rel="noopener noreferrer">
                    Plaid&apos;s End User Privacy Policy
                  </a>.
                </p>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-1">Charles Schwab (Schwab Trader API)</h3>
                <p className="text-slate-400">
                  Used to retrieve brokerage and retirement account data. Authentication is via OAuth —
                  FinForge never sees your Schwab password. Only portfolio positions and balances are retrieved (read-only).
                </p>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-1">Anthropic (Claude AI)</h3>
                <p className="text-slate-400">
                  Used to generate financial insights and power the chat interface. De-identified financial summaries
                  (balances, spending categories, goal progress) are sent to Anthropic&apos;s API. No account numbers,
                  card numbers, or credentials are ever included. See{' '}
                  <a href="https://www.anthropic.com/privacy" className="text-sky-400 hover:underline" target="_blank" rel="noopener noreferrer">
                    Anthropic&apos;s Privacy Policy
                  </a>.
                </p>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-1">Cloudflare</h3>
                <p className="text-slate-400">
                  Used to provide secure tunnel access to the platform. Cloudflare may process IP addresses and
                  request metadata as part of its network services. See{' '}
                  <a href="https://www.cloudflare.com/privacypolicy/" className="text-sky-400 hover:underline" target="_blank" rel="noopener noreferrer">
                    Cloudflare&apos;s Privacy Policy
                  </a>.
                </p>
              </div>
            </div>

            <p className="mt-4">
              We do not sell, rent, or trade your personal data to any third party. Data is shared with
              the processors above solely to operate the platform.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">5. Data Storage &amp; Security</h2>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li>All data is stored in a PostgreSQL database on self-hosted infrastructure (not a cloud provider).</li>
              <li>The database is accessible only on the internal Docker network — not exposed to the internet.</li>
              <li>Authentication tokens (Plaid, Schwab) are stored in encrypted files on the host, never in the database.</li>
              <li>Passwords are hashed with bcrypt. Plaintext passwords are never stored or logged.</li>
              <li>All external connections use TLS encryption.</li>
              <li>Access to the application requires authentication via JWT tokens, with optional TOTP-based multi-factor authentication.</li>
            </ul>
            <p className="mt-3">
              For full details, see our{' '}
              <Link to="/security" className="text-sky-400 hover:underline">Information Security Policy</Link>.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">6. Data Retention &amp; Deletion Policy</h2>

            <p className="mb-3">
              FinForge maintains a defined data retention and deletion policy to ensure compliance with applicable
              data privacy laws, minimize risk from unnecessary data retention, and manage data securely throughout
              its lifecycle.
            </p>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">6.1 Retention Periods</h3>
            <div className="overflow-x-auto mt-2">
              <table className="w-full text-left text-slate-400">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="py-2 pr-4 text-xs font-semibold text-slate-300">Data Category</th>
                    <th className="py-2 pr-4 text-xs font-semibold text-slate-300">Retention Period</th>
                    <th className="py-2 text-xs font-semibold text-slate-300">Basis</th>
                  </tr>
                </thead>
                <tbody className="text-xs">
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4">Transactions &amp; balance snapshots</td>
                    <td className="py-2 pr-4 text-slate-200">7 years from ingestion</td>
                    <td className="py-2">US tax record-keeping guidelines (IRS)</td>
                  </tr>
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4">Investment holdings &amp; position snapshots</td>
                    <td className="py-2 pr-4 text-slate-200">7 years from ingestion</td>
                    <td className="py-2">Cost basis / capital gains record-keeping</td>
                  </tr>
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4">Goal definitions &amp; progress snapshots</td>
                    <td className="py-2 pr-4 text-slate-200">Lifetime of account</td>
                    <td className="py-2">User-created data, deletable on request</td>
                  </tr>
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4">Account data (username, password hash)</td>
                    <td className="py-2 pr-4 text-slate-200">Lifetime of account</td>
                    <td className="py-2">Required for service operation</td>
                  </tr>
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4">Claude AI chat conversations</td>
                    <td className="py-2 pr-4 text-slate-200">Session only (not persisted)</td>
                    <td className="py-2">Data minimization principle</td>
                  </tr>
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4">Cached AI-generated insights</td>
                    <td className="py-2 pr-4 text-slate-200">Until configured expiry date</td>
                    <td className="py-2">Automatically purged on expiry</td>
                  </tr>
                  <tr className="border-b border-slate-800">
                    <td className="py-2 pr-4">API request logs</td>
                    <td className="py-2 pr-4 text-slate-200">90 days</td>
                    <td className="py-2">Operational debugging &amp; security audit</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4">Cron job execution logs</td>
                    <td className="py-2 pr-4 text-slate-200">1 year</td>
                    <td className="py-2">Data pipeline audit trail</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">6.2 Deletion Procedures</h3>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li><span className="text-slate-200 font-medium">Account deletion:</span> Upon request (or exercise of the right to erasure under GDPR Art. 17), all associated personal data — including account records, transaction history, balances, holdings, goals, and alert logs — is permanently deleted from the database within <span className="text-slate-200">30 days</span>.</li>
              <li><span className="text-slate-200 font-medium">Third-party token revocation:</span> When an account is deleted or a linked financial account is disconnected, the corresponding Plaid access token or Schwab OAuth token is removed from the encrypted token store immediately.</li>
              <li><span className="text-slate-200 font-medium">Automated expiry:</span> Data that has exceeded its retention period is identified and purged through scheduled maintenance processes. AI insight caches are automatically deleted on expiry.</li>
              <li><span className="text-slate-200 font-medium">Secure deletion:</span> Database deletions use standard PostgreSQL <code className="bg-slate-800 px-1.5 py-0.5 rounded text-xs">DELETE</code> operations. The underlying storage is encrypted at rest via FileVault, ensuring deleted data is not recoverable from raw disk.</li>
              <li><span className="text-slate-200 font-medium">Backup propagation:</span> Deleted data is excluded from future backups. Existing backups containing deleted data are retained only for the backup rotation period and are then overwritten.</li>
            </ul>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">6.3 Data Minimization</h3>
            <p className="text-slate-400">
              FinForge collects and retains only the data necessary to provide its core services. Financial data
              is de-identified at ingestion (no account numbers, credentials, or government IDs are ever stored).
              Chat conversations are not persisted. The platform does not collect browsing behavior, device
              fingerprints, or any data beyond what is described in Section 2.
            </p>

            <h3 className="text-sm font-semibold text-slate-200 mt-4 mb-2">6.4 Policy Review</h3>
            <p className="text-slate-400">
              This data retention and deletion policy is reviewed at least annually and updated as needed to
              remain aligned with applicable legal requirements (including GDPR and IRS guidelines) and to
              minimize the risks associated with data breaches and unnecessary data retention.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">7. Cookies &amp; Tracking</h2>
            <p>
              FinForge does <span className="text-slate-200 font-medium">not</span> use cookies for authentication or tracking.
              Authentication tokens are stored in your browser&apos;s localStorage and are cleared on logout.
            </p>
            <p className="mt-2">
              We do not use any third-party analytics, advertising pixels, or tracking technologies.
              No data is shared with ad networks or data brokers.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">8. Your Rights Under GDPR</h2>
            <p className="mb-3">If you are located in the European Economic Area (EEA), you have the following rights:</p>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li><span className="text-slate-200 font-medium">Right of access (Art. 15):</span> Request a copy of all personal data we hold about you.</li>
              <li><span className="text-slate-200 font-medium">Right to rectification (Art. 16):</span> Request correction of inaccurate personal data.</li>
              <li><span className="text-slate-200 font-medium">Right to erasure (Art. 17):</span> Request deletion of your personal data (&ldquo;right to be forgotten&rdquo;).</li>
              <li><span className="text-slate-200 font-medium">Right to restrict processing (Art. 18):</span> Request that we limit how we use your data.</li>
              <li><span className="text-slate-200 font-medium">Right to data portability (Art. 20):</span> Request your data in a structured, machine-readable format.</li>
              <li><span className="text-slate-200 font-medium">Right to object (Art. 21):</span> Object to processing based on legitimate interest.</li>
              <li><span className="text-slate-200 font-medium">Right to withdraw consent (Art. 7(3)):</span> Withdraw consent at any time where processing is based on consent (e.g., third-party account linking).</li>
            </ul>
            <p className="mt-3">
              To exercise any of these rights, contact{' '}
              <a href="mailto:nathan.blatter@yahoo.com" className="text-sky-400 hover:underline">
                nathan.blatter@yahoo.com
              </a>.
              We will respond within 30 days.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">9. International Data Transfers</h2>
            <p>
              Your data is stored on self-hosted infrastructure located in the United States. Where data is
              transmitted to third-party processors (Plaid, Schwab, Anthropic, Cloudflare), those transfers are
              governed by the respective processor&apos;s data protection agreements and standard contractual clauses
              where applicable.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">10. Children&apos;s Privacy</h2>
            <p>
              FinForge is not intended for use by individuals under the age of 18. We do not knowingly collect
              personal data from minors.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">11. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. Changes will be posted on this page with an updated
              &ldquo;Last updated&rdquo; date. Continued use of the platform after changes constitutes acceptance of the
              revised policy.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">12. Supervisory Authority</h2>
            <p>
              If you believe your data protection rights have been violated, you have the right to lodge a complaint
              with a supervisory authority in the EU Member State of your habitual residence, place of work, or place
              of the alleged infringement.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-100 mb-3">13. Contact</h2>
            <p>
              For any questions about this Privacy Policy or your personal data, contact:
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
          <Link to="/security" className="hover:text-sky-400 transition-colors">Information Security Policy</Link>
          <span>&middot;</span>
          <Link to="/login" className="hover:text-sky-400 transition-colors">Sign In</Link>
        </div>
      </div>
    </div>
  )
}
