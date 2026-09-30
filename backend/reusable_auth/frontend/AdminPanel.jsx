/**
 * Reusable Admin Panel component.
 *
 * Drop into any React project that uses Tailwind CSS + lucide-react.
 *
 * Props:
 *   authFetch(url, options) – fetch wrapper that injects JWT header
 *   apiBase                – API base URL (default: window.location.origin)
 */

import React, { useState, useEffect } from 'react';
import { Shield, Plus, X, Check, Edit2, Key, RefreshCw, Trash2 } from 'lucide-react';

const AdminPanel = ({ authFetch, apiBase = window.location.origin }) => {
  const [users, setUsers] = useState([]);
  const [allPermissions, setAllPermissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingPerms, setEditingPerms] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [changingPassword, setChangingPassword] = useState(null);
  const [newPassword, setNewPassword] = useState('');
  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '', email: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const clearMessages = () => { setError(''); setSuccess(''); };
  const showSuccess = (msg) => { setSuccess(msg); setTimeout(() => setSuccess(''), 3000); };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [usersRes, permsRes] = await Promise.all([
        authFetch(`${apiBase}/api/admin/users`),
        authFetch(`${apiBase}/api/admin/permissions`),
      ]);
      setUsers(await usersRes.json());
      setAllPermissions(await permsRes.json());
    } catch (err) {
      setError('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreateUser = async () => {
    clearMessages();
    if (!newUser.username.trim() || !newUser.password.trim()) {
      setError('Username and password are required');
      return;
    }
    try {
      const res = await authFetch(`${apiBase}/api/admin/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newUser),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || 'Failed to create user');
      }
      setNewUser({ username: '', password: '', display_name: '', email: '' });
      setShowCreateForm(false);
      showSuccess('User created successfully');
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteUser = async (userId, username) => {
    if (!window.confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    clearMessages();
    try {
      const res = await authFetch(`${apiBase}/api/admin/users/${userId}`, { method: 'DELETE' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || 'Failed to delete user');
      }
      showSuccess('User deleted');
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleToggleActive = async (userId, currentlyActive) => {
    clearMessages();
    try {
      await authFetch(`${apiBase}/api/admin/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !currentlyActive }),
      });
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSavePermissions = async (userId, permissions) => {
    clearMessages();
    try {
      const res = await authFetch(`${apiBase}/api/admin/users/${userId}/permissions`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permissions }),
      });
      if (!res.ok) throw new Error('Failed to save permissions');
      setEditingPerms(null);
      showSuccess('Permissions updated');
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUpdateUser = async (userId) => {
    clearMessages();
    try {
      const res = await authFetch(`${apiBase}/api/admin/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingUser),
      });
      if (!res.ok) throw new Error('Failed to update user');
      setEditingUser(null);
      showSuccess('User updated');
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleChangePassword = async (userId) => {
    clearMessages();
    if (!newPassword.trim()) { setError('Password cannot be empty'); return; }
    try {
      const res = await authFetch(`${apiBase}/api/admin/users/${userId}/password`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword }),
      });
      if (!res.ok) throw new Error('Failed to change password');
      setChangingPassword(null);
      setNewPassword('');
      showSuccess('Password changed');
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-3xl font-bold text-gray-800">Admin Panel</h2>
          <p className="text-sm text-gray-500 mt-1">Manage users and page permissions</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => { setShowCreateForm(!showCreateForm); clearMessages(); }}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2">
            <Plus size={16} /> New User
          </button>
          <button onClick={fetchData}
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 flex items-center gap-2">
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex justify-between items-center">{error} <button onClick={() => setError('')}><X size={14} /></button></div>}
      {success && <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700 flex items-center gap-2"><Check size={14} /> {success}</div>}

      {showCreateForm && (
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 mb-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><Plus size={18} /> Create New User</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username *</label>
              <input type="text" value={newUser.username} onChange={e => setNewUser({ ...newUser, username: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="johndoe" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password *</label>
              <input type="text" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="password" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
              <input type="text" value={newUser.display_name} onChange={e => setNewUser({ ...newUser, display_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="John Doe" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input type="email" value={newUser.email} onChange={e => setNewUser({ ...newUser, email: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="john@example.com" />
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={handleCreateUser} className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">Create User</button>
            <button onClick={() => setShowCreateForm(false)} className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300">Cancel</button>
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Pages</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Login</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr><td colSpan="5" className="px-4 py-8 text-center text-gray-500">Loading...</td></tr>
              ) : users.map(u => (
                <tr key={u.id} className={`${!u.is_active ? 'bg-gray-50 opacity-60' : 'hover:bg-gray-50'}`}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                        {(u.display_name || u.username)[0].toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">{u.display_name || u.username}</p>
                        <p className="text-xs text-gray-500">@{u.username}{u.email ? ` · ${u.email}` : ''}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => handleToggleActive(u.id, u.is_active)}
                      className={`text-xs px-2 py-1 rounded font-medium ${u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      {u.is_active ? 'Active' : 'Disabled'}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(u.permissions || []).slice(0, 3).map(p => (
                        <span key={p} className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded">{p}</span>
                      ))}
                      {(u.permissions || []).length > 3 && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">+{u.permissions.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button onClick={() => { setEditingPerms(editingPerms === u.id ? null : u.id); setEditingUser(null); setChangingPassword(null); }}
                        className="p-1.5 text-blue-600 hover:bg-blue-50 rounded" title="Edit Permissions">
                        <Shield size={14} />
                      </button>
                      <button onClick={() => { setEditingUser(editingUser?.id === u.id ? null : { id: u.id, display_name: u.display_name || '', email: u.email || '' }); setEditingPerms(null); setChangingPassword(null); }}
                        className="p-1.5 text-gray-600 hover:bg-gray-50 rounded" title="Edit User">
                        <Edit2 size={14} />
                      </button>
                      <button onClick={() => { setChangingPassword(changingPassword === u.id ? null : u.id); setNewPassword(''); setEditingPerms(null); setEditingUser(null); }}
                        className="p-1.5 text-yellow-600 hover:bg-yellow-50 rounded" title="Change Password">
                        <Key size={14} />
                      </button>
                      <button onClick={() => handleDeleteUser(u.id, u.username)}
                        className="p-1.5 text-red-500 hover:bg-red-50 rounded" title="Delete User">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {editingPerms && (() => {
        const targetUser = users.find(u => u.id === editingPerms);
        if (!targetUser) return null;
        const currentPerms = new Set(targetUser.permissions || []);
        const togglePerm = (key) => {
          const next = new Set(currentPerms);
          next.has(key) ? next.delete(key) : next.add(key);
          handleSavePermissions(editingPerms, [...next]);
        };
        return (
          <div className="mt-6 bg-white p-6 rounded-lg shadow-sm border border-blue-200">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Shield size={18} className="text-blue-600" />
                Page Permissions for <span className="text-blue-600">@{targetUser.username}</span>
              </h3>
              <button onClick={() => setEditingPerms(null)} className="p-1 hover:bg-gray-100 rounded"><X size={18} /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {allPermissions.map(perm => (
                <label key={perm.key}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    currentPerms.has(perm.key) ? 'bg-blue-50 border-blue-300' : 'bg-gray-50 border-gray-200 hover:bg-gray-100'
                  }`}>
                  <input type="checkbox" checked={currentPerms.has(perm.key)} onChange={() => togglePerm(perm.key)}
                    className="w-4 h-4 text-blue-600 rounded" />
                  <div>
                    <p className="text-sm font-medium text-gray-800">{perm.label}</p>
                    <p className="text-xs text-gray-500">{perm.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        );
      })()}

      {editingUser && (
        <div className="mt-6 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2"><Edit2 size={18} /> Edit User</h3>
            <button onClick={() => setEditingUser(null)} className="p-1 hover:bg-gray-100 rounded"><X size={18} /></button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
              <input type="text" value={editingUser.display_name} onChange={e => setEditingUser({ ...editingUser, display_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input type="email" value={editingUser.email} onChange={e => setEditingUser({ ...editingUser, email: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg" />
            </div>
          </div>
          <button onClick={() => handleUpdateUser(editingUser.id)}
            className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">Save Changes</button>
        </div>
      )}

      {changingPassword && (
        <div className="mt-6 bg-white p-6 rounded-lg shadow-sm border border-yellow-200">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Key size={18} className="text-yellow-600" />
              Change Password for <span className="text-yellow-600">@{users.find(u => u.id === changingPassword)?.username}</span>
            </h3>
            <button onClick={() => { setChangingPassword(null); setNewPassword(''); }} className="p-1 hover:bg-gray-100 rounded"><X size={18} /></button>
          </div>
          <div className="flex gap-3">
            <input type="text" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Enter new password"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg" />
            <button onClick={() => handleChangePassword(changingPassword)}
              className="px-6 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 font-medium">Set Password</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
