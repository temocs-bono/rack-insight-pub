import { useMutation } from "@tanstack/react-query";
import { Server } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { accessToken, setTokens, setUser } = useAuthStore();
  const navigate = useNavigate();

  const login = useMutation({
    mutationFn: async () => {
      const tokens = await api.login(username, password);
      setTokens(tokens.access_token, tokens.refresh_token);
      const me = await api.me();
      setUser(me);
      return me;
    },
    onSuccess: () => navigate("/"),
  });

  if (accessToken) return <Navigate to="/" replace />;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate();
  };

  const lastLogin = login.data?.last_login;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <Card className="w-full max-w-sm">
        <CardContent className="p-8">
          <div className="mb-6 flex flex-col items-center gap-2">
            <Server className="h-10 w-10 text-blue-600" />
            <h1 className="text-xl font-semibold">Rack Insight</h1>
            <p className="text-sm text-gray-500">
              Hardware &amp; Firmware Inventory Management
            </p>
          </div>
          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            <Input
              placeholder="Username"
              value={username}
              autoFocus
              onChange={(e) => setUsername(e.target.value)}
            />
            <Input
              placeholder="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {login.isError && (
              <p className="text-sm text-red-600">
                {login.error instanceof ApiError
                  ? login.error.message
                  : "Login failed"}
              </p>
            )}
            {lastLogin && (
              <p className="text-xs text-gray-500">
                Last login: {new Date(lastLogin).toLocaleString()}
              </p>
            )}
            <Button type="submit" disabled={login.isPending || !username || !password}>
              {login.isPending ? "Signing in…" : "Login"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
