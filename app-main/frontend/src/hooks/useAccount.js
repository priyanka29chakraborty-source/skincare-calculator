import { useCallback, useEffect, useState } from "react";

import { API, api, describeError } from "../api";

/**
 * Session and credit balance.
 *
 * The balance here is for display only. Nothing in this hook decides what the
 * user may see: the server strips paid fields before serialising, so a balance
 * edited in devtools changes a number on screen and nothing else.
 *
 * Every call sends credentials, because the session cookie is set by the API
 * on a different origin to the frontend.
 */
export default function useAccount() {
  const [state, setState] = useState({
    loading: true,
    signedIn: false,
    balance: 0,
    pdfUnlocked: false,
    owner: false,
  });

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get(`${API}/auth/me`, { withCredentials: true });
      setState({
        loading: false,
        signedIn: !!data.signed_in,
        balance: data.balance || 0,
        pdfUnlocked: !!data.pdf_unlocked,
        owner: !!data.owner,
      });
      return data;
    } catch {
      // Not signed in is the overwhelmingly common reason this fails, and it
      // is not an error worth showing anyone.
      setState({ loading: false, signedIn: false, balance: 0, pdfUnlocked: false, owner: false });
      return null;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const requestCode = useCallback(async (email) => {
    const { data } = await api.post(
      `${API}/auth/request-code`, { email }, { withCredentials: true });
    return data;
  }, []);

  const verifyCode = useCallback(async (email, code) => {
    const { data } = await api.post(
      `${API}/auth/verify-code`, { email, code }, { withCredentials: true });
    setState({
      loading: false,
      signedIn: true,
      balance: data.balance || 0,
      pdfUnlocked: !!data.pdf_unlocked,
      owner: !!data.owner,
    });
    return data;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.post(`${API}/auth/signout`, {}, { withCredentials: true });
    } finally {
      setState({ loading: false, signedIn: false, balance: 0, pdfUnlocked: false, owner: false });
    }
  }, []);

  return { ...state, refresh, requestCode, verifyCode, signOut, describeError };
}
