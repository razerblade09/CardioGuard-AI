import { signOut } from 'firebase/auth';
import { auth } from '../firebase';

// Compact ECG waveform for the header — "system is live" indicator
function ECGHeaderPulse() {
  return (
    <div className="ecg-header-indicator">
      <svg viewBox="0 0 120 24" preserveAspectRatio="none">
        <polyline
          className="ecg-header-line"
          points="0,12 15,12 20,12 25,4 28,20 31,10 34,12 50,12 55,12 60,4 63,20 66,10 69,12 85,12 90,12 95,4 98,20 101,10 104,12 120,12"
          fill="none"
        />
      </svg>
    </div>
  );
}

export default function Navbar({ user }) {
  const initials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : 'DR';

  async function handleLogout() {
    try { await signOut(auth); } catch (e) { console.error(e); }
  }

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="navbar-icon" />
        <span className="navbar-name">CardioGuard AI</span>
        <span className="navbar-badge">Clinical</span>
        <ECGHeaderPulse />
      </div>

      <div className="navbar-right">
        <div className="navbar-user">
          <div className="navbar-avatar">{initials}</div>
          <span>{user?.email ?? 'Doctor'}</span>
        </div>
        <button
          id="btn-logout"
          className="btn-logout"
          onClick={handleLogout}
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
