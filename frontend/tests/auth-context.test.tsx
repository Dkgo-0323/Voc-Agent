import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/components/auth/auth-context";
import { AUTH_UNAUTHORIZED_EVENT } from "@/lib/api/client";
import { clearAuthToken, readAuthToken, writeAuthToken } from "@/lib/auth/token-storage";

const authClient = vi.hoisted(() => ({
  fetchAuthIdentity: vi.fn(),
  loginWithPassword: vi.fn(),
}));

vi.mock("@/lib/auth/client", () => authClient);

function Probe() {
  const { error, login, logout, status, user } = useAuth();
  const [loginError, setLoginError] = useState("");
  return <><output data-testid="status">{status}</output><output data-testid="user">{user?.subject ?? ""}</output><output data-testid="error">{error ?? loginError}</output><button onClick={() => void login("correct-password").catch((caughtError) => setLoginError(caughtError.message))}>login</button><button onClick={logout}>logout</button></>;
}

describe("AuthProvider", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    clearAuthToken();
    authClient.fetchAuthIdentity.mockReset();
    authClient.loginWithPassword.mockReset();
  });

  it("restores and validates a saved bearer token on refresh", async () => {
    writeAuthToken("saved-token");
    authClient.fetchAuthIdentity.mockResolvedValue({ subject: "admin" });
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("user")).toHaveTextContent("admin");
  });

  it("clears an invalid or expired saved token after a 401", async () => {
    writeAuthToken("expired-token");
    authClient.fetchAuthIdentity.mockRejectedValue({ message: "Authentication is required.", status: 401 });
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(readAuthToken()).toBeNull();
  });

  it("stores the token only after successful login and supports logout", async () => {
    authClient.loginWithPassword.mockResolvedValue({ access_token: "new-token", token_type: "bearer" });
    authClient.fetchAuthIdentity.mockResolvedValue({ subject: "admin" });
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    await act(async () => screen.getByRole("button", { name: "login" }).click());
    expect(readAuthToken()).toBe("new-token");
    expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    await act(async () => screen.getByRole("button", { name: "logout" }).click());
    expect(readAuthToken()).toBeNull();
    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
  });

  it("keeps the browser unauthenticated when the password is rejected", async () => {
    authClient.loginWithPassword.mockRejectedValue({ message: "Incorrect password.", status: 401 });
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    await act(async () => screen.getByRole("button", { name: "login" }).click());
    expect(screen.getByTestId("error")).toHaveTextContent("Incorrect password.");
    expect(readAuthToken()).toBeNull();
  });

  it("clears the session after an authenticated API 401 notification", async () => {
    writeAuthToken("saved-token");
    authClient.fetchAuthIdentity.mockResolvedValue({ subject: "admin" });
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    act(() => window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT)));
    expect(readAuthToken()).toBeNull();
    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
  });
});
