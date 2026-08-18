import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Bell,
  BellRing,
  Boxes,
  ChevronDown,
  Cpu,
  HardDrive,
  History,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Puzzle,
  Radar,
  Recycle,
  ScrollText,
  Search,
  Server,
  Settings,
  ShieldCheck,
  UserCog,
  Users,
  UsersRound,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Toaster } from "@/components/Toaster";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";
import { countUnread } from "@/stores/alertsSeen";
import { useAuthStore } from "@/stores/auth";

interface MenuItem {
  to: string;
  label: string;
  Icon: LucideIcon;
  permission: string;
}

interface MenuSection {
  key: string;
  label: string;
  Icon: LucideIcon;
  items: MenuItem[];
}

const TOP_MENU: MenuItem[] = [
  { to: "/", label: "Dashboard", Icon: LayoutDashboard, permission: "dashboard.view" },
  { to: "/search", label: "Inventory Search", Icon: Search, permission: "inventory.view" },
  { to: "/plugins", label: "Plugins", Icon: Puzzle, permission: "plugin.view" },
];

const SECTIONS: MenuSection[] = [
  {
    key: "inventory",
    label: "Inventory",
    Icon: Boxes,
    items: [
      { to: "/admin/clusters", label: "Clusters", Icon: Boxes, permission: "cluster.view" },
      { to: "/admin/racks", label: "Racks", Icon: Server, permission: "rack.view" },
      { to: "/admin/devices", label: "Devices", Icon: HardDrive, permission: "device.view" },
      { to: "/admin/device-templates", label: "Device Templates", Icon: Cpu, permission: "template.view" },
    ],
  },
  {
    key: "operations",
    label: "Operations",
    Icon: Wrench,
    items: [
      { to: "/admin/discovery", label: "Discovery", Icon: Radar, permission: "discovery.view" },
      { to: "/admin/collectors", label: "Collector", Icon: Activity, permission: "collector.view" },
      { to: "/admin/lifecycle", label: "Lifecycle", Icon: Recycle, permission: "lifecycle.view" },
    ],
  },
  {
    key: "alerts",
    label: "Alerts",
    Icon: BellRing,
    items: [
      { to: "/alerts", label: "Alerts", Icon: BellRing, permission: "alert.view" },
      { to: "/history", label: "History", Icon: History, permission: "history.view" },
    ],
  },
  {
    key: "administration",
    label: "Administration",
    Icon: Settings,
    items: [
      { to: "/admin/credentials", label: "Credentials", Icon: KeyRound, permission: "credential.view" },
      { to: "/admin/plugins", label: "Plugin Registry", Icon: Puzzle, permission: "plugin.view" },
    ],
  },
  {
    key: "access",
    label: "Access Management",
    Icon: ShieldCheck,
    items: [
      { to: "/admin/users", label: "Users", Icon: UserCog, permission: "user.view" },
      { to: "/admin/user-groups", label: "User Groups", Icon: UsersRound, permission: "group.view" },
      { to: "/admin/roles", label: "Roles", Icon: Users, permission: "role.view" },
      { to: "/admin/audit", label: "Audit Log", Icon: ScrollText, permission: "audit.view" },
    ],
  },
];

const COLLAPSE_STORAGE_KEY = "rack-insight-sidebar-sections";

function loadCollapsed(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(COLLAPSE_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function NotificationBell() {
  const navigate = useNavigate();
  const { hasPermission } = useAuthStore();
  const canView = hasPermission("alert.view");
  const { data } = useQuery({
    queryKey: ["dashboard", "alerts"],
    queryFn: api.dashboardAlerts,
    refetchInterval: 30_000,
    enabled: canView,
  });
  if (!canView) return null;

  const active =
    (data?.active_critical ?? 0) + (data?.active_warning ?? 0) + (data?.active_info ?? 0);
  const unread = data ? countUnread(data.latest_alerts.map((a) => a.created_at)) : 0;

  return (
    <button
      type="button"
      title={`${active} active alert${active !== 1 ? "s" : ""}`}
      onClick={() => navigate("/alerts")}
      className="relative rounded-md p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
    >
      {active > 0 ? <BellRing className="h-5 w-5" /> : <Bell className="h-5 w-5" />}
      {unread > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </button>
  );
}

function SidebarLink({ to, label, Icon }: { to: string; label: string; Icon: LucideIcon }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
          isActive
            ? "bg-blue-600 font-medium text-white"
            : "text-gray-600 hover:bg-gray-100"
        }`
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
    </NavLink>
  );
}

export function AppLayout() {
  const { accessToken, user, logout, hasPermission } = useAuthStore();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsed);

  if (!accessToken) return <Navigate to="/login" replace />;

  const toggleSection = (key: string) =>
    setCollapsed((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore storage failures (private mode, quota)
      }
      return next;
    });

  const topItems = TOP_MENU.filter((i) => hasPermission(i.permission));
  const sections = SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((i) => hasPermission(i.permission)),
  })).filter((section) => section.items.length > 0);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-gray-200 bg-white">
        <div className="flex h-14 items-center justify-between px-6">
          <Link to="/" className="flex items-center gap-2 font-semibold text-blue-700">
            <Server className="h-5 w-5" />
            Rack Insight
          </Link>
          <div className="flex items-center gap-3 text-sm text-gray-600">
            <NotificationBell />
            {user && (
              <span>
                {user.display_name || user.username}
                <span className="ml-1 rounded bg-gray-100 px-1.5 py-0.5 text-xs uppercase">
                  {user.role}
                </span>
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      <div className="flex flex-1">
        <aside className="w-60 shrink-0 border-r border-gray-200 bg-white p-3">
          <nav className="flex flex-col gap-1">
            {topItems.map((item) => (
              <SidebarLink key={item.to} to={item.to} label={item.label} Icon={item.Icon} />
            ))}

            {sections.map((section) => {
              const isCollapsed = collapsed[section.key] ?? false;
              return (
                <div key={section.key} className="mt-3">
                  <button
                    type="button"
                    onClick={() => toggleSection(section.key)}
                    className="flex w-full items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold uppercase tracking-wide text-gray-400 hover:bg-gray-50"
                    aria-expanded={!isCollapsed}
                  >
                    <section.Icon className="h-3.5 w-3.5" />
                    <span className="flex-1 text-left">{section.label}</span>
                    <ChevronDown
                      className={`h-3.5 w-3.5 transition-transform ${
                        isCollapsed ? "-rotate-90" : ""
                      }`}
                    />
                  </button>
                  {!isCollapsed && (
                    <div className="mt-1 flex flex-col gap-1">
                      {section.items.map((item) => (
                        <SidebarLink
                          key={item.to}
                          to={item.to}
                          label={item.label}
                          Icon={item.Icon}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>
        </aside>

        <main className="min-w-0 flex-1 px-6 py-6">
          <div className="mx-auto max-w-[1700px]">
            <Outlet />
          </div>
        </main>
      </div>

      <Toaster />
    </div>
  );
}
