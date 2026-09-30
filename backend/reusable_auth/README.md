# reusable_auth — Drop-in JWT Auth for FastAPI + React

A self-contained authentication module with user management, page-level permissions, and an admin panel. Copy the folder into any project and wire it up in **three lines**.

## Folder structure

```
reusable_auth/
├── __init__.py          # Public API: setup_auth, AuthService, ...
├── auth_service.py      # Core: user CRUD, password hashing, JWT, permissions
├── middleware.py         # JWTAuthMiddleware for FastAPI
├── routes.py            # All /api/auth/* and /api/admin/* endpoints
├── setup.py             # One-call setup_auth() helper
├── frontend/
│   ├── auth_helpers.js  # getStoredToken, authFetch, clearAuth, ...
│   ├── LoginPage.jsx    # Ready-made login page (Tailwind + lucide-react)
│   └── AdminPanel.jsx   # User & permission management UI
└── README.md
```

## Requirements

**Backend** (Python):
- `fastapi`
- `PyJWT`
- `starlette` (comes with FastAPI)

**Frontend** (React):
- `tailwindcss`
- `lucide-react`

## Backend integration

### 1. Copy the folder

```bash
cp -r reusable_auth/ your_project/reusable_auth/
```

### 2. Define your permissions

```python
MY_PERMISSIONS = [
    {"key": "dashboard",  "label": "Dashboard",      "description": "View main dashboard"},
    {"key": "reports",    "label": "Reports",         "description": "View and export reports"},
    {"key": "settings",   "label": "Settings",        "description": "Change app settings"},
    {"key": "admin",      "label": "Admin Panel",     "description": "Manage users & permissions"},
]
```

> **Important**: Always include an `"admin"` permission — it controls access to the admin endpoints.

### 3. Wire it up in your FastAPI app

```python
from fastapi import FastAPI
from reusable_auth import setup_auth

app = FastAPI()

auth_service = setup_auth(
    app,
    db_path="data/app.db",
    permissions=MY_PERMISSIONS,
    default_permissions=["dashboard"],       # given to new users
    exempt_paths={"/api/auth/login", "/api/health"},  # skip JWT check
    admin_username="admin",
    admin_password="admin",
)
```

That's it. You now have:

| Endpoint | Description |
|---|---|
| `POST /api/auth/login` | Authenticate, returns JWT + user |
| `GET /api/auth/me` | Current user info |
| `GET /api/admin/permissions` | List all permissions |
| `GET /api/admin/users` | List all users |
| `POST /api/admin/users` | Create user |
| `PUT /api/admin/users/{id}` | Update user |
| `DELETE /api/admin/users/{id}` | Delete user |
| `PUT /api/admin/users/{id}/password` | Change password |
| `GET /api/admin/users/{id}/permissions` | Get user permissions |
| `PUT /api/admin/users/{id}/permissions` | Set user permissions |

### Environment variables (optional)

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | random hex | Signing key (set in production!) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRY_HOURS` | `24` | Token lifetime |

## Frontend integration

### 1. Copy the frontend files

```bash
cp reusable_auth/frontend/* your_project/src/auth/
```

### 2. Update the storage prefix

In `auth_helpers.js`, change `STORAGE_PREFIX` to your app name:

```js
const STORAGE_PREFIX = 'myapp';  // keys: myapp_token, myapp_user
```

### 3. Use LoginPage

```jsx
import LoginPage from './auth/LoginPage';
import { setStoredToken, setStoredUser } from './auth/auth_helpers';

function App() {
  const [token, setToken] = useState(() => getStoredToken());

  const handleLogin = (token, user) => {
    setStoredToken(token);
    setStoredUser(user);
    setToken(token);
  };

  if (!token) {
    return <LoginPage onLogin={handleLogin} appName="My App" />;
  }

  return <MainApp />;
}
```

### 4. Use AdminPanel

```jsx
import AdminPanel from './auth/AdminPanel';
import { authFetch } from './auth/auth_helpers';

// Inside your router / view switcher:
<AdminPanel authFetch={authFetch} />
```

### 5. Filter sidebar by permissions

```jsx
const user = getStoredUser();
const visiblePages = ALL_PAGES.filter(p => user?.permissions?.includes(p.id));
```

## How permissions work

- There are **no roles** — only page-level permissions stored in the DB.
- The `"admin"` permission key grants access to the admin endpoints.
- Users with the `"admin"` permission automatically receive all permissions on startup.
- New users get `default_permissions` unless explicitly specified.
- The JWT token carries the permissions list, so the frontend can filter UI immediately without extra API calls.

## Customisation

- **Add new permissions**: just add entries to `MY_PERMISSIONS` and restart. Users with `"admin"` permission get them automatically.
- **Custom admin check**: the `_require_admin` helper in `routes.py` checks for `"admin"` in the JWT's permissions list. Override if needed.
- **Different DB**: the module uses SQLite via the stdlib. Swap `auth_service.py` internals for PostgreSQL/MySQL if needed.
