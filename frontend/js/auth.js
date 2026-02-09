/**
 * auth.js
 * トークン管理・認証ユーティリティ
 * 全ページで読み込む前提
 */
(function () {
  "use strict";

  const API_BASE = window.LOTO_ENGINE_BASE || "";

  // ============================================================
  // Token helpers
  // ============================================================

  function getToken() {
    return localStorage.getItem("access_token");
  }

  function setToken(token) {
    localStorage.setItem("access_token", token);
  }

  function removeToken() {
    localStorage.removeItem("access_token");
  }

  function setUser(user) {
    localStorage.setItem("user", JSON.stringify(user));
  }

  function getUser() {
    try {
      return JSON.parse(localStorage.getItem("user"));
    } catch {
      return null;
    }
  }

  function removeUser() {
    localStorage.removeItem("user");
  }

  // ============================================================
  // fetchWithAuth: adds Authorization header
  // ============================================================

  async function fetchWithAuth(url, options = {}) {
    const token = getToken();
    const headers = options.headers ? { ...options.headers } : {};
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
    if (!headers["Content-Type"] && options.body && typeof options.body === "string") {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(url, { ...options, headers });

    // 401 → token expired or invalid → logout
    if (res.status === 401) {
      removeToken();
      removeUser();
      window.location.href = "login.html";
      throw new Error("Unauthorized");
    }
    return res;
  }

  // ============================================================
  // requirePremium: /auth/me を叩いて is_premium を確認
  // false なら login.html?status=unpaid へリダイレクト
  // ============================================================

  async function requirePremium() {
    // トークンが無い → ログインページへ
    if (!getToken()) {
      window.location.href = "login.html";
      return false;
    }

    try {
      const res = await fetch(API_BASE + "/auth/me", {
        headers: { "Authorization": "Bearer " + getToken() },
      });

      if (res.status === 401) {
        removeToken();
        removeUser();
        window.location.href = "login.html";
        return false;
      }

      if (!res.ok) {
        window.location.href = "login.html";
        return false;
      }

      const user = await res.json();
      setUser(user);

      if (!user.is_premium) {
        window.location.href = "login.html?status=unpaid";
        return false;
      }

      return true;
    } catch {
      window.location.href = "login.html";
      return false;
    }
  }

  // ============================================================
  // isPremium (cached, synchronous check)
  // ============================================================

  function isPremium() {
    const user = getUser();
    return user && user.is_premium;
  }

  // ============================================================
  // logout
  // ============================================================

  function logout() {
    removeToken();
    removeUser();
    window.location.href = "login.html";
  }

  // ============================================================
  // Expose as global
  // ============================================================

  window.LotoAuth = {
    getToken,
    setToken,
    removeToken,
    setUser,
    getUser,
    removeUser,
    fetchWithAuth,
    requirePremium,
    isPremium,
    logout,
    API_BASE,
  };
})();
