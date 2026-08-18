import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Me } from "@/types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: Me | null;
  setTokens: (access: string, refresh: string) => void;
  setUser: (user: Me | null) => void;
  logout: () => void;
  /** True if the current user holds the given business-action permission.
   *  Legacy ADMIN role is treated as a superuser (all permissions). */
  hasPermission: (code: string) => boolean;
  hasAnyPermission: (codes: string[]) => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setTokens: (access, refresh) =>
        set({ accessToken: access, refreshToken: refresh }),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
      hasPermission: (code) => {
        const user = get().user;
        if (!user) return false;
        if (user.role === "ADMIN") return true;
        return user.permissions?.includes(code) ?? false;
      },
      hasAnyPermission: (codes) => {
        const user = get().user;
        if (!user) return false;
        if (user.role === "ADMIN") return true;
        return codes.some((c) => user.permissions?.includes(c));
      },
    }),
    { name: "rack-insight-auth" },
  ),
);
