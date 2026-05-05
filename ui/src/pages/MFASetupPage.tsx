import { useState, type FormEvent } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useNavigate } from 'react-router-dom'

export default function MFASetupPage() {
  const { setupMfa, confirmMfa } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState<'start' | 'scan' | 'done'>('start')
  const [qrCode, setQrCode] = useState('')
  const [secret, setSecret] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSetup() {
    setLoading(true)
    setError('')
    try {
      const data = await setupMfa()
      setQrCode(data.qr_code)
      setSecret(data.secret)
      setStep('scan')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await confirmMfa(code)
      setStep('done')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (step === 'done') {
    return (
      <div className="max-w-md mx-auto mt-12">
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 text-center">
          <div className="text-4xl mb-4">&#10003;</div>
          <h2 className="text-xl font-bold text-emerald-400 mb-2">MFA Enabled</h2>
          <p className="text-sm text-slate-400 mb-6">
            Your account is now protected with two-factor authentication.
          </p>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-2.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    )
  }

  if (step === 'scan') {
    return (
      <div className="max-w-md mx-auto mt-12">
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8">
          <h2 className="text-xl font-bold text-slate-100 mb-2">Scan QR Code</h2>
          <p className="text-sm text-slate-400 mb-6">
            Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)
          </p>

          <div className="flex justify-center mb-6">
            <img
              src={`data:image/png;base64,${qrCode}`}
              alt="MFA QR Code"
              className="w-48 h-48 rounded-lg"
            />
          </div>

          <div className="mb-6">
            <p className="text-xs text-slate-500 mb-1">Or enter this key manually:</p>
            <code className="block bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-sky-400 font-mono break-all select-all">
              {secret}
            </code>
          </div>

          <form onSubmit={handleConfirm} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Enter the 6-digit code from your app
              </label>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="w-full px-4 py-3 bg-slate-900 border border-slate-700 rounded-lg text-slate-100 text-center text-2xl tracking-[0.5em] placeholder:text-slate-600 placeholder:tracking-normal placeholder:text-base focus:outline-none focus:border-sky-500"
                autoFocus
              />
            </div>

            {error && <p className="text-rose-400 text-sm">{error}</p>}

            <button
              type="submit"
              disabled={loading || code.length !== 6}
              className="w-full py-3 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium rounded-lg transition-colors"
            >
              {loading ? 'Verifying...' : 'Enable MFA'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-md mx-auto mt-12">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8">
        <h2 className="text-xl font-bold text-slate-100 mb-2">Set Up MFA</h2>
        <p className="text-sm text-slate-400 mb-6">
          Add an extra layer of security to your account with a time-based one-time password (TOTP).
        </p>

        {error && <p className="text-rose-400 text-sm mb-4">{error}</p>}

        <button
          onClick={handleSetup}
          disabled={loading}
          className="w-full py-3 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 text-white font-medium rounded-lg transition-colors"
        >
          {loading ? 'Generating...' : 'Set Up Authenticator App'}
        </button>
      </div>
    </div>
  )
}
