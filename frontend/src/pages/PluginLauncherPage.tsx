import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  HelpCircle,
  Lock,
  Puzzle,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/ui/badge";
import { usePlugins } from "@/hooks/queries";
import { api } from "@/services/api";
import type { Plugin, PluginStatus } from "@/types";

function StatusBadge({ status }: { status: PluginStatus }) {
  if (status === "HEALTHY")
    return (
      <Badge variant="success">
        <CheckCircle2 className="h-3 w-3" /> Healthy
      </Badge>
    );
  if (status === "UNHEALTHY")
    return (
      <Badge variant="critical">
        <XCircle className="h-3 w-3" /> Unhealthy
      </Badge>
    );
  if (status === "DISABLED")
    return (
      <Badge variant="muted">
        <Lock className="h-3 w-3" /> Disabled
      </Badge>
    );
  return (
    <Badge variant="warning">
      <HelpCircle className="h-3 w-3" /> Unknown
    </Badge>
  );
}

/** Card in the plugin grid. Only plugins that advertise a UI are launchable. */
function PluginCard({ plugin }: { plugin: Plugin }) {
  const hasUi = Boolean(plugin.ui);
  const launchable = hasUi && plugin.enabled && plugin.status !== "DISABLED";
  const title = plugin.ui?.title || plugin.display_name;

  const body = (
    <div
      className={`flex h-full flex-col gap-3 rounded-lg border bg-white p-4 transition-colors ${
        launchable
          ? "border-gray-200 hover:border-blue-400 hover:shadow-sm"
          : "border-gray-200 opacity-70"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 font-medium text-gray-800">
          <Puzzle className="h-4 w-4 text-blue-600" />
          {title}
        </div>
        <StatusBadge status={plugin.status} />
      </div>
      {plugin.description && (
        <p className="line-clamp-2 text-sm text-gray-500">{plugin.description}</p>
      )}
      <div className="mt-auto flex items-center justify-between text-xs text-gray-400">
        <span>{plugin.version ? `v${plugin.version}` : plugin.name}</span>
        {hasUi ? (
          launchable ? (
            <span className="flex items-center gap-1 text-blue-600">
              Open <ExternalLink className="h-3 w-3" />
            </span>
          ) : (
            <span>Unavailable</span>
          )
        ) : (
          <span>Backend only</span>
        )}
      </div>
    </div>
  );

  if (!launchable) return body;
  return (
    <Link to={`/plugins/${plugin.name}`} className="block">
      {body}
    </Link>
  );
}

function PluginGrid() {
  const { data: plugins, isLoading } = usePlugins();

  if (isLoading) return <p className="text-sm text-gray-500">Loading plugins…</p>;

  const list = plugins ?? [];
  if (list.length === 0) {
    return (
      <EmptyState
        Icon={Puzzle}
        title="No plugins"
        description="No plugins are registered. Ask an administrator to register one under Administration → Plugins."
      />
    );
  }

  return (
    <>
      <Breadcrumb crumbs={[{ label: "Plugins" }]} />
      <p className="mb-4 text-sm text-gray-500">
        Extensions running as independent services. Select one to open its
        embedded interface.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((p) => (
          <PluginCard key={p.id} plugin={p} />
        ))}
      </div>
    </>
  );
}

/**
 * Embed the selected plugin's own frontend as a same-origin iframe. Before
 * pointing the iframe at the Core UI proxy, we mint the short-lived
 * `ri_plugin_ui` cookie: an iframe navigation cannot carry the SPA's in-memory
 * Bearer token, so the cookie is how the proxy authenticates it. The plugin JS
 * then calls back through the Core proxy, reusing the same cookie.
 */
function PluginFrame({ plugin }: { plugin: Plugin }) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setError(null);
    api
      .createPluginUiSession()
      .then(() => {
        if (!cancelled) setReady(true);
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Could not start plugin session");
      });
    return () => {
      cancelled = true;
    };
  }, [plugin.name]);

  const src = `/api/plugins/${plugin.name}/ui/`;

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Link
            to="/plugins"
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800"
          >
            <ArrowLeft className="h-4 w-4" /> Plugins
          </Link>
          <span className="text-gray-300">/</span>
          <span className="flex items-center gap-2 font-medium text-gray-800">
            <Puzzle className="h-4 w-4 text-blue-600" />
            {plugin.ui?.title || plugin.display_name}
          </span>
        </div>
        <StatusBadge status={plugin.status} />
      </div>

      {error ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-red-200 bg-red-50 text-sm text-red-700">
          <AlertTriangle className="mr-2 h-4 w-4" /> {error}
        </div>
      ) : !ready ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-500">
          Starting plugin session…
        </div>
      ) : (
        <iframe
          key={plugin.name}
          title={plugin.ui?.title || plugin.display_name}
          src={src}
          className="flex-1 rounded-lg border border-gray-200 bg-white"
          // The plugin is untrusted third-party code: sandbox it. allow-scripts
          // + allow-same-origin lets its JS call the Core proxy with the cookie;
          // we deliberately do NOT grant allow-top-navigation or allow-popups.
          sandbox="allow-scripts allow-same-origin allow-forms"
        />
      )}
    </div>
  );
}

/** Detail route: resolve the plugin by name, then embed it. */
function PluginDetail({ name }: { name: string }) {
  const { data: plugins, isLoading } = usePlugins();

  if (isLoading) return <p className="text-sm text-gray-500">Loading…</p>;

  const backLink = (
    <Link to="/plugins" className="text-sm font-medium text-blue-600 hover:underline">
      Back to Plugins
    </Link>
  );

  const plugin = (plugins ?? []).find((p) => p.name === name);
  if (!plugin) {
    return (
      <EmptyState
        Icon={AlertTriangle}
        title="Plugin not found"
        description={`No plugin named "${name}" is registered.`}
        action={backLink}
      />
    );
  }
  if (!plugin.ui) {
    return (
      <EmptyState
        Icon={Puzzle}
        title="No interface"
        description={`"${plugin.display_name}" is a backend-only plugin and has no embedded UI.`}
        action={backLink}
      />
    );
  }
  return <PluginFrame plugin={plugin} />;
}

export function PluginLauncherPage() {
  const { name } = useParams<{ name: string }>();
  return name ? <PluginDetail name={name} /> : <PluginGrid />;
}
