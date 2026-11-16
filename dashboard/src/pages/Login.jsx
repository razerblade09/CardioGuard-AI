import { signInWithEmailAndPassword } from 'firebase/auth';
import { useState } from 'react';
import { auth } from '../firebase';

export default function Login() {
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [error,    setError]    = useState('');
  const [loading,  setLoading]  = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signInWithEmailAndPassword(auth, email, password);
      // App.jsx auth listener will redirect automatically
    } catch (err) {
      setError(friendlyError(err.code));
    } finally {
      setLoading(false);
    }
  }

  function friendlyError(code) {
    switch (code) {
      case 'auth/invalid-credential':
      case 'auth/user-not-found':
      case 'auth/wrong-password':
        return 'Invalid email or password. Please try again.';
      case 'auth/too-many-requests':
        return 'Too many failed attempts. Please wait a moment.';
      default:
        return 'Login failed. Check your connection and try again.';
    }
  }

  // ECG waveform path — a clinical PQRST complex repeated
  const ecgPath = "M0,30 L30,30 L35,28 L40,30 L60,30 L65,30 L70,22 L75,30 L80,30 L85,8 L90,50 L95,25 L100,30 L130,30 L135,28 L140,30 L160,30 L165,30 L170,22 L175,30 L180,30 L185,8 L190,50 L195,25 L200,30 L230,30 L235,28 L240,30 L260,30 L265,30 L270,22 L275,30 L280,30 L285,8 L290,50 L295,25 L300,30 L330,30 L335,28 L340,30 L360,30 L365,30 L370,22 L375,30 L380,30 L385,8 L390,50 L395,25 L400,30 L430,30 L435,28 L440,30 L460,30 L465,30 L470,22 L475,30 L480,30 L485,8 L490,50 L495,25 L500,30";

  return (
    <div className="login-page">
      {/* Left panel — system identity + ECG waveform */}
      <div className="login-left">
        <div className="login-system-name">CardioGuard AI</div>
        <div className="login-tagline">
          Real-time ECG monitoring and cardiovascular disease prediction system
        </div>

        <div className="login-ecg-container">
          <svg viewBox="0 0 500 60" preserveAspectRatio="none">
            <polyline
              className="ecg-waveform-line"
              points={ecgPath.replace(/[ML]/g, '').replace(/\s+/g, ' ').trim()}
            />
          </svg>
        </div>

        <div className="login-system-badge">For Healthcare Professionals</div>
      </div>

      {/* Right panel — login form */}
      <div className="login-right">
        <div className="login-card">
          {/* Header */}
          <div className="login-header">
            <div className="login-brand">
              <span className="login-brand-name">Clinical Dashboard</span>
            </div>
            <h1 className="login-title">Sign in</h1>
            <p className="login-subtitle">Access your clinical monitoring dashboard</p>
          </div>

          {/* Form */}
          <form className="login-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="email">Email Address</label>
              <input
                id="email"
                type="email"
                className="form-input"
                placeholder="doctor@hospital.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                className="form-input"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>

            {error && <div className="login-error">{error}</div>}

            <button
              id="btn-login"
              type="submit"
              className="btn-login"
              disabled={loading}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="login-footer">
            CardioGuard AI is authorized for clinical use only.
          </p>
        </div>
      </div>
    </div>
  );
}
