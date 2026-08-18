"""Canonical RBAC catalog (1.2.1).

Single source of truth for the permission codes, the built-in system roles and
their permission mappings, and the menu -> permission map used to drive the
sidebar. The startup seeder (``services.rbac_service.ensure_rbac_seed``) upserts
these idempotently, so adding a permission here is enough to have it appear in
every environment on the next start.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    name: str
    category: str
    description: str


# --- Permission catalog (business actions, grouped by category) --------------
PERMISSIONS: tuple[PermissionDef, ...] = (
    # Dashboard & inventory (read surfaces)
    PermissionDef("dashboard.view", "View Dashboard", "Dashboard", "View the fleet dashboard"),
    PermissionDef("inventory.view", "View Inventory", "Inventory", "Browse racks, devices and inventory search"),
    # Clusters
    PermissionDef("cluster.view", "View Clusters", "Cluster", "View clusters"),
    PermissionDef("cluster.create", "Create Cluster", "Cluster", "Create a cluster"),
    PermissionDef("cluster.update", "Update Cluster", "Cluster", "Edit a cluster"),
    PermissionDef("cluster.delete", "Delete Cluster", "Cluster", "Delete a cluster"),
    # Racks
    PermissionDef("rack.view", "View Racks", "Rack", "View racks"),
    PermissionDef("rack.create", "Create Rack", "Rack", "Create racks"),
    PermissionDef("rack.update", "Update Rack", "Rack", "Edit racks"),
    PermissionDef("rack.delete", "Delete Rack", "Rack", "Delete racks"),
    PermissionDef("rack.layout.edit", "Edit Rack Layout", "Rack", "Change device placement in a rack"),
    # Device templates
    PermissionDef("template.view", "View Templates", "Device Template", "View device templates"),
    PermissionDef("template.create", "Create Template", "Device Template", "Create device templates"),
    PermissionDef("template.update", "Update Template", "Device Template", "Edit device templates"),
    PermissionDef("template.delete", "Delete Template", "Device Template", "Delete device templates"),
    # Installed devices
    PermissionDef("device.view", "View Devices", "Device", "View installed devices"),
    PermissionDef("device.install", "Install Device", "Device", "Create / install devices"),
    PermissionDef("device.update", "Update Device", "Device", "Edit installed devices"),
    PermissionDef("device.delete", "Delete Device", "Device", "Delete installed devices"),
    PermissionDef("device.move", "Move Device", "Device", "Change a device rack position"),
    # Credentials
    PermissionDef("credential.view", "View Credentials", "Credential", "View credentials (never secrets)"),
    PermissionDef("credential.create", "Create Credential", "Credential", "Create credentials"),
    PermissionDef("credential.update", "Update Credential", "Credential", "Edit credentials"),
    PermissionDef("credential.delete", "Delete Credential", "Credential", "Delete credentials"),
    # Collectors
    PermissionDef("collector.view", "View Collectors", "Collector", "View collector status and logs"),
    PermissionDef("collector.run", "Run Collector", "Collector", "Trigger collection / refresh"),
    # Discovery
    PermissionDef("discovery.view", "View Discovery", "Discovery", "View discovered devices"),
    PermissionDef("discovery.scan", "Run Discovery Scan", "Discovery", "Run an SNMP discovery scan"),
    PermissionDef("discovery.import", "Import Discovery", "Discovery", "Import discovered devices"),
    # Lifecycle
    PermissionDef("lifecycle.view", "View Lifecycle", "Lifecycle", "View retention policies"),
    PermissionDef("lifecycle.manage", "Manage Lifecycle", "Lifecycle", "Edit retention policies and run cleanup"),
    # Export & audit
    PermissionDef("export.run", "Export Data", "Export", "Export inventory data"),
    PermissionDef("audit.view", "View Audit Log", "Audit", "View the audit log"),
    # Alerts & history (1.3.0 Operations)
    PermissionDef("alert.view", "View Alerts", "Alerts", "View the Alert Center"),
    PermissionDef("alert.resolve", "Resolve Alerts", "Alerts", "Resolve active alerts"),
    PermissionDef("history.view", "View Device History", "Alerts", "View the permanent device history"),
    # Access management
    PermissionDef("user.view", "View Users", "Access Management", "View users"),
    PermissionDef("user.create", "Create User", "Access Management", "Create users"),
    PermissionDef("user.update", "Update User", "Access Management", "Edit users"),
    PermissionDef("user.delete", "Delete User", "Access Management", "Delete users"),
    PermissionDef("group.view", "View User Groups", "Access Management", "View user groups"),
    PermissionDef("group.create", "Create User Group", "Access Management", "Create user groups"),
    PermissionDef("group.update", "Update User Group", "Access Management", "Edit user groups and membership"),
    PermissionDef("group.delete", "Delete User Group", "Access Management", "Delete user groups"),
    PermissionDef("role.view", "View Roles", "Access Management", "View roles"),
    PermissionDef("role.create", "Create Role", "Access Management", "Create roles"),
    PermissionDef("role.update", "Update Role", "Access Management", "Edit roles and their permissions"),
    PermissionDef("role.delete", "Delete Role", "Access Management", "Delete roles"),
    PermissionDef("binding.view", "View Role Bindings", "Access Management", "View role bindings"),
    PermissionDef("binding.create", "Create Role Binding", "Access Management", "Bind roles to groups"),
    PermissionDef("binding.delete", "Delete Role Binding", "Access Management", "Remove role bindings"),
    PermissionDef("permission.view", "View Permissions", "Access Management", "View the permission catalog"),
    # Plugins (Plugin Architecture Foundation). Plugins may add their own
    # namespaced permissions (plugin.<name>.<action>) via their manifest in a
    # future release; these are the Core-level plugin permissions.
    PermissionDef("plugin.view", "View Plugins", "Plugins", "View the plugin registry and status"),
    PermissionDef("plugin.manage", "Manage Plugins", "Plugins", "Register, enable/disable and remove plugins"),
    PermissionDef("plugin.proxy", "Use Plugin APIs", "Plugins", "Call plugin APIs through the Core proxy"),
)

ALL_PERMISSION_CODES: tuple[str, ...] = tuple(p.code for p in PERMISSIONS)

# --- System roles ------------------------------------------------------------
# Administrator implicitly receives every permission (kept in sync with the
# catalog). Operator runs day-to-day operations but cannot manage access.
# Viewer is read-only.
_VIEW_ONLY = (
    "dashboard.view", "inventory.view", "cluster.view", "rack.view",
    "template.view", "device.view", "credential.view", "collector.view",
    "discovery.view", "lifecycle.view", "audit.view",
    "alert.view", "history.view", "plugin.view",
)

_OPERATOR = _VIEW_ONLY + (
    "alert.resolve",
    "plugin.proxy",
    "cluster.create", "cluster.update", "cluster.delete",
    "rack.create", "rack.update", "rack.delete", "rack.layout.edit",
    "template.create", "template.update", "template.delete",
    "device.install", "device.update", "device.delete", "device.move",
    "credential.create", "credential.update", "credential.delete",
    "collector.run",
    "discovery.scan", "discovery.import",
    "lifecycle.manage",
    "export.run",
)

SYSTEM_ROLES: dict[str, dict] = {
    "Administrator": {
        "description": "Full access to every feature, including access management.",
        "permissions": ALL_PERMISSION_CODES,
    },
    "Operator": {
        "description": "Manage inventory, run collectors and discovery. No access management.",
        "permissions": tuple(dict.fromkeys(_OPERATOR)),
    },
    "Viewer": {
        "description": "Read-only access to inventory and reports.",
        "permissions": _VIEW_ONLY,
    },
}

ADMIN_ROLE_NAME = "Administrator"
ADMIN_GROUP_NAME = "Administrators"
ADMIN_GROUP_DESCRIPTION = "Built-in group granted the Administrator role."

# --- Menu -> required permission (drives the sidebar) ------------------------
# The frontend keeps its own copy for the sidebar; this list is exposed via
# /auth/me so the two never drift.
MENU_PERMISSIONS: tuple[dict[str, str], ...] = (
    {"key": "dashboard", "permission": "dashboard.view"},
    {"key": "inventory", "permission": "inventory.view"},
    {"key": "alerts", "permission": "alert.view"},
    {"key": "history", "permission": "history.view"},
    {"key": "clusters", "permission": "cluster.view"},
    {"key": "racks", "permission": "rack.view"},
    {"key": "device-templates", "permission": "template.view"},
    {"key": "devices", "permission": "device.view"},
    {"key": "credentials", "permission": "credential.view"},
    {"key": "discovery", "permission": "discovery.view"},
    {"key": "collectors", "permission": "collector.view"},
    {"key": "lifecycle", "permission": "lifecycle.view"},
    {"key": "audit", "permission": "audit.view"},
    {"key": "users", "permission": "user.view"},
    {"key": "user-groups", "permission": "group.view"},
    {"key": "roles", "permission": "role.view"},
    {"key": "role-bindings", "permission": "binding.view"},
    {"key": "permissions", "permission": "permission.view"},
    {"key": "plugins", "permission": "plugin.view"},
)
