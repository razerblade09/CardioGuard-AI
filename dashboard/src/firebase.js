import { initializeApp, getApps } from 'firebase/app';
import { getAuth }     from 'firebase/auth';
import { getDatabase, forceLongPolling } from 'firebase/database';

const firebaseConfig = {
  apiKey:            import.meta.env.VITE_FIREBASE_API_KEY            ?? 'PLACEHOLDER',
  authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN        ?? 'placeholder.firebaseapp.com',
  databaseURL:       import.meta.env.VITE_FIREBASE_DATABASE_URL       ?? 'https://placeholder-default-rtdb.firebaseio.com',
  projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID         ?? 'placeholder',
  storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET     ?? 'placeholder.appspot.com',
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID ?? '000000000000',
  appId:             import.meta.env.VITE_FIREBASE_APP_ID              ?? '1:000000000000:web:placeholder',
};

const app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db   = getDatabase(app);

// Force HTTP long polling to bypass WebSocket restrictions
try {
  forceLongPolling(db);
  console.log("[Firebase] Forced HTTP Long Polling successfully.");
} catch (e) {
  console.warn("[Firebase] Failed to force long polling:", e);
}

export const IS_CONFIGURED = !!import.meta.env.VITE_FIREBASE_API_KEY;
