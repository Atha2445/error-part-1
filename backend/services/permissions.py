"""
Central permissions registry.

Each entry maps a page/module key (used in the sidebar and DB) to its display metadata.
Admin users get ALL permissions by default. New users get the DEFAULT_PERMISSIONS set.
"""

ALL_PERMISSIONS = [
    {"key": "dashboard",  "label": "Dashboard",        "description": "View dashboard overview and stats"},
    {"key": "analytics",  "label": "Analytics",        "description": "Surveillance trends, threat distribution, and data analysis"},
    {"key": "analyze",    "label": "Video Analysis",    "description": "Upload and analyze videos"},
    {"key": "detections", "label": "Detection Logs",    "description": "View detection log history"},
    {"key": "prompts",    "label": "Manage Prompts",    "description": "Add and delete detection prompts"},
    {"key": "verdicts",   "label": "Video Verdicts",    "description": "View video verdict history"},
    {"key": "cctv",       "label": "Manage CCTV",       "description": "Add, remove and monitor CCTV cameras"},
    {"key": "settings",   "label": "System Settings",   "description": "Configure system and alert settings"},
    {"key": "admin",      "label": "Admin Panel",       "description": "Manage users, roles and permissions"},
]

ALL_PERMISSION_KEYS = [p["key"] for p in ALL_PERMISSIONS]

DEFAULT_PERMISSIONS = ["dashboard", "analytics", "detections", "verdicts"]
