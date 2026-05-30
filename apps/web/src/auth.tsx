import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, Me } from "./api";

type Ctx = {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      // Cookie either exists (server returns Me) or doesn't (401 -> null).
      try {
        setMe(await api.me());
      } catch {
        setMe(null);
      }
      setLoading(false);
    })();
  }, []);

  const login = async (email: string, password: string) => {
    await api.login(email, password);
    setMe(await api.me());
  };
  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // ignore — we still drop local state
    }
    setMe(null);
  };

  return <AuthCtx.Provider value={{ me, loading, login, logout }}>{children}</AuthCtx.Provider>;
}

export function useAuth(): Ctx {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("AuthProvider missing");
  return c;
}
