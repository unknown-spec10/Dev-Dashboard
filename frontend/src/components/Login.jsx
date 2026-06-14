import React, { useState } from 'react';
import axios from 'axios';
import { Mail, Key, Shield, ArrowRight, Loader2, Chrome, AlertCircle, HelpCircle } from 'lucide-react';

export default function Login({ onLoginSuccess }) {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState(1); // 1 = enter email, 2 = enter code
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [mockOAuthEmail, setMockOAuthEmail] = useState('');

  // Handle requesting OTP
  const handleRequestOtp = async (e) => {
    e.preventDefault();
    if (!email) return;
    setIsLoading(true);
    setError('');
    setSuccess('');
    try {
      await axios.post('/api/auth/otp/request', { email });
      setSuccess('Verification code logged to backend console!');
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to request verification code.');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle verifying OTP
  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    if (!code) return;
    setIsLoading(true);
    setError('');
    try {
      const res = await axios.post('/api/auth/otp/verify', { email, code });
      onLoginSuccess(res.data.access_token);
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid or expired verification code.');
    } finally {
      setIsLoading(false);
    }
  };

  // Trigger Google OAuth2 Login (real or mock)
  const handleGoogleLogin = () => {
    window.location.href = '/api/auth/oauth/google/login';
  };

  // Trigger Google Mock Login with custom email
  const handleMockGoogleLogin = (e) => {
    e.preventDefault();
    if (!mockOAuthEmail) return;
    const targetEmail = mockOAuthEmail.toLowerCase().strip ? mockOAuthEmail.toLowerCase().strip() : mockOAuthEmail.toLowerCase().trim();
    window.location.href = `/api/auth/oauth/google/login?email=${encodeURIComponent(targetEmail)}`;
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 px-4 relative overflow-hidden font-sans selection:bg-blue-500/30">
      {/* Decorative background orbs */}
      <div className="absolute top-1/4 left-1/4 h-[350px] w-[350px] rounded-full bg-blue-600/10 blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-1/4 right-1/4 h-[400px] w-[400px] rounded-full bg-indigo-600/10 blur-[130px] pointer-events-none"></div>

      <div className="w-full max-w-md z-10">
        {/* Header Branding */}
        <div className="flex flex-col items-center mb-8 text-center animate-fade-in">
          <div className="h-12 w-12 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shadow-xl shadow-blue-500/25 mb-4">
            <Shield className="text-white" size={24} />
          </div>
          <h2 className="text-2xl font-black text-white tracking-tight">Access Dev Dashboard</h2>
          <p className="text-slate-400 text-sm mt-1">Unified LLM Proxy & Task Management Platform</p>
        </div>

        {/* Login Card */}
        <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-2xl p-8 shadow-2xl shadow-black/40">
          
          {error && (
            <div className="mb-5 bg-red-950/40 border border-red-900/30 rounded-xl p-3.5 flex items-start gap-2.5 text-xs text-red-300">
              <AlertCircle size={15} className="shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div className="mb-5 bg-emerald-950/40 border border-emerald-900/30 rounded-xl p-3.5 flex items-start gap-2.5 text-xs text-emerald-300">
              <Shield size={15} className="shrink-0 mt-0.5" />
              <span>{success}</span>
            </div>
          )}

          {step === 1 ? (
            /* Step 1: Email Form */
            <form onSubmit={handleRequestOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Email Address</label>
                <div className="relative flex items-center bg-slate-950 border border-slate-800/80 focus-within:border-blue-500 rounded-xl transition-all duration-300">
                  <span className="pl-3.5 text-slate-500"><Mail size={16} /></span>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@company.com"
                    className="w-full pl-3 pr-4 py-3 bg-transparent text-sm text-white placeholder-slate-600 focus:outline-none"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading || !email}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white font-semibold text-sm py-3 px-4 rounded-xl flex items-center justify-center gap-1.5 transition-all shadow-lg shadow-blue-600/15 cursor-pointer"
              >
                {isLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <>
                    Send Verification Code <ArrowRight size={15} />
                  </>
                )}
              </button>
            </form>
          ) : (
            /* Step 2: OTP Form */
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">Verification Code</label>
                  <button
                    type="button"
                    onClick={() => { setStep(1); setError(''); }}
                    className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer underline"
                  >
                    Change Email
                  </button>
                </div>
                <div className="relative flex items-center bg-slate-950 border border-slate-800/80 focus-within:border-blue-500 rounded-xl transition-all duration-300">
                  <span className="pl-3.5 text-slate-500"><Key size={16} /></span>
                  <input
                    type="text"
                    required
                    maxLength={6}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="Enter 6-digit OTP"
                    className="w-full pl-3 pr-4 py-3 bg-transparent text-sm text-white placeholder-slate-600 tracking-[0.2em] font-mono focus:outline-none"
                  />
                </div>
                <p className="text-[11px] text-slate-500 mt-2 flex items-center gap-1">
                  <HelpCircle size={12} />
                  Check backend logs for code (e.g. <code>docker compose logs api</code>)
                </p>
              </div>

              <button
                type="submit"
                disabled={isLoading || code.length !== 6}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white font-semibold text-sm py-3 px-4 rounded-xl flex items-center justify-center gap-1.5 transition-all shadow-lg shadow-blue-600/15 cursor-pointer"
              >
                {isLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <>
                    Verify & Login <ArrowRight size={15} />
                  </>
                )}
              </button>
            </form>
          )}

          {/* Divider */}
          <div className="relative my-6 flex items-center justify-center">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-800/60"></div>
            </div>
            <span className="relative bg-slate-900 px-3 text-[10px] uppercase font-bold tracking-wider text-slate-500">Or Continue With</span>
          </div>

          {/* OAuth options */}
          <div className="space-y-3">
            {/* Real Google Login */}
            <button
              onClick={handleGoogleLogin}
              className="w-full border border-slate-800 hover:border-slate-700 bg-slate-950/40 hover:bg-slate-950 text-slate-200 font-semibold text-sm py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 cursor-pointer transition-all"
            >
              <Chrome size={16} className="text-red-400" />
              <span>Google Account</span>
            </button>

            {/* Mock Google Login for Local Development */}
            <form onSubmit={handleMockGoogleLogin} className="flex gap-2 mt-4 pt-4 border-t border-slate-800/40">
              <input
                type="email"
                required
                value={mockOAuthEmail}
                onChange={(e) => setMockOAuthEmail(e.target.value)}
                placeholder="mock-email@example.com"
                className="w-full px-3 py-1.5 bg-slate-950 border border-slate-800/80 rounded-lg text-xs text-white placeholder-slate-600 focus:outline-none focus:border-slate-700"
              />
              <button
                type="submit"
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg shrink-0 cursor-pointer transition-all"
              >
                Mock Google
              </button>
            </form>
          </div>

        </div>
      </div>
    </div>
  );
}
